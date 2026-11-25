#!/usr/bin/env python3
"""
htb_api.py — Hack The Box API v4 helper for CTF agent stack.

Usage:
    python3 htb_api.py machines [--os linux|windows] [--diff easy|medium|hard|insane]
    python3 htb_api.py start <machine_id>
    python3 htb_api.py stop
    python3 htb_api.py status
    python3 htb_api.py ovpn [--server 1] [--out /workspace/htb.ovpn]
    python3 htb_api.py submit --flag HTB{...} --id <machine_id> --type user|root [--diff 50]
    python3 htb_api.py whoami

Requires:
    HTB_API_TOKEN environment variable (from HTB Account Settings → API Key)
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip install requests", file=sys.stderr)
    sys.exit(1)

try:
    import yaml
except ImportError:
    yaml = None

BASE_URL = "https://www.hackthebox.com/api/v4"


def get_token():
    token = os.environ.get("HTB_API_TOKEN", "").strip()
    if not token:
        print("ERROR: HTB_API_TOKEN environment variable not set.", file=sys.stderr)
        print("Get your token at: https://app.hackthebox.com/profile/settings", file=sys.stderr)
        sys.exit(1)
    return token


def headers():
    return {
        "Authorization": f"Bearer {get_token()}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def api_get(path, params=None):
    r = requests.get(f"{BASE_URL}{path}", headers=headers(), params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def api_post(path, data=None):
    r = requests.post(f"{BASE_URL}{path}", headers=headers(), json=data or {}, timeout=30)
    r.raise_for_status()
    return r.json()


def cmd_whoami():
    data = api_get("/user/info")
    u = data.get("info", data)
    print(f"Logged in as: {u.get('name', '?')} (#{u.get('id', '?')})")
    print(f"Rank: {u.get('rank', '?')}  Points: {u.get('points', '?')}")
    return 0


def cmd_machines(os_filter=None, diff_filter=None, show_owned=False):
    params = {}
    if os_filter:
        params["os"] = os_filter.capitalize()

    data = api_get("/machine/list", params=params)
    machines = data.get("data", [])

    if diff_filter:
        machines = [m for m in machines if m.get("difficulty", "").lower() == diff_filter.lower()]

    if not show_owned:
        machines = [m for m in machines if not (m.get("authUserInUserOwns") and m.get("authUserInRootOwns"))]

    if not machines:
        print("No matching machines found.")
        return 0

    # Sort by difficulty order
    diff_order = {"Easy": 0, "Medium": 1, "Hard": 2, "Insane": 3}
    machines.sort(key=lambda m: (diff_order.get(m.get("difficulty", ""), 99), m.get("name", "")))

    print(f"\n{'ID':>6}  {'Name':<20} {'OS':<10} {'Diff':<10} {'User':>5} {'Root':>5}  {'Points':>6}")
    print("-" * 70)
    for m in machines:
        user_owned = "✓" if m.get("authUserInUserOwns") else "✗"
        root_owned = "✓" if m.get("authUserInRootOwns") else "✗"
        print(f"{m['id']:>6}  {m['name']:<20} {m.get('os','?'):<10} {m.get('difficulty','?'):<10} "
              f"{user_owned:>5} {root_owned:>5}  {m.get('points',0):>6}")

    print(f"\nShowing {len(machines)} machine(s)")
    return 0


def cmd_start(machine_id):
    print(f"[+] Starting machine {machine_id}...")
    try:
        resp = api_post(f"/machine/play/{machine_id}")
        print(f"[+] {resp.get('message', 'Started')}")
    except requests.HTTPError as e:
        print(f"[-] Failed to start: {e.response.text}", file=sys.stderr)
        return 1

    # Poll for IP
    print("[+] Waiting for IP assignment", end="", flush=True)
    for _ in range(24):  # 120s max
        time.sleep(5)
        print(".", end="", flush=True)
        try:
            active = api_get("/machine/active")
            ip = active.get("info", {}).get("ip") or active.get("ip")
            if ip:
                print(f"\n[+] Machine is up: {ip}")
                return 0
        except Exception:
            pass

    print("\n[-] Timed out waiting for IP. Check: python3 htb_api.py status")
    return 1


def cmd_stop():
    print("[+] Stopping active machine...")
    try:
        resp = api_post("/machine/stop")
        print(f"[+] {resp.get('message', 'Stopped')}")
        return 0
    except requests.HTTPError as e:
        print(f"[-] {e.response.text}", file=sys.stderr)
        return 1


def cmd_status():
    try:
        data = api_get("/machine/active")
        info = data.get("info") or data
        if not info or not info.get("id"):
            print("No active machine.")
            return 0
        print(f"Active machine: {info.get('name', '?')} (#{info.get('id', '?')})")
        print(f"  IP:         {info.get('ip', 'not assigned yet')}")
        print(f"  OS:         {info.get('os', '?')}")
        print(f"  Difficulty: {info.get('difficulty', '?')}")
        return 0
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            print("No active machine.")
            return 0
        raise


def cmd_ovpn(server_id=1, out_path="/workspace/htb.ovpn"):
    token = get_token()
    print(f"[+] Downloading OVPN config (server {server_id})...")
    r = requests.get(
        f"{BASE_URL}/access/ovpnfile/{server_id}/0",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    r.raise_for_status()
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(r.content)
    print(f"[+] Saved to {out_path}")
    return 0


def cmd_submit(flag, machine_id, flag_type="user", difficulty=50):
    print(f"[+] Submitting {flag_type} flag for machine {machine_id}...")
    try:
        resp = api_post("/flag/own", {
            "id": int(machine_id),
            "flag": flag.strip(),
            "difficulty": int(difficulty),
        })
        msg = resp.get("message", str(resp))
        print(f"[+] {msg}")
        return 0
    except requests.HTTPError as e:
        print(f"[-] Submission failed: {e.response.text}", file=sys.stderr)
        return 1


def cmd_write_context(machine_id=None, out="/workspace/ctf-context.yaml"):
    """Fetch active machine info and write ctf-context.yaml."""
    if machine_id:
        data = api_get(f"/machine/info/{machine_id}")
        info = data.get("info", data)
    else:
        data = api_get("/machine/active")
        info = data.get("info", data)

    if not info or not info.get("id"):
        print("[-] No machine info available.", file=sys.stderr)
        return 1

    ctx = {
        "target": {
            "ip": info.get("ip", ""),
            "name": info.get("name", ""),
            "os": info.get("os", "unknown").lower(),
            "difficulty": info.get("difficulty", "unknown").lower(),
            "category": "fullpwn",
            "htb_id": info.get("id"),
        },
        "vpn": {
            "iface": "tun0",
            "ovpn_file": "/workspace/htb.ovpn",
        },
    }

    out_path = Path(out)
    if yaml:
        out_path.write_text(yaml.dump(ctx, default_flow_style=False))
    else:
        import json as _json
        out_path.write_text(_json.dumps(ctx, indent=2))

    print(f"[+] ctf-context.yaml written: {info.get('name')} @ {info.get('ip', 'IP pending')}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="HTB API v4 helper")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("whoami")

    p_machines = sub.add_parser("machines", help="List active machines")
    p_machines.add_argument("--os", help="Filter by OS (linux/windows)")
    p_machines.add_argument("--diff", help="Filter by difficulty (easy/medium/hard/insane)")
    p_machines.add_argument("--owned", action="store_true", help="Include already-owned machines")

    p_start = sub.add_parser("start", help="Start a machine")
    p_start.add_argument("machine_id", type=int)

    sub.add_parser("stop", help="Stop active machine")
    sub.add_parser("status", help="Show active machine status")

    p_ovpn = sub.add_parser("ovpn", help="Download OVPN config")
    p_ovpn.add_argument("--server", type=int, default=1, help="Server ID (1=EU Free, 2=US Free, 3=EU VIP, 4=US VIP)")
    p_ovpn.add_argument("--out", default="/workspace/htb.ovpn")

    p_submit = sub.add_parser("submit", help="Submit a flag")
    p_submit.add_argument("--flag", required=True)
    p_submit.add_argument("--id", dest="machine_id", required=True)
    p_submit.add_argument("--type", dest="flag_type", choices=["user", "root"], default="user")
    p_submit.add_argument("--diff", dest="difficulty", type=int, default=50, help="Self-rated difficulty 1-100")

    p_ctx = sub.add_parser("write-context", help="Write ctf-context.yaml from active/specified machine")
    p_ctx.add_argument("--id", dest="machine_id", type=int, default=None)
    p_ctx.add_argument("--out", default="/workspace/ctf-context.yaml")

    args = parser.parse_args()

    if args.cmd == "whoami":
        return cmd_whoami()
    elif args.cmd == "machines":
        return cmd_machines(os_filter=args.os, diff_filter=args.diff, show_owned=args.owned)
    elif args.cmd == "start":
        return cmd_start(args.machine_id)
    elif args.cmd == "stop":
        return cmd_stop()
    elif args.cmd == "status":
        return cmd_status()
    elif args.cmd == "ovpn":
        return cmd_ovpn(server_id=args.server, out_path=args.out)
    elif args.cmd == "submit":
        return cmd_submit(args.flag, args.machine_id, args.flag_type, args.difficulty)
    elif args.cmd == "write-context":
        return cmd_write_context(machine_id=args.machine_id, out=args.out)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
