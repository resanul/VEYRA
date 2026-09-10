using System.Diagnostics;

namespace Veyra.App;

public sealed class BandwidthLimiter
{
    private readonly object _gate = new();
    private double? _limitBytesPerSecond;
    private double _nextAvailable;

    public BandwidthLimiter(double? limitBytesPerSecond = null) => SetLimit(limitBytesPerSecond);

    public double? LimitBytesPerSecond { get { lock (_gate) return _limitBytesPerSecond; } }

    public void SetLimit(double? value)
    {
        if (value is <= 0) throw new ArgumentOutOfRangeException(nameof(value), "Bandwidth limit must be greater than zero.");
        lock (_gate)
        {
            _limitBytesPerSecond = value;
            _nextAvailable = Now();
        }
    }

    public async Task WaitAsync(int bytes, CancellationToken token)
    {
        if (bytes <= 0) return;
        double delay;
        lock (_gate)
        {
            if (_limitBytesPerSecond is null) return;
            var now = Now();
            var start = Math.Max(now, _nextAvailable);
            _nextAvailable = start + bytes / _limitBytesPerSecond.Value;
            delay = start - now;
        }
        while (delay > 0)
        {
            token.ThrowIfCancellationRequested();
            var slice = Math.Min(0.05, delay);
            await Task.Delay(TimeSpan.FromSeconds(slice), token).ConfigureAwait(false);
            delay -= slice;
        }
    }

    private static double Now() => Stopwatch.GetTimestamp() / (double)Stopwatch.Frequency;
}
