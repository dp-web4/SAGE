#!/bin/bash
# The governance source the governed may read (dp, 2026-10-19: "the governed should see the law and how it's
# applied"; source reads by request, seat-approvable).
#
# A READ-ONLY SNAPSHOT, BECAUSE A SCOPE GRANT IS REACH, NOT READ-ONLY. hestia grants a path, not an access mode:
# a grant on a writable tree would also let a being's memory_write into it. Here the filesystem refuses writes
# (every file and directory a-w), so any grant on it reads only. It is `git archive` of hestia's main (what the
# fleet deploys from), so it carries tracked source only: no .git, no local or ignored files, nothing from
# ~/.hestia (the vault and its passphrase live there; that is never the governance path).
#
# Usage: governance_snapshot.sh [hestia_clone] [dest]
#   source: the clone named here; else $HESTIA_DEPLOY_SRC (the deploy's own clone, exported to post-deploy
#           steps); else <workspace>/hestia (or <workspace>/HESTIA)
#   dest:   <workspace>/governance/hestia
# Idempotent: rebuilds into a temp dir, swaps it in, records the commit in dest/SNAPSHOT.
#
# THE SOURCE'S GIT CONFIG IS NOT TRUSTED (cbp-claude, 2026-10-23). The default source is the shared hestia
# checkout, and every governed member session can write it, its .git included. git obeys a repo's own config,
# and several keys there run a command: measured on git 2.43, a fetch/rev-parse/archive/status pass over a
# clone whose config names them ran core.fsmonitor, core.sshCommand, remote.<r>.uploadpack, and (through a
# repo-local core.hooksPath) a reference-transaction hook. This script runs with whoever invokes it: the
# operator by hand, or the deploy as a post-deploy step (hestia #1368). Either way a member would choose what
# that principal executes. So:
#   - a deploy step reads the deploy's OWN clone ($HESTIA_DEPLOY_SRC), which no member grant reaches, and does
#     not fetch it (the deploy just synced it to the build it deployed). A deploy step that is not given that
#     clone refuses rather than falling back to the shared checkout;
#   - with no private clone, a source that is not owned by the invoker alone (or whose git dir or config is
#     group/world-writable) is refused. On a box where members run as the operator's own uid this cannot tell
#     a member from the operator, which is why the deploy path above does not rely on it;
#   - every git call, on any source, ignores system and global config and overrides each command-running key
#     the measurement found, plus the transports that run local programs (`g` below). That is the backstop,
#     not the boundary: a denylist of keys is only as complete as the list.
set -eu
# THE WORKSPACE IS WHERE THIS SCRIPT LIVES, never a literal path (fleet directive: no hardcoded paths).
# scripts/ sits in the SAGE checkout, which sits in the workspace: ai-workspace on most boxes, ai-agents on
# nomad. HESTIA_WORKSPACE overrides, as it does for the gate.
WS="${HESTIA_WORKSPACE:-$(cd "$(dirname "$(readlink -f "$0")")/../.." && pwd)}"
HESTIA_SRC="$WS/hestia"; [ -e "$HESTIA_SRC/.git" ] || [ ! -e "$WS/HESTIA/.git" ] || HESTIA_SRC="$WS/HESTIA"
DEST="${2:-$WS/governance/hestia}"
PRIVATE=0
if [ -n "${1:-}" ]; then
  SRC="$1"; CLONE="named on the command line"
elif [ -n "${HESTIA_DEPLOY_SRC:-}" ]; then
  SRC="$HESTIA_DEPLOY_SRC"; CLONE="the deploy's own clone"; PRIVATE=1
elif [ -n "${HESTIA_DEPLOYED_BUILD:-}" ]; then
  echo "governance snapshot: refused: run as a post-deploy step without HESTIA_DEPLOY_SRC; the shared checkout" \
       "is member-writable and is never read with the deploy's privileges" >&2
  exit 3
else
  SRC="$HESTIA_SRC"; CLONE="the shared checkout"
