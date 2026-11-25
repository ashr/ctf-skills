#!/usr/bin/env bash
# entrypoint.sh — root-run container entrypoint.
#
# Applies the egress-control allowlist (no-ops cleanly when SANDBOX_TARGETS
# is unset), starts its background refresh loop, then drops privileges to
# the non-root harness user and execs the real command (/bin/bash by
# default, or whatever CMD/override you pass).
#
# gosu (not sudo/su) is used to drop privileges for correct TTY/signal
# forwarding under `docker run -it`.

set -eu

HARNESS_USER="${HARNESS_USER:-agent}"

/usr/local/sbin/egress-control.sh --apply-once

( /usr/local/sbin/egress-control.sh --watch >>/var/log/egress-control.log 2>&1 & disown )

exec gosu "$HARNESS_USER" "$@"
