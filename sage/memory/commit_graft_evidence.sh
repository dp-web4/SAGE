#!/usr/bin/env bash
# Commit a being's graft evidence to main — the missing half of the consolidation timer.
#
# WHY THIS EXISTS. `.gitignore` states the policy in its own words: "the graft, index and log are
# committed as evidence; the per-line own-word index sidecar is [ignored]". The daily
# `sage-consolidation.timer` WRITES those files and nothing committed them. Measured 2026-09-12 by
# cbp-claude and confirmed here: main carried sprout-being v2 of 09-05 while the being was at v9 of
# 09-12, on both seats, last graft commit 45978aa12 — seven days stale. The consequence is not
# untidiness: the monotonic-source WIPE ALARM reads committed artifacts, so run today it reports
# clean over two versions from one day, not because nothing fell but because it cannot see six days.
# An alarm with no input is not an alarm.
#
# WHY A WORKTREE. A timer must not write the shared checkout. Other sessions hold it, often with
# uncommitted work (the fleet rule: "a dirty checkout is a sibling's work in progress — leave it
# alone"), and a `git add` in the shared tree would stage theirs alongside ours. So this commits
# through a detached worktree off origin/main and removes it, serialising on the tree, not the clock.
#
# WHAT IT WILL NOT DO. Only the three evidence paths are ever staged, by explicit allowlist — never
# `git add -A`. The `.own-index.jsonl` sidecars stay local per policy (650 KB/version, re-derivable).
# `--push` is opt-in: a timer that pushes on its own is an outward-facing act, so the default is a
# local commit and the caller decides.
set -euo pipefail

INSTANCE=""; MEMBER=""; PUSH=0; REPO="${SAGE_REPO:-$(git rev-parse --show-toplevel)}"
while [ $# -gt 0 ]; do
  case "$1" in
    --instance) INSTANCE="$2"; shift 2;;
    --member)   MEMBER="$2"; shift 2;;
    --repo)     REPO="$2"; shift 2;;
    --push)     PUSH=1; shift;;
    *) echo "commit-graft-evidence: unknown argument '$1'" >&2; exit 2;;
  esac
done
[ -n "$INSTANCE" ] || { echo "commit-graft-evidence: --instance is required" >&2; exit 2; }
MEMBER="${MEMBER:-$(basename "$INSTANCE")}"

cd "$REPO"
SRC="$REPO/$INSTANCE/grafts"
[ -d "$SRC" ] || { echo "commit-graft-evidence: no grafts at $SRC" >&2; exit 1; }

WT="$(mktemp -d -t sage-graft-commit-XXXXXX)"
cleanup() { git worktree remove --force "$WT" >/dev/null 2>&1 || true; }
trap cleanup EXIT

git fetch --quiet origin main
git worktree add -f --detach "$WT" origin/main >/dev/null

DEST="$WT/$INSTANCE/grafts"
mkdir -p "$DEST"
# Allowlist, and the sidecar exclusion is enforced here rather than trusted to .gitignore.
copied=0
for f in "$SRC"/index.json "$SRC"/consolidation_log.jsonl "$SRC"/self-account-*.json; do
  [ -e "$f" ] || continue
  case "$f" in *.own-index.jsonl) continue;; esac
  cp -- "$f" "$DEST/"; copied=$((copied + 1))
done
[ "$copied" -gt 0 ] || { echo "commit-graft-evidence: nothing to commit" >&2; exit 1; }

cd "$WT"
git add -- "$INSTANCE/grafts/index.json" \
           "$INSTANCE/grafts/consolidation_log.jsonl" \
           "$INSTANCE/grafts/self-account-"*.json
if git diff --cached --quiet; then
  echo "commit-graft-evidence: committed evidence already matches local grafts (no-op)"
  exit 0
fi
LATEST="$(python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));m=d["members"][sys.argv[2]];print(m["latest"],len(m["versions"]))' \
          "$DEST/index.json" "$MEMBER" 2>/dev/null || echo "unknown ?")"
git -c user.name="${GIT_AUTHOR_NAME:-sage-consolidation}" \
    -c user.email="${GIT_AUTHOR_EMAIL:-sage-consolidation@localhost}" \
    commit --quiet -m "graft evidence ($MEMBER): $LATEST

The consolidation timer writes the graft; this commits it, so the wipe alarm has an input and a
third seat can check the being's account against the record instead of taking a seat's word for it.

Seat: sprout-claude" 
echo "commit-graft-evidence: committed $(git rev-parse --short HEAD) ($LATEST versions)"

if [ "$PUSH" = "1" ]; then
  git rebase --quiet origin/main
  git push --quiet origin HEAD:main
  echo "commit-graft-evidence: pushed to origin/main"
else
  # Without this the no-push path is a no-op that LOOKS like it worked: the commit is made in a
  # worktree the exit trap then removes, so it is unreachable and gone. Park it on a local branch
  # so a default run leaves something real behind for the operator to inspect and push.
  BRANCH="graft-evidence/$MEMBER"
  git branch --force "$BRANCH" HEAD
  echo "commit-graft-evidence: NOT pushed. Commit parked on local branch '$BRANCH'."
  echo "commit-graft-evidence: publish with: git push origin $BRANCH:main   (or re-run with --push)"
fi
