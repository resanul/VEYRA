using System.ComponentModel;
using System.Runtime.CompilerServices;

namespace Veyra.App;

public enum DownloadItemStatus
{
    Queued,
    Downloading,
    Paused,
    Completed,
    Failed,
    Cancelled
}

public sealed class DownloadItem : INotifyPropertyChanged
{
    private DownloadItemStatus _status = DownloadItemStatus.Queued;
    private long _downloadedBytes;
    private long _totalBytes;
    private double _bytesPerSecond;
    private string? _error;

    public DownloadItem(string url, string filePath)
    {
        Id = Guid.NewGuid().ToString("N");
        Url = url;
        FilePath = filePath;
        FileName = Path.GetFileName(filePath);
    }

    public string Id { get; }
    public string Url { get; }
    public string FilePath { get; }
    public string FileName { get; }
    public DateTime CreatedAt { get; } = DateTime.Now;

    public DownloadItemStatus Status
    {
        get => _status;
        set => Set(ref _status, value);
    }

    public long DownloadedBytes
    {
        get => _downloadedBytes;
        set
        {
            if (Set(ref _downloadedBytes, value))
                OnPropertyChanged(nameof(Progress));
        }
    }

    public long TotalBytes
    {
        get => _totalBytes;
        set
        {
            if (Set(ref _totalBytes, value))
                OnPropertyChanged(nameof(Progress));
        }
    }

    public double BytesPerSecond
    {
        get => _bytesPerSecond;
        set
        {
            if (Set(ref _bytesPerSecond, value))
            {
                OnPropertyChanged(nameof(SpeedText));
                OnPropertyChanged(nameof(EtaText));
            }
        }
    }

    public string? Error
    {
        get => _error;
        set => Set(ref _error, value);
    }

    public double Progress => TotalBytes > 0 ? Math.Clamp((double)DownloadedBytes / TotalBytes * 100.0, 0, 100) : 0;
    public string ProgressText => TotalBytes > 0 ? $"{FormatBytes(DownloadedBytes)} / {FormatBytes(TotalBytes)}" : FormatBytes(DownloadedBytes);
    public string SpeedText => BytesPerSecond > 0 ? $"{FormatBytes(BytesPerSecond)}/s" : "—";
    public string EtaText => BytesPerSecond > 0 && TotalBytes > DownloadedBytes
        ? FormatDuration(TimeSpan.FromSeconds((TotalBytes - DownloadedBytes) / BytesPerSecond))
        : "—";

    public string StatusText => Status switch
    {
        DownloadItemStatus.Queued => "Queued",
        DownloadItemStatus.Downloading => "Downloading",
        DownloadItemStatus.Paused => "Paused",
        DownloadItemStatus.Completed => "Completed",
        DownloadItemStatus.Failed => "Failed",
        DownloadItemStatus.Cancelled => "Cancelled",
        _ => Status.ToString()
    };

    public event PropertyChangedEventHandler? PropertyChanged;

    public void RefreshDerivedProperties()
    {
        OnPropertyChanged(nameof(Progress));
        OnPropertyChanged(nameof(ProgressText));
        OnPropertyChanged(nameof(SpeedText));
        OnPropertyChanged(nameof(EtaText));
        OnPropertyChanged(nameof(StatusText));
    }

    private bool Set<T>(ref T field, T value, [CallerMemberName] string? name = null)
    {
        if (EqualityComparer<T>.Default.Equals(field, value)) return false;
        field = value;
        OnPropertyChanged(name);
        if (name is nameof(Status) or nameof(DownloadedBytes) or nameof(TotalBytes))
            RefreshDerivedProperties();
        return true;
    }

    private void OnPropertyChanged([CallerMemberName] string? name = null)
        => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));

    public static string FormatBytes(double value)
    {
        string[] units = ["B", "KB", "MB", "GB", "TB"];
        var index = 0;
        while (value >= 1024 && index < units.Length - 1)
        {
            value /= 1024;
            index++;
        }
        return index == 0 ? $"{value:0} {units[index]}" : $"{value:0.##} {units[index]}";
    }

    private static string FormatDuration(TimeSpan value)
    {
        if (value.TotalDays >= 1) return $"{(int)value.TotalDays}d {value.Hours:00}h";
        if (value.TotalHours >= 1) return $"{(int)value.TotalHours:00}:{value.Minutes:00}:{value.Seconds:00}";
        return $"{value.Minutes:00}:{value.Seconds:00}";
    }
}
