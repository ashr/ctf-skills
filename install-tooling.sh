#\!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# install-tooling.sh — CTF Pentesting Environment Setup
# ══════════════════════════════════════════════════════════════════════════════
#
# Installs all tools required by the CTF agent stack.
# Targets Ubuntu/Debian-based systems (including Docker containers).
#
# Usage:
#   chmod +x install-tooling.sh
#   sudo ./install-tooling.sh              # install everything
#   ./install-tooling.sh --check           # verify installed tools
#
# Environment variables:
#   WORDLISTS_DIR   — where to install wordlists (default: /opt/wordlists)
#   TOOLS_DIR       — where to install git-based tools (default: /opt/tools)
#   GOPATH          — Go workspace (default: /opt/go)
#   SKIP_WORDLISTS  — set to "1" to skip wordlist downloads
# ══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

WORDLISTS_DIR="${WORDLISTS_DIR:-/opt/wordlists}"
TOOLS_DIR="${TOOLS_DIR:-/opt/tools}"
export GOPATH="${GOPATH:-/opt/go}"
export PATH="$GOPATH/bin:/usr/local/bin:$TOOLS_DIR/bin:$PATH"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

CHECK_ONLY=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --check) CHECK_ONLY=true; shift ;;
        --help|-h) head -20 "$0" | grep '^#' | sed 's/^# \?//'; exit 0 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

log_section() { echo -e "\n${BLUE}══════ $1 ══════${NC}\n"; }
log_ok()      { echo -e "  ${GREEN}[+]${NC} $1"; }
log_skip()    { echo -e "  ${YELLOW}[~]${NC} $1 already present, skipping"; }
log_warn()    { echo -e "  ${YELLOW}[\!]${NC} $1"; }
log_err()     { echo -e "  ${RED}[✗]${NC} $1"; }

has_cmd() { command -v "$1" &>/dev/null; }

apt_install() {
    local pkg="$1"
    if dpkg -s "$pkg" &>/dev/null 2>&1; then
        log_skip "$pkg"
    else
        log_ok "apt install $pkg"
        apt-get install -y --no-install-recommends "$pkg" >/dev/null 2>&1 || log_warn "Failed: $pkg"
    fi
}

pip_install() {
    local pkg="$1"
    local cmd="${2:-}"
    if [ -n "$cmd" ] && has_cmd "$cmd"; then
        log_skip "$pkg"
    elif python3 -c "import ${pkg//-/_}" 2>/dev/null; then
        log_skip "$pkg (python module)"
    else
        log_ok "pip install $pkg"
        pip install --break-system-packages --no-cache-dir "$pkg" >/dev/null 2>&1 || log_warn "pip: $pkg failed"
    fi
}

go_install() {
    local pkg="$1"
    local bin="${2:-$(basename $pkg | cut -d@ -f1)}"
    if has_cmd "$bin"; then
        log_skip "$bin"
    else
        log_ok "go install $bin"
        go install "$pkg" 2>/dev/null || log_warn "go install $pkg failed"
    fi
}

gem_install() {
    local gem="$1"
    local cmd="${2:-$1}"
    if has_cmd "$cmd"; then
        log_skip "$gem"
    else
        log_ok "gem install $gem"
        gem install --no-document "$gem" >/dev/null 2>&1 || log_warn "gem: $gem failed"
    fi
}

if $CHECK_ONLY; then
    log_section "Tool check"
    tools=(openvpn nmap nc socat curl wget git python3 go ruby john hashcat hydra
           searchsploit sqlmap ffuf gobuster httpx nuclei katana dalfox
           smbclient ldapsearch evil-winrm nxc gdb radare2 ROPgadget
           binwalk foremost tshark steghide exiftool vol arjun whatweb
           sudo faketime kerbrute windapsearch lsassy gMSADumper dcc2reformat
           interpreter)
    for t in "${tools[@]}"; do
        has_cmd "$t" && echo -e "  ${GREEN}✓${NC} $t" || echo -e "  ${RED}✗${NC} $t"
    done
    exit 0
fi

# Require root for apt
[[ $EUID -ne 0 ]] && { echo "Run as root (sudo)"; exit 1; }

