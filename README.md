# CTF Pentesting Agent Stack

Multi-agent AI pentesting stack for Hack The Box and similar CTF platforms.
Connect VPN, drop a target IP, let the agents drive to flags.

---

## Quick Start

### 1. Build the image

```bash
make -f Makefile.ctf build
```

### 2. Start a CTF session

```bash
# Run from your HTB project directory — ctf-context.yaml is auto-seeded from template
./run-ctf.sh ~/ctf/htb/editorial

# With credentials
GITHUB_TOKEN=ghp_xxx SHODAN_API_KEY=yyy ./run-ctf.sh ~/ctf/htb/editorial

# Host networking (better for VPN — no NAT between container and tun0)
CTF_NETWORK=host GITHUB_TOKEN=ghp_xxx ./run-ctf.sh ~/ctf/htb/editorial

# Lock egress down to the target only (+ tool-infra hosts) — see "Egress Control"
CTF_TARGETS="editorial.htb,10.10.11.42" ./run-ctf.sh ~/ctf/htb/editorial
```

The script:
- **Auto-seeds** `ctf-context.yaml` from the template if it doesn't exist yet
- **Mounts** your project directory live into `/workspace` (edit files from host, see loot instantly)
- **Creates** `loot/` directory automatically
- **Runs** the container as the non-root `ctf` user by default
- **Persists** CLI auth/config in `.ctf-agent-home/` inside your project directory
- **Passes** credentials (`GITHUB_TOKEN`, `SHODAN_API_KEY`, `ANTHROPIC_API_KEY`, etc.) into the container
- **Wires** VPN device (`/dev/net/tun`) and scoped network capabilities for OpenVPN/Nmap

### 3. Fill in ctf-context.yaml

On first run, `ctf-context.yaml` is created in your project dir. Edit it:

```yaml
target:
  ip: "10.10.11.42"           # Machine IP from HTB
  name: "Editorial"           # Machine name
  os: "linux"                 # linux | windows | unknown
  difficulty: "easy"          # easy | medium | hard | insane
  category: "fullpwn"         # fullpwn | web | pwn | crypto | forensics | misc

vpn:
  iface: "tun0"
  ovpn_file: "/workspace/htb.ovpn"   # drop htb.ovpn in your project dir
```

### 4. Connect VPN + start hacking

Inside the container:

```bash
# VPN connects automatically if ovpn_file is set in ctf-context.yaml
# Or manually:
openvpn --config /workspace/htb.ovpn --daemon
ping 10.10.11.42

# Copilot CLI (authenticate once per session)
gh auth login   # or: export GH_TOKEN=$GITHUB_TOKEN
gh copilot suggest "scan 10.10.11.42 for open ports and services"
gh copilot explain "$(cat /workspace/loot/nmap_full.nmap)"
```

---

## Attack Flow

```
VPN Verify → Recon → Exploit Branch(es) → Foothold → PrivEsc → Flags
```

Branches after recon:
- Web services → WebTestAgent / APIAgent / JSLibAgent
- CVE version → ExploitAgent
- Binary challenge → PWNAgent
- Crypto challenge → CryptoAgent
- Forensics artifact → ForensicsAgent

If `HTB_API_TOKEN` is set and `ctf-context.yaml` has no target IP yet, HTBAgent
runs first to pick/start a machine and populate the target before Recon.
LoggerAgent isn't part of the phase chain — every agent calls it immediately
after any confirmed exploit, credential capture, or flag find.

---

## Agents

| Agent | Role |
|-------|------|
| OrchestratorAgent | Lead — VPN verify, phase management, agent delegation |
| HTBAgent | HTB platform integration — select/start machine, fetch VPN config, submit flags |
| ReconAgent | Port scanning, web enum, service fingerprinting, vhost discovery |
| InfraAgent | CVE identification, exploit path recommendations |
| WebTestAgent | Web vulnerabilities (SQLi, LFI, SSRF, SSTI, XSS, upload bypass) |
| APIAgent | REST/GraphQL API testing, BOLA, JWT attacks |
| JSLibAgent | JavaScript library CVEs, secret scanning in bundles |
| ExploitAgent | CVE exploitation, hash cracking (john/hashcat), SMB/AD attacks |
| PrivEscAgent | Linux (linpeas, SUID, sudo, cron) + Windows (winpeas, tokens, services) |
| FlagAgent | Find and capture user.txt / root.txt |
| ValidatorAgent | PoC verification + attack chain writeup |
| PWNAgent | Binary exploitation (BOF, ROP, format strings, shellcode) |
| CryptoAgent | RSA attacks, classical ciphers, hash cracking, XOR |
| ForensicsAgent | Steganography, PCAP analysis, memory forensics, file carving |
| LoggerAgent | Evidence recorder — logs every confirmed exploit/credential/flag for writeup + replay |

