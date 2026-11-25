# llm-harness

A minimal, egress-controlled, non-root container for giving an LLM agent
shell access somewhere contained. No offensive tooling, no agent personas —
just the cage: a user with no `sudo`, and a root-run entrypoint that applies
an nftables egress allowlist before dropping privileges to that user.

This was extracted from a larger CTF/pentest agent stack — the containment
mechanism has nothing to do with CTF, so it's packaged here on its own.

## What's in here

| File | Role |
|------|------|
| `Dockerfile` | Base image, package install, non-root user creation, cert trust, entrypoint wiring |
| `entrypoint.sh` | Root-run `ENTRYPOINT`. Applies the firewall, starts its refresh loop, then drops to the non-root user and hands off to your real command |
| `egress-control.sh` | Builds/applies the nftables allowlist from `SANDBOX_TARGETS` |
| `Makefile.llm-harness` | `make build` / `make run` convenience wrapper — not load-bearing, just saves typing `docker` flags |
| `certs/` | Drop your corporate CA (`.crt`) here if you're behind a TLS-inspecting proxy. Empty is fine otherwise |

There is **no agent or runtime included**. This is deliberately just the
box — add your own agent's code/dependencies to the Dockerfile where it says
`# ─── Add your own agent/runtime here ───`, or mount your agent's code into
`/workspace` and run it from there.

## Quick start

```bash
# Build
docker build -t llm-harness .          # or: make -f Makefile.llm-harness build

# Run, unrestricted egress (default)
docker run --rm -it --cap-add NET_ADMIN -v $(pwd):/workspace llm-harness

# Run, locked down to an explicit allowlist
docker run --rm -it --cap-add NET_ADMIN --security-opt no-new-privileges \
  -e SANDBOX_TARGETS="api.example.com,10.0.0.5" \
  -v $(pwd):/workspace llm-harness
```

Or via the Makefile:

```bash
make -f Makefile.llm-harness build
make -f Makefile.llm-harness run
make -f Makefile.llm-harness run SANDBOX_TARGETS=api.example.com WORKSPACE=~/my-project
```

## How the containment actually works

1. The container **starts as root** (there's no final `USER` line in the
   Dockerfile) so `entrypoint.sh` can set up the firewall, which needs
   `CAP_NET_ADMIN`.
2. `entrypoint.sh` calls `egress-control.sh --apply-once`, backgrounds
   `egress-control.sh --watch` (re-applies every ~60s so DNS-rotated IPs
   don't fall out of the allowlist mid-run), then `exec gosu agent "$@"` —
   this permanently hands off to the non-root `agent` user and never comes
   back to root.
3. `agent` has **no `sudo`**, and nothing else in the image is
   setuid/setcap'd to give it root back. That's what makes the firewall
   actually hold: the agent process can't `sudo nft flush ruleset` its way
   out, because there's no `sudo` and it never has `CAP_NET_ADMIN` itself.

If `SANDBOX_TARGETS` is unset, `egress-control.sh` is a complete no-op — no
table is created, egress is unrestricted, nothing about default behavior
changes.

## `SANDBOX_TARGETS`

Comma-separated hostnames, IPs, or CIDRs — the only things the container
can reach once this is set (besides what's listed below). Hostnames are
re-resolved every refresh cycle, so CDN/round-robin IP rotation doesn't cut
off a target mid-run; an in-flight connection also survives a refresh even
if the target's IP has since rotated away (established connections are
allowed regardless of the current allowlist).

```bash
SANDBOX_TARGETS="api.example.com,192.168.1.0/24"
```

**Also always allowed, automatically, whenever `SANDBOX_TARGETS` is set:**

- Loopback, and established/related return traffic
- DNS to whatever resolver the container is actually configured with
- The host of `ANTHROPIC_BASE_URL`, `OLLAMA_API_BASE`, or
  `LlamaServer__BaseUrl`, if any of those env vars are set for this run (so
  you don't have to duplicate a backend host you've already configured) —
  add your own agent's backend env var name to the list in
  `egress-control.sh` if it uses something else
- A small built-in baseline: `api.anthropic.com`, `api.openai.com`,
  `github.com`, `api.github.com`, `api.githubcopilot.com`. Edit
  `BASELINE_HOSTS` at the top of `egress-control.sh` to match whatever your
  agent actually needs — set it to an empty array for a strictly
  target-only allowlist with zero implicit exceptions.

Check what's actually applied from inside a running container:

```bash
docker exec <container> nft list table inet egress_filter
docker exec <container> cat /var/log/egress-control.log   # refresh-loop history
```

(Both of those need to run as root — `docker exec` without `-u` defaults to
root here since there's no final `USER` in the image; `docker exec -u agent
...` will correctly fail to run either, which is the point.)

## What this does and doesn't give you

- **A real boundary, not best-effort** — as long as you don't add `sudo`
  or some other root escape back in, the agent genuinely cannot see or
  modify the firewall rules constraining it.
- **Network egress control only.** This says nothing about filesystem
  access inside `/workspace`, CPU/memory usage (`--pids-limit`/`--memory`
  are your job at `docker run` time), or some other escalation path in
  whatever you add to the base image. Treat it as one layer, not the whole
  story.
- **Guards against overreach, not a motivated attacker.** This stops an
  agent that's trying to reach the wrong thing by mistake — scope creep, a
  tool phoning home somewhere it shouldn't. It is not a claim that a
  sufficiently motivated adversary with arbitrary code execution and time
  to find a kernel-level container escape can't get out. No single-host
  network filter is that.

## Verifying a change you made

If you edit the Dockerfile (add your agent's runtime, change packages,
etc.), re-run this sanity check — don't just trust it:

```bash
docker build -t llm-harness .

# default: no-op
docker run --rm llm-harness bash -c 'whoami; command -v sudo || echo no-sudo'

# locked down: allow/deny + no-bypass
docker run -d --rm --cap-add NET_ADMIN -e SANDBOX_TARGETS=example.com --name h llm-harness sleep 60
docker exec -u agent h curl -sI --max-time 5 -o /dev/null -w "%{http_code}\n" https://example.com   # expect 200
docker exec -u agent h curl -sI --max-time 5 -o /dev/null -w "%{http_code}\n" https://neverssl.com  # expect 000 (timeout, not a reset)
docker exec -u agent h bash -c 'command -v sudo; nft list ruleset'                                  # expect both to fail
docker rm -f h
```

If either of the last two bypass checks succeeds, something in your
Dockerfile edits broke the no-root guarantee — the firewall is only real
because the agent user can never touch it.
