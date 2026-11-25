# Shared Agent Constraints

> All CTF agents MUST adhere to these constraints. No agent definition should duplicate these rules.

---

## CTF Context

- At the start of every phase, agents must load `/workspace/ctf-context.yaml`.
- This file contains the target IP, machine name, OS hint, difficulty, and VPN configuration.
- All output files go to `loot/` at the workspace root.

## Security & Credentials

- **Never** hardcode credentials in agent definitions or output files.
- Captured credentials, hashes, and tokens go exclusively into `loot/loot.yaml`.
- Mask sensitive values in logs (e.g. `NTLM: aad3...REDACTED`).

## Scope

- Only test the single target IP specified in `ctf-context.yaml`.
- Do not probe other HTB machines, HTB infrastructure, or any host outside the `/10.10.0.0/8` or `/10.129.0.0/16` range.
- Do not attack HTB platform systems (10.10.10.2, resolvers, etc.).
- If a discovered host is outside scope, record it and **do not test it**.
- This is policy, not enforcement — if the operator set `CTF_TARGETS` when
  launching the container (see root README "Egress Control"), out-of-scope
  traffic is also dropped at the network level as a backstop.

## Output Format

- All inter-agent data must use schemas defined in [`output-schemas.md`](output-schemas.md).
- Write all output to `/workspace/loot/` using **absolute paths**. Never use relative `loot/` paths — the working directory in the container may not always be `/workspace`.
- Use YAML for structured data, Markdown for human-readable notes.

## Flag Format

- HTB flags follow the format `HTB{...}` (case-sensitive).
- Other CTF platforms may use different formats — record raw flag value regardless.
- As soon as a flag is found, write it immediately to `loot/flags.yaml`.

## Severity Classification

Simple 4-tier scale: `Critical` (RCE/root), `High` (LFI/SSRF/SQLi with impact), `Medium` (info disclosure, auth bypass), `Low` (minor misconfig).

## Error Handling

- If a tool fails or is unavailable, log the error and try an alternative.
- Do not retry more than 3 times on transient failures.
- Mark failed checks as `status: failed` with the actual error output.

## Execution Completeness

- Do not defer attack paths to a "later pass" without documenting the blocker.
- A test may be marked `blocked` only with:
  - exact blocker category (`tool_missing`, `target_unreachable`, `creds_needed`, `binary_not_exploitable`)
  - command attempted and error observed
  - retry count
  - specific next action needed

## Exploit Logging (mandatory)

Every agent MUST invoke LoggerAgent immediately upon any confirmed exploit, credential capture,
hash crack, or flag find. Append to `loot/exploit_log.yaml` using the log_exploit() helper
defined in `agents/LoggerAgent/definition.md`. Save full response/output to `loot/evidence/`.

**Logging is not optional. Skipping is a defect.**

## Communication

- Log key actions to stdout for operator visibility:
  ```
  [PHASE]  Agent: action — result
  ```
- Critical findings (shell access, flag captured) must be surfaced immediately.
- No Telegram, no Jira, no Confluence. All comms are local stdout + `loot/` files.
