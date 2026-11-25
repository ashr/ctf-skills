# CTF Tooling Matrix

> Complete inventory of tools available to CTF agents. All tools are pre-installed
> in the CTF container image. Agents reference specific tools from this file.

---

## Network & VPN

| Tool | Binary | Purpose | Install |
|------|--------|---------|---------|
| openvpn | `openvpn` | HTB VPN connectivity | `apt install openvpn` |
| nmap | `nmap` | Port scanning, service detection, NSE | `apt install nmap` |
| netcat | `nc` | Reverse shell listener / connections | `apt install netcat-traditional` |
| socat | `socat` | Stable shell upgrades, port forwarding | `apt install socat` |
| chisel | `chisel` | TCP/UDP tunnel over HTTP | GitHub releases |
| proxychains4 | `proxychains4` | Route through SOCKS proxy | `apt install proxychains4` |

---

## Reconnaissance & Discovery

| Tool | Binary | Purpose | Install |
|------|--------|---------|---------|
| httpx | `httpx` | HTTP probing — status, title, tech | go install projectdiscovery/httpx |
| ffuf | `ffuf` | Directory/file/vhost fuzzing | go install ffuf/ffuf |
| gobuster | `gobuster` | Alt dir/DNS brute-forcer | go install OJ/gobuster |
| nikto | `nikto` | Web server misconfig scanner | `apt install nikto` |
| whatweb | `whatweb` | Web tech fingerprinting | `apt install whatweb` |
| katana | `katana` | Web crawler | go install projectdiscovery/katana |
| arjun | `arjun` | Hidden HTTP parameter discovery | `pip install arjun` |
| dnsx | `dnsx` | DNS resolution, brute-force | go install projectdiscovery/dnsx |
| dig | `dig` | DNS queries + zone transfer | `apt install dnsutils` |
| enum4linux-ng | `enum4linux-ng` | SMB/LDAP/RPC enumeration | `pip install enum4linux-ng` |
| smbmap | `smbmap` | SMB share enumeration | `pip install smbmap` |
| snmpwalk | `snmpwalk` | SNMP enumeration | `apt install snmp` |

---

## Web Application Testing

| Tool | Binary | Purpose | Install |
|------|--------|---------|---------|
| sqlmap | `sqlmap` | SQL injection detection + exploitation | `pip install sqlmap` |
| dalfox | `dalfox` | XSS scanner | go install hahwul/dalfox |
| commix | `commix` | Command injection | `pip install commix` |
| wfuzz | `wfuzz` | Web fuzzer | `pip install wfuzz` |
| jwt_tool | `jwt_tool` | JWT analysis + attacks | `pip install jwt-tool` |
| wpscan | `wpscan` | WordPress scanner | `gem install wpscan` |
| wafw00f | `wafw00f` | WAF detection | `pip install wafw00f` |
| curl | `curl` | Manual HTTP requests | pre-installed |
| httpie | `http` | Human-friendly HTTP client | `pip install httpie` |

---

## Exploitation

| Tool | Binary | Purpose | Install |
|------|--------|---------|---------|
| metasploit | `msfconsole` | CVE exploitation framework | `apt install metasploit-framework` |
| searchsploit | `searchsploit` | Offline ExploitDB search | `apt install exploitdb` |
| nuclei | `nuclei` | Template-based CVE detection | go install projectdiscovery/nuclei |

---

## Password Cracking

| Tool | Binary | Purpose | Install |
|------|--------|---------|---------|
| john | `john` | John the Ripper — hash cracking | `apt install john` |
| hashcat | `hashcat` | GPU-accelerated hash cracking | `apt install hashcat` |
| hydra | `hydra` | Service brute-forcing (SSH, FTP, HTTP) | `apt install hydra` |
| hash-identifier | `hash-identifier` | Identify hash type | `pip install hash-identifier` |

---

## AD / Windows Attacks

| Tool | Binary | Purpose | Install |
|------|--------|---------|---------|
| impacket | various | AD attacks, SMB, Kerberos, PSExec | `pip install impacket` |
| netexec | `nxc` | CME successor — SMB/WinRM/LDAP exec | `pip install netexec` |
| evil-winrm | `evil-winrm` | WinRM shell | `gem install evil-winrm` |
| smbclient | `smbclient` | SMB share access | `apt install smbclient` |
| krb5-user | `kinit` | Kerberos authentication | `apt install krb5-user` |
| ldapsearch | `ldapsearch` | LDAP enumeration | `apt install ldap-utils` |
| bloodhound | `bloodhound-python` | AD graph ingestion | `pip install bloodhound` |

---

## Privilege Escalation

| Tool | Binary | Purpose | Install |
|------|--------|---------|---------|
| linpeas | `linpeas.sh` | Linux privesc enumeration | GitHub releases |
| winpeas | `winpeas.exe` | Windows privesc enumeration | GitHub releases |
| pspy | `pspy64` | Linux process spy (no root) | GitHub releases |
| linux-exploit-suggester | `les.sh` | Kernel exploit suggester | GitHub |

---

## Binary Exploitation (PWN)

