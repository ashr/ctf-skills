using System.Diagnostics;
using System.Text;
using System.Text.Json;

namespace small_model_orchestrator.Services;

public sealed record BashCommandResult(int ExitCode, bool TimedOut, string Output);

public sealed class BashCommandExecutor(ExecutionOptions options)
{
    public JsonElement ToolSchema => JsonSerializer.SerializeToElement(new
    {
        type = "function",
        function = new
        {
            name = "run_bash",
            description = "Run a Bash command inside the isolated CTF tools container. The container has the installed security tools, running as the non-root ctf user with no sudo. Use only the single authorized target in ctf-context.yaml, never HTB infrastructure or other hosts. The command runs from the configured workspace unless cwd is provided. Commands are recorded and timed out processes are killed as a process tree.",
            parameters = new
            {
                type = "object",
                properties = new
                {
                    command = new { type = "string", description = "The Bash command to execute." },
                    timeout_seconds = new { type = "integer", description = "Optional wall-clock timeout in seconds; capped by the container policy." },
                    cwd = new { type = "string", description = "Optional existing working directory inside the container." }
                },
                required = new[] { "command" },
                additionalProperties = false
            }
        }
    });

    public async Task<BashCommandResult> ExecuteAsync(
        string command,
        int? timeoutSeconds,
        string? workingDirectory,
        int maxOutputCharacters,
        CancellationToken cancellationToken)
    {
        if (!options.EnableShellTools)
        {
            return new BashCommandResult(126, false, "[shell execution disabled by container policy]");
        }

        if (string.IsNullOrWhiteSpace(command))
        {
            return new BashCommandResult(2, false, "[command is empty]");
        }

        if (command.Length > options.MaxCommandCharacters)
        {
            return new BashCommandResult(2, false, $"[command exceeds {options.MaxCommandCharacters} characters]");
        }

        var cwd = string.IsNullOrWhiteSpace(workingDirectory) ? options.WorkingDirectory : workingDirectory;
        string fullCwd;
        try
        {
            fullCwd = Path.GetFullPath(cwd, options.WorkingDirectory);
        }
        catch (Exception exception)
        {
            return new BashCommandResult(2, false, $"[invalid working directory: {exception.Message}]");
        }

        if (!Directory.Exists(fullCwd))
        {
            return new BashCommandResult(2, false, $"[working directory does not exist: {fullCwd}]");
        }

        var timeout = Math.Clamp(
            timeoutSeconds ?? options.DefaultCommandTimeoutSeconds,
            1,
            options.MaxCommandTimeoutSeconds);
        var outputLimit = Math.Clamp(maxOutputCharacters, 100, 50000);
        var streamLimit = (outputLimit + 1) / 2;
        using var process = new Process
        {
            StartInfo = new ProcessStartInfo
            {
                FileName = "/bin/bash",
                WorkingDirectory = fullCwd,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true
            },
            EnableRaisingEvents = true
        };
        process.StartInfo.ArgumentList.Add("-lc");
        process.StartInfo.ArgumentList.Add(command);

        try
        {
            if (!process.Start())
            {
                return new BashCommandResult(127, false, "[failed to start /bin/bash]");
            }
        }
        catch (Exception exception)
        {
            return new BashCommandResult(127, false, $"[failed to start /bin/bash: {exception.Message}]");
        }

        var stdoutTask = ReadBoundedAsync(process.StandardOutput, streamLimit);
        var stderrTask = ReadBoundedAsync(process.StandardError, streamLimit);
        using var timeoutSource = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeoutSource.CancelAfter(TimeSpan.FromSeconds(timeout));
        var timedOut = false;

        try
        {
            await process.WaitForExitAsync(timeoutSource.Token);
        }
        catch (OperationCanceledException)
        {
            TryKillTree(process);
            await process.WaitForExitAsync(CancellationToken.None);
            if (cancellationToken.IsCancellationRequested)
            {
                throw;
            }

            timedOut = true;
        }

        var stdout = await stdoutTask;
        var stderr = await stderrTask;
        var output = JoinOutput(stdout, stderr, outputLimit);
        if (timedOut)
        {
            output = $"[timed out after {timeout}s; process tree killed]\n{output}";
        }
        else
        {
            output = $"[exit_code={process.ExitCode}]\n{output}";
        }

        return new BashCommandResult(timedOut ? 124 : process.ExitCode, timedOut, output);
    }

    private static async Task<string> ReadBoundedAsync(StreamReader reader, int limit)
    {
        var buffer = new char[2048];
        var captured = new StringBuilder(Math.Min(limit, 8192));
        var truncated = false;
        while (true)
        {
            var count = await reader.ReadAsync(buffer.AsMemory());
            if (count == 0)
            {
                break;
            }

            var remaining = limit - captured.Length;
            if (remaining > 0)
            {
                captured.Append(buffer, 0, Math.Min(count, remaining));
            }

            if (count > remaining)
            {
                truncated = true;
            }
        }

        if (truncated)
        {
            captured.Append("\n...[stream truncated]");
        }

        return captured.ToString();
    }

    private static string JoinOutput(string stdout, string stderr, int limit)
    {
        var combined = string.IsNullOrEmpty(stderr) ? stdout : string.IsNullOrEmpty(stdout)
            ? stderr
            : $"{stdout}\n[stderr]\n{stderr}";
        if (combined.Length <= limit)
        {
            return combined;
        }

        return $"{combined[..limit]}\n...[output truncated]";
    }

    private static void TryKillTree(Process process)
    {
        try
        {
            if (!process.HasExited)
            {
                process.Kill(entireProcessTree: true);
            }
        }
        catch (InvalidOperationException)
        {
        }
        catch (System.ComponentModel.Win32Exception)
        {
        }
    }
}
