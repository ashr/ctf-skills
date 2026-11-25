# Small Model Orchestrator

A local web workbench for defining repeatable LLM jobs, running them one at a
time against a llama-server-hosted model, and reviewing outputs and artifacts.

## Run

Requires the .NET 8 SDK.

```sh
dotnet run --project small-model-orchestrator.csproj
```

The workbench includes an editable SQLite job library, a serial run queue,
llama-server integration, and gated Bash tool calls. See
[`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) for the architecture and
remaining work.

Restore the pinned local EF tool once, then create a schema migration after
changing the EF Core model:

```sh
dotnet tool restore
dotnet ef migrations add <MigrationName>
```

The database is created at `data/orchestrator.db` on first run. Local database
files and build output are excluded from version control.

The llama-server OpenAI-compatible API is configured under `LlamaServer` in
`appsettings.json`; the default endpoint is `http://192.168.101.128:8080/v1/`.
Set `LlamaServer__BaseUrl` in the environment to override it. Job definitions
use the model alias returned by that server's `/v1/models` endpoint.

## CTF Container UI

The standard launcher still opens an interactive shell. To launch the UI from
the CTF tools container, rebuild the image once after pulling these changes,
then launch it:

```sh
docker build -t ctf-agents .
CTF_WEB_UI=1 ./run-ctf.sh /path/to/engagement
```

Open `http://127.0.0.1:5280`. Set `CTF_WEB_PORT=5283` to choose another free
port. The launcher publishes only on host loopback (and
binds directly to host loopback when `CTF_NETWORK=host`). Bash tool calls run as
the container's `ctf` user — non-root, no sudo (see the main README's "Runtime
privilege model"). The
global shell setting is off during ordinary local `dotnet run` and is enabled
only by this launcher mode. A job must also have **Allow Bash tool calls**
checked.

This is full command execution within the CTF container, not a host sandbox.
Commands, bounded output, and output artifacts are persisted with each run.
Docker isolation is the security boundary; shell text instructions are not a
network scope enforcement mechanism. Keep the container limited to the
authorized CTF workspace and target network.