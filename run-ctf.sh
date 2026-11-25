#!/usr/bin/env bash
set -euo pipefail
# ══════════════════════════════════════════════════════════════════════════════
# run-ctf.sh — Launch the CTF agent container
# ══════════════════════════════════════════════════════════════════════════════
#
# Usage:
#   ./run-ctf.sh                        # use cwd as workspace, interactive bash
#   ./run-ctf.sh /path/to/ctf-dir       # use specific directory as workspace
#   CTF_WEB_UI=1 ./run-ctf.sh /path/to/ctf-dir  # launch local job UI instead
#
# Environment variables (optional — passed into container if set):
#   GITHUB_TOKEN                        — gh copilot CLI auth
#   SHODAN_API_KEY                      — ReconAgent / InfraAgent
#   ANTHROPIC_API_KEY                   — Claude Code CLI, default Anthropic API auth
#   ANTHROPIC_BASE_URL                  — Claude Code CLI, point at a router/gateway or local llama-server
#   ANTHROPIC_AUTH_TOKEN                — Claude Code CLI, auth token/key for ANTHROPIC_BASE_URL
#   ANTHROPIC_MODEL                     — Claude Code CLI, model id/alias as the backend knows it
#   CLAUDE_CODE_MAX_OUTPUT_TOKENS       — Claude Code CLI, cap output tokens per turn (lower for small local models)
#   OPENAI_API_KEY                      — OpenAI API (future)
#   HTB_API_TOKEN                       — HTBAgent: machine select/start, VPN config, flag submit
#   HTB_AUTO_SELECT / HTB_MACHINE_ID    — HTBAgent: pick a machine automatically or by ID
#   CTF_NETWORK                         — Docker network mode: bridge (default) | host
#                                         Use host to route VPN traffic without NAT
#   CTF_TARGETS                         — comma-separated hostnames/IPs/CIDRs to lock
#                                         egress down to (+ ctf-context.yaml's target.ip +
#                                         LLM backend host + a small tool-infra baseline).
#                                         Unset = unrestricted egress (default). See README
#                                         "Egress Control" — best-effort scope guard, not a
#                                         hard security boundary.
#   CTF_WEB_UI=1                        — launch the .NET workbench at http://127.0.0.1:5280
#   CTF_WEB_PORT                         — override local UI port (default: 5280)
#   LlamaServer__BaseUrl                — llama-server OpenAI API base URL
#
# VPN:
#   Place your .ovpn file at <workspace>/htb.ovpn and set vpn.ovpn_file in
#   ctf-context.yaml — the container will connect automatically.
#   Requires --cap-add NET_ADMIN + /dev/net/tun (handled below).
#
# On first run in a new directory, ctf-context.yaml is seeded from the
# template so you can fill in the target IP and machine details.
# ══════════════════════════════════════════════════════════════════════════════

#LLM_CONTEXT_WINDOW=65536 LLM_MODEL=gemma4:12b OLLAMA_API_BASE=http://192.168.101.127:11434 python3 -m runner.main


IMAGE="ctf-agents"
CONTAINER_USER="ctf"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NETWORK_MODE="${CTF_NETWORK:-bridge}"
CTF_WEB_UI="${CTF_WEB_UI:-0}"
CTF_WEB_PORT="${CTF_WEB_PORT:-5280}"
CTF_TARGETS="${CTF_TARGETS:-}"

# ─── Workspace directory ──────────────────────────────────────────────────────

WORKSPACE="${1:-$(pwd)}"
WORKSPACE="$(realpath "$WORKSPACE")"
shift 2>/dev/null || true

if [[ ! -d "$WORKSPACE" ]]; then
    echo "error: not a directory: $WORKSPACE" >&2
    exit 1
fi

echo "[+] Workspace: $WORKSPACE"

# ─── Seed ctf-context.yaml on first run ──────────────────────────────────────

CTF_CONTEXT="$WORKSPACE/ctf-context.yaml"
CTF_TEMPLATE="$SCRIPT_DIR/Templates/ctf-context-template.yaml"

if [[ ! -f "$CTF_CONTEXT" && -f "$CTF_TEMPLATE" ]]; then
    cp "$CTF_TEMPLATE" "$CTF_CONTEXT"
    echo "[+] Seeded ctf-context.yaml from template — fill in target IP before starting"
fi