log_section "System packages"
apt-get update -qq
for pkg in \
    ca-certificates curl wget git unzip zip tar build-essential libpcap-dev \
    python3 python3-pip python3-venv golang-go nodejs npm ruby-full ruby-dev \
    openvpn iproute2 iputils-ping \
    nmap netcat-traditional socat ncat \
    openssh-client sshpass \
    dnsutils whois proxychains4 \
    smbclient ldap-utils krb5-user \
    nikto whatweb \
    binwalk foremost tshark wireshark-common steghide aircrack-ng exiv2 \
    libimage-exiftool-perl \
    xxd jq vim nano tmux \
    snmp libssl-dev \
    gdb ltrace strace radare2 binutils \
    john hashcat hydra \
    exploitdb \
    sudo faketime \
    libxml2-dev libxslt1-dev zlib1g-dev libffi-dev; do
    apt_install "$pkg"
done

# seclists
apt_install seclists || true

log_section "Python packages"
for pkg_cmd in \
    "sqlmap:sqlmap" "wafw00f:wafw00f" "arjun:arjun" "wfuzz:wfuzz" \
    "commix:commix" "jwt-tool:jwt_tool" "httpie:http" "shodan:shodan" \
    "graphw00f:graphw00f" "theHarvester:theHarvester" \
    "oletools:olevba" "volatility3:vol" \
    "pycryptodome:" "gmpy2:" "owiener:" "sympy:sage" \
    "hashid:hashid" "pwntools:pwn" \
    "impacket:" "netexec:nxc" "bloodhound:bloodhound-python" \
    "bloodyAD:bloodyAD" "lsassy:lsassy" "pywhisker:pywhisker" "dacledit:dacledit" \
    "requests:" "pyyaml:" "sslyze:sslyze" "cvss:" \
    "enum4linux-ng:enum4linux-ng" "smbmap:smbmap" \
    "ROPgadget:ROPgadget" "ropper:ropper" "checksec:checksec"; do
    pkg="${pkg_cmd%%:*}"
    cmd="${pkg_cmd##*:}"
    pip_install "$pkg" "$cmd"
done

