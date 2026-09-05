using System.Windows;
using Microsoft.Win32;

namespace Veyra.App;

public partial class MainWindow : Window
{
    public MainWindow()
    {
        InitializeComponent();
        DragOver += MainWindow_DragOver;
        Drop += MainWindow_Drop;
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
}
