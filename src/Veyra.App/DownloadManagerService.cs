using System.Collections.Concurrent;
using System.Net;
using System.Net.Http.Headers;

namespace Veyra.App;

public sealed class DownloadManagerService : IDisposable
{
    private const int MaxConcurrent = 3;
    private static readonly TimeSpan RequestTimeout = TimeSpan.FromSeconds(30);

    private readonly HttpClient _httpClient = new(new HttpClientHandler
    {
        AutomaticDecompression = DecompressionMethods.None,
        AllowAutoRedirect = true
    })
    {
        Timeout = RequestTimeout
    };
    private readonly SemaphoreSlim _slots = new(MaxConcurrent, MaxConcurrent);
    private readonly ConcurrentDictionary<string, CancellationTokenSource> _cancellations = new();
    private readonly ConcurrentDictionary<string, Task> _workers = new();
    private bool _disposed;

    public DownloadManagerService()
    {
        _httpClient.DefaultRequestHeaders.UserAgent.ParseAdd("VEYRA/0.3.2");
    }

    public async Task<DownloadItem> AddAsync(string url, string? fileName = null, string? directory = null)
    {
        if (!Uri.TryCreate(url, UriKind.Absolute, out var uri) ||
            (uri.Scheme != Uri.UriSchemeHttp && uri.Scheme != Uri.UriSchemeHttps))
            throw new ArgumentException("Downloads require an HTTP(S) URL.", nameof(url));

        var name = SanitizeFileName(fileName ?? Path.GetFileName(Uri.UnescapeDataString(uri.AbsolutePath)));
        if (string.IsNullOrWhiteSpace(name)) name = "download";
        var targetDirectory = directory ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Downloads", "VEYRA");
        Directory.CreateDirectory(targetDirectory);

        var item = new DownloadItem(uri.ToString(), Path.Combine(targetDirectory, name));
        Start(item);
        await Task.CompletedTask;
        return item;
    }

    public void Start(DownloadItem item)
    {
        if (_disposed) throw new ObjectDisposedException(nameof(DownloadManagerService));
        if (item.Status == DownloadItemStatus.Completed) return;

        item.Status = DownloadItemStatus.Queued;
        item.Error = null;
        var cts = new CancellationTokenSource();
        if (!_cancellations.TryAdd(item.Id, cts)) return;
        var worker = RunAsync(item, cts);
        _workers[item.Id] = worker;
        _ = worker.ContinueWith(_ =>
        {
            _workers.TryRemove(item.Id, out _);
            if (_cancellations.TryRemove(item.Id, out var source)) source.Dispose();
        }, TaskScheduler.Default);
    }

    public async Task PauseAsync(DownloadItem item)
    {
        if (item.Status is DownloadItemStatus.Downloading or DownloadItemStatus.Queued)
        {
            item.Status = DownloadItemStatus.Paused;
            CancelWorker(item);
            await WaitForWorkerAsync(item.Id);
        }
    }

    public async Task ResumeAsync(DownloadItem item)
    {
        if (item.Status is not (DownloadItemStatus.Paused or DownloadItemStatus.Failed or DownloadItemStatus.Cancelled)) return;
        item.Error = null;
        Start(item);
        await Task.CompletedTask;
    }

    public async Task CancelAsync(DownloadItem item, bool deletePartial = false)
    {
        if (item.Status == DownloadItemStatus.Completed) return;
        item.Status = DownloadItemStatus.Cancelled;
        CancelWorker(item);
        await WaitForWorkerAsync(item.Id);
        if (deletePartial) DeletePartial(item);
    }

    public async Task RemoveAsync(DownloadItem item, bool deleteFile = false)
    {
        if (item.Status is DownloadItemStatus.Downloading or DownloadItemStatus.Queued)
            await CancelAsync(item, deleteFile);
        else if (deleteFile)
            DeletePartial(item);
    }