Agent definitions live in `agents/<AgentName>/definition.md`.

---

## Output — loot/

All output goes to `/workspace/loot/` (which is your host project dir):

| File | Written by | Contents |
|------|-----------|----------|
| `recon_results.yaml` | ReconAgent | Attack surface map |
| `infra_findings.yaml` | InfraAgent | CVEs + exploit recommendations |
| `foothold.yaml` | First agent to get shell | Initial access method + user |
| `loot.yaml` | All agents | Credentials, hashes, keys, tokens |
| `privesc.yaml` | PrivEscAgent | Escalation path used |
| `flags.yaml` | FlagAgent | `HTB{...}` flag values |
| `attack_chain.md` | ValidatorAgent | Full writeup |
| `nmap_full.*` | ReconAgent | Raw nmap output |
| `web_findings.yaml` | WebTestAgent | Web vulnerabilities |
| `api_findings.yaml` | APIAgent | API findings |
| `exploit_log.yaml` + `evidence/` | LoggerAgent | Every confirmed payload/command/response, with full evidence files |

### HTB platform integration (optional)

Set `HTB_API_TOKEN` (from HTB Account Settings → API Key) to let HTBAgent
auto-select a machine, fetch its VPN config, and submit flags for you instead
of doing it by hand:

```bash
HTB_API_TOKEN=xxx HTB_AUTO_SELECT=1 ./run-ctf.sh ~/ctf/htb/
# or target a specific machine:
HTB_API_TOKEN=xxx HTB_MACHINE_ID=123 ./run-ctf.sh ~/ctf/htb/
```

`htb_api.py` can also be driven directly (`machines`, `start`, `stop`,
`status`, `ovpn`, `submit`, `whoami` — see the script header for usage).

---

## Key Tools in the Image

| Category | Tools |
|----------|-------|
| VPN / Tunneling | openvpn, chisel, socat, proxychains4 |
| Recon | nmap, httpx, ffuf, gobuster, nikto, whatweb, subfinder, dnsx |
| Web | sqlmap, dalfox, commix, jwt_tool, arjun, wfuzz, wpscan, katana |
| AD / Windows | impacket, netexec (nxc), evil-winrm, bloodhound-python, smbclient |
| Exploit | msfconsole, searchsploit, nuclei |
| Credentials | john, hashcat, hydra |
| PrivEsc | linpeas, winpeas, pspy |
| PWN | pwntools, gdb+pwndbg, radare2, ROPgadget, ropper, checksec |
| Crypto | pycryptodome, gmpy2, owiener, hashcat, john |
| Forensics | binwalk, foremost, steghide, zsteg, tshark, volatility3, exiftool, aircrack-ng |
| Copilot | gh, gh copilot (authenticate at runtime) |
| AI assistant | `interpreter`, `i` (Open Interpreter) |
| Wordlists | `/opt/wordlists/SecLists/`, `/opt/wordlists/rockyou.txt` |

Runtime privilege model:
- The image installs tooling as root at build time, then an `entrypoint.sh`
  applies egress control (see "Egress Control" below) and drops to the `ctf`
  user via `gosu` before handing off to the real command.
