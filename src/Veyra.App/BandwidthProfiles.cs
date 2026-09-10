namespace Veyra.App;

public static class BandwidthProfiles
{
    public static readonly (string Label, double? BytesPerSecond)[] Options =
    [
        ("Unlimited", null),
        ("256 KB/s", 256 * 1024),
        ("512 KB/s", 512 * 1024),
        ("1 MB/s", 1024 * 1024),
        ("2 MB/s", 2 * 1024 * 1024),
        ("5 MB/s", 5 * 1024 * 1024),
        ("10 MB/s", 10 * 1024 * 1024),
    ];
}
