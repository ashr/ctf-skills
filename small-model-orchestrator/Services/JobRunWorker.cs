using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using small_model_orchestrator.Data;

namespace small_model_orchestrator.Services;

public sealed class JobRunWorker(
    IServiceScopeFactory scopeFactory,
    RunQueue queue,
    ExecutionOptions executionOptions,
    ILogger<JobRunWorker> logger) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        await RecoverQueueAsync(stoppingToken);

        await foreach (var runId in queue.ReadAllAsync(stoppingToken))
        {
            try
            {
                await ProcessRunAsync(runId, stoppingToken);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception exception)
            {
                logger.LogError(exception, "Unhandled failure while processing run {RunId}", runId);
            }
        }
    }

    private async Task RecoverQueueAsync(CancellationToken cancellationToken)
    {
        await using var scope = scopeFactory.CreateAsyncScope();
        var database = scope.ServiceProvider.GetRequiredService<OrchestratorDbContext>();
        var abandonedRuns = await database.JobRuns
            .Where(run => run.Status == JobRunStatus.Running)
            .ToListAsync(cancellationToken);
        var now = DateTime.UtcNow;
        foreach (var run in abandonedRuns)
        {
            run.Status = JobRunStatus.Interrupted;
            run.CompletedAtUtc = now;
            run.ErrorMessage = "The application stopped while this run was active.";
            run.Events.Add(new JobRunEvent
            {
                Kind = "recovery",
                Message = run.ErrorMessage,
                CreatedAtUtc = now
            });
        }

        var queuedIds = await database.JobRuns
            .Where(run => run.Status == JobRunStatus.Queued)
            .OrderBy(run => run.QueuedAtUtc)
            .Select(run => run.Id)
            .ToListAsync(cancellationToken);
        await database.SaveChangesAsync(cancellationToken);
        foreach (var runId in queuedIds)
        {
            queue.TryEnqueue(runId);
        }
    }

    private async Task ProcessRunAsync(int runId, CancellationToken cancellationToken)
    {
        await using var scope = scopeFactory.CreateAsyncScope();
        var database = scope.ServiceProvider.GetRequiredService<OrchestratorDbContext>();
        var run = await database.JobRuns
            .Include(item => item.Events)
            .SingleOrDefaultAsync(item => item.Id == runId, cancellationToken);
        if (run is null || run.Status != JobRunStatus.Queued)
        {
            return;
        }

        var now = DateTime.UtcNow;
        run.Status = JobRunStatus.Running;
        run.StartedAtUtc = now;
        run.Events.Add(new JobRunEvent { Kind = "status", Message = "Run started.", CreatedAtUtc = now });
        await database.SaveChangesAsync(cancellationToken);

        try
        {
            var snapshot = JsonSerializer.Deserialize<JobRunSnapshot>(run.PromptSnapshotJson)
                ?? throw new InvalidOperationException("The saved job snapshot could not be read.");
            var client = scope.ServiceProvider.GetRequiredService<LlamaServerClient>();
            var bash = scope.ServiceProvider.GetRequiredService<BashCommandExecutor>();
            var shellEnabled = executionOptions.EnableShellTools && snapshot.AllowShellTools;
            var toolSchemas = shellEnabled ? new[] { bash.ToolSchema } : [];
            var messages = new List<LlamaChatMessage>
            {
                new("system", BuildSystemPrompt(snapshot.SystemPrompt, shellEnabled)),
                new("user", BuildUserMessage(snapshot.UserPrompt, run.InputText))
            };
            var promptTokens = 0;
            var completionTokens = 0;
            var totalTokens = 0;
            var hasPromptUsage = false;
            var hasCompletionUsage = false;
            var hasTotalUsage = false;
            var toolCallCount = 0;
            var finished = false;

            for (var turn = 1; turn <= snapshot.MaxIterations; turn++)
            {
                var completion = await client.CompleteAsync(snapshot, messages, toolSchemas, cancellationToken);
                AccumulateUsage(completion, ref promptTokens, ref completionTokens, ref totalTokens,
                    ref hasPromptUsage, ref hasCompletionUsage, ref hasTotalUsage);

                if (completion.ToolCalls.Count == 0)
                {
                    if (completion.Text is null)
                    {
                        throw new InvalidOperationException("The model returned neither text nor a tool call.");
                    }

                    var completedAt = DateTime.UtcNow;
                    run.Status = JobRunStatus.Completed;
                    run.Result = completion.Text;
                    run.PromptTokens = hasPromptUsage ? promptTokens : null;
                    run.CompletionTokens = hasCompletionUsage ? completionTokens : null;
                    run.TotalTokens = hasTotalUsage ? totalTokens : null;
                    run.CompletedAtUtc = completedAt;
                    run.Events.Add(new JobRunEvent
                    {
                        Kind = "assistant",
                        Message = completion.Text,
                        CreatedAtUtc = completedAt
                    });
                    run.Artifacts.Add(new RunArtifact
                    {
                        Name = "response.txt",
                        MediaType = "text/plain; charset=utf-8",
                        Content = System.Text.Encoding.UTF8.GetBytes(completion.Text),
                        CreatedAtUtc = completedAt
                    });
                    finished = true;
                    break;
                }

                messages.Add(new LlamaChatMessage("assistant", completion.Text, ToolCalls: completion.ToolCalls));
                foreach (var toolCall in completion.ToolCalls)
                {
                    toolCallCount++;
                    if (toolCallCount > snapshot.MaxIterations)
                    {
                        throw new InvalidOperationException($"Tool-call limit reached ({snapshot.MaxIterations}).");
                    }

                    var toolResult = await ExecuteToolAsync(
                        toolCall,
                        shellEnabled,
                        snapshot,
                        run,
                        database,
                        bash,
                        cancellationToken);
                    messages.Add(new LlamaChatMessage("tool", toolResult, toolCall.Id, toolCall.Name));
                }
            }

            if (!finished)
            {
                throw new InvalidOperationException($"The model reached the configured turn limit ({snapshot.MaxIterations}) without a final response.");
            }
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            CompleteAsFailed(run, "The model request timed out.");
        }
        catch (Exception exception)
        {
            logger.LogWarning(exception, "Run {RunId} failed", runId);
            var message = exception.Message.Length > 2000 ? exception.Message[..2000] : exception.Message;
            CompleteAsFailed(run, message);
        }

        await database.SaveChangesAsync(cancellationToken);
    }

    private async Task<string> ExecuteToolAsync(
        LlamaToolCall toolCall,
        bool shellEnabled,
        JobRunSnapshot snapshot,
        JobRun run,
        OrchestratorDbContext database,
        BashCommandExecutor bash,
        CancellationToken cancellationToken)
    {
        if (!shellEnabled || !string.Equals(toolCall.Name, "run_bash", StringComparison.Ordinal))
        {
            return $"[tool rejected: {toolCall.Name} is not enabled for this job]";
        }

        string command;
        int? timeoutSeconds = null;
        string? workingDirectory = null;
        try
        {
            using var arguments = JsonDocument.Parse(toolCall.Arguments);
            var root = arguments.RootElement;
            if (!root.TryGetProperty("command", out var commandElement)
                || commandElement.ValueKind != JsonValueKind.String
                || string.IsNullOrWhiteSpace(command = commandElement.GetString() ?? ""))
            {
                return "[tool rejected: run_bash requires a non-empty command string]";
            }

            if (root.TryGetProperty("timeout_seconds", out var timeoutElement)
                && timeoutElement.ValueKind == JsonValueKind.Number
                && timeoutElement.TryGetInt32(out var requestedTimeout))
            {
                timeoutSeconds = requestedTimeout;
            }

            if (root.TryGetProperty("cwd", out var cwdElement) && cwdElement.ValueKind == JsonValueKind.String)
            {
                workingDirectory = cwdElement.GetString();
            }
        }
        catch (JsonException)
        {
            return "[tool rejected: arguments were not valid JSON]";
        }

        var startedAt = DateTime.UtcNow;
        run.Events.Add(new JobRunEvent
        {
            Kind = "tool_call",
            Message = $"run_bash: {command}",
            CreatedAtUtc = startedAt
        });
        var result = await bash.ExecuteAsync(
            command,
            timeoutSeconds,
            workingDirectory,
            snapshot.MaxToolOutputCharacters,
            cancellationToken);
        var artifactName = $"tool-{run.Artifacts.Count + 1:00}-output.txt";
        run.Artifacts.Add(new RunArtifact
        {
            Name = artifactName,
            MediaType = "text/plain; charset=utf-8",
            Content = System.Text.Encoding.UTF8.GetBytes(result.Output),
            CreatedAtUtc = DateTime.UtcNow
        });
        run.Events.Add(new JobRunEvent
        {
            Kind = "tool_result",
            Message = $"run_bash exit_code={result.ExitCode}; output saved as {artifactName}.",
            CreatedAtUtc = DateTime.UtcNow
        });
        await database.SaveChangesAsync(cancellationToken);
        return result.Output;
    }

    private static string BuildUserMessage(string prompt, string input)
    {
        return prompt.Contains("{{input}}", StringComparison.Ordinal)
            ? prompt.Replace("{{input}}", input, StringComparison.Ordinal)
            : $"{prompt}\n\nInput:\n{input}";
    }

    private static string BuildSystemPrompt(string prompt, bool shellEnabled)
    {
        if (!shellEnabled)
        {
            return prompt;
        }

        return prompt + "\n\n## Container shell and CTF scope\n"
            + "run_bash executes inside the isolated CTF tools container, never on the host. "
            + "Use only the single target IP from /workspace/ctf-context.yaml; never probe 10.10.10.2 or any other host. "
            + "Verify the configured VPN is connected before scanning or exploitation. "
            + "Follow the required Recon -> Foothold -> PrivEsc -> Flags gates. There is no sudo in this container; "
            + "use the non-root tooling already provided (setcap'd binaries, sleuthkit instead of mount, etc.). "
            + "Treat command output as the only evidence; do not claim a command succeeded unless its output confirms it.";
    }

    private static void AccumulateUsage(
        LlamaCompletion completion,
        ref int promptTokens,
        ref int completionTokens,
        ref int totalTokens,
        ref bool hasPromptUsage,
        ref bool hasCompletionUsage,
        ref bool hasTotalUsage)
    {
        if (completion.PromptTokens is { } prompt)
        {
            promptTokens += prompt;
            hasPromptUsage = true;
        }
        if (completion.CompletionTokens is { } generated)
        {
            completionTokens += generated;
            hasCompletionUsage = true;
        }
        if (completion.TotalTokens is { } total)
        {
            totalTokens += total;
            hasTotalUsage = true;
        }
    }

    private static void CompleteAsFailed(JobRun run, string message)
    {
        var now = DateTime.UtcNow;
        run.Status = JobRunStatus.Failed;
        run.ErrorMessage = message;
        run.CompletedAtUtc = now;
        run.Events.Add(new JobRunEvent { Kind = "error", Message = message, CreatedAtUtc = now });
    }
}
