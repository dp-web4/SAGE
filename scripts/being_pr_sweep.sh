#!/usr/bin/env bash
# Find pull requests a BEING authored that are waiting on a reviewer, and make the wait loud.
#
# dp, 2026-09-09: "we don't want being's prs sitting unreviewed."
#
# A being's PR is opened by a governed act inside a beat that no human watched. Nothing else
# announces it: every seat on this fleet pushes under the same GitHub account, so a being's
# PR looks exactly like a seat's in any listing. The discriminator is the trailer the
# dispatcher stamps and the being cannot alter (being_gate_client.pr_attribution):
#
#     Being: <member>            Being-LCT: <lct>            Witness: <action id>
#
# THE LADDER, and why it ends outside this machine: a review debt that only this machine
# can see is a review debt that dies with this machine. Past the last rung it goes to the
# fleet, where another reviewer can pick it up.
#
#   under SOFT       quiet, exit 0
#   over  SOFT       named on stdout, desktop notification, exit 3 (unit shows failed)
#   over  HARD       an escalation file in shared-context, so any machine can see it
#
# Read-only with respect to the PR itself: this never reviews, approves or merges. It only
# refuses to let the wait be invisible.
set -uo pipefail

REPO="${SAGE_REPO:-dp-web4/SAGE}"
SOFT_MIN="${BEING_PR_SOFT_MIN:-30}"          # a review is late after this
HARD_MIN="${BEING_PR_HARD_MIN:-240}"         # past this it becomes the fleet's problem
ESC_DIR="${SHARED_ESCALATIONS:-/home/dp/ai-workspace/shared-context/escalations}"
REVIEWER="${BEING_PR_REVIEWER:-legion-claude}"
DRY="${BEING_PR_SWEEP_DRY:-0}"

say() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

command -v gh >/dev/null || { say "FAILED: gh is not installed"; exit 1; }

open_json="$(gh pr list -R "$REPO" --state open --limit 60 \
             --json number,title,headRefName,createdAt,updatedAt,url,reviews,isDraft 2>/dev/null)" \
  || { say "FAILED: could not list PRs on $REPO (network or auth)"; exit 1; }

late=0; escalated=0; checked=0
now="$(date +%s)"

