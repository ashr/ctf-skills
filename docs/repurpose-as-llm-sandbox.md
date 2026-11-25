# Repurposing this harness as a general LLM sandbox

This repo is built around a CTF/pentest agent stack, but the part that
actually matters for *any* "let an LLM run shell commands somewhere
contained" use case has nothing to do with CTF: a non-root container with no
`sudo`, a root-run entrypoint that applies an egress allowlist before
handing off, and a refresh loop that keeps it current. That core is
reusable as-is. Everything else here — the 15GB of offensive tooling,
wordlists, agent personas, HTB integration — is CTF-specific and should be
stripped.

This doc walks through what to keep, what to drop, and how to wire your own
agent/runtime in.

## What to keep (verbatim, or near enough)

| File | Role |
|------|------|
| [`entrypoint.sh`](../entrypoint.sh) | Root-run `ENTRYPOINT`: applies the allowlist, starts the refresh loop, drops to a non-root user via `gosu`, `exec`s your real command. Copy as-is. |
| [`egress-control.sh`](../egress-control.sh) | Builds/applies the nftables OUTPUT allowlist. Copy as-is, then edit the two spots noted below. |
| The user-creation + no-sudo + `setcap` pattern in [`Dockerfile`](../Dockerfile) (search for `CTF_USER`, `setcap`, and the final `ENTRYPOINT`/`CMD` block) | The actual security property: no root escape at runtime, so the firewall this applies can't be bypassed with `sudo nft flush ruleset`. |
| `run-ctf.sh`'s `--cap-add NET_ADMIN`, the `docker run` shape, and the egress-lockdown env-var block | The launcher pattern — strip the CTF-specific flags (see below) and keep this skeleton. |

The important realization: **the egress control has nothing to do with
pentesting.** It's "root applies an nftables allowlist once, then gives up
root forever." That works identically whether the thing running in the
container is `nmap` or your own agent's tool-calling loop.

## What to strip

- All `apt`/`pip`/`go install`/`gem install` blocks for offensive tooling
  (nmap, sqlmap, hydra, impacket, pwntools, wordlists, etc.) — replace with
  whatever your agent's runtime actually needs (e.g. `python3` + your
  framework, or `node`, or nothing extra at all if your agent runs outside
  the container and only shells into it).
- `openvpn`, the `cap_net_raw`/`cap_net_bind_service` grants on `nmap`, the
  `/dev/net/tun` device, and the `net.ipv4.ip_unprivileged_port_start`
  sysctl — all VPN/low-port-relay specific. Drop unless your agent genuinely
  needs to bind privileged ports or run a VPN client.
- `cap_sys_time` on `/bin/date` (Kerberos clock-skew workaround) — drop
  unless you have the same problem.
- `ctf-context.yaml` / `Templates/ctf-context-template.yaml` and the
  `target.ip`/`vpn.iface` lookups in `egress-control.sh`'s `ctx_value()` —
  CTF-engagement-specific config. See below for what replaces it.
- `agents/`, `prompts/`, `htb_api.py`, `runner/`, `small-model-orchestrator/`
  — all CTF agent personas/orchestration. Keep `small-model-orchestrator/`
  only if you want its generic "job queue + gated Bash tool + llama-server"
  UI shell — but its prompt text (`JobRunWorker.cs`,
  `BashCommandExecutor.cs`) talks about CTF scope/flags and needs rewriting
  for your use case.
- `wordlists`, `certs/` (unless you have your own corporate CA to trust).

## Adapting `egress-control.sh`

Two spots to change, everything else is domain-agnostic:

1. **`BASELINE_HOSTS`** (near the top) — this is "hosts that stay reachable
   whenever the allowlist is on." It currently lists Anthropic/OpenAI/GitHub/
   HTB. Replace with whatever your agent's own infra is (its model API,
   your package registry, your telemetry endpoint — or leave it empty for a
   strictly target-only allowlist with zero implicit exceptions).
2. **`ctx_value()` / the `ctf-context.yaml` lookup in `collect_candidates()`**
   — this folds in a CTF engagement's declared target automatically. If you
   don't have an equivalent "already-declared scope" file, delete the
   `ctx_value ip`/`ctx_value iface` calls and just rely on the env var
   (rename `CTF_TARGETS` to whatever fits — `SANDBOX_TARGETS`, `ALLOWED_HOSTS`,
   whatever). If you *do* have some config file describing what this agent
   run is allowed to touch, point `ctx_value()`'s `grep`/`sed` at it the same
   way.

