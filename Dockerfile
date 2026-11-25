# ══════════════════════════════════════════════════════════════════════════════
# Dockerfile — CTF Pentesting Agent Container
# ══════════════════════════════════════════════════════════════════════════════
#
# Single-image CTF environment for Hack The Box and similar platforms.
# Includes VPN, all attack tooling, wordlists, and agent definitions.
#
# Build:
#   mkdir -p certs            # corporate CA certs (*.crt, PEM) — may be empty
#   docker build -t ctf-agents .
#
# The certs/ directory MUST exist in the build context (COPY fails otherwise).
# Only files with a .crt extension are registered; rename .pem -> .crt.
#
# Run (HTB VPN):
#   docker run -it --rm \
#     --cap-add=NET_ADMIN --cap-add=NET_RAW --cap-add=SYS_TIME \
#     --device /dev/net/tun \
#     -v $(pwd)/htb.ovpn:/workspace/htb.ovpn:ro \
#     -v $(pwd)/loot:/workspace/loot \
#     -v $(pwd)/ctf-context.yaml:/workspace/ctf-context.yaml:ro \
#     ctf-agents
#
# Container starts as root; entrypoint.sh applies egress control then drops
# to the non-root ctf user via gosu — see README "Egress Control" and
# "Runtime privilege model".
#
# ══════════════════════════════════════════════════════════════════════════════

FROM mcr.microsoft.com/dotnet/sdk:8.0 AS orchestrator-build

# Corporate CA certs — NuGet restore needs to trust the TLS-inspecting proxy.
COPY certs/ /usr/local/share/ca-certificates/
RUN update-ca-certificates

WORKDIR /src
COPY small-model-orchestrator/ ./
RUN dotnet publish small-model-orchestrator.csproj \
    --configuration Release \
    --runtime linux-x64 \
    --self-contained true \
    --output /out

FROM ubuntu:24.04

ARG DEBIAN_FRONTEND=noninteractive
ARG CTF_USER=ctf
ARG CTF_UID=1000
ARG CTF_GID=1000

# ─── Base system ──────────────────────────────────────────────────────────────