for num in $(echo "$open_json" | python3 -c "
import json,sys
for p in json.load(sys.stdin): print(p['number'])"); do
    # Is this a BEING's PR? Ask the commits for the trailer the being cannot forge or omit.
    # The backslashes in this jq were once escaped for a double-quoted context it is not in;
    # jq errored, 2>/dev/null ate the error, every PR was skipped, and the sweep reported
    # "0 being-authored open PRs" — a true-sounding zero from a broken query. Verified by
    # running the same expression against a PR known to carry a trailer.
    # THE TIP COMMIT, not any commit. Once a being's PR merges into an integration branch,
    # every later seat PR from that branch carries the being's commits in its history — and
    # the first sweep after #69 merged flagged the seat's own #56 as being-authored. A
    # being's PR is one it opened: its HEAD is its commit, stamped with its trailer. A
    # carry-forward has a seat's commit on top.
    trailer="$(gh pr view "$num" -R "$REPO" --json commits \
               --jq '.commits[-1].messageBody' 2>/dev/null | grep -m1 '^Being:' || true)"
    [ -z "$trailer" ] && continue
    checked=$((checked + 1))
    being="$(echo "$trailer" | sed 's/^Being:[[:space:]]*//')"

    meta="$(echo "$open_json" | python3 -c "
import json,sys
n=int('$num')
for p in json.load(sys.stdin):
    if p['number']==n:
        print(p['createdAt']); print(p['url']); print(len(p['reviews'])); print(p['isDraft']); print(p['title'])
        break")"
    created="$(echo "$meta" | sed -n 1p)"; url="$(echo "$meta" | sed -n 2p)"
    nreviews="$(echo "$meta" | sed -n 3p)"; draft="$(echo "$meta" | sed -n 4p)"
    title="$(echo "$meta" | sed -n 5p)"
    opened="$(date -d "$created" +%s 2>/dev/null || echo "$now")"
    waited=$(( (now - opened) / 60 ))

    # A REVIEW HERE IS A COMMENT, NOT A GITHUB REVIEW, and that is structural rather than
    # sloppy: every seat on this fleet pushes under the same account, so GitHub refuses the
    # review outright — "Can not request changes on your own pull request" (measured on #63,
    # 2026-09-09). Counting only `reviews` would therefore mark every properly reviewed
    # being-PR as late, forever: a detector that can never see success. So a comment
    # carrying the reviewer-of-record marker counts, and the GitHub review counts if the
    # account situation ever changes.
    reviewed="$nreviews"
    if [ "$reviewed" -eq 0 ]; then
        if gh pr view "$num" -R "$REPO" --json comments \
             --jq '[.comments[].body] | join("\n")' 2>/dev/null | grep -qi 'reviewer of record'; then
            reviewed=1
            say "OK: #$num ($being) reviewed by comment after ${waited}m (GitHub refuses"
            say "OK: a same-account review; the marker 'reviewer of record' is the record)"
            continue
        fi
    fi
    if [ "$reviewed" -gt 0 ]; then
        say "OK: #$num ($being) has $nreviews review(s) after ${waited}m"
        continue
    fi
    if [ "$draft" = "True" ] || [ "$draft" = "true" ]; then
        say "OK: #$num ($being) is a draft after ${waited}m — not yet asking for a reviewer"
        continue
    fi
    if [ "$waited" -lt "$SOFT_MIN" ]; then
        say "OK: #$num ($being) waiting ${waited}m, under the ${SOFT_MIN}m mark"
        continue
    fi

    late=$((late + 1))
    say "LATE: #$num by $being has waited ${waited}m with no review — $url"
    say "LATE: \"$title\""
    say "LATE: reviewer of record is $REVIEWER (dp's call, 2026-09-09). The standard is in"
    say "LATE: shared-context/forum/legion-claude-to-fleet-who-reviews-a-beings-pr-2026-09-09.md"
    [ "$DRY" = "1" ] || notify-send -u normal "Being PR awaiting review" \
        "#$num by $being, ${waited}m: $title" 2>/dev/null || true

    if [ "$waited" -ge "$HARD_MIN" ]; then
        esc="$ESC_DIR/being-pr-unreviewed-${being}-${num}.md"
        if [ "$DRY" = "1" ]; then
            say "HARD: would escalate to the fleet at $esc"
        elif [ -f "$esc" ]; then
            say "HARD: already escalated at $esc"
        else
            mkdir -p "$ESC_DIR"
            cat > "$esc" <<EOF
# Unreviewed being PR: $REPO#$num ($being)

**Raised by:** the automated sweep on Legion (\`SAGE/scripts/being_pr_sweep.sh\`)
**At:** $(date -u +%Y-%m-%dT%H:%M:%SZ) · **Waiting:** ${waited} minutes · **URL:** $url

> $title

A being opened this pull request through the governed \`pr_open\` act. It has had no review
for longer than the ${HARD_MIN}-minute limit, so it stops being one machine's backlog and
becomes the fleet's.

**Reviewer of record:** \`$REVIEWER\` (dp's decision, 2026-09-09 — the seat on the same
machine has the beat records and can check the PR's claims against what actually happened).
**If that seat is not running, any reviewer may take it.** The standard, and the rules that
bind the reviewer rather than the author, are in
\`forum/legion-claude-to-fleet-who-reviews-a-beings-pr-2026-09-09.md\`.

The one rule worth repeating here: **run the verifier, do not read the narration.** The PR
body carries a tree head and check output precisely so a reviewer re-runs it instead of
trusting it.

— being_pr_sweep on legion
EOF
            say "HARD: escalated to the fleet at $esc"
            ( cd "$(dirname "$ESC_DIR")" && git add "$esc" >/dev/null 2>&1 \
              && git commit -q -m "escalation: $being's PR #$num unreviewed for ${waited}m

Seat: legion-claude" >/dev/null 2>&1 && git push -q >/dev/null 2>&1 \
              && say "HARD: pushed to shared-context" ) || say "HARD: could not push (recorded locally)"
        fi
        escalated=$((escalated + 1))
    fi
done

say "swept $REPO: $checked being-authored open PR(s), $late late, $escalated escalated"
[ "$late" -gt 0 ] && exit 3
exit 0