- **No sudo.** `ctf` has no root escape at runtime — `openvpn`, `nmap`, and
  `date` (for Kerberos clock-skew fixes) get exactly the Linux file
  capabilities they need via `setcap`; the Python `dist-packages` tree is
  `ctf`-owned at build time so tools like impacket can be live-patched
  without root; disk images are read via `sleuthkit` (no `mount` needed);
  low ports (SMB relay, etc.) are bindable via a container-level sysctl, not
  a capability grant. This also means egress control (below) can't be
  trivially bypassed with `sudo nft flush ruleset`. A `setcap` grant only
  takes effect if the *container* itself was also given that capability —
  `run-ctf.sh` already passes `--cap-add NET_ADMIN --cap-add NET_RAW
  --cap-add SYS_TIME` and the low-port sysctl; a hand-rolled `docker run`
  needs to do the same (see the Dockerfile header comment).
- Runtime `apt`/system changes are intentionally unavailable; install extra
  Python tools with `python3 -m pip install --user ...`, or rebuild the image
  to add a system package permanently.

---

## Egress Control

By default the container has unrestricted outbound network access. Set
`CTF_TARGETS` to lock it down to an explicit allowlist:

```bash
CTF_TARGETS="editorial.htb,10.10.11.42" ./run-ctf.sh ~/ctf/htb/editorial
```

Comma-separated hostnames, IPs, or CIDRs. `ctf-context.yaml`'s `target.ip`
is folded in automatically — no need to duplicate it. So is the host of
whichever LLM backend you've configured for this run (`ANTHROPIC_BASE_URL`,
`OLLAMA_API_BASE`, or `LlamaServer__BaseUrl`, if set), plus a small built-in
baseline that stays reachable whenever `CTF_TARGETS` is set: `api.anthropic.com`,
`api.openai.com`, `github.com`, `api.github.com`, `api.githubcopilot.com`,
`www.hackthebox.com`. Add anything else you rely on (e.g. `api.shodan.io`)
to `CTF_TARGETS` yourself.

