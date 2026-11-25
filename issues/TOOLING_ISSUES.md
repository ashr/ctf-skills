# Tooling Issues & Missing Packages

**Context:** CTF engagement against `10.129.244.95` (Pirate, pirate.htb, Windows DC).
This document lists every tooling gap encountered so far, what it blocked, and the
exact command(s) to fix it. Once installed, see `CONTINUATION.md` for full engagement state.

Environment: Linux, user `ctf` (uid 1000, NO sudo), Python 3.12.3, pip 24.0.

> **2026-08-20 UPDATE:** User rebuilt the container with intended tooling. **VERIFY after
> restart before relying on anything** (impacket PKINIT, sudo, etc.):
> ```bash
> python3 -c "import impacket.krb5.pkinit; print('pkinit OK')"
> getTGT.py -h 2>&1 | grep -i pfx
> which sudo bloodhound-python dacledit pywhisker impacket-wmiexec 2>/dev/null
> ```
> Installed during session 2 via pip (internet IS available, needs `--break-system-packages`):
> `bloodhound 1.9.0` → `/home/ctf/.local/bin/bloodhound-python`.
> **bloodhound-python gotcha:** `-dc` must be the FQDN `dc01.pirate.htb` (bare IP rejected);
> pass `-ns 10.129.244.95`.

---

## CRITICAL — Missing impacket PKINIT module

| | |
|---|---|
| **Issue** | `impacket.krb5.pkinit` does not exist. `getTGT.py` has no `-pfx` option. |
| **Version** | `impacket 0.14.0.dev0+20260819.94127.f133bb88` (a dev snapshot without PKINIT). |
| **Blocked** | Cert-based Kerberos auth (PKINIT) using the ESC17 cert. Could not do `getTGT.py -pfx administrator.pfx` to obtain a usable Administrator TGT. |
| **Fix** | Upgrade impacket to a release that ships `krb5/pkinit.py` (0.11+ has it): |

```bash
pip install --upgrade impacket
# verify:
python3 -c "import impacket.krb5.pkinit; print('pkinit OK')"
# verify getTGT.py has -pfx:
getTGT.py -h 2>&1 | grep -i pfx
```

## Missing `sudo` (blocks editing system Python packages)

| | |
|---|---|
| **Issue** | `sudo` not installed. `/usr/local/lib/python3.12/dist-packages/**` is root-owned, read-only. |
| **Blocked** | Could not patch `impacket/.../ldaprelayclient.py` to log the real LDAP bind error — had to write a runtime monkeypatch instead (works, but fragile). |
| **Fix** | Install sudo for the `ctf` user, or make impacket dir writable: |

```bash
apt-get install -y sudo && usermod -aG sudo ctf
# OR just chown the impacket dir:
sudo chown -R ctf:ctf /usr/local/lib/python3.12/dist-packages/impacket
```

## Nice-to-have missing AD tools

| Tool | Why useful | Install |
|---|---|---|
| `bloodhound-python` | Full AD graph (would have mapped delegation/gMSA paths faster) | `pip install bloodhound` (python) |
| `windapsearch` | Simple LDAP user/group dump | `pip install windapsearch` |
| `kerbrute` | Fast user enum + password spray / roast | download binary from github.com/ropnop/kerbrute |
| `crackmapexec` | Legacy alias for netexec (not needed — `netexec` present) | — |
| `impacket-smbserver` | Convenience wrapper (`smbserver.py` already exists in impacket) | `pip install impacket` provides it |

## Behavioral workarounds already in place (do NOT "fix" — avoid regressions)

1. **`netexec -M daclread`**: the `-tgt` flag is invalid. Use `-M daclread -o TARGET_DN=CN=...,CN=Computers,DC=pirate,DC=htb` instead.
2. **`pkill` footgun**: `pkill -f "tail -f /dev/null"` matches its own parent shell command line and kills it (exit 144/143). Always kill relay by **PID** found via `ss -tlnp | grep ':445'`.
3. **sitecustomize auto-import is silently swallowed** in this Python build. To load a patch at interpreter start, use an explicit `import` in a wrapper or `python3 -c "import patch; import runpy; runpy.run_path('/usr/local/bin/ntlmrelayx.py', run_name='__main__')"` — do NOT rely on `PYTHONPATH=/path python3 ...` auto-importing `sitecustomize.py`.
4. **Port 445 binding works as non-root** (relay runs fine) — no fix needed.
5. **requests/urllib3 version warning** on import — cosmetic only.
6. **ldap3 2.9.1**: `Connection.send()`/`post_send_single_response()` live on the *strategy* object and are proxied via `Connection.__getattr__` — instance-attribute patching won't intercept internal calls.

## Already present (verified working) — no action needed

`evil-winrm`, `hashcat`, `john`, `netexec`, `proxychains4`, `socat`, `chisel`,
`smbclient`, `enum4linux-ng`, `ldapsearch`, `impacket` (getTGT/getNPUsers/secretsdump/certipy
work), `ldapdomaindump`, Python pkgs: `ldap3 2.9.1`, `cryptography 42`, `pyasn1`,
`certipy 5.1.0`, `OpenSSL`, `requests`, `bs4`, `paramiko`.
