using System.Threading.Channels;

namespace small_model_orchestrator.Services;

public sealed class RunQueue
{
    private readonly Channel<int> channel = Channel.CreateUnbounded<int>(new UnboundedChannelOptions
    {
        SingleReader = true,
        SingleWriter = false
    });

    public bool TryEnqueue(int runId) => channel.Writer.TryWrite(runId);

    public IAsyncEnumerable<int> ReadAllAsync(CancellationToken cancellationToken) =>
        channel.Reader.ReadAllAsync(cancellationToken);
}