# No released impacket version ships a krb5/pkinit.py module — getTGT.py has no
# -pfx flag upstream. Cert-based Kerberos auth (PKINIT) is provided by certipy-ad
# (already installed: `certipy auth -pfx ...`) and by PKINITtools, installed here
# as a fallback/alternative.
if [ ! -d "$TOOLS_DIR/PKINITtools" ]; then
    git clone --depth 1 https://github.com/dirkjanm/PKINITtools "$TOOLS_DIR/PKINITtools" && \
    pip install --break-system-packages --no-cache-dir -r "$TOOLS_DIR/PKINITtools/requirements.txt" && \
    for f in "$TOOLS_DIR"/PKINITtools/*.py; do
        chmod +x "$f"
        ln -sf "$f" "/usr/local/bin/$(basename "$f" .py)"
    done && log_ok "PKINITtools" || log_warn "PKINITtools failed"
else
    log_skip "PKINITtools"
fi

# passwordless sudo for the current non-root user (needed to patch root-owned dist-packages, etc.)
if has_cmd sudo && [ -n "${SUDO_USER:-}" ]; then
    echo "${SUDO_USER} ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/${SUDO_USER}" && \
    chmod 0440 "/etc/sudoers.d/${SUDO_USER}" && log_ok "passwordless sudo for ${SUDO_USER}"
fi

log_section "Go tools"
mkdir -p "$GOPATH/bin"
go_install "github.com/projectdiscovery/httpx/cmd/httpx@latest" httpx
go_install "github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest" nuclei
go_install "github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest" subfinder
go_install "github.com/projectdiscovery/dnsx/cmd/dnsx@latest" dnsx
go_install "github.com/projectdiscovery/katana/cmd/katana@latest" katana
go_install "github.com/ffuf/ffuf/v2@latest" ffuf
go_install "github.com/OJ/gobuster/v3@latest" gobuster
go_install "github.com/hahwul/dalfox/v2@latest" dalfox
go_install "github.com/trufflesecurity/trufflehog/v3@latest" trufflehog

log_section "Ruby gems"
gem_install wpscan
gem_install evil-winrm evil-winrm
gem_install one_gadget
gem_install zsteg

log_section "Node packages"
has_cmd retire || npm install -g retire >/dev/null 2>&1 || log_warn "npm: retire failed"

log_section "Open Interpreter"
if has_cmd interpreter; then
    log_skip "open-interpreter"
else
    curl -fsSL https://www.openinterpreter.com/install | \
        OPEN_INTERPRETER_NONINTERACTIVE=1 OPEN_INTERPRETER_INSTALL_DIR=/usr/local/bin sh && \
        log_ok "open-interpreter" || log_warn "open-interpreter failed"
fi

log_section "Binary tools from GitHub"
mkdir -p "$TOOLS_DIR/bin"

# chisel
if \! has_cmd chisel; then
    CHISEL_VER=$(curl -sf https://api.github.com/repos/jpillora/chisel/releases/latest | grep tag_name | cut -d'"' -f4)
    curl -fsSL "https://github.com/jpillora/chisel/releases/download/${CHISEL_VER}/chisel_${CHISEL_VER#v}_linux_amd64.gz" | \
        gunzip > "$TOOLS_DIR/bin/chisel" && chmod +x "$TOOLS_DIR/bin/chisel" && log_ok "chisel" || log_warn "chisel failed"
fi

# pspy64
if [ \! -f "$TOOLS_DIR/bin/pspy64" ]; then
    curl -fsSL https://github.com/DominicBreuker/pspy/releases/latest/download/pspy64 \
        -o "$TOOLS_DIR/bin/pspy64" && chmod +x "$TOOLS_DIR/bin/pspy64" && log_ok "pspy64" || log_warn "pspy64 failed"
fi

# linPEAS + winPEAS
mkdir -p "$TOOLS_DIR/privesc"
[ -f "$TOOLS_DIR/privesc/linpeas.sh" ] || \
    curl -fsSL https://github.com/carlospolop/PEASS-ng/releases/latest/download/linpeas.sh \
    -o "$TOOLS_DIR/privesc/linpeas.sh" && chmod +x "$TOOLS_DIR/privesc/linpeas.sh" && log_ok "linpeas" || log_warn "linpeas failed"
[ -f "$TOOLS_DIR/privesc/winPEASx64.exe" ] || \
    curl -fsSL https://github.com/carlospolop/PEASS-ng/releases/latest/download/winPEASx64.exe \
    -o "$TOOLS_DIR/privesc/winPEASx64.exe" && log_ok "winpeas" || log_warn "winpeas failed"

# pwndbg
if [ \! -d "$TOOLS_DIR/pwndbg" ]; then
    git clone --depth 1 https://github.com/pwndbg/pwndbg "$TOOLS_DIR/pwndbg" && \
    cd "$TOOLS_DIR/pwndbg" && ./setup.sh --quiet 2>/dev/null && log_ok "pwndbg" || log_warn "pwndbg setup failed"
fi

# testssl.sh
if \! has_cmd testssl.sh; then
    git clone --depth 1 https://github.com/drwetter/testssl.sh "$TOOLS_DIR/testssl.sh" && \
    ln -sf "$TOOLS_DIR/testssl.sh/testssl.sh" /usr/local/bin/testssl.sh && log_ok "testssl.sh" || log_warn "testssl.sh failed"
fi

# kerbrute
if \! has_cmd kerbrute; then
    curl -fsSL https://github.com/ropnop/kerbrute/releases/latest/download/kerbrute_linux_amd64 \
        -o "$TOOLS_DIR/bin/kerbrute" && chmod +x "$TOOLS_DIR/bin/kerbrute" && log_ok "kerbrute" || log_warn "kerbrute failed"
fi

# windapsearch
if \! has_cmd windapsearch; then
    git clone --depth 1 https://github.com/ropnop/windapsearch "$TOOLS_DIR/windapsearch" && \
    chmod +x "$TOOLS_DIR/windapsearch/windapsearch.py" && \
    ln -sf "$TOOLS_DIR/windapsearch/windapsearch.py" /usr/local/bin/windapsearch && log_ok "windapsearch" || log_warn "windapsearch failed"
fi

# gMSADumper
if [ ! -d "$TOOLS_DIR/gMSADumper" ]; then
    git clone --depth 1 https://github.com/micahvandeusen/gMSADumper "$TOOLS_DIR/gMSADumper" && \
    (pip install --break-system-packages --no-cache-dir -r "$TOOLS_DIR/gMSADumper/requirements.txt" 2>/dev/null || true) && \
    chmod +x "$TOOLS_DIR/gMSADumper/gMSADumper.py" && \
    ln -sf "$TOOLS_DIR/gMSADumper/gMSADumper.py" /usr/local/bin/gMSADumper && log_ok "gMSADumper" || log_warn "gMSADumper failed"
else
    log_skip "gMSADumper"
fi

# dcc2reformat — convert secretsdump cached-cred lines to hashcat -m 2100 format
if [ ! -f /usr/local/bin/dcc2reformat ]; then
    cat > /usr/local/bin/dcc2reformat << 'PYEOF'
#!/usr/bin/env python3
# Extract secretsdump cached-cred lines to hashcat -m 2100 (mscash2) format
import sys, re
pat = re.compile(r'\$DCC2\$\d+#[^#]+#[0-9a-fA-F]+')
for line in sys.stdin:
    m = pat.search(line)
    if m:
        print(m.group())
PYEOF
    chmod +x /usr/local/bin/dcc2reformat && log_ok "dcc2reformat"
else
    log_skip "dcc2reformat"
fi

log_section "Windows pre-staged binaries"
mkdir -p "$TOOLS_DIR/win"

# chisel.exe
if [ ! -f "$TOOLS_DIR/win/chisel.exe" ]; then
    CHISEL_VER=$(curl -sf https://api.github.com/repos/jpillora/chisel/releases/latest | grep tag_name | cut -d'"' -f4)
    curl -fsSL "https://github.com/jpillora/chisel/releases/download/${CHISEL_VER}/chisel_${CHISEL_VER#v}_windows_amd64.gz" | \
        gunzip > "$TOOLS_DIR/win/chisel.exe" && log_ok "chisel.exe" || log_warn "chisel.exe failed"
else
    log_skip "chisel.exe"
fi

# SharpHound.exe
if [ ! -f "$TOOLS_DIR/win/SharpHound.exe" ]; then
    SH_TAG=$(curl -sf https://api.github.com/repos/BloodHoundAD/SharpHound/releases/latest | grep tag_name | cut -d'"' -f4)
    curl -fsSL "https://github.com/BloodHoundAD/SharpHound/releases/download/${SH_TAG}/SharpHound-${SH_TAG}.zip" \
        -o /tmp/sh.zip 2>/dev/null && \
    (unzip -j /tmp/sh.zip "*/SharpHound.exe" -d "$TOOLS_DIR/win/" 2>/dev/null || \
     unzip -j /tmp/sh.zip "SharpHound.exe" -d "$TOOLS_DIR/win/" 2>/dev/null) && \
    rm -f /tmp/sh.zip && log_ok "SharpHound.exe" || log_warn "SharpHound.exe failed"