fi

# git, with nothing from the source's own config that can run a command (see the header).
g() {
  GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null git \
    -c core.fsmonitor= -c core.sshCommand=ssh -c core.hooksPath=/dev/null \
    -c core.alternateRefsCommand= -c credential.helper= -c core.askPass= \
    -c protocol.allow=never -c protocol.https.allow=always -c protocol.ssh.allow=always \
    -C "$SRC" "$@"
}

# Owned by the invoker and writable by no one else (-perm -g+w / -o+w: BSD find has no `/`).
# GROUP-WRITABLE IN A PRIVATE GROUP IS STILL OWNER-ONLY (pub-claude, 2026-10-23). Ubuntu gives each user a
# group of their own and a umask of 002, so every clone there is g+w: on pub the hourly snapshot refused its
# own checkout from the hour #520 landed. A group bit reaches someone else only if the group has someone
# else in it, so g+w passes when the file's group lists no member but the invoker and is no other account's
# primary group. Without getent (macOS) that cannot be asked, and g+w is refused as before; a gid with no
# group entry is refused too. The check is absence-of-evidence: it trusts getent to enumerate every account,
# which holds on files-backed hosts (pub, cbp, HUB) but not under sssd/LDAP with enumeration off.
private_group() {
  command -v getent >/dev/null 2>&1 || return 1
  pg_gid="$(stat -c %g "$1" 2>/dev/null || stat -f %g "$1" 2>/dev/null)" || return 1
  pg_me="$(id -un)"
  pg_entry="$(getent group "$pg_gid")" || return 1
  pg_members="$(printf '%s\n' "$pg_entry" | cut -d: -f4)"
  [ -z "$pg_members" ] || [ "$pg_members" = "$pg_me" ] || return 1
  [ -z "$(getent passwd | awk -F: -v g="$pg_gid" -v me="$pg_me" '$4 == g && $1 != me')" ]
}
owner_only() {
  [ -e "$1" ] && [ -O "$1" ] || return 1
  [ -z "$(find "$1" -maxdepth 0 -perm -o+w 2>/dev/null || true)" ] || return 1
  [ -z "$(find "$1" -maxdepth 0 -perm -g+w 2>/dev/null || true)" ] || private_group "$1"
}
if [ "$PRIVATE" -eq 0 ]; then
  GITDIR="$(g rev-parse --absolute-git-dir 2>/dev/null || true)"
  if ! owner_only "$SRC" || [ -z "$GITDIR" ] || ! owner_only "$GITDIR" \
      || { [ -e "$GITDIR/config" ] && ! owner_only "$GITDIR/config"; }; then
    echo "governance snapshot: refused: $SRC (or its git dir/config) is not owned by $(id -un) alone" >&2
    exit 3
  fi
  # A fetch that fails (offline, or a transport the overrides refuse) leaves the clone's refs as they are.
  g fetch -q origin main || echo "governance snapshot: fetch failed; using $SRC as it is" >&2
fi
MAIN="$(g rev-parse -q --verify origin/main^{commit} 2>/dev/null || g rev-parse HEAD)"
# THE DEPLOYED BUILD, WHEN KNOWN (cbp-claude, 2026-10-19). Log lines a member sees name file:line in the DEPLOYED
# tree; a snapshot of main shows unrelated code at that line (CBP: the log's http.rs:1436 was http.rs:1819 on
# main), and that becomes a new mystery. hestia records the deployed commit in current-build.json (head_sha).
#
# ASKED OF THE DAEMON, NOT READ FROM ~/.hestia (cbp-claude, 2026-10-20). Any member with the workspace may run
# this, and ~/.hestia is outside every member's grant: a script that opened current-build.json would be reaching
# it by a route the gate never sees. The running daemon publishes the same commit on /api/version (build_id
# "...-g<sha>"), at the endpoint the gate already uses (HESTIA_ENDPOINT). An operator may still name a build
# file explicitly with HESTIA_CURRENT_BUILD_FILE. Neither answering falls back to main, and SNAPSHOT says which.
# A post-deploy step is told the build it follows (HESTIA_DEPLOYED_BUILD, a `git describe`); that answer comes
# first, since the daemon may not be serving it yet.
DEPLOYED=""
if [ -n "${HESTIA_DEPLOYED_BUILD:-}" ]; then
  case "$HESTIA_DEPLOYED_BUILD" in *-g*) DEPLOYED="${HESTIA_DEPLOYED_BUILD##*-g}" ;; *) DEPLOYED="$HESTIA_DEPLOYED_BUILD" ;; esac
  HOW="the deploy that ran this step (HESTIA_DEPLOYED_BUILD)"
