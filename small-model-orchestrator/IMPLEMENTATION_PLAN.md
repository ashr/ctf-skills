# Implementation Plan

## Goal

Build a local .NET web UI for authoring reusable prompts/jobs, launching runs
against a small Qwen model served by llama-server, and reviewing persisted
outputs, tool activity, and artifacts. SQLite is the durable source of truth.

## Architecture

- ASP.NET Core Blazor Web App with Interactive Server UI.
- SQLite persistence, with EF Core migrations for schema evolution.
- A hosted background worker that runs at most one LLM job at a time.
- An OpenAI-compatible HTTP client targeting llama-server's `/v1` endpoint.
- Explicit job and run state, rather than a large autonomous agent framework.

## Phases

### 0. Foundation

- Keep the app buildable and runnable with the .NET 8 SDK.
- Add configuration for the llama-server base URL, model alias, API key, and
  context/output limits; do not put secrets in source control.
- Add a health/status view for the web app, SQLite database, and model endpoint.

### 1. Persistence

- Add EF Core SQLite and migrations.
- Create entities for job definitions, job runs, run events/messages, tool calls,
  and artifacts.
- Persist the prompt/settings snapshot on each run so editing a job never
  changes the record of a previous or queued run.
- Define artifact size/type limits; keep artifact content in SQLite initially
  and measure database growth before considering external blob storage.

### 2. Job authoring and launch UI

- List, create, edit, clone, enable/disable, and delete job definitions.
- Support a system prompt, task prompt/template variables, model parameters,
  allowed tools, and per-job budgets.
- Add an explicit **Run** action for a selected job and a queue view with
  pending/running/completed/blocked/failed states.
- Show the active run, queue order, and a clear cancel action.

### 3. llama-server integration

- Use the OpenAI-compatible chat-completions API at `<base-url>/v1`.
- Resolve/validate the configured model alias from `/v1/models`.
- Support non-streaming first; add streaming once persistence and cancellation
  are reliable.
- Add tool-call request/response handling and a small deterministic tool
  registry; tool results return through the next chat turn.
- Verify function calling against the actual Qwen GGUF chat template and the
  deployed llama-server build before relying on it.

### 4. Serial job execution

- Implement a durable queue consumed by one `BackgroundService` worker.
- On startup, reconcile runs left in `running` state and mark them interrupted
  or requeue them according to an explicit retry policy.
- Save status transitions and each request/response/tool event as they happen.
- Enforce cancellation, request timeouts, retry limits, and a hard maximum
  number of model/tool iterations.
- Keep model concurrency at one by default to protect 12 GB VRAM and avoid
  unpredictable KV-cache pressure.

### 5. Run detail and artifacts

- Add a run detail page with final response, chronological event/tool log,
  errors, token/iteration usage when supplied, and linked artifacts.
- Store text/JSON artifacts as searchable content; store binary artifacts as
  SQLite blobs only within configured size limits.
- Make artifact creation explicit and record the producing run/tool and time.

### 6. Small-model reliability controls

- Keep tool definitions few, short, typed, and purpose-specific.
- Bound prompt size, tool output size, generated tokens, tool calls, retries,
  and wall-clock runtime; make limits visible in the job editor.
- Compact older conversation turns while retaining the system prompt, original
  objective, recent actions, and confirmed facts/findings.
- Detect repeated identical tool calls and excessive enumeration; nudge, block,
  or stop at configured thresholds.
- Prefer structured evidence/facts over asking the model to reconstruct long
  histories from transcripts.
- Add stop conditions for completion, blocked work, and model errors; never
  infer success solely from an empty response.

### 7. CTF execution safety

- Load the target and VPN details from the configured CTF context before
  enabling command/exploitation tools.
- Verify VPN connectivity before scanning; do not run scan tools if the check
  fails.
- Enforce single-target scope in the tool layer, including exclusion of
  out-of-scope hosts such as HTB infrastructure addresses.
- Require completed recon evidence before exploit work, a recorded foothold
  before privilege escalation, and successful escalation before flag capture.
- Treat prompt text as instructions, not as authority to bypass these gates.
- Record commands, outputs, and artifact provenance for review.

### 8. Tests and packaging

- Unit-test persistence, queue transitions/recovery, prompt snapshots, tool
  budgets, repeated-call handling, cancellation, and safety gates.
- Add an offline fake OpenAI-compatible endpoint for deterministic integration
  tests; keep live llama-server smoke tests opt-in.
- Add container/run documentation only after local build, migration, and run
  lifecycle are stable.

## First implementation slice

1. [x] Add EF Core SQLite, an initial migration, and the job-definition model.
2. [x] Build the job list/editor and persist definitions, prompt text, model
  alias, temperature, output token cap, iteration cap, and tool-output cap.
3. [x] Add run snapshots, queue/run persistence, and queue controls with a
  serial worker.
4. [x] Add non-streaming llama-server chat-completions integration.
5. [x] Add gated sequential Bash tool calls, command/output persistence, and an
  opt-in CTF-container UI launch path.

## Current implementation

- `Data/JobDefinition.cs` holds reusable prompt and resource-budget settings.
- `Data/Migrations/` tracks the SQLite schema; startup applies pending
  migrations automatically.
- `Data/JobRepository.cs` handles definition CRUD using short-lived EF contexts.
- The home page supports create, edit, duplicate, enable/pause, and delete.
- Browser-tested create/save/reload confirms definitions persist across reloads.
- Runs save an immutable prompt snapshot and execute through one durable,
  single-reader background worker; queued work is restored after restart and
  abandoned in-progress work is marked interrupted.
- llama-server uses the OpenAI-compatible `/v1/chat/completions` route. Model
  alias and timeout are configurable in `appsettings.json` / environment vars.
- Each run stores its input, output/error, token counts when provided, timeline,
  and `response.txt` artifact; `/runs/{id}` displays the persisted record.
- A local fake OpenAI-compatible endpoint verified queue -> completion -> run
  detail/artifact rendering without using the GPU.
- `run_bash` is offered only when both process-level `Execution:EnableShellTools`
  and the job's `AllowShellTools` are enabled. The container launcher enables
  the process switch only for `CTF_WEB_UI=1`; ordinary host development remains
  shell-disabled.
- Bash commands run as the container `ctf` user (non-root, no sudo),
  `/workspace` default CWD, bounded command length/runtime/output, process-tree
  termination on timeout, and command/result events plus output artifacts.
- The UI is published on host loopback only. The container itself is the
  execution boundary; the app does not claim to technically enforce target
  network scope for arbitrary Bash.
- The Docker build stage and a containerized run were verified. A deterministic
  OpenAI-compatible tool response executed `id -un; sudo -n id -u; printf ...`
  inside the cached CTF image and persisted `[exit_code=0]`, `ctf`, `0`, and the
  marker output as a run artifact.

## Next implementation slice

1. Add real test projects for queue capacity, prompt snapshots, status recovery,
   API request shape, response/error handling, and artifact persistence.
2. Add an explicit model health/alias check and surface endpoint status in the UI.
3. Test native Qwen tool-call formatting against the real llama-server and
  validate the CTF context/VPN status workflow before broader use.
4. Add stronger target-network restrictions at the Docker/network layer if
  isolation from non-target destinations is required.
5. Add run cancellation and streaming only after the persisted lifecycle tests
   are in place.

Keep each slice runnable and covered by focused tests before adding the next.