else
    log_skip "SharpHound.exe"
fi

# PrintSpoofer64.exe
if [ ! -f "$TOOLS_DIR/win/PrintSpoofer64.exe" ]; then
    curl -fsSL https://github.com/itm4n/PrintSpoofer/releases/latest/download/PrintSpoofer64.exe \
        -o "$TOOLS_DIR/win/PrintSpoofer64.exe" && log_ok "PrintSpoofer64.exe" || log_warn "PrintSpoofer64.exe failed"
else
    log_skip "PrintSpoofer64.exe"
fi

# JuicyPotato.exe
if [ ! -f "$TOOLS_DIR/win/JuicyPotato.exe" ]; then
    curl -fsSL https://github.com/ohpe/juicy-potato/releases/latest/download/JuicyPotato.exe \
        -o "$TOOLS_DIR/win/JuicyPotato.exe" && log_ok "JuicyPotato.exe" || log_warn "JuicyPotato.exe failed"
else
    log_skip "JuicyPotato.exe"
fi

# PowerView.ps1
if [ ! -f "$TOOLS_DIR/win/PowerView.ps1" ]; then
    curl -fsSL https://raw.githubusercontent.com/PowerShellMafia/PowerSploit/master/Recon/PowerView.ps1 \
        -o "$TOOLS_DIR/win/PowerView.ps1" && log_ok "PowerView.ps1" || log_warn "PowerView.ps1 failed"