fi
if [ -z "$DEPLOYED" ]; then
  API="${HESTIA_ENDPOINT:-http://127.0.0.1:7711/mcp}"; API="${API%/mcp}/api/version"
  DEPLOYED="$(curl -fsS --max-time 5 "$API" 2>/dev/null | python3 -c "import json,sys; b=json.load(sys.stdin).get('build_id') or ''; print(b.rsplit('-g',1)[1] if '-g' in b else '')" 2>/dev/null || true)"
  HOW="the running daemon's /api/version"
fi
if [ -z "$DEPLOYED" ] && [ -n "${HESTIA_CURRENT_BUILD_FILE:-}" ]; then
  DEPLOYED="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('head_sha') or '')" "$HESTIA_CURRENT_BUILD_FILE" 2>/dev/null || true)"
  HOW="current-build.json head_sha"
fi
if [ -n "$DEPLOYED" ]; then DEPLOYED="$(g rev-parse --verify -q "$DEPLOYED^{commit}" 2>/dev/null || echo "$DEPLOYED")"; fi
if [ -n "$DEPLOYED" ] && g cat-file -e "$DEPLOYED^{commit}" 2>/dev/null; then
  REV="$DEPLOYED"; BASIS="the deployed build ($HOW)"
else
  REV="$MAIN"
  BASIS="origin/main ($( [ -n "$DEPLOYED" ] && echo "deployed $DEPLOYED is not in this clone" || echo "deployed build unknown here" ))"
fi
if [ -f "$DEST/SNAPSHOT" ] && grep -q "^commit: $REV$" "$DEST/SNAPSHOT" && grep -q "^deployed: ${DEPLOYED:-unknown}$" "$DEST/SNAPSHOT"; then
  echo "governance snapshot already at $REV"; exit 0
fi
PARENT="$(dirname "$DEST")"
mkdir -p "$PARENT"
TMP="$PARENT/.hestia.new"
[ -d "$TMP" ] && chmod -R u+w "$TMP" && rm -rf "$TMP"
mkdir -p "$TMP"
g archive "$REV" | tar -x -C "$TMP"
printf 'source: dp-web4/hestia\ncommit: %s\nbasis: %s\ndeployed: %s\nmain: %s\nclone: %s\nmade: %s\nread-only: every file and directory is non-writable, so a member'"'"'s own writes fail here. The owner can still chmod; a run that chmods this tree is a self-governance write.\n' \
  "$REV" "$BASIS" "${DEPLOYED:-unknown}" "$MAIN" "$CLONE" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$TMP/SNAPSHOT"
chmod -R a-w "$TMP"
if [ -d "$DEST" ]; then
  OLD="$PARENT/.hestia.old"
  [ -d "$OLD" ] && chmod -R u+w "$OLD" && rm -rf "$OLD"
  chmod u+w "$PARENT"
  mv "$DEST" "$OLD"
fi
mv "$TMP" "$DEST"
[ -d "$PARENT/.hestia.old" ] && chmod -R u+w "$PARENT/.hestia.old" && rm -rf "$PARENT/.hestia.old"
echo "governance snapshot now at $REV ($(find "$DEST" -type f | wc -l) files, read-only)"
