using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using small_model_orchestrator.Data;

namespace small_model_orchestrator.Services;

public sealed class JobRunService(
    IDbContextFactory<OrchestratorDbContext> contextFactory,
    RunQueue queue)
{
    public const int MaxQueuedRuns = 32;
    public const int MaxInputCharacters = 50_000;

    public async Task<JobRun> QueueAsync(int jobDefinitionId, string inputText, CancellationToken cancellationToken = default)
    {
        if (inputText.Length > MaxInputCharacters)
        {
            throw new ArgumentException($"Input is limited to {MaxInputCharacters:N0} characters.", nameof(inputText));
        }

        await using var database = await contextFactory.CreateDbContextAsync(cancellationToken);
        var job = await database.JobDefinitions.SingleAsync(item => item.Id == jobDefinitionId, cancellationToken);
        if (!job.IsEnabled)
        {
            throw new InvalidOperationException("This job is paused. Enable it before queueing a run.");
        }

        var queuedCount = await database.JobRuns.CountAsync(run => run.Status == JobRunStatus.Queued, cancellationToken);
        if (queuedCount >= MaxQueuedRuns)
        {
            throw new InvalidOperationException($"The queue is full ({MaxQueuedRuns} pending runs).");
        }

        var snapshot = new JobRunSnapshot(
            job.Name,
            job.Model,
            job.SystemPrompt,
            job.UserPrompt,
            job.Temperature,
            job.MaxOutputTokens,
            job.MaxIterations,
            job.MaxToolOutputCharacters,
            job.AllowShellTools);
        var now = DateTime.UtcNow;
        var run = new JobRun
        {
            JobDefinitionId = job.Id,
            JobName = job.Name,
            Model = job.Model,
            InputText = inputText,
            PromptSnapshotJson = JsonSerializer.Serialize(snapshot),
            Status = JobRunStatus.Queued,
            QueuedAtUtc = now,
            Events = [new JobRunEvent { Kind = "status", Message = "Run queued.", CreatedAtUtc = now }]
        };

        database.JobRuns.Add(run);
        await database.SaveChangesAsync(cancellationToken);
        queue.TryEnqueue(run.Id);
        return run;
    }

    public async Task<List<JobRun>> ListRecentAsync(int limit = 12, CancellationToken cancellationToken = default)
    {
        await using var database = await contextFactory.CreateDbContextAsync(cancellationToken);
        return await database.JobRuns
            .AsNoTracking()
            .Include(run => run.Events)
            .OrderByDescending(run => run.QueuedAtUtc)
            .Take(limit)
            .ToListAsync(cancellationToken);
    }
}
