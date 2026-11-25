using System.ComponentModel.DataAnnotations;

namespace small_model_orchestrator.Data;

public sealed class JobDefinition
{
    public int Id { get; set; }

    [Required, StringLength(100)]
    public string Name { get; set; } = "";

    [StringLength(500)]
    public string Description { get; set; } = "";

    [Required]
    public string SystemPrompt { get; set; } = "";

    [Required]
    public string UserPrompt { get; set; } = "";

    [Required, StringLength(160)]
    public string Model { get; set; } = "qwen36";

    [Range(0, 2)]
    public double Temperature { get; set; } = 0.2;

    [Range(1, 32768)]
    public int MaxOutputTokens { get; set; } = 2048;

    [Range(1, 60)]
    public int MaxIterations { get; set; } = 12;

    [Range(100, 50000)]
    public int MaxToolOutputCharacters { get; set; } = 12000;

    public bool AllowShellTools { get; set; }

    public bool IsEnabled { get; set; } = true;

    public DateTime CreatedAtUtc { get; set; }

    public DateTime UpdatedAtUtc { get; set; }

    public JobDefinition CopyForNew()
    {
        return new JobDefinition
        {
            Name = $"{Name} copy",
            Description = Description,
            SystemPrompt = SystemPrompt,
            UserPrompt = UserPrompt,
            Model = Model,
            Temperature = Temperature,
            MaxOutputTokens = MaxOutputTokens,
            MaxIterations = MaxIterations,
            MaxToolOutputCharacters = MaxToolOutputCharacters,
            AllowShellTools = AllowShellTools,
            IsEnabled = IsEnabled
        };
    }
}