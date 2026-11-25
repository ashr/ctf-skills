# CTF Agent Definitions

Each subdirectory contains a `definition.md` that defines an agent's role,
responsibilities, tools, and workflow for CTF pentesting.

## Agent Roster

| Agent | Role |
|-------|------|
| OrchestratorAgent | Lead — VPN verify, phase management, delegation |
| HTBAgent | HTB platform integration — select/start machine, VPN config, flag submit |
| ReconAgent | Nmap, web enum, service fingerprinting |
| InfraAgent | CVE identification, exploit path recommendations |
| WebTestAgent | Web vulnerability testing (SQLi, LFI, SSRF, SSTI, etc.) |
| APIAgent | REST/GraphQL API security testing |
| JSLibAgent | Client-side JS analysis, secret scanning |
| ExploitAgent | CVE exploitation, hash cracking, credential attacks |
| PrivEscAgent | Linux/Windows privilege escalation |
| FlagAgent | Flag capture and recording |
| ValidatorAgent | PoC verification, attack chain writeup |
| PWNAgent | Binary exploitation (BOF, ROP, format strings) |
| CryptoAgent | Crypto challenge solving |
| ForensicsAgent | Forensics and steganography |
| LoggerAgent | Exploitation evidence recorder — logs payloads/creds/flags for writeup |

## Shared Files

| File | Purpose |
|------|---------|
| shared/constraints.md | Rules all agents must follow |
| shared/output-schemas.md | YAML schemas for inter-agent data files |
| shared/tooling.md | Full tool inventory with install commands |

## Attack Flow

```
OrchestratorAgent
  |
  +-- ReconAgent ─────────────────────────────────── loot/recon_results.yaml
  |
  +-- InfraAgent (CVE analysis) ─────────────────── loot/infra_findings.yaml
  |
  +-- [WebTestAgent | APIAgent | JSLibAgent] ─────── loot/web/api/jslib_findings.yaml
  |
  +-- [ExploitAgent | PWNAgent | CryptoAgent | ForensicsAgent]
  |       ↓
  |   loot/foothold.yaml  (first shell)
  |
  +-- PrivEscAgent ───────────────────────────────── loot/privesc.yaml
  |
  +-- FlagAgent ──────────────────────────────────── loot/flags.yaml
  |
  +-- ValidatorAgent ─────────────────────────────── loot/attack_chain.md
```