if [[ ! -f "$CTF_CONTEXT" ]]; then
    echo "[!] WARNING: ctf-context.yaml not found at $CTF_CONTEXT"
    echo "    Create it manually or copy Templates/ctf-context-template.yaml"
fi

# ─── Loot directory ──────────────────────────────────────────────────────────

mkdir -p "$WORKSPACE/loot"
mkdir -p "$WORKSPACE/.ctf-agent-home"

# ─── Network flags ───────────────────────────────────────────────────────────

NETWORK_FLAGS=()
SYSCTL_FLAGS=()
if [[ "$NETWORK_MODE" == "host" ]]; then
    NETWORK_FLAGS+=(--network host)
    echo "[+] Network mode: host (VPN traffic routes directly)"
    # --sysctl is not allowed in host network mode (shares host namespace)
    # Use --pull-filter ignore in openvpn command to suppress IPv6 push options instead
elif [[ "$NETWORK_MODE" == "bridge" ]]; then
    NETWORK_FLAGS+=(--add-host=host.docker.internal:host-gateway)
    # Zscaler intercepts DNS on zcctun0 and returns CGNAT IPs (100.64.x.x) for
    # internal hostnames. Docker's generated resolv.conf puts the LAN router
    # first, which returns NXDOMAIN — Zscaler DNS (100.64.0.2) is never reached.
    # Force bridge containers to use Zscaler's DNS directly.
    NETWORK_FLAGS+=(--dns 100.64.0.2)
    # Disable IPv6 inside bridge container so openvpn doesn't abort on IPv6 push options.
    # Only apply if /proc/sys/net/ipv6 exists — if IPv6 is fully disabled at the kernel
    # level (ipv6.disable=1 boot param or module blacklist) the path won't exist and
    # Docker will error trying to set these sysctls.
    if [[ -d /proc/sys/net/ipv6 ]]; then
        SYSCTL_FLAGS+=(--sysctl net.ipv6.conf.all.disable_ipv6=1)
        SYSCTL_FLAGS+=(--sysctl net.ipv6.conf.default.disable_ipv6=1)
    else
        echo "[+] IPv6 disabled at kernel level — skipping IPv6 sysctls"
    fi
    # Let ctf (non-root, no sudo) bind privileged ports directly — needed for
    # SMB/NTLM relay tooling (ntlmrelayx.py, smbserver.py: :445 primarily,
    # also :80/:443/:389 depending on attack). Pinned explicitly rather than
    # relying on whatever the host's own default happens to be.
    SYSCTL_FLAGS+=(--sysctl net.ipv4.ip_unprivileged_port_start=0)
    echo "[+] Network mode: bridge"
else
    echo "error: unsupported CTF_NETWORK='$NETWORK_MODE' (expected: bridge or host)" >&2
    exit 1
fi

# ─── Credential passthrough ───────────────────────────────────────────────────

ENV_FLAGS=()

declare -a PASSTHROUGH_VARS=(
    GITHUB_TOKEN
    GH_TOKEN
    SHODAN_API_KEY
    ANTHROPIC_API_KEY
    ANTHROPIC_BASE_URL
    ANTHROPIC_AUTH_TOKEN
    ANTHROPIC_MODEL
    CLAUDE_CODE_MAX_OUTPUT_TOKENS
    OPENAI_API_KEY
    HTB_API_TOKEN
    HTB_EMAIL
    HTB_PASSWORD
    HTB_AUTO_SELECT
    HTB_MACHINE_ID
    OLLAMA_API_BASE
    OLLAMA_API_KEY
    LLM_MODEL
    LlamaServer__BaseUrl
    LlamaServer__ApiKey
    HTTP_PROXY
    HTTPS_PROXY
    NO_PROXY
    http_proxy
    https_proxy
    no_proxy
)

for var in "${PASSTHROUGH_VARS[@]}"; do
    if [[ -n "${!var:-}" ]]; then
        ENV_FLAGS+=(-e "$var=${!var}")
        echo "[+] Passing env: $var"
    fi
done

# ─── Egress lockdown ───────────────────────────────────────────────────────────

EGRESS_ENV_FLAGS=()
if [[ -n "$CTF_TARGETS" ]]; then
    EGRESS_ENV_FLAGS+=(-e "CTF_TARGETS=$CTF_TARGETS")
    echo "[+] Egress lockdown: restricting outbound traffic to: $CTF_TARGETS"
    echo "    (+ ctf-context.yaml's target.ip, the configured LLM backend host,"
    echo "     and a small built-in tool-infra baseline — see README)"
    echo "    This is a best-effort scope guard, not a hard security boundary."
