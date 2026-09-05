namespace Veyra.Core.Models;

public enum PlaybackState { Idle, Loading, Playing, Paused, Buffering, Ended, Error }
public enum RepeatMode { Off, One, All }
public enum MediaType { Unknown, Video, Audio, Stream }

public sealed record MediaItem(
    string Id,
    string Title,
    string Source,
    MediaType Type = MediaType.Unknown,
    TimeSpan? Duration = null,
    string? Thumbnail = null);

public sealed record TrackInfo(
    string Id,
    string Label,
    string? Language,
    bool IsDefault = false,
    string? Codec = null);

public sealed record PlaybackSnapshot(
    PlaybackState State,
    TimeSpan Position,
    TimeSpan Duration,
    double Speed,
    double Volume,
    bool IsMuted,
    RepeatMode RepeatMode,
    MediaItem? CurrentMedia);
