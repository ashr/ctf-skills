# ══════════════════════════════════════════════════════════════════════════════
# Dockerfile — blank LLM sandbox harness
# ══════════════════════════════════════════════════════════════════════════════
#
# Egress-controlled, non-root container for running an LLM agent's shell
# access somewhere contained. No offensive tooling, no agent personas — just
# the sandbox: a user with no sudo, and a root-run entrypoint that applies an
# nftables allowlist before dropping privileges to that user.
#
# Build:
#   docker build -t llm-harness .
#   (certs/ must exist in the build context — empty dir is fine if you have
#   no corporate CA to trust)
#
# Run:
#   docker run --rm -it \
#     --cap-add NET_ADMIN \
#     --security-opt no-new-privileges \
#     -e SANDBOX_TARGETS=api.example.com \
#     -v $(pwd):/workspace \
#     llm-harness
#
# ══════════════════════════════════════════════════════════════════════════════

FROM ubuntu:24.04

ARG DEBIAN_FRONTEND=noninteractive
ARG HARNESS_USER=agent
ARG HARNESS_UID=1000
ARG HARNESS_GID=1000

# ─── Base system ──────────────────────────────────────────────────────────────

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl \
    nftables gosu dnsutils \
    && rm -rf /var/lib/apt/lists/*

# ─── Corporate CA certificates ───────────────────────────────────────────────
# certs/ must exist in the build context (COPY fails otherwise) — empty dir
# is fine if you have no TLS-inspecting proxy to trust. Only .crt files are
# registered; rename .pem -> .crt.

COPY certs/ /usr/local/share/ca-certificates/
RUN update-ca-certificates

# Dedicated custom-CA-only bundle for tools/runtimes whose TLS stack is
# stricter than OpenSSL's and chokes on the full multi-hundred-cert system
# bundle (seen with some Node-based CLIs). Harmless to build even if nothing
# inside this container ends up needing it.
RUN { for f in /usr/local/share/ca-certificates/*.crt; do \
         [ -f "$f" ] || continue; \
         cat "$f"; \
         echo; \
       done; } > /etc/ssl/certs/custom-ca-certs.pem

ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV CURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV GIT_SSL_CAINFO=/etc/ssl/certs/ca-certificates.crt
ENV NODE_EXTRA_CA_CERTS=/etc/ssl/certs/custom-ca-certs.pem

# ─── Non-root user, no sudo ───────────────────────────────────────────────────
# This is the actual security property the egress allowlist depends on: the
# agent user can never regain root (no sudo, nothing setuid/setcap beyond
# stock distro binaries), so it can never flush/modify the nftables rules
# entrypoint.sh applies below it.

RUN set -eux; \
    if getent group "$HARNESS_GID" >/dev/null; then \
        group_name="$(getent group "$HARNESS_GID" | cut -d: -f1)"; \
        if [ "$group_name" != "$HARNESS_USER" ]; then groupmod --new-name "$HARNESS_USER" "$group_name"; fi; \
    else \
        groupadd --gid "$HARNESS_GID" "$HARNESS_USER"; \
    fi; \
    if getent passwd "$HARNESS_UID" >/dev/null; then \
        user_name="$(getent passwd "$HARNESS_UID" | cut -d: -f1)"; \
        if [ "$user_name" != "$HARNESS_USER" ]; then usermod --login "$HARNESS_USER" --home "/home/$HARNESS_USER" --move-home "$user_name"; fi; \
        usermod --gid "$HARNESS_GID" --shell /bin/bash "$HARNESS_USER"; \
    else \
        useradd --uid "$HARNESS_UID" --gid "$HARNESS_GID" --create-home --shell /bin/bash "$HARNESS_USER"; \
    fi; \
    usermod --groups "" "$HARNESS_USER"; \
    mkdir -p "/home/$HARNESS_USER/.local/bin"; \
    chown -R "$HARNESS_USER:$HARNESS_USER" "/home/$HARNESS_USER"

ENV HOME=/home/$HARNESS_USER
ENV WORKSPACE=/workspace
ENV HARNESS_USER=$HARNESS_USER
ENV PATH="/home/$HARNESS_USER/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

RUN mkdir -p /workspace && chown -R "$HARNESS_USER:$HARNESS_USER" /workspace
WORKDIR /workspace

# ─── Add your own agent/runtime here ─────────────────────────────────────────
# e.g.:
#   RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip && rm -rf /var/lib/apt/lists/*
#   COPY my_agent/ /opt/my_agent/
#   RUN pip install --break-system-packages -r /opt/my_agent/requirements.txt

# ─── Entrypoint ───────────────────────────────────────────────────────────────
# No final USER directive — the container must start as root so
# entrypoint.sh can apply the egress-control allowlist (needs CAP_NET_ADMIN)
# before dropping privileges itself via gosu.

COPY egress-control.sh /usr/local/sbin/egress-control.sh
COPY entrypoint.sh /usr/local/sbin/entrypoint.sh
RUN chmod +x /usr/local/sbin/egress-control.sh /usr/local/sbin/entrypoint.sh

ENTRYPOINT ["/usr/local/sbin/entrypoint.sh"]
CMD ["/bin/bash"]