Everything else — IP/CIDR detection, DNS resolution with a per-run refresh,
the `ANTHROPIC_BASE_URL`/`OLLAMA_API_BASE`/`LlamaServer__BaseUrl`
auto-detection, the atomic `nft -f` apply, the "no targets configured = full
no-op" gate — is generic. Keep it, and add any other backend-URL env vars
your own agent uses to that same auto-detection loop so you don't have to
duplicate a host you've already configured elsewhere.

## Minimal Dockerfile skeleton

```dockerfile
FROM ubuntu:24.04   # or whatever base your agent needs

ARG AGENT_USER=agent
ARG AGENT_UID=1000
ARG AGENT_GID=1000

RUN apt-get update && apt-get install -y --no-install-recommends \
    nftables gosu \
    # + whatever your agent's runtime needs \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid "$AGENT_GID" "$AGENT_USER" && \
    useradd --uid "$AGENT_UID" --gid "$AGENT_GID" --create-home --shell /bin/bash "$AGENT_USER"
# No sudo installed, no sudoers entry. This is the whole point.

# ... install/COPY your agent's actual code here ...

COPY egress-control.sh /usr/local/sbin/egress-control.sh
COPY entrypoint.sh /usr/local/sbin/entrypoint.sh
RUN chmod +x /usr/local/sbin/egress-control.sh /usr/local/sbin/entrypoint.sh

ENTRYPOINT ["/usr/local/sbin/entrypoint.sh"]
CMD ["/bin/bash"]   # or your agent's own entry command
```

Note there's no final `USER` directive — the container must start as root so
`entrypoint.sh` can apply the firewall before it `exec gosu agent "$@"`s into
your real workload.

## Minimal launcher skeleton

Strip `run-ctf.sh` down to roughly:

```bash
docker run --rm -it \
    --cap-add NET_ADMIN \
    -e SANDBOX_TARGETS="$SANDBOX_TARGETS" \
    -v "$WORKSPACE:/workspace" \
    --pids-limit 512 \
    --memory 4g \
    --security-opt no-new-privileges \
    my-agent-sandbox
```

`NET_ADMIN` is the only capability `nft` actually needs — if you dropped
VPN/raw-socket/low-port requirements above, you don't need `NET_RAW`,
`SYS_TIME`, `/dev/net/tun`, or the low-port sysctl at all. Add
`--security-opt no-new-privileges` too: with no VPN/nmap-style `setcap`
binaries left to worry about, there's no reason for this container to ever
gain a new capability at runtime, and it closes off privilege-escalation
paths you haven't thought of. `--pids-limit`/`--memory` are generic
containment hygiene worth keeping regardless of what the agent does.

## What this does and doesn't give you

Carried over unchanged from the CTF version:

- **A real boundary, not best-effort** — as long as you don't reintroduce
  `sudo` or another root escape, the allowlist can't be flushed by the agent
  it constrains, because the agent never has `NET_ADMIN` itself (only root,
  briefly, at startup).
- **Fail-closed, auto-refreshing** — unresolvable/rotating hosts don't open
  things up; established connections survive a refresh tick; nothing is
  allowed by default unless you set the env var.

Still true, so don't oversell it to whoever you hand this to:

- This is **network egress control only**. It says nothing about what the
  agent can do to the filesystem inside `/workspace`, how much CPU/memory it
  burns (that's `--pids-limit`/`--memory`'s job), or whether the base image
  itself has some other escalation path you haven't audited. Treat it as one
  layer of containment, not the whole story.
- It protects against the agent *trying* to reach the wrong thing —
  accidental overreach, a tool phoning home, scope creep — not against a
  sufficiently motivated adversary with arbitrary code execution and time to
  find a kernel-level container escape. No single-host network filter is.

## Verifying your stripped-down version

Don't just trust the Dockerfile — build it and check both paths, the same
way this was verified here:

```bash
# default: no SANDBOX_TARGETS set — should be a complete no-op
docker run --rm my-agent-sandbox bash -c 'whoami; curl -sI https://example.com'

# locked down — allowed host succeeds, everything else times out (not RST)
docker run --rm --cap-add NET_ADMIN -e SANDBOX_TARGETS="example.com" my-agent-sandbox \
  bash -c 'curl -sI --max-time 5 https://example.com; curl -sI --max-time 5 https://neverssl.com'

# confirm the agent user genuinely cannot see or touch the ruleset
docker run --rm --cap-add NET_ADMIN -e SANDBOX_TARGETS="example.com" my-agent-sandbox \
  bash -c 'command -v sudo; nft list ruleset'
```

The last command should fail on both counts (`sudo` not found, `nft`
"Operation not permitted") — if either succeeds, something's wrong with the
user/capability setup and the allowlist is decorative.