else
    log_skip "PowerView.ps1"
fi

# mimikatz.exe
if [ ! -f "$TOOLS_DIR/win/mimikatz.exe" ]; then
    MK_TAG=$(curl -sf https://api.github.com/repos/gentilkiwi/mimikatz/releases/latest | grep tag_name | cut -d'"' -f4)
    curl -fsSL "https://github.com/gentilkiwi/mimikatz/releases/download/${MK_TAG}/mimikatz_trunk.zip" \
        -o /tmp/mk.zip 2>/dev/null && \
    unzip -j /tmp/mk.zip "x64/mimikatz.exe" -d "$TOOLS_DIR/win/" && \
    rm -f /tmp/mk.zip && log_ok "mimikatz.exe" || log_warn "mimikatz.exe failed"
else
    log_skip "mimikatz.exe"
fi

# Rubeus.exe (r3motecontrol/Ghostpack-CompiledBinaries — community compiled)
if [ ! -f "$TOOLS_DIR/win/Rubeus.exe" ]; then
    curl -fsSL https://github.com/r3motecontrol/Ghostpack-CompiledBinaries/raw/master/Rubeus.exe \
        -o "$TOOLS_DIR/win/Rubeus.exe" && log_ok "Rubeus.exe" || log_warn "Rubeus.exe failed"
else
    log_skip "Rubeus.exe"
fi

# procdump64.exe — use -accepteula at runtime
if [ ! -f "$TOOLS_DIR/win/procdump64.exe" ]; then
    curl -fsSL https://download.sysinternals.com/files/Procdump.zip \
        -o /tmp/procdump.zip 2>/dev/null && \
    unzip -j /tmp/procdump.zip procdump64.exe -d "$TOOLS_DIR/win/" && \
    rm -f /tmp/procdump.zip && log_ok "procdump64.exe" || log_warn "procdump64.exe failed"
else
    log_skip "procdump64.exe"
fi

log_section "Wordlists"
mkdir -p "$WORDLISTS_DIR"

# SecLists
if [ \! -d "$WORDLISTS_DIR/SecLists" ]; then
    if [ -d /usr/share/seclists ]; then
        ln -sf /usr/share/seclists "$WORDLISTS_DIR/SecLists" && log_ok "SecLists (linked from apt)"
    else
        git clone --depth 1 https://github.com/danielmiessler/SecLists "$WORDLISTS_DIR/SecLists" && log_ok "SecLists"
    fi
else
    log_skip "SecLists"
fi

# rockyou.txt
if [ \! -f "$WORDLISTS_DIR/rockyou.txt" ]; then
    if [ -f /usr/share/wordlists/rockyou.txt ]; then
        ln -sf /usr/share/wordlists/rockyou.txt "$WORDLISTS_DIR/rockyou.txt" && log_ok "rockyou.txt (linked)"
    elif [ -f /usr/share/wordlists/rockyou.txt.gz ]; then
        gunzip -k /usr/share/wordlists/rockyou.txt.gz
        ln -sf /usr/share/wordlists/rockyou.txt "$WORDLISTS_DIR/rockyou.txt" && log_ok "rockyou.txt (decompressed)"
    else
        curl -fsSL https://github.com/brannondorsey/naive-hashcat/releases/download/data/rockyou.txt \
            -o "$WORDLISTS_DIR/rockyou.txt" && log_ok "rockyou.txt (downloaded)" || log_warn "rockyou download failed"
    fi
else
    log_skip "rockyou.txt"
fi

log_section "Nuclei templates"
nuclei -update-templates 2>/dev/null && log_ok "nuclei templates" || log_warn "nuclei template update failed"

log_section "Done"
echo -e "\n${GREEN}CTF tooling installation complete.${NC}"
echo "Run with --check to verify installed tools."
