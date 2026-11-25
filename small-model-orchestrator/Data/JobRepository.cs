using Microsoft.EntityFrameworkCore;

namespace small_model_orchestrator.Data;

public sealed class JobRepository(IDbContextFactory<OrchestratorDbContext> contextFactory)
{
    public async Task<List<JobDefinition>> ListAsync(CancellationToken cancellationToken = default)
    {
        await using var database = await contextFactory.CreateDbContextAsync(cancellationToken);
        return await database.JobDefinitions
            .AsNoTracking()
            .OrderByDescending(job => job.UpdatedAtUtc)
            .ToListAsync(cancellationToken);
    }

    public async Task<JobDefinition> SaveAsync(JobDefinition job, CancellationToken cancellationToken = default)
    {
        await using var database = await contextFactory.CreateDbContextAsync(cancellationToken);
        var now = DateTime.UtcNow;
        if (job.Id == 0)
        {
            job.CreatedAtUtc = now;
            job.UpdatedAtUtc = now;
            database.JobDefinitions.Add(job);
        }
        else
        {
            var existing = await database.JobDefinitions
                .SingleAsync(item => item.Id == job.Id, cancellationToken);
            job.CreatedAtUtc = existing.CreatedAtUtc;
            job.UpdatedAtUtc = now;
            database.Entry(existing).CurrentValues.SetValues(job);
        }

        await database.SaveChangesAsync(cancellationToken);
        return job;
    }

    public async Task DeleteAsync(int id, CancellationToken cancellationToken = default)
    {
        await using var database = await contextFactory.CreateDbContextAsync(cancellationToken);
        var job = await database.JobDefinitions.SingleAsync(item => item.Id == id, cancellationToken);
        database.JobDefinitions.Remove(job);
        await database.SaveChangesAsync(cancellationToken);
    }
}