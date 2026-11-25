namespace small_model_orchestrator.Services;

public sealed class ExecutionOptions
{
    public bool EnableShellTools { get; set; }

    public string WorkingDirectory { get; set; } = "/workspace";

    public int DefaultCommandTimeoutSeconds { get; set; } = 600;

    public int MaxCommandTimeoutSeconds { get; set; } = 1800;

    public int MaxCommandCharacters { get; set; } = 16000;
}