The VPN interface (`tun0` by default, or `ctf-context.yaml`'s `vpn.iface`) is
always fully trusted — HTB/VPN providers already scope that network
themselves. DNS to whatever resolver the container is actually configured
with is always allowed. Hostnames are re-resolved every ~60s so IP rotation
(round-robin/CDN) doesn't cut off an in-progress target mid-engagement.

**This is a best-effort scope guard against accidental overreach** — an
agent scanning the wrong IP, a tool phoning home somewhere random, scope
creep beyond the authorized target — not a mathematically airtight boundary
against a determined adversary with arbitrary code execution in the
container. It's considerably stronger than it would be with sudo present
(no more `sudo nft flush ruleset`/`sudo bash` bypass), but no single-layer
network filter is a substitute for not running untrusted code in the first
place.

With no `CTF_TARGETS` and no `target.ip` set, egress control is a complete
no-op — nothing changes from today's behavior. Check status inside the
container with `nft list table inet egress_filter` (or
`/var/log/egress-control.log` for the refresh loop's history).

The non-root/no-sudo + egress-control mechanism here isn't CTF-specific —
see [`docs/repurpose-as-llm-sandbox.md`](docs/repurpose-as-llm-sandbox.md)
for a guide to stripping this down into a general-purpose contained sandbox
for any LLM agent, minus the offensive tooling.

---

## Directory Structure

```
ctf-skills/
├── Dockerfile              — CTF container image
├── Makefile.ctf            — build / check targets
├── run-ctf.sh              — launch script (workspace mount, credential passthrough)
├── entrypoint.sh           — root-run container entrypoint (egress control, drops to ctf)
├── egress-control.sh       — builds/applies the CTF_TARGETS nftables allowlist
├── install-tooling.sh      — bare-metal tool installer
├── htb_api.py              — Hack The Box API v4 helper (used by HTBAgent)
├── .gitignore              — excludes .venv/, __pycache__, build output, *.db, secrets
├── agents/
│   ├── OrchestratorAgent/  — attack flow controller
│   ├── HTBAgent/           — HTB platform integration (machine select, VPN, flag submit)
│   ├── ReconAgent/         — reconnaissance
│   ├── InfraAgent/         — CVE analysis
│   ├── WebTestAgent/       — web exploitation
│   ├── APIAgent/           — API testing
│   ├── JSLibAgent/         — JS analysis
│   ├── ExploitAgent/       — CVE exploitation + hash cracking
│   ├── PrivEscAgent/       — privilege escalation
│   ├── FlagAgent/          — flag capture
│   ├── ValidatorAgent/     — verification + writeup
│   ├── PWNAgent/           — binary exploitation
│   ├── CryptoAgent/        — crypto challenges
│   ├── ForensicsAgent/     — forensics + stego
│   ├── LoggerAgent/        — exploitation evidence recorder
│   └── shared/
│       ├── constraints.md  — rules all agents follow
│       ├── output-schemas.md — YAML schemas for loot files
│       └── tooling.md      — full tool inventory
├── prompts/
│   └── ctf-htb-kickoff.prompt.md  — Copilot Chat kickoff prompt
├── runner/                 — standalone Ollama/litellm agent loop (see "Local Models" below)
│   ├── main.py              — CLI entrypoint
│   ├── agent_runner.py      — tool-calling loop, delegation, context compaction
│   ├── agent_loader.py      — assembles system prompts from agents/*/definition.md
│   ├── llm.py               — litellm/Ollama client
│   └── tools.py             — run_command / read_file / write_file / list_dir
├── small-model-orchestrator/  — .NET web workbench for repeatable llama-server jobs
│                                (see "Web Workbench" below, launched via CTF_WEB_UI=1)
└── Templates/
    └── ctf-context-template.yaml  — fill in per-machine
```

---

## Copilot Chat (VS Code)

Use `prompts/ctf-htb-kickoff.prompt.md` in Copilot Chat to invoke the full agent stack:

```
@OrchestratorAgent Start CTF engagement.
Inputs:
  CTF context: /workspace/ctf-context.yaml
...
```

## Copilot CLI (inside container)

```bash
export GH_TOKEN=$GITHUB_TOKEN
gh copilot suggest "one-liner to find SUID binaries on Linux"
gh copilot explain "$(cat /workspace/loot/nmap_full.nmap)"
```

---

## Claude Code CLI (router / local LLM backend)

The image installs the `claude` CLI (see Dockerfile). By default it talks to
Anthropic's API — authenticate with `claude login` or `export ANTHROPIC_API_KEY=...`
(passed through automatically by `run-ctf.sh`). You can instead point it at
**any Anthropic-Messages-API-compatible endpoint** — an LLM router/gateway in
front of multiple providers, or a fully local model server — via three env
vars Claude Code reads directly: `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`,
`ANTHROPIC_MODEL`.

### Via a router/gateway (e.g. Bifrost)

```bash
export ANTHROPIC_BASE_URL="https://bifrostgatewayendpoint/"   # your gateway's URL
export ANTHROPIC_AUTH_TOKEN="BIFROST-KEY"                     # your gateway's key
export ANTHROPIC_MODEL="91ryilt8uc1f"                          # model id as the gateway knows it

claude
```

Values above are placeholders — swap in your gateway's actual endpoint, key,
and model id.

### Via a fully local llama.cpp server

Start `llama-server` with a tool-calling-capable model (`--jinja` is required
for tool calls to render correctly):

```bash
# Pull a model straight from Hugging Face
llama-server -hf unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL --alias qwen36 --jinja \
  -ngl 99 --n-cpu-moe 30 -c 65536 --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0.0 --port 8080

# Or point at a model file you already have on disk
./build/bin/llama-server -m ~/models/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf --alias qwen36 --jinja \
  -c 81920 --parallel 1 --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0.0 --port 8080
```

Then point Claude Code at it (`ANTHROPIC_AUTH_TOKEN` can be any non-empty
dummy value — llama-server doesn't check it):

```bash
export ANTHROPIC_BASE_URL=http://localhost:8080
export ANTHROPIC_AUTH_TOKEN=local
export ANTHROPIC_MODEL=qwen36
export CLAUDE_CODE_MAX_OUTPUT_TOKENS=12288   # smaller local models need a lower cap than Claude's default

claude
```

`CLAUDE_CODE_MAX_OUTPUT_TOKENS` bounds how many tokens Claude Code will ask
the model to generate per turn — lower it for small/slow local models (raise
`-c`/context size on the `llama-server` side accordingly if you do).

`run-ctf.sh` passes `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`,
`ANTHROPIC_MODEL`, and `CLAUDE_CODE_MAX_OUTPUT_TOKENS` through to the
container if set on the host, so you can export them before launching
instead of re-exporting inside the container each time.

---

## Local Models (Ollama via litellm)

If `gh copilot` isn't an option (no GitHub Copilot subscription, air-gapped
engagement, or you just want to run a local model), `runner/` is a standalone
Python agent loop that drives the same `agents/*/definition.md` personas
against a local or self-hosted **Ollama** server instead of Copilot Chat.

It reads `ctf-context.yaml` the same way OrchestratorAgent's definition
describes, calls tools (`run_command`, `read_file`, `write_file`, `list_dir`)
directly against the container filesystem/shell, and lets OrchestratorAgent
hand off work to specialist agents via a `delegate_agent` tool call (the
standalone equivalent of `@ReconAgent` chat mentions, since there's no chat
UI here to do that hand-off for us).

### Usage

```bash
# Point at wherever Ollama is actually running — usually the host, not the container
export OLLAMA_API_BASE=http://host.docker.internal:11434   # bridge networking
# or: export OLLAMA_API_BASE=http://192.168.x.x:11434       # host networking / remote box

export LLM_MODEL=qwen2.5:14b   # must support native tool-calling (Ollama /api/chat)

# Default: runs OrchestratorAgent with the standard kickoff message
python3 -m runner.main

# Run a single specialist agent directly
python3 -m runner.main --agent ReconAgent --task "scan 10.10.11.42, all TCP ports"

# Override the model/host per-invocation instead of via env vars
python3 -m runner.main --model qwen2.5:32b --api-base http://192.168.101.127:11434
```

Requires a tool-calling-capable model — `qwen2.5`, `llama3.1`/`3.3`,
`mistral-nemo`, etc. Plain chat-only models will never emit a tool call and
the loop will just print text back at you.

### Env vars

| Var | Default | Purpose |
|-----|---------|---------|
| `OLLAMA_API_BASE` | `http://localhost:11434` | Ollama server address |
| `OLLAMA_API_KEY`  | *(unset)* | Only needed if your Ollama server is behind auth |
| `LLM_MODEL` | `qwen2.5:14b` | Model name as known to Ollama (`ollama list`) |
| `LLM_CONTEXT_WINDOW` | `32768` | Passed to Ollama as `num_ctx` — set to what the model/your VRAM can actually hold. Note: Ollama caps this at whatever `OLLAMA_CONTEXT_LENGTH` the server was started with, regardless of the model's native window. |
| `LLM_MAX_TOKENS` | `8192` | Max tokens per completion. Hybrid-reasoning models can burn this whole budget on hidden thinking before emitting a real answer/tool call — raise it if you see empty final messages. |
| `LLM_DISABLE_THINKING` | `1` | Disables Ollama's native `think` channel for hybrid-reasoning models (gemma4, qwen3, ...). Some quantizations leak raw `<think>`/`<|channel|>` tokens into tool-call arguments instead of a separate reasoning channel when thinking is left on — set to `0` to re-enable. |
| `LLM_COMPACTION_RATIO` | `0.5` | Fraction of `num_ctx` at which rolling compaction kicks in. Lower this if your Ollama/llama.cpp backend gets unstable (context-checkpoint churn, occasional 500s) at large context sizes well before `num_ctx` is hit. |
| `LLM_SLIM_PROMPT` | `0` | `1` drops `shared/tooling.md` from the system prompt to save tokens on small models |
| `LLM_DEBUG` | `0` | `1` enables litellm's verbose request/response logging |
| `LLM_RETRY_ATTEMPTS` / `LLM_RETRY_BASE_DELAY` | `3` / `2` | Retry/backoff for transient connection errors |

### Visibility & logs

Every agent invocation (including delegated sub-agents) writes its full,
untruncated message transcript to `loot/agent_logs/<timestamp>-<agent>-d<depth>-<id>.jsonl`
— one JSON object per line, so you can inspect exactly what the model saw and
said even after the run finishes or is killed. The live console shows a
truncated preview of the model's reasoning text and each tool call/result.

### Task/fact store — `loot/agent_tasks.db`

Every run opens (or creates) a SQLite DB at `loot/agent_tasks.db` with `tasks`,
`facts`, `findings`, and `events` tables — see `runner/db.py`. Agents use
`get_facts`/`set_fact` for single-value engagement state (target IP, os, ...),
`record_finding`/`list_findings` for a running evidence log (confirmed ports,
endpoints, vulns, credentials), and `complete_task` to explicitly signal
they're done (rather than the loop guessing from the model going quiet).

**This file is reused across runs by default, not blanked.** If you re-run
`python3 -m runner.main` against the same workspace directory, facts/findings/
task rows from the previous run are still there and visible — useful for
resuming after a crash, but means stale data (e.g. a different machine's
`target_ip`) can leak into a new engagement if you reuse a directory. Pass
`--fresh-db` to wipe it and start clean, or `--no-db` to disable the task/fact
tools entirely and run a plain conversational loop.

### Fighting hallucination and "getting lost" on small models

Small local models tend to drift the longer a task runs — inventing details,
forgetting the objective, or re-enumerating things they already found instead
of recognizing they have enough to act on. The runner pushes back on this a
few ways:

- **Grounding rule** in every system prompt: only state facts/findings backed
  by real tool output seen earlier in the conversation, never invent hosts,
  ports, credentials, or flags.
- **Enumeration throttle** — `run_command` calls matching scan/enum tools
  (nmap, gobuster, ffuf, nikto, httpx, nuclei, ...) are counted regardless of
  their exact arguments. At 6 calls the model gets a checkpoint nudge to check
  `list_findings`/`get_facts` before scanning more; at 12 the task is
  auto-completed using whatever findings exist rather than left to spiral.
- **Exact-repeat detection** — separately, calling the *exact same* tool with
  the *exact same* arguments repeatedly (e.g. retrying an identically broken
  command) gets a warning on the 3rd repeat and a forced `blocked` abort on
  the 5th.
- **Periodic reorientation** — every 8 iterations, a reminder is injected
  re-stating the original objective plus current known facts/findings, so a
  model doesn't lose the plot as the (even compacted) conversation grows long.

### Context-limit strategy for small local models

Small models run out of context fast once tool-call transcripts pile up, and
Ollama truncates from the *front* of the token sequence when `num_ctx` is
exceeded — which can silently drop the system prompt/persona rather than
failing loudly. The runner mitigates this with:

- **Rolling compaction** — once the running conversation crosses ~60% of
  `num_ctx`, older tool-call/result turns are collapsed into a one-line-per-action
  summary, keeping the system prompt, the original kickoff message, and the
  most recent turns verbatim.
- **`LLM_SLIM_PROMPT=1`** — drop the full CLI tool inventory from the system
  prompt for models that already know common pentest tool names.
- **Delegate early, delegate often** — each `delegate_agent` call starts a
  *brand-new* message history for that sub-agent, so prefer having
  OrchestratorAgent hand off narrow tasks (one scan, one exploit attempt)
  rather than one persona doing everything in a single long-lived loop. Pair
  this with a smaller `--max-iterations` per delegated agent for genuinely
  small (≤14B) models.

---

## Web Workbench (small-model-orchestrator)

A local .NET web UI for defining repeatable LLM jobs and running them one at
a time against a llama-server-hosted model, with an editable SQLite job
library, a serial run queue, and gated Bash tool calls. Launch it from the
CTF container instead of the interactive shell:

```bash
CTF_WEB_UI=1 ./run-ctf.sh ~/ctf/htb/editorial
# open http://127.0.0.1:5280 — set CTF_WEB_PORT to use a different port
```

Bash tool calls run as the container's `ctf` user; a job must have **Allow
Bash tool calls** checked for that to be enabled. See
[`small-model-orchestrator/README.md`](small-model-orchestrator/README.md)
for the full architecture, EF Core migrations, and running it standalone
with `dotnet run`.

---

## Building with Makefile

```bash
make -f Makefile.ctf build           # build image
make -f Makefile.ctf build-nocache   # force rebuild from scratch
make -f Makefile.ctf check           # verify tools are installed in image
make -f Makefile.ctf run             # run with cwd as workspace
make -f Makefile.ctf run WORKSPACE=~/ctf/htb/editorial
```
