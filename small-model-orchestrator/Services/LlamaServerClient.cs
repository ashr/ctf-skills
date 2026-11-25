using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using small_model_orchestrator.Data;

namespace small_model_orchestrator.Services;

public sealed record LlamaToolCall(string Id, string Name, string Arguments);

public sealed record LlamaChatMessage(
    string Role,
    string? Content,
    string? ToolCallId = null,
    string? Name = null,
    IReadOnlyList<LlamaToolCall>? ToolCalls = null);

public sealed record LlamaCompletion(
    string? Text,
    IReadOnlyList<LlamaToolCall> ToolCalls,
    int? PromptTokens,
    int? CompletionTokens,
    int? TotalTokens);

public sealed class LlamaServerClient(HttpClient httpClient, IConfiguration configuration)
{
    public async Task<LlamaCompletion> CompleteAsync(
        JobRunSnapshot job,
        IReadOnlyList<LlamaChatMessage> messages,
        IReadOnlyList<JsonElement> tools,
        CancellationToken cancellationToken = default)
    {
        var request = new JsonObject
        {
            ["model"] = job.Model,
            ["messages"] = BuildMessages(messages),
            ["temperature"] = job.Temperature,
            ["max_tokens"] = job.MaxOutputTokens,
            ["stream"] = false,
            ["parallel_tool_calls"] = false
        };
        if (tools.Count > 0)
        {
            var toolArray = new JsonArray();
            foreach (var tool in tools)
            {
                toolArray.Add(JsonNode.Parse(tool.GetRawText()));
            }
            request["tools"] = toolArray;
            request["tool_choice"] = "auto";
        }

        using var message = new HttpRequestMessage(HttpMethod.Post, "chat/completions")
        {
            Content = new StringContent(request.ToJsonString(), Encoding.UTF8, "application/json")
        };
        var apiKey = configuration["LlamaServer:ApiKey"];
        if (!string.IsNullOrWhiteSpace(apiKey))
        {
            message.Headers.Authorization = new AuthenticationHeaderValue("Bearer", apiKey);
        }

        using var response = await httpClient.SendAsync(message, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
        var responseBody = await response.Content.ReadAsStringAsync(cancellationToken);
        if (!response.IsSuccessStatusCode)
        {
            var detail = responseBody.Length > 1000 ? responseBody[..1000] : responseBody;
            throw new HttpRequestException($"llama-server returned {(int)response.StatusCode} {response.ReasonPhrase}: {detail}");
        }

        using var document = JsonDocument.Parse(responseBody);
        var root = document.RootElement;
        var choices = root.GetProperty("choices");
        if (choices.GetArrayLength() == 0)
        {
            throw new InvalidOperationException("llama-server returned no completion choices.");
        }

        var assistantMessage = choices[0].GetProperty("message");
        var content = assistantMessage.TryGetProperty("content", out var contentElement)
            && contentElement.ValueKind == JsonValueKind.String
                ? contentElement.GetString()
                : null;
        var toolCalls = new List<LlamaToolCall>();
        if (assistantMessage.TryGetProperty("tool_calls", out var callsElement)
            && callsElement.ValueKind == JsonValueKind.Array)
        {
            var callIndex = 0;
            foreach (var call in callsElement.EnumerateArray())
            {
                callIndex++;
                var id = call.TryGetProperty("id", out var idElement) && idElement.ValueKind == JsonValueKind.String
                    ? idElement.GetString() ?? $"call_{callIndex}"
                    : $"call_{callIndex}";
                var function = call.GetProperty("function");
                var name = function.GetProperty("name").GetString() ?? "";
                var argumentsElement = function.GetProperty("arguments");
                var arguments = argumentsElement.ValueKind == JsonValueKind.String
                    ? argumentsElement.GetString() ?? "{}"
                    : argumentsElement.GetRawText();
                toolCalls.Add(new LlamaToolCall(id, name, arguments));
            }
        }

        var usage = root.TryGetProperty("usage", out var usageElement) ? usageElement : default;
        return new LlamaCompletion(
            content,
            toolCalls,
            ReadUsage(usage, "prompt_tokens"),
            ReadUsage(usage, "completion_tokens"),
            ReadUsage(usage, "total_tokens"));
    }

    private static JsonArray BuildMessages(IReadOnlyList<LlamaChatMessage> messages)
    {
        var result = new JsonArray();
        foreach (var message in messages)
        {
            var item = new JsonObject
            {
                ["role"] = message.Role,
                ["content"] = message.Content
            };
            if (message.ToolCallId is not null)
            {
                item["tool_call_id"] = message.ToolCallId;
            }
            if (message.Name is not null)
            {
                item["name"] = message.Name;
            }
            if (message.ToolCalls is { Count: > 0 })
            {
                var calls = new JsonArray();
                foreach (var call in message.ToolCalls)
                {
                    calls.Add(new JsonObject
                    {
                        ["id"] = call.Id,
                        ["type"] = "function",
                        ["function"] = new JsonObject
                        {
                            ["name"] = call.Name,
                            ["arguments"] = call.Arguments
                        }
                    });
                }
                item["tool_calls"] = calls;
            }
            result.Add(item);
        }
        return result;
    }

    private static int? ReadUsage(JsonElement usage, string propertyName)
    {
        return usage.ValueKind == JsonValueKind.Object
            && usage.TryGetProperty(propertyName, out var value)
            && value.TryGetInt32(out var count)
                ? count
                : null;
    }
}
