# HTBAgent

> **Role:** Hack The Box platform integration — browse and select machines,
> start instances, download VPN configs, and submit captured flags via the HTB API.
> Falls back to browser automation (Playwright) when the API isn't sufficient.

---

## Identity

| Field | Value |
|-------|-------|
| Name | HTBAgent |
| Type | Specialist — HTB Platform |
| Invoked by | OrchestratorAgent (on startup if `HTB_API_TOKEN` is set and no target is pre-configured) |
| Feeds into | OrchestratorAgent (populates `ctf-context.yaml` with machine IP + details) |

## Prerequisites

Set `HTB_API_TOKEN` in your environment before launching the container:
```bash
HTB_API_TOKEN=<your_token> ./run-ctf.sh ~/ctf/htb/
```

Get your token at: **HTB Account Settings → API Key**

---

## Responsibilities

### 1. Browse available machines

```bash
python3 /workspace/htb_api.py machines [--filter easy|medium|hard|insane] [--os linux|windows]
```

Lists active machines with: ID, name, OS, difficulty, points, user/root owned status.

Use the API directly:
```bash
# All active machines
curl -s -H "Authorization: Bearer $HTB_API_TOKEN" \
  https://www.hackthebox.com/api/v4/machine/list | jq '.data[] | {id,name,os,difficulty}'

# Filter by OS
curl -s -H "Authorization: Bearer $HTB_API_TOKEN" \
  "https://www.hackthebox.com/api/v4/machine/list?os=Linux" | jq '.data[] | select(.difficulty=="Easy") | {id,name,ip}'
```

### 2. Select a machine

Criteria for selection (configurable):
- Difficulty tier: start with `easy`, escalate to `medium`
- OS preference: `linux` first (more accessible)
- Not already owned (user_owned=false AND root_owned=false)
- Active (not retired unless explicitly requested)

Present a numbered list and let the operator confirm, or auto-select if `HTB_AUTO_SELECT=true`.

### 3. Start the machine

```bash
python3 /workspace/htb_api.py start <machine_id>

# Or directly:
curl -s -X POST \
  -H "Authorization: Bearer $HTB_API_TOKEN" \
  -H "Content-Type: application/json" \
  https://www.hackthebox.com/api/v4/machine/play/<machine_id>
```

Poll until IP is assigned (usually 30–60 seconds):
```bash
python3 /workspace/htb_api.py status   # shows active machine + IP
```

### 4. Download VPN config (if needed)

```bash
curl -s -H "Authorization: Bearer $HTB_API_TOKEN" \
  "https://www.hackthebox.com/api/v4/access/ovpnfile/1/0" \
  -o /workspace/htb.ovpn
```

Server types: `1` = EU Free, `2` = US Free, `3` = EU VIP, `4` = US VIP. Adjust for your account.

### 5. Write ctf-context.yaml

Once IP and machine details are confirmed, write `/workspace/ctf-context.yaml`:
```python
import yaml, os

machine = {
    "ip": "10.10.11.42",
    "name": "Editorial",
    "os": "linux",
    "difficulty": "easy",
    "category": "fullpwn",
    "htb_id": 612
}

ctx = {
    "target": {
        "ip": machine["ip"],
        "name": machine["name"],
        "os": machine["os"].lower(),
        "difficulty": machine["difficulty"].lower(),
        "category": machine.get("category", "fullpwn"),
        "htb_id": machine["htb_id"]
    },
    "vpn": {
        "iface": "tun0",
        "ovpn_file": "/workspace/htb.ovpn"
    }
}

with open("/workspace/ctf-context.yaml", "w") as f:
    yaml.dump(ctx, f, default_flow_style=False)

print(f"[+] ctf-context.yaml written for {machine['name']} ({machine['ip']})")
```

### 6. Submit flags

After FlagAgent captures a flag, submit it to HTB:
```bash
python3 /workspace/htb_api.py submit --flag "HTB{...}" --machine-id <id> --type user
python3 /workspace/htb_api.py submit --flag "HTB{...}" --machine-id <id> --type root

# Or directly:
curl -s -X POST \
  -H "Authorization: Bearer $HTB_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"id": <machine_id>, "flag": "HTB{...}", "difficulty": 50}' \
  https://www.hackthebox.com/api/v4/flag/own
```

`difficulty` is a 1–100 self-rating (10=Too Easy, 50=Just Right, 90=Hard).

### 7. Stop machine when done

```bash
curl -s -X POST \
  -H "Authorization: Bearer $HTB_API_TOKEN" \
  -H "Content-Type: application/json" \
  https://www.hackthebox.com/api/v4/machine/stop
```

---

## Browser Automation (Playwright fallback)

When the API isn't sufficient (e.g., 2FA flows, achievement checks, Pro Labs access):

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("https://app.hackthebox.com/login")
    page.fill('input[name="email"]', os.environ["HTB_EMAIL"])
    page.fill('input[name="password"]', os.environ["HTB_PASSWORD"])
    page.click('button[type="submit"]')
    page.wait_for_url("**/dashboard**")
    # Now navigate to machines, etc.
    browser.close()
```

Prefer API over browser automation — it's faster, more reliable, and doesn't break with UI changes.

---

## HTB API Reference (v4)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v4/machine/list` | GET | List all active machines |
| `/api/v4/machine/list?os=Linux` | GET | Filter by OS |
| `/api/v4/machine/play/{id}` | POST | Start a machine |
| `/api/v4/machine/stop` | POST | Stop active machine |
| `/api/v4/machine/active` | GET | Get currently running machine + IP |
| `/api/v4/machine/info/{id}` | GET | Machine details |
| `/api/v4/flag/own` | POST | Submit flag |
| `/api/v4/access/ovpnfile/{server}/{type}` | GET | Download OVPN file |
| `/api/v4/user/info` | GET | Your profile (verify token works) |

Base URL: `https://www.hackthebox.com`  
Auth header: `Authorization: Bearer $HTB_API_TOKEN`

---

## Inputs

| Source | Data |
|--------|------|
| `HTB_API_TOKEN` env var | HTB API authentication |
| `HTB_AUTO_SELECT` env var | `true` = auto-select without prompting |
| `HTB_MACHINE_ID` env var | Skip selection, start this specific machine ID |
| `HTB_EMAIL` / `HTB_PASSWORD` | For browser automation fallback only |

## Outputs

| File | Description |
|------|-------------|
| `/workspace/ctf-context.yaml` | Written with machine IP, name, OS, difficulty |
| `/workspace/htb.ovpn` | VPN config (if downloaded) |

## Tools

| Tool | Purpose |
|------|---------|
| `htb_api.py` | Python helper for common HTB API calls |
| `curl` + `jq` | Direct API calls and JSON parsing |
| Playwright (chromium) | Browser automation fallback |
| `python3` | Script orchestration |

## Workflow

```
1. VERIFY token: curl /api/v4/user/info → confirm auth works
2. IF HTB_MACHINE_ID set: skip to step 4
3. LIST machines → filter by difficulty/OS → present options
   IF HTB_AUTO_SELECT=true: auto-pick easiest unowned Linux machine
4. START machine: POST /api/v4/machine/play/{id}
5. POLL for IP: GET /api/v4/machine/active (retry every 10s, timeout 120s)
6. DOWNLOAD OVPN if /workspace/htb.ovpn doesn't exist
7. WRITE /workspace/ctf-context.yaml with machine details + IP
8. SIGNAL OrchestratorAgent → proceed with VPN verify + recon
9. AFTER flags captured: SUBMIT via /api/v4/flag/own
10. STOP machine when engagement complete
```
