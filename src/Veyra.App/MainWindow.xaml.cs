using System.Collections.ObjectModel;
using System.Diagnostics;
using System.Windows;
using System.Windows.Input;
using System.Windows.Threading;
using Microsoft.Win32;

namespace Veyra.App;

public partial class MainWindow : Window
{
    private readonly DownloadManagerService _downloadManager = new();
    private readonly ObservableCollection<DownloadItem> _downloads = [];
    private readonly DispatcherTimer _mediaTimer;
    private bool _seeking;
    private bool _updatingProgress;

    public MainWindow()
    {
        InitializeComponent();
        DownloadList.ItemsSource = _downloads;
        DragOver += MainWindow_DragOver;
        Drop += MainWindow_Drop;
        Closed += MainWindow_Closed;

        _mediaTimer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(250) };
        _mediaTimer.Tick += MediaTimer_Tick;
        _mediaTimer.Start();
    }

    private void OpenButton_Click(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFileDialog
        {
            Title = "Open media",
            Filter = "Media files|*.mp4;*.mkv;*.webm;*.avi;*.mov;*.m4v;*.ts;*.mp3;*.flac;*.aac;*.wav;*.ogg|All files|*.*"
        };
        if (dialog.ShowDialog(this) == true)
            OpenMedia(dialog.FileName);
    }

    private void MainWindow_DragOver(object sender, DragEventArgs e)
        => e.Effects = e.Data.GetDataPresent(DataFormats.FileDrop) ? DragDropEffects.Copy : DragDropEffects.None;

    private void MainWindow_Drop(object sender, DragEventArgs e)
    {
        if (!e.Data.GetDataPresent(DataFormats.FileDrop)) return;
        if (e.Data.GetData(DataFormats.FileDrop) is string[] files && files.Length > 0)
            OpenMedia(files[0]);
    }

    private void OpenMedia(string path)
    {
        NativePreview.Source = new Uri(path);
        NativePreview.Visibility = Visibility.Visible;
        PlayPauseButton.Content = "❚❚";
        NativePreview.Play();
    }

    private void PlayPause_Click(object sender, RoutedEventArgs e)
    {
        if (NativePreview.Source is null) return;
        if (PlayPauseButton.Content?.ToString() == "▶")
        {
            NativePreview.Play();
            PlayPauseButton.Content = "❚❚";
        }
        else
        {
            NativePreview.Pause();
            PlayPauseButton.Content = "▶";
        }
    }

    private void Previous_Click(object sender, RoutedEventArgs e) { }
    private void Next_Click(object sender, RoutedEventArgs e) { }

    private async void AddDownload_Click(object sender, RoutedEventArgs e)
    {
        var url = DownloadUrlBox.Text.Trim();
        if (string.IsNullOrWhiteSpace(url)) return;

        try
        {
            var item = await _downloadManager.AddAsync(url);
            item.PropertyChanged += DownloadItem_PropertyChanged;
            _downloads.Insert(0, item);
            DownloadUrlBox.Clear();
            UpdateDownloadSummary();
        }
        catch (Exception ex)
        {
            MessageBox.Show(this, ex.Message, "Unable to start download", MessageBoxButton.OK, MessageBoxImage.Error);
        }
    }

    private async void PauseDownload_Click(object sender, RoutedEventArgs e)
    {
        if (GetItem(sender) is { } item) await _downloadManager.PauseAsync(item);
    }

    private async void ResumeDownload_Click(object sender, RoutedEventArgs e)
    {
        if (GetItem(sender) is { } item) await _downloadManager.ResumeAsync(item);
    }

    private async void CancelDownload_Click(object sender, RoutedEventArgs e)
    {
        if (GetItem(sender) is { } item) await _downloadManager.CancelAsync(item);
    }

    private async void RemoveDownload_Click(object sender, RoutedEventArgs e)
    {
        if (GetItem(sender) is not { } item) return;
        await _downloadManager.RemoveAsync(item);
        _downloads.Remove(item);
    }

    private async void StartAllDownloads_Click(object sender, RoutedEventArgs e)
    {
        foreach (var item in _downloads.Where(x => x.Status is DownloadItemStatus.Paused or DownloadItemStatus.Failed or DownloadItemStatus.Cancelled).ToList())
            await _downloadManager.ResumeAsync(item);
    }

    private async void PauseAllDownloads_Click(object sender, RoutedEventArgs e)
    {
        foreach (var item in _downloads.Where(x => x.Status is DownloadItemStatus.Downloading or DownloadItemStatus.Queued).ToList())
            await _downloadManager.PauseAsync(item);
    }

    private void ClearCompleted_Click(object sender, RoutedEventArgs e)
    {
        foreach (var item in _downloads.Where(x => x.Status == DownloadItemStatus.Completed).ToList())
            _downloads.Remove(item);
        UpdateDownloadSummary();
    }

    private void OpenDownloadsFolder_Click(object sender, RoutedEventArgs e)
    {
        var directory = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Downloads", "VEYRA");
        Directory.CreateDirectory(directory);
        Process.Start(new ProcessStartInfo { FileName = directory, UseShellExecute = true });
    }

    private DownloadItem? GetItem(object sender)
        => (sender as FrameworkElement)?.Tag as DownloadItem;

    private void DownloadItem_PropertyChanged(object? sender, System.ComponentModel.PropertyChangedEventArgs e)
    {
        if (!Dispatcher.CheckAccess())
        {
            Dispatcher.BeginInvoke(UpdateDownloadSummary);
            return;
        }
        UpdateDownloadSummary();
    }

    private void UpdateDownloadSummary()
    {
        var active = _downloads.Count(x => x.Status == DownloadItemStatus.Downloading);
        var queued = _downloads.Count(x => x.Status == DownloadItemStatus.Queued);
        DownloadSummary.Text = $"{active} active · {queued} queued · {_downloads.Count} total";
    }

    private void MediaTimer_Tick(object? sender, EventArgs e)
    {
        if (NativePreview.Source is null || _seeking) return;
        if (!NativePreview.NaturalDuration.HasTimeSpan) return;

        var duration = NativePreview.NaturalDuration.TimeSpan;
        var position = NativePreview.Position;
        _updatingProgress = true;
        ProgressSlider.Maximum = Math.Max(1, duration.TotalSeconds);
        ProgressSlider.Value = Math.Min(ProgressSlider.Maximum, position.TotalSeconds);
        _updatingProgress = false;
        TimeText.Text = $"{FormatTime(position)} / {FormatTime(duration)}";
    }

    private void ProgressSlider_MouseDown(object sender, MouseButtonEventArgs e)
        => _seeking = true;

    private void ProgressSlider_MouseUp(object sender, MouseButtonEventArgs e)
    {
        _seeking = false;
        if (NativePreview.Source is not null)
            NativePreview.Position = TimeSpan.FromSeconds(ProgressSlider.Value);
    }

    private void ProgressSlider_ValueChanged(object sender, RoutedPropertyChangedEventArgs<double> e)
    {
        if (_updatingProgress || !_seeking || NativePreview.Source is null) return;
        NativePreview.Position = TimeSpan.FromSeconds(e.NewValue);
    }

    private void MainWindow_Closed(object? sender, EventArgs e)
    {
        _mediaTimer.Stop();
        _downloadManager.Dispose();
    }

    private static string FormatTime(TimeSpan value)
        => value.TotalHours >= 1 ? value.ToString(@"h\:mm\:ss") : value.ToString(@"mm\:ss");
}