    private async Task RunAsync(DownloadItem item, CancellationTokenSource cts)
    {
        await _slots.WaitAsync(cts.Token).ConfigureAwait(false);
        try
        {
            item.Status = DownloadItemStatus.Downloading;
            var partial = item.FilePath + ".part";
            var existing = File.Exists(partial) ? new FileInfo(partial).Length : 0L;

            using var request = new HttpRequestMessage(HttpMethod.Get, item.Url);
            if (existing > 0)
                request.Headers.Range = new RangeHeaderValue(existing, null);

            using var response = await _httpClient.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cts.Token).ConfigureAwait(false);
            if (existing > 0 && response.StatusCode != HttpStatusCode.PartialContent)
            {
                existing = 0;
                File.Delete(partial);
            }
            response.EnsureSuccessStatusCode();

            var contentLength = response.Content.Headers.ContentLength;
            item.TotalBytes = contentLength.HasValue ? existing + contentLength.Value : 0;
            item.DownloadedBytes = existing;

            await using var input = await response.Content.ReadAsStreamAsync(cts.Token).ConfigureAwait(false);
            await using var output = new FileStream(
                partial,
                existing > 0 ? FileMode.Append : FileMode.Create,
                FileAccess.Write,
                FileShare.Read,
                64 * 1024,
                FileOptions.Asynchronous | FileOptions.SequentialScan);

            var buffer = new byte[64 * 1024];
            var stopwatch = System.Diagnostics.Stopwatch.StartNew();
            var lastBytes = existing;
            var lastSample = stopwatch.Elapsed;
            while (true)
            {
                var read = await input.ReadAsync(buffer.AsMemory(0, buffer.Length), cts.Token).ConfigureAwait(false);
                if (read == 0) break;
                await output.WriteAsync(buffer.AsMemory(0, read), cts.Token).ConfigureAwait(false);
                item.DownloadedBytes += read;
                var elapsed = stopwatch.Elapsed - lastSample;
                if (elapsed.TotalMilliseconds >= 250)
                {
                    item.BytesPerSecond = (item.DownloadedBytes - lastBytes) / Math.Max(0.001, elapsed.TotalSeconds);
                    lastBytes = item.DownloadedBytes;
                    lastSample = stopwatch.Elapsed;
                    item.RefreshDerivedProperties();
                }
            }

            output.Close();
            File.Move(partial, item.FilePath, true);
            item.BytesPerSecond = 0;
            item.Status = DownloadItemStatus.Completed;
            item.DownloadedBytes = item.TotalBytes > 0 ? item.TotalBytes : item.DownloadedBytes;
        }
        catch (OperationCanceledException) when (cts.IsCancellationRequested)
        {
            if (item.Status != DownloadItemStatus.Paused && item.Status != DownloadItemStatus.Cancelled)
                item.Status = DownloadItemStatus.Cancelled;
        }
        catch (Exception ex)
        {
            item.Status = DownloadItemStatus.Failed;
            item.Error = ex.Message;
        }
        finally
        {
            item.BytesPerSecond = 0;
            item.RefreshDerivedProperties();
            _slots.Release();
        }
    }

    private void CancelWorker(DownloadItem item)
    {
        if (_cancellations.TryGetValue(item.Id, out var cts)) cts.Cancel();
    }

    private async Task WaitForWorkerAsync(string id)
    {
        if (_workers.TryGetValue(id, out var worker))
        {
            try { await worker.ConfigureAwait(false); }
            catch (OperationCanceledException) { }
        }
    }

    private static void DeletePartial(DownloadItem item)
    {
        File.Delete(item.FilePath + ".part");
        if (item.Status == DownloadItemStatus.Cancelled) File.Delete(item.FilePath);
    }

    private static string SanitizeFileName(string value)
    {
        value = Path.GetFileName(value).Trim();
        foreach (var invalid in Path.GetInvalidFileNameChars()) value = value.Replace(invalid, '_');
        return value.TrimEnd(' ', '.');
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        foreach (var cts in _cancellations.Values) cts.Cancel();
        _httpClient.Dispose();
        _slots.Dispose();
    }
}
