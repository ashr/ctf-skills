using System.ComponentModel.DataAnnotations;

namespace small_model_orchestrator.Data;

public static class JobRunStatus
{
    public const string Queued = "Queued";
    public const string Running = "Running";
    public const string Completed = "Completed";
    public const string Failed = "Failed";
    public const string Interrupted = "Interrupted";
}

public sealed class JobRun
{
    public int Id { get; set; }

    public int JobDefinitionId { get; set; }

    [Required, StringLength(100)]
    public string JobName { get; set; } = "";

    [Required, StringLength(160)]
    public string Model { get; set; } = "";

    [Required]
    public string InputText { get; set; } = "";

    [Required]
    public string PromptSnapshotJson { get; set; } = "";

    [Required, StringLength(20)]
    public string Status { get; set; } = JobRunStatus.Queued;

    public string? Result { get; set; }

    public string? ErrorMessage { get; set; }

    public int? PromptTokens { get; set; }

    public int? CompletionTokens { get; set; }

    public int? TotalTokens { get; set; }

    public DateTime QueuedAtUtc { get; set; }

    public DateTime? StartedAtUtc { get; set; }

    public DateTime? CompletedAtUtc { get; set; }

    public List<JobRunEvent> Events { get; set; } = [];

    public List<RunArtifact> Artifacts { get; set; } = [];
}

public sealed class JobRunEvent
{
    public int Id { get; set; }

    public int JobRunId { get; set; }

    [Required, StringLength(24)]
    public string Kind { get; set; } = "status";

    [Required]
    public string Message { get; set; } = "";

    public DateTime CreatedAtUtc { get; set; }

    public JobRun JobRun { get; set; } = null!;
}

public sealed class RunArtifact
{
    public int Id { get; set; }

    public int JobRunId { get; set; }

    [Required, StringLength(200)]
    public string Name { get; set; } = "";

    [Required, StringLength(120)]
    public string MediaType { get; set; } = "text/plain";

    [Required]
    public byte[] Content { get; set; } = [];

    public DateTime CreatedAtUtc { get; set; }

    public JobRun JobRun { get; set; } = null!;
}

public sealed record JobRunSnapshot(
    string JobName,
    string Model,
    string SystemPrompt,
    string UserPrompt,
    double Temperature,
    int MaxOutputTokens,
    int MaxIterations,
    int MaxToolOutputCharacters,
    bool AllowShellTools);