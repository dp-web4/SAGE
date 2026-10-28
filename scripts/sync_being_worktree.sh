#!/usr/bin/env bash
# Sync a being's worktree forward WITHOUT destroying its work.
#
#   scripts/sync_being_worktree.sh <worktree> [ref] [member]
#     ref     the branch it follows (default main)
#     member  whose worktree it is (default: the worktree directory's name, e.g. mcnugget-being);
#             the being works on <member>/work, and its PR verbs read that branch's upstream as
#             the base (being_gate_client.pr_base_branch).
#
# Ported to main from Legion's carrier (2026-10-23), where it was written for legion-being alone
# (hard-coded legion-being/work and legion/mission-artifact). McNugget's seat never had it: its
# being's worktree sat on a detached HEAD from 2026-10-03 for three weeks, so every git_read and
# search showed three-week-old code, and the being spent whole beats looking in it for a file that
# had never been in SAGE.
#
# Until M1 the seat synced with `git reset --hard`, which was fine while the being could only
# read its tree. It can write it now. A hard reset would silently delete a test it has been
# authoring across beats — the exact kind of loss that would look, from its side, like the
# world eating its work. So: fast-forward only, never destructive; otherwise say why.
#
# UNTRACKED FILES DO NOT BLOCK A FAST-FORWARD. git already refuses a fast-forward that would
# clobber an untracked file, and says which. MODIFIED TRACKED files stop the sync (that is the
# being's work in progress); untracked files do not, and are named so the record shows what
# was carried across. The being has no delete verb, so a script that froze on its scratch files
# left it unable to unblock itself (Legion, 09-08 and 09-09).
set -euo pipefail
# Hooks OFF for every git this script runs in the being's worktree: .githooks is a tracked
# directory the being can write (M1), and checkout/merge run post-checkout/post-merge hooks as the
# seat (2026-09-25).
export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null
WT="${1:?usage: sync_being_worktree.sh <worktree> [ref] [member]}"
REF="${2:-main}"
MEMBER="${3:-$(basename "$WT")}"
WORK="$MEMBER/work"
cd "$WT"

# Tracked-and-modified (or staged) only. `--porcelain` prefixes untracked lines with '??'.
DIRTY_TRACKED="$(git status --porcelain --untracked-files=no)"
if [ -n "$DIRTY_TRACKED" ]; then
  echo "NOT SYNCED: $WT has modified tracked files (the being's work). Leaving it alone." >&2
  echo "$DIRTY_TRACKED" >&2
  exit 3
fi

UNTRACKED="$(git ls-files --others --exclude-standard)"
if [ -n "$UNTRACKED" ]; then
  echo "carrying $(echo "$UNTRACKED" | wc -l | tr -d ' ') untracked file(s) across the sync:" >&2
  echo "$UNTRACKED" | sed 's/^/  /' >&2
fi

# Fetch BEFORE the branch check: deciding whether a PR branch is still live needs to know
# where the base is now.
git fetch -q origin "$REF"

BR="$(git rev-parse --abbrev-ref HEAD)"
if [ "$BR" != "$WORK" ]; then
  # A DETACHED HEAD OR A PR BRANCH WHOSE WORK IS ALREADY IN THE BASE strands the being (Legion
  # 2026-09-14: parked on its merged camera-verb branch, watching PRs it could no longer observe).
  # The discriminator is containment: if HEAD is an ancestor of the base, returning to
  # <member>/work loses nothing. If it is NOT, an open PR is still live and the sync refuses.
  if git merge-base --is-ancestor HEAD FETCH_HEAD 2>/dev/null; then
    if git show-ref -q --verify "refs/heads/$WORK"; then
      echo "'$BR' is fully contained in $REF; returning to $WORK" >&2
      git checkout -q "$WORK" || { echo "NOT SYNCED: could not return to $WORK from '$BR'" >&2; exit 7; }
    else
      echo "'$BR' is fully contained in $REF; creating $WORK here" >&2
      git checkout -q -b "$WORK" || { echo "NOT SYNCED: could not create $WORK" >&2; exit 7; }
    fi
  else
    echo "NOT SYNCED: worktree is on '$BR', whose work is NOT yet in $REF (an open PR," >&2
    echo "NOT SYNCED: presumably). Leaving it alone." >&2
    exit 4
  fi
fi
# The upstream is what pr_open reads to choose a PR's base branch (Legion's first PR, #63, went
# to the wrong base for want of it). Set it every sync.
git branch --set-upstream-to="origin/$REF" "$WORK" >/dev/null 2>&1 || \
  echo "WARNING: could not set upstream to origin/$REF; pr_open will refuse to guess a base" >&2
if [ "$(git rev-parse HEAD)" = "$(git rev-parse FETCH_HEAD)" ]; then
  echo "already at $(git log --oneline -1)"
  exit 0
fi
# Capture git's own refusal: a fast-forward that would overwrite an untracked file names it.
if OUT="$(git merge --ff-only FETCH_HEAD 2>&1)"; then
  echo "synced to $(git log --oneline -1)"
else
  if echo "$OUT" | grep -qi "untracked working tree files would be overwritten"; then
    echo "NOT SYNCED: an incoming commit adds a file the being already wrote untracked." >&2
    echo "$OUT" | sed 's/^/  /' >&2
    echo "Resolve with the being — the file is its work, and it holds no delete verb." >&2
    exit 6
  fi
  echo "NOT SYNCED: $WORK has diverged from $REF; needs a human." >&2
  echo "$OUT" | sed 's/^/  /' >&2
  exit 5
fi
