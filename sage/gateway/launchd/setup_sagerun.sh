#!/bin/bash
# One-time McNugget setup for SAGE `run` under Seatbelt: the being's sandboxed code runs as a separate,
# unprivileged, hidden user, so it cannot read other processes' arguments or environment (the kernel
# shows kern.procargs2 only to the same uid or root; Seatbelt does not govern it -- measured 2026-10-18).
#
# Run as the operator:   sudo bash sage/gateway/launchd/setup_sagerun.sh
# (SEAT below is the account the heartbeat runs as; edit it on another Mac.)
# Idempotent. Undo:      sudo dscl . -delete /Users/_sagerun ; sudo rm /etc/sudoers.d/sage-run
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }

USER_NAME=_sagerun
RUN_UID=401
SEAT=dennispalatov

if ! dscl . -read "/Users/$USER_NAME" >/dev/null 2>&1; then
  dscl . -create "/Users/$USER_NAME"
  dscl . -create "/Users/$USER_NAME" UniqueID "$RUN_UID"
  # staff (20): the seat's home is drwxr-x--- dennispalatov:staff, and the run must reach the
  # interpreter and the worktree under it. Seatbelt, not the uid, is the file wall; the uid is the
  # process wall.
  dscl . -create "/Users/$USER_NAME" PrimaryGroupID 20
  dscl . -create "/Users/$USER_NAME" UserShell /usr/bin/false
  dscl . -create "/Users/$USER_NAME" NFSHomeDirectory /var/empty
  dscl . -create "/Users/$USER_NAME" RealName "SAGE run sandbox"
  dscl . -create "/Users/$USER_NAME" IsHidden 1
  dscl . -create "/Users/$USER_NAME" Password "*"
fi

# The seat may start sandbox-exec as _sagerun, and stop what it started (the watchdog's kill), and
# nothing else, without a password. _sagerun itself has no sudo at all.
TMP=$(mktemp)
cat > "$TMP" <<EOF
# SAGE run (McNugget): the being's sandboxed code runs as $USER_NAME (setup_sagerun.sh, 2026-10-18)
# umask 0007 for its commands: what a run creates is group (staff) writable, so the seat can delete
# the run's dirs afterwards
Defaults>$USER_NAME umask=0007, umask_override
$SEAT ALL=($USER_NAME) NOPASSWD: /usr/bin/sandbox-exec, /bin/kill
EOF
visudo -cf "$TMP"
install -m 0440 -o root -g wheel "$TMP" /etc/sudoers.d/sage-run
rm -f "$TMP"
grep -q '^#includedir /private/etc/sudoers.d' /etc/sudoers || echo "WARNING: /etc/sudoers has no includedir for sudoers.d"

id "$USER_NAME"
sudo -u "$SEAT" sudo -n -u "$USER_NAME" /usr/bin/sandbox-exec -p '(version 1)(allow default)' /usr/bin/id -un
echo "ok"