| Tool | Binary | Purpose | Install |
|------|--------|---------|---------|
| pwntools | `pwn` | Exploit dev framework | `pip install pwntools` |
| gdb | `gdb` | Debugger | `apt install gdb` |
| pwndbg | gdb plugin | Enhanced GDB for exploit dev | GitHub |
| radare2 | `r2` | Disassembler / binary analysis | `apt install radare2` |
| ROPgadget | `ROPgadget` | ROP chain gadget finder | `pip install ROPgadget` |
| ropper | `ropper` | Alt ROP gadget finder | `pip install ropper` |
| checksec | `checksec` | Binary protections check | `pip install checksec` |
| one_gadget | `one_gadget` | Magic gadget finder for libc | `gem install one_gadget` |
| objdump | `objdump` | Disassembly | pre-installed (binutils) |
| strings | `strings` | Extract printable strings | pre-installed (binutils) |
| ltrace | `ltrace` | Library call tracing | `apt install ltrace` |
| strace | `strace` | Syscall tracing | `apt install strace` |

---

## Cryptography

| Tool | Binary | Purpose | Install |
|------|--------|---------|---------|
| pycryptodome | python lib | Crypto algorithms (AES, RSA, etc.) | `pip install pycryptodome` |
| gmpy2 | python lib | Big integer / number theory | `pip install gmpy2` |
| owiener | python lib | RSA Wiener attack | `pip install owiener` |
| sympy | python lib | Symbolic math / factoring | `pip install sympy` |
| sage | `sage` | SageMath — advanced number theory | `apt install sagemath` |
| hashid | `hashid` | Hash type identification | `pip install hashid` |

---

## Forensics & Steganography

| Tool | Binary | Purpose | Install |
|------|--------|---------|---------|
| binwalk | `binwalk` | Embedded file detection + extraction | `apt install binwalk` |
| foremost | `foremost` | File carving | `apt install foremost` |
| exiftool | `exiftool` | Metadata extraction | `apt install libimage-exiftool-perl` |
| steghide | `steghide` | JPEG/BMP steganography | `apt install steghide` |
| zsteg | `zsteg` | PNG/BMP LSB steg analysis | `gem install zsteg` |
| tshark | `tshark` | PCAP CLI analysis | `apt install tshark` |
| wireshark | `wireshark` | PCAP GUI analysis | `apt install wireshark` |
| volatility3 | `vol` | Memory forensics | `pip install volatility3` |
| sleuthkit | `mmls`/`fls`/`icat`/`tsk_recover` | Disk image analysis (no `mount`/root needed — see README "Runtime privilege model") | `apt install sleuthkit` |
| aircrack-ng | `aircrack-ng` | WPA2 cracking from PCAP | `apt install aircrack-ng` |
| oletools | `olevba` | Office macro extraction | `pip install oletools` |
| testssl.sh | `testssl.sh` | TLS assessment | GitHub |

---

## JavaScript / Client-Side

| Tool | Binary | Purpose | Install |
|------|--------|---------|---------|
| retire.js | `retire` | Vulnerable JS library detection | `npm install -g retire` |
| trufflehog | `trufflehog` | Secret scanning in JS | go install trufflesecurity/trufflehog |
| npm audit | `npm` | Package vulnerability audit | ships with npm |

---

## Wordlists

| Wordlist | Path | Use |
|----------|------|-----|
| SecLists | `/opt/wordlists/SecLists/` | Directories, usernames, passwords, subdomains |
| rockyou.txt | `/opt/wordlists/rockyou.txt` | Password cracking (primary) |
| raft-medium-directories | `/opt/wordlists/SecLists/Discovery/Web-Content/raft-medium-directories.txt` | Dir brute-force |
| raft-medium-files | `/opt/wordlists/SecLists/Discovery/Web-Content/raft-medium-files.txt` | File brute-force |
| top-usernames-shortlist | `/opt/wordlists/SecLists/Usernames/top-usernames-shortlist.txt` | Username brute-force |
| Common-Credentials/best1050 | `/opt/wordlists/SecLists/Passwords/Common-Credentials/best1050.txt` | Service brute-force |

---

## MCP Servers

| MCP | Purpose |
|-----|---------|
| Burp MCP | HTTP request crafting, response analysis, proxy interception |
| Browser MCP | DOM inspection, JS analysis, browser-level testing |

## AI Assistants

| Tool | Binary | Purpose | Install |
|------|--------|---------|---------|
| Open Interpreter | `interpreter` / `i` | Local natural-language coding and shell assistant | `curl -fsSL https://www.openinterpreter.com/install \| sh` |

---

## Utility

| Tool | Binary | Purpose | Install |
|------|--------|---------|---------|
| jq | `jq` | JSON parsing | `apt install jq` |
| python3 | `python3` | Scripting | pre-installed |
| curl | `curl` | HTTP client | pre-installed |
| wget | `wget` | File download | pre-installed |
| xxd | `xxd` | Hex dump | pre-installed (vim) |
| file | `file` | File type detection | pre-installed |
| openssl | `openssl` | Crypto operations, TLS | pre-installed |
| base64 | `base64` | Base64 encode/decode | pre-installed |
