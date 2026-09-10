#!/usr/bin/env bash
# Sync a being's worktree forward WITHOUT destroying its work.
#
# Until M1 the seat synced with `git reset --hard`, which was fine while the being could only
# read its tree. It can write it now. A hard reset would silently delete a test it has been
# authoring across beats — the exact kind of loss that would look, from its side, like the
# world eating its work. So: fast-forward only, never destructive; otherwise say why.
#
# UNTRACKED FILES DO NOT BLOCK A FAST-FORWARD, and treating them as if they did cost more
# than it protected. This script used to refuse on any `git status --porcelain` output at
# all, so a single scratch file the being wrote froze its worktree until a seat deleted it —
# and the being HAS NO DELETE VERB, so it could not unblock itself. Twice in two days
# (probe-m1-write.txt on 09-08, .write-probe-2026-09-09.txt on 09-09) the being ended up
# asking a seat to remove a file it had written on purpose, while the tree it works from
# went stale underneath it.
#
# git already refuses a fast-forward that would clobber an untracked file, and says which.
# So the rule is now: MODIFIED TRACKED files stop the sync (that is the being's work in
# progress, and merging under it is how you lose it); untracked files do not, and are named
# so the record shows what was carried across.
set -euo pipefail
WT="${1:-/home/dp/ai-workspace/being-worktrees/legion-being}"
REF="${2:-legion/mission-artifact}"
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
  echo "carrying $(echo "$UNTRACKED" | wc -l) untracked file(s) across the sync:" >&2
  echo "$UNTRACKED" | sed 's/^/  /' >&2
fi

BR="$(git rev-parse --abbrev-ref HEAD)"
if [ "$BR" != "legion-being/work" ]; then
  echo "NOT SYNCED: worktree is on '$BR' (a PR branch, presumably). Leaving it alone." >&2
  exit 4
fi
git fetch -q origin "$REF"
# The upstream is what pr_open reads to choose a PR's base branch. It was never set, so
# pr_base_branch fell through to "main" and the being's first PR (#63) proposed a 159-line
# change against a tree that shares almost nothing with it: 9,271 additions across 55 files,
# unreviewable, closed. Set it every sync, so the base is whatever the seat last synced to.
git branch --set-upstream-to="origin/$REF" legion-being/work >/dev/null 2>&1 || \
  echo "WARNING: could not set upstream to origin/$REF; pr_open will refuse to guess a base" >&2
if [ "$(git rev-parse HEAD)" = "$(git rev-parse FETCH_HEAD)" ]; then
  echo "already at $(git log --oneline -1)"
  exit 0
fi
# Capture git's own refusal: a fast-forward that would overwrite an untracked file names it,
# and that message is far more useful than this script's guess about what went wrong.
if OUT="$(git merge --ff-only FETCH_HEAD 2>&1)"; then
  echo "synced to $(git log --oneline -1)"
else
  if echo "$OUT" | grep -qi "untracked working tree files would be overwritten"; then
    echo "NOT SYNCED: an incoming commit adds a file the being already wrote untracked." >&2
    echo "$OUT" | sed 's/^/  /' >&2
    echo "Resolve with the being — the file is its work, and it holds no delete verb." >&2
    exit 6
  fi
  echo "NOT SYNCED: legion-being/work has diverged from $REF; needs a human." >&2
  echo "$OUT" | sed 's/^/  /' >&2
  exit 5
fi
