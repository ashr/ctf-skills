# CTF Kickoff Prompt

Use this to start a CTF machine compromise via GitHub Copilot Chat.

```text
@OrchestratorAgent Start CTF engagement.

Inputs:
  CTF context: /workspace/ctf-context.yaml

Execution policy:
  - Use agents/OrchestratorAgent/definition.md as the workflow source of truth.
  - Use agents/shared/constraints.md and agents/shared/output-schemas.md.
  - All output goes to /workspace/loot/.
  - If HTB_API_TOKEN is set and ctf-context.yaml has no target IP, invoke HTBAgent
    to select and start a machine before proceeding (see agents/HTBAgent/definition.md).
  - Connect VPN automatically before any scanning:
      openvpn --config /workspace/htb.ovpn --daemon \
        --pull-filter ignore "route-ipv6" \
        --pull-filter ignore "ifconfig-ipv6" \
        --pull-filter ignore tun-ipv6
    Wait for tun0 to be up (ip addr show tun0) and target to respond to ping.
  - Follow the attack flow: Recon -> Exploit -> Foothold -> PrivEsc -> Flags.
  - Capture user.txt and root.txt to loot/flags.yaml.
  - Every confirmed exploit, credential, hash crack, or flag MUST be logged via
    LoggerAgent to loot/exploit_log.yaml (see agents/LoggerAgent/definition.md).
  - After capturing root flag, invoke HTBAgent to submit flags via HTB API.
  - Never expand scope beyond the single target IP in ctf-context.yaml.

Begin.
```

```
@OrchestratorAgent Start CTF engagement.

Inputs:
  CTF context: /workspace/ctf-context.yaml

Execution policy:
  - Use agents/OrchestratorAgent/definition.md as the workflow source of truth.
  - Use agents/shared/constraints.md and agents/shared/output-schemas.md.
  - All output goes to /workspace/loot/.
  - Connect VPN automatically before any scanning:
      openvpn --config /workspace/htb.ovpn --daemon \
        --pull-filter ignore "route-ipv6" \
        --pull-filter ignore "ifconfig-ipv6" \
        --pull-filter ignore tun-ipv6
    Wait for tun0 to be up (ip addr show tun0) and target to respond to ping.
  - Follow the attack flow: Recon -> Exploit -> Foothold -> PrivEsc -> Flags.
  - Capture user.txt and root.txt to loot/flags.yaml.
  - Every confirmed exploit, credential, hash crack, or flag MUST be logged via
    LoggerAgent to loot/exploit_log.yaml (see agents/LoggerAgent/definition.md).
  - After capturing root flag, sing a joyous song and celebrate your victory by creating a folder with the     machine name, a copy of its ctf-context.yaml, and any relevant loot.

Begin.
```

##With the python runner:
```
python3 -m runner.main --task "$(cat <<'EOF'
Start CTF engagement.
Inputs:
  CTF context: /workspace/ctf-context.yaml
Execution policy:
  - Use agents/OrchestratorAgent/definition.md as the workflow source of truth.
  - Connect VPN: openvpn --config /workspace/htb.ovpn --daemon --pull-filter ignore route-ipv6 --pull-filter ignore ifconfig-ipv6 --pull-filter ignore tun-ipv6
  - Follow the attack flow: Recon -> Exploit -> Foothold -> PrivEsc -> Flags.
  - Log every exploit/credential/flag via LoggerAgent to loot/exploit_log.yaml.
Begin.
EOF
)"
```

## Setup

### 1. Build the image (once)

```bash
make -f Makefile.ctf build
```

### 2. Launch your CTF session

```bash
# From your project dir (auto-seeds ctf-context.yaml from template)
./run-ctf.sh

# Or specify a dir
./run-ctf.sh ~/ctf/htb/editorial

# With credentials
GITHUB_TOKEN=ghp_xxx SHODAN_API_KEY=yyy CTF_NETWORK=host ./run-ctf.sh ~/ctf/htb/editorial
```

### 3. ctf-context.yaml template

```yaml
target:
  ip: "10.10.11.42"
  name: "MachineName"
  os: "linux"               # linux | windows | unknown
  difficulty: "easy"        # easy | medium | hard | insane
  category: "fullpwn"       # fullpwn | web | pwn | crypto | forensics | misc

vpn:
  iface: "tun0"
  ovpn_file: "/workspace/htb.ovpn"   # drop htb.ovpn in your project dir; omit if already connected
```
