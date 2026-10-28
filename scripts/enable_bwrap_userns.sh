#!/usr/bin/env bash
# Let bubblewrap (and only bubblewrap) create user namespaces under Ubuntu 24.04's
# kernel.apparmor_restrict_unprivileged_userns=1, so the being's `run` sandbox works.
# See sage/gateway/being_gate_client.py ENABLEMENT.
#
# OPERATOR ONLY, BY HAND. It needs root, and nothing in SAGE runs it: no gateway start-up, no
# beat, no verb (test_no_sage_code_runs_the_userns_setup). A being's `run` is in a sandbox with no
# root and no /etc, and its request_run goes to a seat, which declines sudo.
#
# WHAT IT CHANGES ON THE HOST. One AppArmor profile, /etc/apparmor.d/bwrap, which lets any process
# that executes /usr/bin/bwrap, for any user, create an unprivileged user namespace. The kernel
# setting stays 1 for every other binary; the alternative, setting it to 0, would open user
# namespaces to every program on the machine. What remains: any local user can now use bwrap's
# namespaces, as on distributions without the restriction (Ubuntu ships the same pattern for
# flatpak, crun and ch-run). The profile is unconfined apart from that: it adds no other permission.
#
# ONLY ITS OWN PROFILE. A profile this script wrote carries the marker line below. One without it
# (the distro's, or another tool's) is refused by both setup and --remove: neither loads, replaces,
# unloads nor deletes it. To hand such a profile to this script, delete it first (that is the
# operator's decision, made explicitly), then run setup.
#
# REVERSAL: sudo bash enable_bwrap_userns.sh --remove
# Unloads the profile, checks the kernel no longer holds it, and only then deletes the file. If the
# unload fails the file stays, so the rollback can be retried, and it exits non-zero
# (test_bwrap_setup_remove_keeps_the_profile_when_unload_fails). After removal `run` on this box
# refuses again ("run needs its sandbox and cannot get one"); it never falls back to running
# unsandboxed (test_run_fails_closed_when_no_sandbox_is_usable).
#
# Usage: sudo bash enable_bwrap_userns.sh [--remove]
set -euo pipefail

PROFILE=/etc/apparmor.d/bwrap
LOADED=/sys/kernel/security/apparmor/profiles
BWRAP=/usr/bin/bwrap
MARK="# written by SAGE scripts/enable_bwrap_userns.sh"

[ "$(id -u)" -eq 0 ] || { echo "run with sudo"; exit 1; }

is_loaded() { grep -q "^bwrap " "$LOADED" 2>/dev/null; }
ours() { grep -qxF "$MARK" "$PROFILE"; }

if [ "${1:-}" = "--remove" ]; then
  [ -e "$PROFILE" ] || { echo "$PROFILE is not there; nothing to remove"; exit 0; }
  ours || { echo "$PROFILE was not written by this script; leaving it (loaded and on disk) as it is"; exit 1; }
  if is_loaded; then
    if ! apparmor_parser -R "$PROFILE"; then
      echo "could not unload the bwrap profile; it is still active and $PROFILE is kept so this can be retried"
      exit 3
    fi
    if is_loaded; then
      echo "the kernel still holds the bwrap profile after unload; $PROFILE is kept so this can be retried"
      exit 3
    fi
  fi
  rm -f "$PROFILE"
  echo "unloaded and removed $PROFILE; bwrap user namespaces are restricted again"
  exit 0
fi

[ -x "$BWRAP" ] || { echo "bubblewrap not installed: apt install bubblewrap"; exit 1; }
[ -n "${SUDO_USER:-}" ] || { echo "run through sudo from the account that runs the beings"; exit 1; }

echo "restrict_unprivileged_userns = $(cat /proc/sys/kernel/apparmor_restrict_unprivileged_userns 2>/dev/null || echo n/a)"

if [ -e "$PROFILE" ]; then
  ours || { echo "$PROFILE exists and was not written by this script; not loading or replacing it."
            echo "If it should be replaced, delete it yourself first, then run this again."; exit 1; }
  echo "$PROFILE (written by this script) already exists; reloading it"
else
  cat > "$PROFILE" <<EOF
$MARK
abi <abi/4.0>,
include <tunables/global>

profile bwrap /usr/bin/bwrap flags=(unconfined) {
  userns,

  include if exists <local/bwrap>
}
EOF
  echo "wrote $PROFILE"
fi

apparmor_parser -r "$PROFILE"
echo "profile loaded"

# The same probe SAGE uses (sandbox_available), run as the user who invoked sudo.
if sudo -u "$SUDO_USER" "$BWRAP" --ro-bind /usr /usr --ro-bind /lib /lib --ro-bind-try /lib64 /lib64 \
     --unshare-pid /usr/bin/true; then
  echo "sandbox ok for $SUDO_USER"
else
  echo "sandbox STILL FAILS for $SUDO_USER"; exit 2
fi
