using Microsoft.EntityFrameworkCore;

namespace small_model_orchestrator.Data;

public sealed class OrchestratorDbContext(DbContextOptions<OrchestratorDbContext> options) : DbContext(options)
{
    public DbSet<JobDefinition> JobDefinitions => Set<JobDefinition>();

    public DbSet<JobRun> JobRuns => Set<JobRun>();

    public DbSet<JobRunEvent> JobRunEvents => Set<JobRunEvent>();

    public DbSet<RunArtifact> RunArtifacts => Set<RunArtifact>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<JobDefinition>()
            .HasIndex(job => job.Name);

        modelBuilder.Entity<JobRun>()
            .HasIndex(run => new { run.Status, run.QueuedAtUtc });

        modelBuilder.Entity<JobRunEvent>()
            .HasOne(runEvent => runEvent.JobRun)
            .WithMany(run => run.Events)
            .HasForeignKey(runEvent => runEvent.JobRunId)
            .OnDelete(DeleteBehavior.Cascade);

        modelBuilder.Entity<RunArtifact>()
            .HasOne(artifact => artifact.JobRun)
            .WithMany(run => run.Artifacts)
            .HasForeignKey(artifact => artifact.JobRunId)
            .OnDelete(DeleteBehavior.Cascade);
    }
}