else
    echo "[+] Egress lockdown: disabled (CTF_TARGETS not set — unrestricted egress)"
fi

UI_FLAGS=()
UI_ENV_FLAGS=()
CONTAINER_COMMAND=("$@")
if [[ "$CTF_WEB_UI" == "1" ]]; then
    if ! [[ "$CTF_WEB_PORT" =~ ^[0-9]+$ ]] || (( CTF_WEB_PORT < 1 || CTF_WEB_PORT > 65535 )); then
        echo "error: CTF_WEB_PORT must be an integer from 1 to 65535" >&2
        exit 1
    fi
    if [[ "$NETWORK_MODE" == "host" ]]; then
        UI_BIND_ADDRESS="127.0.0.1"
    else
        UI_BIND_ADDRESS="0.0.0.0"
        UI_FLAGS+=(--publish "127.0.0.1:${CTF_WEB_PORT}:${CTF_WEB_PORT}")
    fi
    UI_ENV_FLAGS+=(
        -e "ASPNETCORE_URLS=http://${UI_BIND_ADDRESS}:${CTF_WEB_PORT}"
        -e Execution__EnableShellTools=true
        -e Execution__WorkingDirectory=/workspace
        -e Data__Directory=/workspace/loot/small-model-orchestrator
    )
    if [[ ${#CONTAINER_COMMAND[@]} -eq 0 ]]; then
        CONTAINER_COMMAND=(
            /opt/small-model-orchestrator/small-model-orchestrator
            --contentRoot /opt/small-model-orchestrator
        )
    fi
    echo "[+] Web UI:    http://127.0.0.1:${CTF_WEB_PORT} (Bash tools enabled inside this container)"
fi

# ─── VPN device ───────────────────────────────────────────────────────────────

TUN_FLAGS=()
if [[ -e /dev/net/tun ]]; then
    TUN_FLAGS+=(--device /dev/net/tun)
else
    echo "[!] WARNING: /dev/net/tun not found on host — openvpn inside container may fail"
    echo "    On Linux: sudo modprobe tun"
fi

# ─── Summary ─────────────────────────────────────────────────────────────────

echo ""
echo "  Image:     $IMAGE"
echo "  User:      $CONTAINER_USER (non-root)"
echo "  Workspace: $WORKSPACE → /workspace"
echo "  Loot:      $WORKSPACE/loot → /workspace/loot"
echo "  Config:    $WORKSPACE/.ctf-agent-home → /home/$CONTAINER_USER/.config"
echo "  VPN:       place htb.ovpn in workspace dir"
echo ""

# ─── Run ──────────────────────────────────────────────────────────────────────

exec docker run --rm -it \
    --cap-add NET_ADMIN \
    --cap-add NET_RAW \
    --cap-add SYS_TIME \
    "${TUN_FLAGS[@]+"${TUN_FLAGS[@]}"}" \
    "${NETWORK_FLAGS[@]}" \
    "${UI_FLAGS[@]}" \
    "${SYSCTL_FLAGS[@]+"${SYSCTL_FLAGS[@]}"}" \
    --pids-limit 2048 \
    --memory 8g \
    -w /workspace \
    -v "${WORKSPACE}:/workspace" \
    -v "${WORKSPACE}/.ctf-agent-home:/home/${CONTAINER_USER}/.config" \
    -v "${SCRIPT_DIR}/agents:/workspace/agents:ro" \
    -v "${SCRIPT_DIR}/prompts:/workspace/prompts:ro" \
    -v "${SCRIPT_DIR}/runner:/workspace/runner:ro" \
    -v "${SCRIPT_DIR}/Templates:/workspace/Templates:ro" \
    -v "${SCRIPT_DIR}/htb_api.py:/workspace/htb_api.py:ro" \
    -v "${SCRIPT_DIR}/proxywrap.sh:/workspace/proxywrap.sh:ro" \
    "${ENV_FLAGS[@]+"${ENV_FLAGS[@]}"}" \
    "${UI_ENV_FLAGS[@]+"${UI_ENV_FLAGS[@]}"}" \
    "${EGRESS_ENV_FLAGS[@]+"${EGRESS_ENV_FLAGS[@]}"}" \
    "$IMAGE" \
    "${CONTAINER_COMMAND[@]}"
