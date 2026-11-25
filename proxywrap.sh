#!/usr/bin/env bash
set -euo pipefail

# Run a command through proxychains when SOCKS proxy mode is enabled.
# Usage:
#   ./proxywrap.sh nmap -Pn target.internal

if [[ $# -eq 0 ]]; then
  echo "usage: $0 <command> [args...]" >&2
  exit 1
fi

PROXY_CONF="${PROXYCHAINS_CONF_FILE:-/workspace/.proxychains-agent.conf}"

if [[ -f "$PROXY_CONF" ]]; then
  exec proxychains4 -f "$PROXY_CONF" "$@"
fi

exec "$@"