# Pre-answer tshark's interactive prompt (install without setuid)
RUN apt-get update && apt-get install -y --no-install-recommends debconf-utils && \
    echo 'wireshark-common wireshark-common/install-setuid boolean false' | debconf-set-selections && \
    rm -rf /var/lib/apt/lists/*

RUN apt-get update && apt-get install -y --no-install-recommends \
    # Core utilities
    ca-certificates curl wget git unzip zip tar \
    build-essential libpcap-dev libcap2-bin \
    # Scripting runtimes
    python3 python3-pip python3-venv python3-dev \
    golang-go nodejs npm ruby-full ruby-dev \
    # Network tools
    openvpn iproute2 iputils-ping \
    nmap netcat-traditional socat ncat \
    openssh-client sshpass \
    dnsutils whois \
    proxychains4 \
    nftables gosu \
    # SMB / AD
    smbclient ldap-utils krb5-user \
    # Web
    nikto whatweb \
    # Forensics
    binwalk foremost tshark wireshark-common \
    steghide aircrack-ng exiv2 sleuthkit \
    libimage-exiftool-perl \
    xxd jq \
    # Binary analysis
    gdb ltrace strace radare2 binutils \
    # Password cracking
    john hashcat hydra \
    # Crypto
    libssl-dev \
    # Misc
    vim nano tmux screen faketime \
    snmp snmpd \
    libxml2-dev libxslt1-dev zlib1g-dev libffi-dev libreadline-dev \
    && rm -rf /var/lib/apt/lists/*

# ─── Corporate CA certificates ───────────────────────────────────────────────
# Placed immediately after the apt layer (which installs ca-certificates) and
# before every curl / pip / go / git / npm / gem call, so all of them trust the
# TLS-inspecting proxy. Kept out of the apt layer so a cert change does not
# invalidate the (slow) package-install cache.
# certs/ must exist in the build context — empty dir if no certs are needed.

COPY certs/ /usr/local/share/ca-certificates/
RUN update-ca-certificates

# Dedicated custom-CA-only bundle for tools that mis-parse the full OS bundle.
# Some CLIs (e.g. Claude Code) merge NODE_EXTRA_CA_CERTS themselves, and their
# PEM parsers can be stricter than OpenSSL's. Debian/Ubuntu's
# /etc/ssl/certs/ca-certificates.crt is a multi-hundred-cert bundle with
# comment headers; a strict parser can stop partway and silently drop the
# corporate certs. A small file containing ONLY the custom certs avoids that.
RUN { for f in /usr/local/share/ca-certificates/*.crt; do \
         [ -f "$f" ] || continue; \
         cat "$f"; \
         echo; \
       done; } > /etc/ssl/certs/custom-ca-certs.pem

ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV CURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV GIT_SSL_CAINFO=/etc/ssl/certs/ca-certificates.crt
# NOTE: NODE_OPTIONS=--use-system-ca is deliberately NOT set here (unlike
# Dockerfile.copilot, which uses node:22). Ubuntu 24.04's apt nodejs is 18.x,
# which rejects --use-system-ca in NODE_OPTIONS and refuses to start. Node
# trusts the corporate CAs via NODE_EXTRA_CA_CERTS instead.
ENV NODE_EXTRA_CA_CERTS=/etc/ssl/certs/custom-ca-certs.pem

# Persist for login shells (sudo -i, su -, tmux login shells reset the env)
RUN echo 'export NODE_EXTRA_CA_CERTS=/etc/ssl/certs/custom-ca-certs.pem' \
    > /etc/profile.d/custom-ca.sh

RUN set -eux; \
        if getent group "$CTF_GID" >/dev/null; then \
            group_name="$(getent group "$CTF_GID" | cut -d: -f1)"; \
            if [ "$group_name" != "$CTF_USER" ]; then groupmod --new-name "$CTF_USER" "$group_name"; fi; \
        else \
            groupadd --gid "$CTF_GID" "$CTF_USER"; \
        fi; \
        if getent passwd "$CTF_UID" >/dev/null; then \
            user_name="$(getent passwd "$CTF_UID" | cut -d: -f1)"; \
            if [ "$user_name" != "$CTF_USER" ]; then usermod --login "$CTF_USER" --home "/home/$CTF_USER" --move-home "$user_name"; fi; \
            usermod --gid "$CTF_GID" --shell /bin/bash "$CTF_USER"; \
        else \
            useradd --uid "$CTF_UID" --gid "$CTF_GID" --create-home --shell /bin/bash "$CTF_USER"; \
        fi; \
        usermod --groups "" "$CTF_USER"; \
        mkdir -p "/home/$CTF_USER/.local/bin" "/home/$CTF_USER/.config" "/home/$CTF_USER/go/bin"; \
        chown -R "$CTF_USER:$CTF_USER" "/home/$CTF_USER"

# No sudo for ctf (see README "Runtime privilege model"): clock-skew fixes,
# dist-packages patching, and low-port binding are covered below via file
# capabilities / build-time ownership instead of a blanket root escape.
RUN setcap cap_net_admin,cap_net_raw+eip /usr/sbin/openvpn && \
    setcap cap_net_admin,cap_net_raw,cap_net_bind_service+eip /usr/bin/nmap && \
    setcap cap_sys_time+eip /bin/date || \
    echo "[WARN] failed to assign network/time capabilities"

# ─── Environment ─────────────────────────────────────────────────────────────

ENV GOPATH=/opt/go
ENV PATH="$GOPATH/bin:/usr/local/bin:/opt/tools/bin:$PATH"
ENV WORDLISTS_DIR=/opt/wordlists
ENV TOOLS_DIR=/opt/tools
ENV WORKSPACE=/workspace

RUN mkdir -p "$GOPATH/bin" "$WORDLISTS_DIR" "$TOOLS_DIR/bin" "$WORKSPACE/loot"

WORKDIR $WORKSPACE

# ─── Python packages ─────────────────────────────────────────────────────────

RUN pip install --break-system-packages --no-cache-dir \
    # Web testing (jwt-tool and commix installed from GitHub below; trufflehog is a Go binary)
    sqlmap wafw00f arjun wfuzz xsstrike \
    httpie shodan \
    # Forensics / analysis
    oletools volatility3 \
    # Crypto
    pycryptodome gmpy2 owiener sympy \
    # Hash utils
    hashid \
    # PWN
    pwntools \
    # AD / impacket (bloodhound-python is the correct PyPI package name; netexec installed separately below)
    impacket bloodhound-python \
    # Utility
    requests pyyaml sslyze cvss \
    # Local-model agent runner (see runner/) — Ollama via litellm
    # NOTE: pycares/aiodns get re-pinned again near the end of this file —
    # NetExec's aardwolf dependency (installed later) downgrades them again.
    litellm "pycares>=4.6" "aiodns>=3.2" \
    # enum (smbmap is real; enum4linux-ng/theHarvester/graphw00f are PyPI stubs — installed from GitHub below)
    smbmap

# AD abuse helpers
RUN pip install --break-system-packages --no-cache-dir bloodyAD lsassy pywhisker || \
    echo "[WARN] one or more AD abuse pip packages failed"
RUN pip install --break-system-packages --no-cache-dir dacledit 2>/dev/null || \
    pip install --break-system-packages --no-cache-dir \
        git+https://github.com/ThePorgs/dacledit.git 2>/dev/null || \
    echo "[WARN] dacledit install failed"

# ─── Go tools ─────────────────────────────────────────────────────────────────

RUN go install github.com/projectdiscovery/httpx/cmd/httpx@latest && \
    go install github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest && \
    go install github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest && \
    go install github.com/projectdiscovery/dnsx/cmd/dnsx@latest && \
    go install github.com/projectdiscovery/katana/cmd/katana@latest && \
    go install github.com/ffuf/ffuf/v2@latest && \
    go install github.com/OJ/gobuster/v3@latest && \
    go install github.com/hahwul/dalfox/v2@latest

# trufflehog — go install blocked by replace directives in go.mod; use official binary installer
RUN curl -sSfL https://raw.githubusercontent.com/trufflesecurity/trufflehog/main/scripts/install.sh \
    | sh -s -- -b /usr/local/bin || \
    echo "[WARN] trufflehog install failed"

# ─── Ruby gems ───────────────────────────────────────────────────────────────

RUN gem install --no-document wpscan evil-winrm one_gadget zsteg

# ─── Node packages ───────────────────────────────────────────────────────────

RUN npm install -g retire

# ─── Binary tools from GitHub releases ───────────────────────────────────────

# chisel (TCP tunnel)
RUN CHISEL_VER=$(curl -sf https://api.github.com/repos/jpillora/chisel/releases/latest | grep tag_name | cut -d'"' -f4) && \
    curl -fsSL "https://github.com/jpillora/chisel/releases/download/${CHISEL_VER}/chisel_${CHISEL_VER#v}_linux_amd64.gz" | \
    gunzip > /opt/tools/bin/chisel && chmod +x /opt/tools/bin/chisel || \
    echo "[WARN] chisel download failed — install manually"

# pspy
RUN curl -fsSL https://github.com/DominicBreuker/pspy/releases/latest/download/pspy64 \
    -o /opt/tools/bin/pspy64 && chmod +x /opt/tools/bin/pspy64 || \
    echo "[WARN] pspy download failed"

# ROPgadget + ropper (pip)
RUN pip install --break-system-packages --no-cache-dir ROPgadget ropper

# checksec — shell script, not a pip package
RUN curl -sSL https://raw.githubusercontent.com/slimm609/checksec.sh/main/checksec \
    -o /usr/local/bin/checksec && chmod +x /usr/local/bin/checksec
# jwt_tool — PyPI package requires Python <3.11; install from GitHub for Python 3.12 compat
RUN git clone --depth 1 https://github.com/ticarpi/jwt_tool /opt/tools/jwt_tool && \
    pip install --break-system-packages --no-cache-dir -r /opt/tools/jwt_tool/requirements.txt && \
    ln -sf /opt/tools/jwt_tool/jwt_tool.py /usr/local/bin/jwt_tool && \
    chmod +x /opt/tools/jwt_tool/jwt_tool.py

# commix — PyPI version is a 0.1 stub; install real tool from GitHub
RUN git clone --depth 1 https://github.com/commixproject/commix /opt/tools/commix && \
    ln -sf /opt/tools/commix/commix.py /usr/local/bin/commix && \
    chmod +x /opt/tools/commix/commix.py

# NetExec (nxc) — PyPI package name is polluted; install from GitHub
# aardwolf (a netexec dependency) has a Rust extension — install cargo first
RUN apt-get update && apt-get install -y --no-install-recommends cargo rustc \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --break-system-packages --no-cache-dir \
    git+https://github.com/Pennyw0rth/NetExec.git

# No released impacket version (nor NetExec's dev-snapshot dependency) ships a
# krb5/pkinit.py module — getTGT.py has no -pfx flag upstream. Cert-based Kerberos
# auth (PKINIT) is provided by certipy-ad (already installed: `certipy auth -pfx ...`)
# and by PKINITtools (gettgtpkinit.py), installed here as a fallback/alternative.
RUN git clone --depth 1 https://github.com/dirkjanm/PKINITtools /opt/tools/PKINITtools && \
    pip install --break-system-packages --no-cache-dir -r /opt/tools/PKINITtools/requirements.txt && \
    for f in /opt/tools/PKINITtools/*.py; do \
        name="$(basename "$f" .py)"; \
        ln -sf "$f" "/usr/local/bin/$name"; \
        chmod +x "$f"; \
    done

# kerbrute — no PyPI/apt package; install prebuilt binary from GitHub releases
RUN curl -fsSL https://github.com/ropnop/kerbrute/releases/latest/download/kerbrute_linux_amd64 \
    -o /usr/local/bin/kerbrute && chmod +x /usr/local/bin/kerbrute || \
    echo "[WARN] kerbrute download failed"

# windapsearch — no real PyPI package; install script from GitHub
RUN git clone --depth 1 https://github.com/ropnop/windapsearch /opt/tools/windapsearch && \
    chmod +x /opt/tools/windapsearch/windapsearch.py && \
    ln -sf /opt/tools/windapsearch/windapsearch.py /usr/local/bin/windapsearch

# gMSADumper — managed service account password extraction
RUN git clone --depth 1 https://github.com/micahvandeusen/gMSADumper /opt/tools/gMSADumper && \
    (pip install --break-system-packages --no-cache-dir \
        -r /opt/tools/gMSADumper/requirements.txt 2>/dev/null || true) && \
    chmod +x /opt/tools/gMSADumper/gMSADumper.py && \
    ln -sf /opt/tools/gMSADumper/gMSADumper.py /usr/local/bin/gMSADumper || \
    echo "[WARN] gMSADumper install failed"

# enum4linux-ng — PyPI stub (wrong package); install from GitHub
RUN git clone --depth 1 https://github.com/cddmp/enum4linux-ng /opt/tools/enum4linux-ng && \
    pip install --break-system-packages --no-cache-dir -r /opt/tools/enum4linux-ng/requirements.txt && \
    ln -sf /opt/tools/enum4linux-ng/enum4linux-ng.py /usr/local/bin/enum4linux-ng && \
    chmod +x /opt/tools/enum4linux-ng/enum4linux-ng.py

# theHarvester — PyPI stub (0.0.1); install real package from GitHub URL.
# Pinned to 4.8.0: master now requires Python >=3.14, incompatible with Ubuntu 24.04's 3.12.
RUN pip install --break-system-packages --no-cache-dir \
    git+https://github.com/laramies/theHarvester.git@4.8.0

# graphw00f — no setup.py/pyproject.toml; clone and symlink main.py
RUN git clone --depth 1 https://github.com/dolevf/graphw00f /opt/tools/graphw00f && \
    (pip install --break-system-packages --no-cache-dir -r /opt/tools/graphw00f/requirements.txt 2>/dev/null || true) && \
    chmod +x /opt/tools/graphw00f/main.py && \
    ln -sf /opt/tools/graphw00f/main.py /usr/local/bin/graphw00f

# linPEAS + winPEAS (download at runtime or pre-bake)
RUN mkdir -p /opt/tools/privesc && \
    curl -fsSL https://github.com/carlospolop/PEASS-ng/releases/latest/download/linpeas.sh \
         -o /opt/tools/privesc/linpeas.sh && chmod +x /opt/tools/privesc/linpeas.sh || \
    echo "[WARN] linpeas download failed" && \
    curl -fsSL https://github.com/carlospolop/PEASS-ng/releases/latest/download/winPEASx64.exe \
         -o /opt/tools/privesc/winPEASx64.exe || \
    echo "[WARN] winpeas download failed"

# Windows post-exploitation binaries (pre-staged in /opt/tools/win/)
RUN mkdir -p /opt/tools/win && \
    CHISEL_VER=$(curl -sf https://api.github.com/repos/jpillora/chisel/releases/latest | grep tag_name | cut -d'"' -f4) && \
    curl -fsSL "https://github.com/jpillora/chisel/releases/download/${CHISEL_VER}/chisel_${CHISEL_VER#v}_windows_amd64.gz" | \
        gunzip > /opt/tools/win/chisel.exe || echo "[WARN] chisel.exe failed"

RUN SH_TAG=$(curl -sf https://api.github.com/repos/BloodHoundAD/SharpHound/releases/latest | grep tag_name | cut -d'"' -f4) && \
    curl -fsSL "https://github.com/BloodHoundAD/SharpHound/releases/download/${SH_TAG}/SharpHound-${SH_TAG}.zip" \
        -o /tmp/sh.zip 2>/dev/null && \
    (unzip -j /tmp/sh.zip "*/SharpHound.exe" -d /opt/tools/win/ 2>/dev/null || \
     unzip -j /tmp/sh.zip "SharpHound.exe" -d /opt/tools/win/ 2>/dev/null) && \
    rm -f /tmp/sh.zip || echo "[WARN] SharpHound.exe failed"

