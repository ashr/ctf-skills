#!/usr/bin/env bash
# egress-control.sh — build/apply an nftables OUTPUT allowlist scoping the
# container's own egress to CTF_TARGETS (+ the ctf-context.yaml target +
# whatever LLM backend host is configured + a small built-in tool-infra
# baseline). Root-run, invoked by entrypoint.sh before it drops to ctf.
#
# Usage:
#   egress-control.sh --apply-once   # single synchronous apply, for startup
#   egress-control.sh --watch        # loop forever, re-apply every ~60s
#
# No-ops cleanly (removes any existing table, touches nothing further) when
# there is nothing to allow-list at all — i.e. CTF_TARGETS is unset and
# ctf-context.yaml has no target.ip. This is a best-effort scope guard
# against accidental overreach; see README "Egress Control" for what it
# does and does not guarantee.

set -u

TABLE="egress_filter"
REFRESH_SECONDS="${EGRESS_REFRESH_SECONDS:-60}"
CTX_FILE="/workspace/ctf-context.yaml"
NFT_SCRIPT="/tmp/.egress-filter.nft"

log() { echo "[egress-control] $*"; }

# Kept reachable whenever CTF_TARGETS locks the container down. Deliberately
# small and explicit — add anything else you rely on to CTF_TARGETS yourself.
BASELINE_HOSTS=(
    api.anthropic.com
    api.openai.com
    github.com
    api.github.com
    api.githubcopilot.com
    www.hackthebox.com
)

is_ipv4_or_cidr() {
    [[ "$1" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}(/[0-9]{1,2})?$ ]]
}

is_ipv6_or_cidr() {
    [[ "$1" == *:* ]]
}

url_host() {
    sed -E 's#^[A-Za-z][A-Za-z0-9+.-]*://##; s#[:/].*$##' <<<"$1"
}

ctx_value() {
    # $1=yaml key (e.g. "ip" under target:, "iface" under vpn:)
    [[ -f "$CTX_FILE" ]] || return 0
    sed -n "s/^[[:space:]]*${1}:[[:space:]]*\"\\{0,1\\}\\([^\"[:space:]]*\\)\"\\{0,1\\}.*/\\1/p" "$CTX_FILE" | head -1
}

