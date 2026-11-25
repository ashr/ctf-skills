#!/usr/bin/env bash
# entrypoint.sh — root-run container entrypoint.
#
# Applies the egress-control allowlist (no-ops cleanly when CTF_TARGETS and
# ctf-context.yaml's target.ip are both unset), starts its background
# refresh loop, then drops privileges to the ctf user and execs the real
# command (/bin/bash by default, or the small-model-orchestrator override
# when CTF_WEB_UI=1 — see run-ctf.sh).
#
# gosu (not sudo/su) is used to drop privileges for correct TTY/signal
# forwarding under `docker run -it`.

set -eu

CTF_USER="${CTF_USER:-ctf}"

/usr/local/sbin/egress-control.sh --apply-once

( /usr/local/sbin/egress-control.sh --watch >>/var/log/egress-control.log 2>&1 & disown )

exec gosu "$CTF_USER" "$@"