RUN curl -fsSL https://github.com/itm4n/PrintSpoofer/releases/latest/download/PrintSpoofer64.exe \
        -o /opt/tools/win/PrintSpoofer64.exe || echo "[WARN] PrintSpoofer64.exe failed"

RUN curl -fsSL https://github.com/ohpe/juicy-potato/releases/latest/download/JuicyPotato.exe \
        -o /opt/tools/win/JuicyPotato.exe || echo "[WARN] JuicyPotato.exe failed"

RUN curl -fsSL https://raw.githubusercontent.com/PowerShellMafia/PowerSploit/master/Recon/PowerView.ps1 \
        -o /opt/tools/win/PowerView.ps1 || echo "[WARN] PowerView.ps1 failed"

RUN MK_TAG=$(curl -sf https://api.github.com/repos/gentilkiwi/mimikatz/releases/latest | grep tag_name | cut -d'"' -f4) && \
    curl -fsSL "https://github.com/gentilkiwi/mimikatz/releases/download/${MK_TAG}/mimikatz_trunk.zip" \
        -o /tmp/mk.zip 2>/dev/null && \
    unzip -j /tmp/mk.zip "x64/mimikatz.exe" -d /opt/tools/win/ && \
    rm -f /tmp/mk.zip || echo "[WARN] mimikatz.exe failed"

# Rubeus — no official pre-built from GhostPack; using r3motecontrol/Ghostpack-CompiledBinaries (community)
RUN curl -fsSL https://github.com/r3motecontrol/Ghostpack-CompiledBinaries/raw/master/Rubeus.exe \
        -o /opt/tools/win/Rubeus.exe || echo "[WARN] Rubeus.exe failed"

# procdump64.exe — use -accepteula at runtime
RUN curl -fsSL https://download.sysinternals.com/files/Procdump.zip \
        -o /tmp/procdump.zip 2>/dev/null && \
    unzip -j /tmp/procdump.zip procdump64.exe -d /opt/tools/win/ && \
    rm -f /tmp/procdump.zip || echo "[WARN] procdump64.exe failed"

# pwndbg (GDB enhancement)
RUN git clone --depth 1 https://github.com/pwndbg/pwndbg /opt/tools/pwndbg && \
    cd /opt/tools/pwndbg && ./setup.sh --quiet 2>/dev/null || \
    echo "[WARN] pwndbg setup failed"

# testssl.sh
RUN git clone --depth 1 https://github.com/drwetter/testssl.sh /opt/tools/testssl.sh && \
    ln -s /opt/tools/testssl.sh/testssl.sh /usr/local/bin/testssl.sh

# ExploitDB / searchsploit (not an Ubuntu apt package — clone from GitLab)
RUN git clone --depth 1 https://gitlab.com/exploit-database/exploitdb /opt/tools/exploitdb && \
    ln -sf /opt/tools/exploitdb/searchsploit /usr/local/bin/searchsploit && \
    cp /opt/tools/exploitdb/.searchsploit_rc /root/.searchsploit_rc && \
    cp /opt/tools/exploitdb/.searchsploit_rc /home/$CTF_USER/.searchsploit_rc && \
    chown $CTF_USER:$CTF_USER /home/$CTF_USER/.searchsploit_rc

# ─── Wordlists ────────────────────────────────────────────────────────────────

# SecLists — not an Ubuntu apt package; clone from GitHub
RUN git clone --depth 1 https://github.com/danielmiessler/SecLists /opt/wordlists/SecLists

# rockyou.txt
RUN if [ -f /usr/share/wordlists/rockyou.txt ]; then \
      ln -sf /usr/share/wordlists/rockyou.txt /opt/wordlists/rockyou.txt; \
    elif [ -f /usr/share/wordlists/rockyou.txt.gz ]; then \
      gunzip -k /usr/share/wordlists/rockyou.txt.gz && \
      ln -sf /usr/share/wordlists/rockyou.txt /opt/wordlists/rockyou.txt; \
    else \
      curl -fsSL https://github.com/brannondorsey/naive-hashcat/releases/download/data/rockyou.txt \
           -o /opt/wordlists/rockyou.txt || echo "[WARN] rockyou download failed"; \
    fi

# ─── Proxychains config ───────────────────────────────────────────────────────

# Use workspace config when present (analyst can drop .proxychains-agent.conf in /workspace)
RUN echo '[ -f /workspace/.proxychains-agent.conf ] && \
    export PROXYCHAINS_CONF_FILE=/workspace/.proxychains-agent.conf' \
    >> /etc/profile.d/proxychains.sh

# ─── Nuclei templates ─────────────────────────────────────────────────────────

RUN nuclei -update-templates 2>/dev/null || echo "[WARN] nuclei template update failed"
# ─── Playwright (browser automation for HTBAgent) ────────────────────────────

RUN pip install --break-system-packages --no-cache-dir playwright && \
    playwright install chromium --with-deps 2>/dev/null || \
    echo "[WARN] playwright chromium install failed"

# ─── HTB API helper ──────────────────────────────────────────────────────────

COPY htb_api.py /workspace/htb_api.py
RUN chmod +x /workspace/htb_api.py

# ─── Helper scripts ───────────────────────────────────────────────────────────

COPY scripts/dcc2reformat.py /usr/local/bin/dcc2reformat
RUN chmod +x /usr/local/bin/dcc2reformat

# ─── GitHub CLI + Copilot CLI ────────────────────────────────────────────────

RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg && \
    chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    | tee /etc/apt/sources.list.d/github-cli.list > /dev/null && \
    apt-get update && apt-get install -y --no-install-recommends gh && \
    rm -rf /var/lib/apt/lists/*

# Install gh copilot extension (public extension — no auth needed at build time)
# Authenticate at runtime: export GITHUB_TOKEN=ghp_... or: gh auth login
USER $CTF_USER
ENV HOME=/home/$CTF_USER
ENV GOPATH=/home/$CTF_USER/go
ENV PATH="/home/$CTF_USER/.local/bin:/home/$CTF_USER/go/bin:/opt/go/bin:/usr/local/bin:/opt/tools/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin"

# Open Interpreter CLI
RUN curl -fsSL https://www.openinterpreter.com/install | \
    OPEN_INTERPRETER_NONINTERACTIVE=1 sh

RUN gh extension install github/gh-copilot 2>/dev/null || \
    echo "[WARN] gh copilot extension install failed — run 'gh auth login && gh extension install github/gh-copilot' at runtime"

# ─── Claude Code CLI ──────────────────────────────────────────────────────────
# Authenticate at runtime: export ANTHROPIC_API_KEY=... or: claude login
RUN curl -fsSL https://claude.ai/install.sh | bash || \
    echo "[WARN] claude cli install failed — run 'curl -fsSL https://claude.ai/install.sh | bash' at runtime"

USER root

# ─── Final pycares/aiodns re-pin ──────────────────────────────────────────────
# NetExec's aardwolf dependency (installed above) silently downgrades pycares
# to a version aiodns.DNSResolver can't import against (missing
# ares_query_a_result). Every RUN pip install resolves independently, so this
# MUST be the last pip step touching these two packages.
RUN pip install --break-system-packages --no-cache-dir -U "pycares>=4.6" "aiodns>=3.2"

# Let ctf patch/live-debug installed Python packages (e.g. impacket) without
# needing sudo — must run after every pip-install step above (they all run
# as root and would otherwise re-root-own anything installed later). Build
# already runs fully as root doing far more invasive things, so this adds
# no risk.
RUN dist_packages="$(python3 -c 'import sysconfig; print(sysconfig.get_path("purelib"))')" && \
    chown -R "$CTF_USER:$CTF_USER" "$dist_packages"

# ─── Agent definitions ────────────────────────────────────────────────────────

COPY agents/ /workspace/agents/
COPY proxywrap.sh /workspace/proxywrap.sh
RUN chmod +x /workspace/proxywrap.sh

# ─── CTF context template ─────────────────────────────────────────────────────

COPY Templates/ /workspace/Templates/

# ─── Small Model Orchestrator web UI ─────────────────────────────────────────

COPY --from=orchestrator-build /out/ /opt/small-model-orchestrator/
RUN chmod +x /opt/small-model-orchestrator/small-model-orchestrator

# ─── Entrypoint ───────────────────────────────────────────────────────────────

RUN mkdir -p /workspace/loot /home/$CTF_USER/.cache /home/$CTF_USER/.config && \
    chown -R $CTF_USER:$CTF_USER /workspace /home/$CTF_USER

COPY egress-control.sh /usr/local/sbin/egress-control.sh
COPY entrypoint.sh /usr/local/sbin/entrypoint.sh
RUN chmod +x /usr/local/sbin/egress-control.sh /usr/local/sbin/entrypoint.sh

# Container starts as root so entrypoint.sh can apply the egress-control
# allowlist (needs CAP_NET_ADMIN) before dropping privileges itself via
# gosu — see README "Egress Control". No blanket sudo exists for ctf;
# see README "Runtime privilege model" for what that used to cover and how
# it's handled now (file capabilities / build-time ownership instead).
ENTRYPOINT ["/usr/local/sbin/entrypoint.sh"]
CMD ["/bin/bash"]
