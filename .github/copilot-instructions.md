# CTF Agent Operating Rules

This repository runs a CTF-focused pentesting agent stack for Hack The Box and
similar platforms, connected via OpenVPN.

## Startup Behavior

- Route all CTF machine attacks through OrchestratorAgent.
- On kickoff, load `/workspace/ctf-context.yaml` first (target IP, OS, VPN config).
- Verify VPN connectivity before any scanning or exploitation.
- HTB machines are intentionally vulnerable sandboxes — no legal authorization gate needed.
- No Jira, Confluence, Telegram, or questionnaire references anywhere.

## Attack Flow

```
VPN Verify -> Recon -> Exploit Branch(es) -> Foothold -> PrivEsc -> Flags
```

## Mandatory Gates

- Recon MUST complete (loot/recon_results.yaml exists) before exploit phases.
- PrivEscAgent only runs after loot/foothold.yaml exists.
- FlagAgent runs after privilege escalation success.

## Scope

- Single target IP only. No lateral movement beyond the target unless explicitly instructed.
- Never probe 10.10.10.2 (HTB infra) or hosts outside the target machine.

## Agents

| Agent | Role |
|-------|------|
| OrchestratorAgent | Lead — VPN verify, phase management, delegation |
| HTBAgent | HTB platform — machine selection, start/stop, VPN download, flag submission |
| ReconAgent | Nmap, web enum, service fingerprinting |
| InfraAgent | CVE identification, exploit recommendations |
| WebTestAgent | Web vulnerability testing |
| APIAgent | REST/GraphQL API security testing |
| JSLibAgent | Client-side JS analysis, secret scanning |
| ExploitAgent | CVE exploitation, credential attacks, hash cracking |
| PrivEscAgent | Linux/Windows privilege escalation |
| FlagAgent | Flag capture and recording |
| LoggerAgent | Exploit evidence logger — payloads, responses, credentials, flags |
| ValidatorAgent | Finding verification and attack chain writeup |
| PWNAgent | Binary exploitation |
| CryptoAgent | Crypto challenge solving |
| ForensicsAgent | Forensics and steganography |

## Output

All outputs go to /workspace/loot/:
- loot/recon_results.yaml -- attack surface
- loot/foothold.yaml      -- initial access method
- loot/loot.yaml          -- credentials, hashes, keys
- loot/flags.yaml         -- captured flags (HTB{...})
- loot/attack_chain.md    -- writeup

## Source of Truth

- Orchestrator behavior: agents/OrchestratorAgent/definition.md
- Shared constraints: agents/shared/constraints.md
- Output schemas: agents/shared/output-schemas.md
- Tooling: agents/shared/tooling.md