collect_candidates() {
    local -a candidates=()
    local t

    if [[ -n "${CTF_TARGETS:-}" ]]; then
        local IFS=,
        for t in $CTF_TARGETS; do
            t="$(xargs <<<"$t")"
            [[ -n "$t" ]] && candidates+=("$t")
        done
    fi

    local ctx_ip
    ctx_ip="$(ctx_value ip)"
    [[ -n "$ctx_ip" ]] && candidates+=("$ctx_ip")

    if [[ ${#candidates[@]} -gt 0 ]]; then
        local var val host
        for var in ANTHROPIC_BASE_URL OLLAMA_API_BASE LlamaServer__BaseUrl; do
            val="${!var:-}"
            [[ -z "$val" ]] && continue
            host="$(url_host "$val")"
            [[ -n "$host" ]] && candidates+=("$host")
        done
        candidates+=("${BASELINE_HOSTS[@]}")
    fi

    if [[ ${#candidates[@]} -gt 0 ]]; then
        printf '%s\n' "${candidates[@]}"
    fi
}

vpn_iface() {
    local iface
    iface="$(ctx_value iface)"
    echo "${iface:-tun0}"
}

resolver_ips() {
    awk '/^[[:space:]]*nameserver/{print $2}' /etc/resolv.conf 2>/dev/null
}

join_by_comma() {
    local IFS=,
    echo "$*"
}

remove_table() {
    nft list table inet "$TABLE" >/dev/null 2>&1 && nft delete table inet "$TABLE" 2>/dev/null
    return 0
}

apply_ruleset() {
    local -a candidates
    mapfile -t candidates < <(collect_candidates)

    if [[ ${#candidates[@]} -eq 0 ]]; then
        remove_table
        return 0
    fi

    local -a v4=() v6=()
    local cand ip resolved
    for cand in "${candidates[@]}"; do
        if is_ipv4_or_cidr "$cand"; then
            v4+=("$cand")
            continue
        fi
        if is_ipv6_or_cidr "$cand"; then
            v6+=("$cand")
            continue
        fi

        resolved=0
        while IFS= read -r ip; do
            [[ -z "$ip" ]] && continue
            v4+=("$ip")
            resolved=1
        done < <(dig +time=2 +tries=1 +short A "$cand" 2>/dev/null | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$')
        while IFS= read -r ip; do
            [[ -z "$ip" ]] && continue
            v6+=("$ip")
            resolved=1
        done < <(dig +time=2 +tries=1 +short AAAA "$cand" 2>/dev/null | grep -E '^[0-9a-fA-F:]+$')

        if [[ "$resolved" -eq 0 ]]; then
            log "WARNING: could not resolve '$cand' — skipping for now (retried on next refresh)"
        fi
    done

    local -a resolver4=() resolver6=()
    while IFS= read -r ip; do
        [[ -z "$ip" ]] && continue
        if [[ "$ip" == *:* ]]; then resolver6+=("$ip"); else resolver4+=("$ip"); fi
    done < <(resolver_ips)

    local iface v4_set v6_set r4_set r6_set
    iface="$(vpn_iface)"
    v4_set="$(join_by_comma "${v4[@]:-}")"
    v6_set="$(join_by_comma "${v6[@]:-}")"
    r4_set="$(join_by_comma "${resolver4[@]:-}")"
    r6_set="$(join_by_comma "${resolver6[@]:-}")"

    {
        echo "add table inet $TABLE"
        echo "flush table inet $TABLE"
        echo "add chain inet $TABLE output { type filter hook output priority 0; policy drop; }"
        echo "add set inet $TABLE allowed_dst4 { type ipv4_addr; flags interval; }"
        echo "add set inet $TABLE allowed_dst6 { type ipv6_addr; flags interval; }"
        [[ -n "$v4_set" ]] && echo "add element inet $TABLE allowed_dst4 { $v4_set }"
        [[ -n "$v6_set" ]] && echo "add element inet $TABLE allowed_dst6 { $v6_set }"
        echo "add rule inet $TABLE output oifname \"lo\" accept"
        echo "add rule inet $TABLE output oifname \"$iface\" accept"
        echo "add rule inet $TABLE output ct state established,related accept"
        [[ -n "$r4_set" ]] && echo "add rule inet $TABLE output ip daddr { $r4_set } udp dport 53 accept"
        [[ -n "$r4_set" ]] && echo "add rule inet $TABLE output ip daddr { $r4_set } tcp dport 53 accept"
        [[ -n "$r6_set" ]] && echo "add rule inet $TABLE output ip6 daddr { $r6_set } udp dport 53 accept"
        [[ -n "$r6_set" ]] && echo "add rule inet $TABLE output ip6 daddr { $r6_set } tcp dport 53 accept"
        echo "add rule inet $TABLE output ip daddr @allowed_dst4 accept"
        echo "add rule inet $TABLE output ip6 daddr @allowed_dst6 accept"
        echo "add rule inet $TABLE output counter drop"
    } > "$NFT_SCRIPT"

    if nft -f "$NFT_SCRIPT" 2>/tmp/.egress-filter.err; then
        log "applied: ${#candidates[@]} target(s) -> $(( ${#v4[@]} + ${#v6[@]} )) IP(s), VPN iface=$iface"
    else
        log "WARNING: failed to apply egress rules (missing NET_ADMIN?) — continuing WITHOUT egress lockdown"
        sed 's/^/[egress-control]   /' /tmp/.egress-filter.err
        remove_table
    fi
}

case "${1:-}" in
    --apply-once)
        apply_ruleset
        ;;
    --watch)
        while true; do
            sleep "$REFRESH_SECONDS"
            apply_ruleset
        done
        ;;
    *)
        echo "usage: $0 --apply-once|--watch" >&2
        exit 1
        ;;
esac
