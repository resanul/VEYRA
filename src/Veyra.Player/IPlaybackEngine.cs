using Veyra.Core.Models;

namespace Veyra.Player;

public interface IPlaybackEngine : IAsyncDisposable
{
    PlaybackSnapshot Snapshot { get; }
    IReadOnlyList<TrackInfo> VideoTracks { get; }
    IReadOnlyList<TrackInfo> AudioTracks { get; }
    IReadOnlyList<TrackInfo> SubtitleTracks { get; }

    Task OpenAsync(MediaItem media, CancellationToken cancellationToken = default);
    Task PlayAsync(CancellationToken cancellationToken = default);
    Task PauseAsync(CancellationToken cancellationToken = default);
    Task SeekAsync(TimeSpan position, CancellationToken cancellationToken = default);
    Task StopAsync(CancellationToken cancellationToken = default);
    Task SetSpeedAsync(double speed, CancellationToken cancellationToken = default);
    Task SetVolumeAsync(double volume, CancellationToken cancellationToken = default);
    Task SetMutedAsync(bool muted, CancellationToken cancellationToken = default);
    Task SelectAudioTrackAsync(string trackId, CancellationToken cancellationToken = default);
    Task SelectVideoTrackAsync(string trackId, CancellationToken cancellationToken = default);
    Task SelectSubtitleTrackAsync(string? trackId, CancellationToken cancellationToken = default);

    event EventHandler<PlaybackSnapshot>? SnapshotChanged;
    event EventHandler<Exception>? PlaybackError;
}
