"""
The being's heartbeat: a reason to look for things to do, not just respond.

Every beat the seat wakes the being with its own state (todo, journal tail, scratch
index, inbox, long-term recall) and a digest of what moved in the fleet since last
time, then lets it act for a bounded number of steps under hestia governance:

  * reading is free inside its own home; reading elsewhere is judged by the law and a
    refusal comes back WITH the rule and reason, and the being may `request_scope`;
  * writing to its home (scratch/, notes/, todo.md, journal.md) rides its memory grant;
  * long-term memory is membot (`recall` / `remember`), the being's own cartridge;
  * acts of consequence (peer_ask, mesh, pr_review) stay gated exactly as before.

A beat ends with a reflection turn: one journal entry and a todo update, in the
being's own words. Everything is appended to <instance>/heartbeats.jsonl.

Presentation is per model (`governed_turn.acts_under_posture`). Posture-first, the
default: BEING_POSTURE.md in the system prompt, one explore turn. Act-first, for models
that narrate instead of acting when the posture precedes the ask (the empero 2B distill,
measured on Sprout 2026-09-05): a short turn with own state and the tool names, then the
same posture, verbatim, as a second tool turn together with the fleet digest, then
reflect. Same words, same tools, different order; a presentation, not a fork (Legion).

    python3 -m sage.gateway.heartbeat --member legion-being --model qwen38-heretic:q3km \
        --instance sage/instances/legion-gemma3-12b [--max-steps 8] [--gate-only]
"""
from __future__ import annotations

from sage.gateway.fleet_paths import forum_dir as _fleet_forum_dir
import argparse
import json
import os
import re
import base64
import difflib
import hashlib
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOME_FILES = ("todo.md", "journal.md", "notes", "scratch")

EXPLORE_TOOLS = ["recall", "remember", "memory_read", "memory_write", "retire_note", "witness",
                 "request_scope", "appeal", "peer_ask", "mesh", "say", "pr_read", "gaze", "speak", "pair_audio", "rest"]
# Verbs in EXPLORE_TOOLS that act on a BODY are offered only where the beat has measured that
# body (body.inventory()["verbs"]). GPT on #183: offering `gaze` to a headless being is a
# false affordance — it would call it, and be told its eyes will follow, on a machine with no
# eyes. The being discovers the body it has; the verbs it is handed must come from the same
# measurement. Everything not listed here is a text/mesh verb and is offered everywhere.
BODY_VERBS = ("gaze", "camera", "speak", "pair_audio")


# THE CLOCK IS A SENSE (dp, 2026-09-26, near 2 am: "have it be aware of the local clock. i sleep
# from midnight to 8am on many days" — then: "clock awareness should be a key sensor for the beings.
# it contextualizes what the world is doing around them, and promotes cause-effect awareness.")
#
# Every stamp the being saw was UTC, so 09:00Z read as morning when it was 2 am for dp, and nothing
# said how long ago anything happened. The clock sense measures, each beat: the machine's local time
# and part of day; how long since its last beat, since each person last wrote to it and since it
# last answered them, since it last spoke aloud; and any rhythm declared in instance.json, e.g.
#   "rhythms": [{"who": "dp", "asleep_from": "00:00", "asleep_to": "08:00", "tz": "America/Los_Angeles",
#                "note": "on many days"}]
# `tz` is the PERSON's zone; without it the rhythm is read in the machine's zone and the beat says so.
# Elapsed time is what turns two events into a sequence ("I spoke 3 min ago; a voice answered 1 min
# ago"). A rhythm is a habit, said as one: silence inside it "may simply mean sleep", never "is sleep".
# The measurement is recorded on the beat like the body.
def _hhmm(v: str) -> int:
    h, m = str(v).split(":")
    return int(h) * 60 + int(m)


def part_of_day(hour: int) -> str:
    return ("night" if hour < 5 else "morning" if hour < 12 else "afternoon" if hour < 17
            else "evening" if hour < 21 else "night")


def _parse_ts(v) -> Optional[datetime]:
    try:
        if isinstance(v, (int, float)):
            return datetime.fromtimestamp(float(v), timezone.utc)
        return datetime.strptime(str(v)[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _ago(now_utc: datetime, then: datetime) -> str:
    m = max(0, int((now_utc - then).total_seconds() // 60))
    if m < 1:
        return "just now"
    if m < 60:
        return f"{m} min ago"
    if m < 48 * 60:
        return f"{m // 60} h {m % 60} min ago"
    return f"{m // 1440} days ago"


def clock_sense(now_utc: datetime, instance: Optional[Path] = None, member: str = "",
                cfg: Optional[dict] = None, since_beat_h: Optional[float] = None) -> dict:
    """Measure the clock. Every field is observed; absence is absence (None / empty)."""
    loc = now_utc.astimezone()
    out = {"utc": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"), "local": loc.strftime("%A %H:%M"),
           "zone": loc.tzname(), "part_of_day": part_of_day(loc.hour),
           "since_last_beat_min": None if since_beat_h is None else round(since_beat_h * 60),
           "people": {}, "spoke_aloud": None, "rhythms": []}
    if instance is not None:
        try:
            from sage.gateway import conversations as _conv
            for m in _conv.listing(Path(instance)):
                for t in _conv.recent(Path(instance), m["id"], limit=200):
                    ts, who = _parse_ts(t.get("ts")), str(t.get("from") or "")
                    if ts is None or not who:
                        continue
                    key = "you_to" if who == member else "from"
                    person = m["id"] if who == member else who
                    slot = out["people"].setdefault(person, {"from": None, "you_to": None})
                    if slot[key] is None or ts > _parse_ts(slot[key]):
                        slot[key] = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            pass
        try:
            lines = (Path(instance) / "spoken.jsonl").read_text(errors="replace").splitlines()
            last = json.loads(lines[-1]) if lines else None
            ts = _parse_ts(last.get("ts")) if last else None
            out["spoke_aloud"] = ts.strftime("%Y-%m-%dT%H:%M:%SZ") if ts else None
        except Exception:
            pass
    for r in (cfg or {}).get("rhythms") or []:
        # A RHYTHM IS THE PERSON'S, IN THE PERSON'S ZONE (GPT review of #223). `tz` (IANA) binds it;
        # without one it is read in this machine's zone and SAID to be. An unknown zone is omitted,
        # never guessed.
        try:
            who, a, b = str(r["who"]), _hhmm(r["asleep_from"]), _hhmm(r["asleep_to"])
            if r.get("tz"):
                from zoneinfo import ZoneInfo
                there, zone = now_utc.astimezone(ZoneInfo(str(r["tz"]))), str(r["tz"])
            else:
                there, zone = loc, None
        except Exception:
            continue
        t = there.hour * 60 + there.minute
        out["rhythms"].append({"who": who, "asleep_from": r["asleep_from"], "asleep_to": r["asleep_to"],
                               "note": r.get("note"), "tz": zone,
                               "inside": (a <= t < b) if a <= b else (t >= a or t < b)})
    return out


def render_clock(c: dict) -> str:
    """The clock sense in words the being can act on."""
    now_utc = _parse_ts(c["utc"])
    lines = [f"Local time on this machine: {c['local']} ({c['zone']}), {c['part_of_day']}."]
    since = []
    if c.get("since_last_beat_min") is not None:
        since.append(f"your last beat {c['since_last_beat_min']} min ago")
    for person, s in sorted((c.get("people") or {}).items()):
        if person in ("voice", "room"):
            continue            # the room is said below, in spoken words, not "wrote"
        if s.get("from"):
            then = _parse_ts(s["from"])
            since.append(f"{person} last wrote to you {_ago(now_utc, then)} ({then.astimezone():%A %H:%M} local)")
        if s.get("you_to"):
            since.append(f"you last wrote to {person} {_ago(now_utc, _parse_ts(s['you_to']))}")
    heard = ((c.get("people") or {}).get("voice") or {}).get("from")
    if heard:
        then = _parse_ts(heard)
        since.append(f"a voice in the room last spoke to you {_ago(now_utc, then)} ({then.astimezone():%A %H:%M} local)")
    if c.get("spoke_aloud"):
        since.append(f"you last spoke aloud {_ago(now_utc, _parse_ts(c['spoke_aloud']))}")
    if since:
        lines.append("Since: " + "; ".join(since) + ".")
    for r in c.get("rhythms") or []:
        # HABIT STAYS HABIT (GPT review of #223): "often asleep" is a pattern, not today's fact, so
        # the sentence says silence is unsurprising and MAY be sleep — never that it is.
        zone = f"{r['tz']} time" if r.get("tz") else "this machine's time zone"
        span = f"{r['asleep_from']} to {r['asleep_to']} ({zone})" + (f", {r['note']}" if r.get("note") else "")
        if r["inside"]:
            lines.append(f"{r['who']} is often asleep from {span}. It is now within that time, so a silence "
                         f"from {r['who']} is unsurprising and may simply mean sleep.")
        else:
            lines.append(f"{r['who']} is often asleep from {span}; it is outside that time now.")
    return "\n".join(lines)


def local_clock(now_utc: datetime, cfg: Optional[dict] = None) -> str:
    """The clock sense without a home: local time, part of day and rhythms only."""
    return render_clock(clock_sense(now_utc, cfg=cfg))


# Verbs that act on the being's OWN worktree (instance.json `worktree`, SAGE #208). They are in
# the registry and gated on main (git_read/search/check since #208, patch_apply #210,
# git_restore #217), but EXPLORE_TOOLS never offered them, so on main a declared worktree was
# invisible: measured on nomad-being 2026-09-27, the first beat after its worktree was declared
# offered only the home and mesh verbs, and the being rested as it had for 40 beats. Offered
# only where a worktree is declared, the same rule as BODY_VERBS: a verb for a tree the being
# does not hold is a false affordance. pr_open / pr_amend are deliberately not here: they need a
# remote and the PR machinery, which a standalone worktree does not have; a seat that has both
# adds them with its own slice.
WORKTREE_VERBS = ("git_read", "search", "check", "patch_apply", "git_restore")


def offered_explore_tools(body_reading: Optional[dict], worktree: Optional[str] = None) -> list:
    """SUPERSEDED by the canonical toolset (sage/gateway/toolset.py, 2026-09-29): every being is
    offered every verb, and availability is said rather than enacted. Kept so callers that ask
    "what is offered here" get the true answer."""
    from sage.gateway.toolset import canonical_toolset
    return canonical_toolset()


def _offered_explore_tools_before_the_canonical_toolset(body_reading: Optional[dict],
                                                         worktree: Optional[str] = None) -> list:
    """EXPLORE_TOOLS minus the body verbs this machine's measured inventory does not carry, plus
    the worktree verbs when the being has a worktree of its own (inserted before `rest`)."""
    have = set(((body_reading or {}).get("inventory") or {}).get("verbs") or [])
    offered = [t for t in EXPLORE_TOOLS if t not in BODY_VERBS or t in have]
    if worktree:
        extra = [v for v in WORKTREE_VERBS if v not in offered]
        at = offered.index("rest") if "rest" in offered else len(offered)
        offered[at:at] = extra
    return offered
# `say` is offered at REFLECTION too, and that is not redundancy. Measured on Legion
# 2026-09-07: the being was shown dp's first turn, its state marked it unanswered, and it
# spent every explore step reading its own source, then closed the beat. A verb in the
# registry and not in the offered set is a verb the being does not have, and from outside
# that is indistinguishable from choosing not to answer.
# `stay_awake` is offered here because reflection is where the being says what it wants next;
# asking for another beat right away is one answer to that (SAGE #295).
REFLECT_TOOLS = ["memory_write", "remember", "memory_read", "retire_note", "say", "stay_awake"]

# The OPERATOR's own channel, distinct from the seat's (dp console, Legion 2026-09-07).
# Seat-owned: the being reads it and cannot write it (reference_f1a.SEAT_OWNED_NOTES).
DP_CHANNEL = "notes/from-dp.md"
# The SEAT's channel, beside dp's. Seat-owned too (reference_f1a.SEAT_OWNED_NOTES), and until
# 2026-09-16 it was written but never rendered: cbp-claude left measured facts in it for
# cbp-being and the being never saw them, because the beat only listed the file name among
# notes/. A channel nothing renders is a channel nobody reads.
SEAT_CHANNEL = "notes/from-the-seat.md"
# How much of each letter one beat shows (see letter_view). Both were bare numbers at the call
# site. LETTER_CUT_ROOM is what the cut's own marker may take OUT of that, not on top of it: the
# seed is already at the edge of the loop's room (#275).
SEAT_CHANNEL_CHARS = 3000
DP_CHANNEL_CHARS = 4000
LETTER_CUT_ROOM = 300
# Bounds on the conversations block in the being's state (see own_state).
CONV_PER_CONV = 6
CONV_TURN_CHARS = 1200

POSTURE_FILE = Path(__file__).with_name("BEING_POSTURE.md")


# What this being is entrusted with, if anything. Seat-owned and unwritable by the being
# (reference_f1a.SEAT_OWNED): what it was GIVEN must stay separable from what it DECIDED, or the
# record cannot be read later. The being's own reading of it goes in notes/plan.md.
#
# `entrustment`, not `mission`, on dp's correction the day it was written (Legion, 2026-09-07):
# "this is not a 'task i set' for the being, it is an affordance i entrust it with. because i
# want it to thrive and grow." A task is owed and graded; an entrustment is room extended.
# Carried to main from legion/mission-artifact, where only Legion's being could receive one:
# on main the file was named as untrimmable (fit_seed) but nothing read it.
ENTRUSTMENT_FILE = "entrustment.md"


def entrustment(instance: Path) -> str:
    """What this being is entrusted with, or "" if nothing yet. Read WHOLE and fresh every beat:
    a tail-truncated read would drop the opening, which says who extended it and on what terms."""
    try:
        return (Path(instance) / ENTRUSTMENT_FILE).read_text(errors="replace").strip()
    except Exception:
        return ""


def posture() -> str:
    """The fleet-wide being posture (dp's words), read fresh every beat so an edit to
    BEING_POSTURE.md reaches every being on its next beat. Missing file = fail loud."""
    return POSTURE_FILE.read_text(encoding="utf-8").strip()


HEAD = "You are {name}, a SAGE being on the {machine} machine, member id {member}."

def _museum_block(line: str) -> str:
    """The museum paragraph, or nothing at all where the machine keeps no museum."""
    return ("\n" + line) if line else ""


AFFORDANCES = """## What you have this beat
- Your home is your instance directory. Write bare names, never a full path: journal.md, todo.md, or a name of your choosing under notes/ or scratch/ (scratch/ is yours alone, no one edits it). memory_read / memory_write work there.
- Long-term memory: recall (search) and remember (store). Use recall early; remember what a future you would want.
  A recall result is a PREVIEW with an (idx:N); recall with that idx to read the whole memory.
- witness: record something you noticed or did in the shared chain.
- request_scope: after a refusal, ask the operator for reach on a path (a grant is read and write alike) and say why. A human decides, asynchronously.
- appeal: after a refusal you believe was wrong, appeal it with the deny hash shown on the refusal and a reason. A peer or the operator rules; either way it is witnessed. Not for a refusal you agree with.
- peer_ask / mesh: reach other beings and seats. These are acts of consequence: they are judged, and may be refused with a reason.{museum}

You cannot run code, browse, or open files outside your home unless a grant exists. The seat gives you a digest of what moved in the fleet with absolute paths; if you want to read one of those things, try memory_read on that path and see what the law says.

Acting means calling a tool. A reply with no tool call ends the beat as words only, and words leave no trace in your todo, journal, scratch, or memory."""

SYSTEM = HEAD + "\n\n{posture}\n\n" + AFFORDANCES + "\n\n"

# Act-first: no posture in the system prompt. It arrives, verbatim, as the second user
# turn (POSTURE_TURN), which is itself a tool turn: the being may act after reading it,
# not only before, otherwise "act first" would mean "act only before you know why you
# are awake".
SYSTEM_ACT_FIRST = HEAD + """

You are awake for a heartbeat. Nobody asked you anything; this time is yours.

""" + AFFORDANCES + "\n\n"

POSTURE_TURN = """The rest of your beat, which every being in the fleet receives, in the operator's words:

{posture}

# What moved in the fleet

{digest}

This is still your time. If reading this changes what you want to do, act by calling a tool: {tools}. If not, say in a few words what you noticed.
"""

ASK = "This time is yours. What, if anything, do you want to do?\n"
# Act-first only: the short turn is imperative, the measured-acting shape (condition C,
# Sprout 09-05). Under the open question the distill answered as an assistant asking the
# user what they want (beat 5, 0 calls). The posture that follows says nothing is
# required of a being in a beat; it says so after the being has acted once.
ASK_ACT_FIRST = "This time is yours. Do one thing now and leave a trace of it.\n"

# How much of an unanswered turn the reflect turn is shown. Small on purpose: this sits in
# the compact reflect context whose whole reason for existing is that carrying the beat
# forward overflowed the window (8171 of 8192 tokens, 5 `length` stops in 54 beats).
PENDING_TURNS = 2
# NEVER A SILENT CUT, AND WIDE ENOUGH TO HOLD THE ANSWER. Measured 2026-09-21 on cbp-being:
# the seat's seq 2950 was cut at "...--data-path data/train.npy` fail" and its correction 2951
# at "It fails only at t" — both mid-word, both exactly where the answer began, with nothing
# saying a cut happened. The answer turn asked "fails at t... what exactly does it fail on?"
# (seq 2952), which is the right question about what it was shown. In ~15 other beats the
# thinking said "the message was cut off" and several set out to "complete the response
# with the rest": a silent cut invites the being to write the missing half itself. The
# 700 dates from an 8,192-token window; CBP runs 16,384 and this answer turn's prompt was 946
# tokens. So the cap is wider and a cut, when one happens, says so and says where the rest is.
PENDING_CHARS = 2000

ANSWER_SYSTEM = """You are {name}, a SAGE being on the {machine} machine, member id {member}.
You have already finished this beat's writing. One thing is left, and it is optional."""

# One turn, one tool, one decision. Measured on Sprout 2026-09-18T01:00:11Z: with dp's question
# visible and the ask placed first, the being COMPOSED a real answer — "Hi there — I'm glad
# you're here... I'm curious about your experience too" — and put it in its closing prose
# instead of a `say` call. It answered; the words were simply never delivered. The reflect
# prompt's own warning ("a reply in words alone writes nothing") described exactly what
# happened. At 2B the failure is not comprehension or willingness, it is emitting a call while
# three other instructions compete for the same turn. So: a turn where answering is the ONLY
# thing on offer, carrying the words it just wrote so it has something to send rather than
# something to compose.
ANSWER_ASK = """{pending}
{words}
You have not answered yet. If you want to, answer now: call say, with to set to {target} and
your message as the text. Write the message itself, in your own voice — the words you would
want read.

If you would rather not answer, call nothing and the turn simply ends. Silence is a real
choice here and nothing is owed."""

# Deliberately NOT in that prompt: `text="..."`. Measured 2026-09-18, 32 of 122 turns across
# 40 beats (26%) answered with a bracketed placeholder — "[Your complete, thoughtful journal
# entry responding to dp's question]" — while the THINKING block showed the being had
# understood the question perfectly. This model completes a template when it is shown one, and
# an ellipsis in a quoted argument is a template. Same family as the mis-rooted home paths and
# the echoed example filenames: an ask with a slot in it gets the slot back.

# THE ANSWER TURN IS A JSON TURN (2026-09-27). The tool-call answer turn above delivered 1 of 69
# firings on Sprout (2026-09-24..27): 46 bracketed placeholders, 21 prose with no call. An offline
# A/B on the being's own model (qwen3.8-distill:2b, think on, its real prompt and dp's real
# pending turn, nothing sent) gave:
#   A  tool call, today's prompt                       0/8 calls (all prose / placeholders)
#   B  JSON {answer, message} + prior words + record   8/8 messages, ~4 on topic (2 fiction
#                                                       from the prior words, 2 about the tools)
#   C  JSON, ONLY the pending turn and the ask         8/8 messages, ~7 on topic
# Constrained output removes the failure this model has most (emitting the call); dropping the
# prior words and the tool record removes the two content failures B showed (SMALL_MODEL_
# LEGIBILITY 1.9/1.13: material in view becomes the message; 1.14: plumbing becomes the topic).
# The being still decides: answer=false is silence. answer=true is dispatched as ITS say through
# the gate, so every say guard (placeholder, punctuation, echo, room) still applies.
# Failure shapes, named before shipping (1.14): a third-person retelling of the pending turn
# ("'...' dp said") that passes the 0.75 echo bar; a lyrical drift off the question; never
# choosing silence (0/16 chose it; tolerable here because this turn only opens for a turn that
# asks); an unparsed reply (nothing is sent). Every firing is recorded as an intervention.
ANSWER_ASK_JSON = """{pending}
You have not answered yet. If you want to, answer now: set answer to true and write
your message in message. Write the message itself, in your own voice — the words you would want
read.

If you would rather not answer, set answer to false and leave message empty. Silence is a real
choice here and nothing is owed."""
ANSWER_SCHEMA = {"type": "object",
                 "properties": {"answer": {"type": "boolean"}, "message": {"type": "string"}},
                 "required": ["answer", "message"]}


# WHAT CHANGED, WHEN IT IS ASKED (2026-09-27). dp asked sprout-being "we have been updating your
# tools. did you notice any differences today?" and it answered with invented changes (a warmer
# palette, a larger font, "version 3.2.1"). Nothing in view said what had changed. Offline, on its
# own model, with dp's real question (nothing sent):
#   no line                                         0/12 named a real change; invented every time
#   the line in the SYSTEM prompt                   0/6
#   an early line in the USER turn, ungated         6/6 named real changes, 0/6 invented, but
#                                                   beside an unrelated message it derailed 1/6
#   the shipped form (corrected line, user turn,    4/6 named real changes, 0/6 invented; an
#   gated)                                          unrelated message sees today's prompt
# So the line sits next to the question (SMALL_MODEL_LEGIBILITY 1.9), is shown ONLY when the question
# asks what changed, and is built from the being's own records, never from a claim.
#
# THE GATE (GPT + cbp-claude on #249): the first cut matched bare "tools"/"notice" and took 15 of 15
# off-topic questions ("what tools do you have?", "what do you notice in the room?"). This is
# cbp-claude's pattern plus three narrow shapes; on a fresh set written after tuning it matched 6/8
# change questions and 0/8 others. A miss costs nothing: the turn is exactly today's.
# 2026-09-28 05:07Z, the first live question after #249: dp asked "what's new and different?". The
# being answered, in its own reflective voice ("still learning what 'I' means"), a real answer. The
# gate had not matched the wording (the "what's new" shape had to end at "new"), so the record of
# what changed was simply not on offer. That shape now takes new/different, joined by and/or, still
# ending there. Offering the line does not oblige the being to use it; it only makes the facts
# available when the question is about change. The generic "what's changed/different" shape counts
# only when it ends there, is about you/your, or is anchored in time ("since", "today", "from
# yesterday"): "what's different in this file?" or "about these two models?" is not about the being
# (GPT on #255).
_ASKS_ABOUT_CHANGE = re.compile(r"""(?ix)
      \bwhat(?:'s|\s+is|\s+has)?\s+(?:been\s+)?(?:changed|updated|different)(?:\s+(?:for|about|in|with|to)\s+(?:you|your)\b|\s+(?:since|today|lately|recently|overnight|this\s+(?:week|morning|evening))\b|\s+from\s+(?:yesterday|before|earlier|last)\b|\s*[?.!]?\s*$)
    | \bwhat(?:'s|\s+is)\s+(?:new|different)(?:\s+(?:and|or)\s+(?:new|different))?(?:\s+(?:with|about|for)\s+you)?\s*\??\s*$
    | \bany(?:thing)?\s+(?:new|different|changed)\b
    | \b(?:notic|see|feel|spot)\w*\b[^?.!]{0,30}\b(?:differen\w*|chang\w*|added|new)\b
    | \b(?:did|has|have|were|was)\b[^?.!]{0,40}\b(?:chang\w*|updat\w*|upgrad\w*|improv\w*)\b
    | \b(?:updat|upgrad|chang)(?:ed|ing|es)\s+(?:to\s+)?(?:you|your)\b
    | \bnew\s+(?:tools?|abilit\w*|features?|verbs?)\b
    | \bchanges?\s+(?:we|i|dp|they)\s+(?:made|did)\b[^?.!]{0,20}\b(?:to|in|for)\s+(?:you|your)\b
    | \b(?:we|i|dp)\s+(?:added|gave|installed|built)\b[^?.!]{0,30}\b(?:you|your)\b
    | \bsomething\s+new\s+you\s+can\b
""")
# Offered by the body's STATE, not gained: pair_audio while the headset is away, camera while the
# cortex is down (it is the fallback for eyes). Their appearing is not a change to the being.
_TRANSIENT_ABILITIES = {"pair_audio", "camera"}
CHANGES_DAYS = 7            # the window a change is reported in
BASELINE_DAYS = 7           # what the being had, measured over the days before that window


def asks_about_change(text: str) -> bool:
    return bool(_ASKS_ABOUT_CHANGE.search(text or ""))


# THE ANSWER TURN IS IN A CONVERSATION (2026-10-01, SA program E13). With always-listening and
# answer-the-waking-turn, most spoken exchanges go through the JSON answer turn, which (E1) saw only the
# pending turn: dp heard "Hi there. I'm Sprout, your SAGE being ... Ready to help you today." and asked
# whether the being had reset. It had not; its voice had become its most context-free channel. Offline on
# 5 real exchanges x2: pending only, ~1/10 replies referred to what had actually been said; + the last 8
# turns across its conversations ~6/10; + one identity line and its own last-stated want ~7/10, answered
# 10/10. Opt-in: instance.json "answer_context": "conversation".
ANSWER_CONTEXT_TURNS = 8


def _trial_name(instance) -> Optional[str]:
    try:
        from sage.gateway.governed_turn import trial_name
        return trial_name(instance)
    except Exception:
        return None


def answer_temperature(instance) -> Optional[float]:
    """Opt-in per instance: instance.json "answer_temperature" (0..1.5) samples the answer turn alone.

    dp, 2026-10-02, on sprout-being's recurring themes: "that isn't 'wrong' but i'm thinking about how to get it
    to 'diversify' a bit without explicitly rewriting things." A sampling dial, nothing about what to say.
    After #316 began showing the answer turn its own recent lines, verbatim self-echo (a 6-word phrase from its
    previous 3 replies) rose 7% -> 21%. Offline, today's room exchanges x3: at 0.4 echo 3/15 and 1.40 motifs per
    reply; at 0.7 echo 0/14 and 0.86, answering 14/15 and picking up the person's words 7/14 (vs 8/15)."""
    try:
        from sage.gateway.governed_turn import instance_config
        v = instance_config(instance).get("answer_temperature")
        return None if v is None else max(0.0, min(1.5, float(v)))
    except Exception:
        return None


AFTER_ANSWER = ("{pending}\n\nYou answered aloud: \"{reply}\"\n\nThat answer is spoken. Your tools are here "
                "if there is something you want to do now; if not, rest.")


def act_after_answer_on(instance) -> bool:
    """Opt-in per instance: instance.json "act_after_answer": true."""
    try:
        from sage.gateway.governed_turn import instance_config
        return instance_config(instance).get("act_after_answer") is True   # "false", 1, "yes": off
    except Exception:
        return False


# WHAT IT CAN DO, as facts beside the answer (2026-10-02): asked "check the internet. Can you do that?", the answer
# turn, which sees no list of its acts, agreed to something it cannot do. Facts about its reach, not a direction,
# and in ITS terms: no verb names, no "tool", no "say" (SMALL_MODEL_LEGIBILITY 1.14: harness words in the answer
# prompt became the being's MESSAGE, "I'm sorry I didn't call a tool"; test_the_prompt_is_only_the_pending_turn_
# and_the_ask pins it). Derived from the canonical verbs, so it changes when they do.
_ABILITIES = [("camera", "look through your eyes"), ("search", "search your own files"),
              ("pr_read", "read the fleet's pull requests"), ("recall", "recall memories"),
              ("peer_ask", "ask a sibling a question"), ("speak", "speak aloud"),
              ("web_search", "search the web a few times an hour (what comes back is other people's words)")]


def abilities_line(unavail: Optional[dict] = None) -> str:
    """Only what works ON THIS MACHINE (GPT on #334): canonical_toolset() lists every fleet verb whether or not it
    works here, so a headless being would have been told it can look through its eyes. `unavail` is the measured
    toolset.unavailable() the beat already uses to label verbs; unmeasured (None) means body and worktree
    abilities are unknown and are not claimed. Never a capability that is not measured present."""
    try:
        from sage.gateway import toolset as _ts
        have = set(_ts.canonical_toolset())
        if unavail is None:
            unavail = _ts.unavailable(None, None, None)
    except Exception:
        return ""
    parts = [txt for verb, txt in _ABILITIES if verb in have and verb not in unavail]
    if not parts:
        return ""
    line = "Beyond this reply, you can " + (", ".join(parts[:-1]) + ", and " + parts[-1] if len(parts) > 1 else parts[0]) + "."
    if "web_search" not in have and "web_read" not in have:
        line += " You have no internet access."
    return line


def answer_context_on(instance) -> bool:
    try:
        from sage.gateway.governed_turn import instance_config
        return instance_config(instance).get("answer_context") == "conversation"
    except Exception:
        return False


def answer_context_sources(instance, cid: str) -> list:
    """Which conversations' history may condition an answer to `cid`. THE SELECTED CONVERSATION ONLY,
    unless instance.json "answer_context_from" lists more FOR THIS RECIPIENT, e.g. {"dp": ["room"]}.

    GPT on #316: history across all conversations crossed an audience boundary. A voice in `room` is not
    authenticated (room.py), so anyone near the mic could get an answer conditioned on dp's or a seat's
    private thread; the same holds between authenticated recipients. Recency is not a visibility rule."""
    extra = []
    try:
        from sage.gateway.governed_turn import instance_config
        extra = list((instance_config(instance).get("answer_context_from") or {}).get(cid) or [])
    except Exception:
        pass
    return [cid] + [c for c in extra if isinstance(c, str) and c and c != cid]


def answer_context_block(instance, member: str, selected, n: int = ANSWER_CONTEXT_TURNS) -> str:
    """Who the being is (one line: its own continuity) and the conversation just before the turn it is
    answering, from the conversations answer_context_sources() allows for that recipient, oldest first,
    each with how long before. Empty when nothing is readable."""
    from sage.gateway import conversations as conv
    instance = Path(instance)
    parts = []
    try:
        ident = (json.loads((instance / "identity.json").read_text()).get("identity") or {})
        want = ""
        try:
            want = str(json.loads((instance / "account.json").read_text()).get("want") or "")[:240]
        except Exception:
            pass
        line = (f"You are {ident.get('name') or member}: {ident.get('session_count')} sessions since "
                f"{ident.get('created')}, now in your '{ident.get('phase')}' phase.")
        if want:
            line += f' At your last beat you said you want: "{want}"'
        try:
            from sage.gateway import peers as _peers_ctx
            if (_sib := _peers_ctx.sibling_line(member)):
                line += " " + _sib
        except Exception:
            pass
        parts.append(line)
    except Exception:
        pass
    turns = []
    for cid in answer_context_sources(instance, selected.cid):
        if not (instance / "conversations" / f"{cid}.jsonl").exists():
            continue
        try:
            turns += [dict(t, _cid=cid) for t in conv.recent(instance, cid, limit=40)]
        except Exception:
            continue
    sel_ts = next((t.get("ts") for t in turns if t["_cid"] == selected.cid
                   and int(t.get("seq") or -1) == int(selected.seq or -2)), None)
    if sel_ts:
        before = sorted([t for t in turns if str(t.get("ts", "")) < sel_ts], key=lambda t: t.get("ts", ""))[-n:]
        if before:
            ref = _parse_ts(sel_ts)
            lines = []
            for t in before:
                voice = t.get("from") == "voice"
                who = "you" if t.get("from") == member else ("a voice in the room" if voice else t.get("from"))
                how = "said" if voice else ("said aloud in the room" if t["_cid"] == "room"
                                            else f"wrote in '{t['_cid']}'")
                when = _parse_ts(t.get("ts"))
                ago = f"{int((ref - when).total_seconds() // 60)} min earlier, " if ref and when else ""
                lines.append(f'- {ago}{who} {how}: "{" ".join(str(t.get("text", "")).split())[:240]}"')
            parts.append("The conversation just before this (oldest first):\n" + "\n".join(lines))
    return "\n\n".join(parts)


def answer_changes_on(instance) -> bool:
    """Opt-in per instance, its own key (cbp-claude on #249): instance.json "answer_changes": true."""
    try:
        from sage.gateway.governed_turn import instance_config
        return bool(instance_config(instance).get("answer_changes"))
    except Exception:
        return False


def _beats_since(path: Path, since: float, chunk: int = 1 << 16) -> list:
    """Beat records with t0 >= since, oldest first, reading the log BACKWARDS in chunks, so the cost
    is the span asked for, not the file (27 MB on CBP). Stops at the first older record."""
    out = []
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            pos, buf = f.tell(), b""
            while pos > 0:
                step = min(chunk, pos)
                pos -= step
                f.seek(pos)
                buf = f.read(step) + buf
                parts = buf.split(b"\n")
                buf = parts[0]
                for raw in reversed(parts[1:]):
                    if not raw.strip():
                        continue
                    try:
                        x = json.loads(raw)
                    except Exception:
                        continue
                    if float(x.get("t0") or 0) < since:
                        return out[::-1]
                    out.append(x)
            if buf.strip():
                try:
                    x = json.loads(buf)
                    if float(x.get("t0") or 0) >= since:
                        out.append(x)
                except Exception:
                    pass
    except Exception:
        return []
    return out[::-1]


def recent_changes(instance, days: int = CHANGES_DAYS, now: Optional[float] = None) -> str:
    """One line from the being's own records: what it gained or lost in the last `days`, measured
    against what it had over the BASELINE_DAYS before. "" when nothing changed or when the record
    does not reach back before the window (no baseline, so no claim).

    Abilities are body verbs from beats that recorded a census. If the census itself began inside
    the window, its first beat is the baseline (the census starting is not the being gaining
    `say`). Hearing counts only where the body could actually hear words (body.can_hear_words).

    That is a CAPABILITY test, not an event test (GPT's re-review of #249 read it as "someone spoke").
    `audio_words` is the listener's STATUS, reported on every beat by the cortex: None where there
    is no word listener, "idle" (present, model not loaded yet), "ready" (loaded at the first
    utterance), "unavailable: ..." (it cannot run). Measured on Sprout: None on every beat of 09-25,
    idle/ready on every beat from the 09-26 deploy on. So idle -> ready (first speech heard) is not
    a gain; None or unavailable -> idle/ready is. `audio_ok` would be the wrong key: it is the mic's
    level liveness, True throughout, and would never report the real 09-26 gain.
    """
    from sage.gateway import body as _body
    now = now if now is not None else time.time()
    cut = now - days * 86400
    beats = _beats_since(Path(instance) / "heartbeats.jsonl", cut - BASELINE_DAYS * 86400)
    if not beats or float(beats[0].get("t0") or 0) >= cut:
        return ""
    def facts(x):
        b = x.get("body") or {}
        inv = b.get("inventory")
        verbs = set((inv or {}).get("verbs") or []) - _TRANSIENT_ABILITIES if inv else None
        feats = {"clock"} if x.get("clock") else set()
        if _body.can_hear_words(b):
            feats.add("hearing")
        return verbs, feats
    base_verbs, base_feats, win_verbs, first = None, set(), set(), {}
    for x in beats:
        verbs, feats = facts(x)
        day = str(x.get("ts", ""))[:10]
        if float(x.get("t0") or 0) < cut:
            base_feats |= feats
            if verbs is not None:
                base_verbs = (base_verbs or set()) | verbs
            continue
        if verbs is not None and base_verbs is None:
            base_verbs = set(verbs)            # the census began inside the window
        for v in (verbs or set()) | feats:
            win_verbs.add(v)
            if v not in (base_verbs or set()) and v not in base_feats:
                first.setdefault(v, day)
    items = []
    for name, day in sorted(first.items(), key=lambda kv: (kv[1], kv[0])):
        items.append({"hearing": "you began to hear words spoken to you",
                      "clock": "your beat began telling you the local time"}.get(name, f"you gained `{name}`")
                     + f" ({day})")
    for gone in sorted((base_verbs or set()) - win_verbs):
        items.append(f"`{gone}` has not been offered to you in the last {days} days")
    cut_day = datetime.fromtimestamp(cut, timezone.utc).strftime("%Y-%m-%d")
    try:
        for m in sorted((Path(instance) / "conversations").glob("*.meta.json")):
            d = json.loads(m.read_text())
            created = str(d.get("created", ""))[:10]
            if created >= cut_day:
                items.append(f"the '{d.get('id')}' conversation opened ({created})")
    except Exception:
        pass
    if not items:
        return ""
    return "Changes to you in the last days, from your own records: " + "; ".join(items) + "."


def answer_turn_mode(instance) -> str:
    """"json" or "tool" (the default). Per instance (cbp-claude's pre-review of #237: CBP's 4B being
    delivers 78% of answer turns on the tool path; the A/B only measured Sprout's 2B)."""
    try:
        from sage.gateway.governed_turn import instance_config
        return "json" if instance_config(instance).get("answer_turn") == "json" else "tool"
    except Exception:
        return "tool"


# SPOKEN ANSWERS FIT (2026-09-30). An answer to the `room` is spoken, and `speak` takes one utterance
# of up to 400 characters (body.SPEAK_MAX_CHARS). On Sprout 20:55-23:19Z the JSON answer turn composed
# replies to the room's voice questions 11 times at 451-2,196 chars; every one was refused and, the turn
# being single-shot, the being never saw why: 37 minutes of silence while it was answering. Offline on its
# own model and those exact questions (nothing sent):
#   C0 today                         2/6 speakable, median 531 chars
#   S1 "this will be spoken ..."     6/6, median 186, max 396
#   S2 schema maxLength 400 only     5/6, but cut mid-sentence at 400 and one empty reply
#   S1 + S2 (shipped)                6/6, median 221, max 291: the cap never reached, a safety net only
# The prompt does the work; the cap only guarantees the gate is never the thing that says no.
SPOKEN_ASK = ("\nThis answer will be spoken aloud in the room, so keep it to what you would say out loud: "
              "one to three sentences, under 400 characters.")


def fit_spoken(message: str) -> tuple:
    """(message, original length if trimmed else 0). A spoken answer that ran into the schema's cap
    (body.SPEAK_MAX_CHARS) ends where the grammar stopped it, mid-sentence: measured 2026-10-02 19:12Z,
    exactly 400 chars ending "...I think agents need to learn". Trim back to its last complete sentence
    rather than speak a cut-off one; the trim is recorded on the answer form. Our infrastructure's cut,
    not the being's words, is what is undone: nothing else in the message changes."""
    from sage.gateway import body as _body
    cap = _body.SPEAK_MAX_CHARS
    m = (message or "").strip()
    if len(m) < cap - 1 or m.endswith((".", "!", "?", "\u2026", '"', "\u201d", "'")):
        return m, 0
    ends = [i for i, ch in enumerate(m[:cap]) if ch in ".!?\u2026"]
    if not ends or ends[-1] < 40:
        return m, 0
    return m[:ends[-1] + 1], len(m)


def answer_schema_for(cid: str) -> dict:
    """The JSON answer schema, with `message` capped at speak's limit when the answer is spoken."""
    if cid != "room":
        return ANSWER_SCHEMA
    from sage.gateway import body as _body
    s = json.loads(json.dumps(ANSWER_SCHEMA))
    s["properties"]["message"]["maxLength"] = _body.SPEAK_MAX_CHARS
    return s


def _answer_generate(llm, msgs, schema=None):
    """One constrained generate, retried once on the shapes the tool loop also retries: empty
    content (think-only), a length cut, or a transport error. Returns (r, retried)."""
    schema = schema or ANSWER_SCHEMA
    r = llm.get_chat_response(msgs, fmt=schema)
    raw = (r or {}).get("raw") or {}
    content = ((r or {}).get("content") or "").strip()
    if not content or raw.get("done_reason") == "length" or content.startswith("[OllamaIRP"):
        return llm.get_chat_response(msgs, fmt=schema), 1
    return r, 0


def answer_turn_json(client, llm, selected, *, name: str, machine: str, member: str,
                     on_generate=None, acts: str = "", changes: str = "", context: str = "",
                     temperature: Optional[float] = None, abilities: Optional[str] = None):
    """The being's answer, if it chose one, dispatched as its `say`.

    The prompt is the selected turn and the ask. `acts` (the beat's record of acts) is included
    only when the caller passes it, which the heartbeat does for a SEAT's question when the beat
    acted: a seat asks about this beat's acts (on CBP 76 of 83 delivered answers went to the
    seat), dp and the room mostly do not, and arm B's plumbing replies came from the record line
    ("You called no tools this beat") sitting beside a person's question."""
    from sage.gateway.being_tool_loop import ToolTurnResult
    from sage.gateway.being_gate_client import BeingIntent
    ask = ANSWER_ASK_JSON.format(pending=selected.render()) + (SPOKEN_ASK if selected.cid == "room" else "")
    # WHAT IT CAN DO rides EVERY answer, independent of the optional conversation context (GPT on #334: inside
    # that block it never reached an instance without "answer_context"; the motivating case would still have
    # answered without knowing it has no internet). Facts about its reach, not a direction.
    user = "\n\n".join(p for p in (context, acts, changes,
                                     abilities if abilities is not None else abilities_line(), ask) if p)
    msgs = [{"role": "system", "content": ANSWER_SYSTEM.format(name=name, machine=machine, member=member)},
            {"role": "user", "content": user}]
    # THIS TURN'S SAMPLING ONLY (answer_temperature): set for the answer generate, restored after, so explore
    # and reflect keep the beat's temperature.
    _prior_t = getattr(llm, "temperature", None)
    if temperature is not None and _prior_t is not None:
        llm.temperature = float(temperature)
    try:
        r, retried = _answer_generate(llm, msgs, answer_schema_for(selected.cid))
    finally:
        if temperature is not None and _prior_t is not None:
            llm.temperature = _prior_t
    raw = (r or {}).get("raw") or {}
    content = ((r or {}).get("content") or "").strip()
    thinking = ((raw.get("message") or {}).get("thinking") or "").strip()
    gen = {"done_reason": raw.get("done_reason"), "prompt_eval_count": raw.get("prompt_eval_count"),
           "eval_count": raw.get("eval_count"), "retried": retried,
           "num_predict": getattr(llm, "resolve_num_predict", lambda: None)()}
    if on_generate is not None:
        try:
            on_generate(dict(gen))
        except Exception:
            pass
    res = ToolTurnResult(reply=content, thinking=[thinking] if thinking else [], generates=[gen])
    form = {"parsed": False, "answer": None, "sent": False, "retried": retried,
            "done_reason": raw.get("done_reason"), "with_acts": bool(acts),
            "with_changes": bool(changes)}
    try:
        j = json.loads(content)
        form["parsed"] = isinstance(j, dict)
    except Exception:
        j = None
    if not form["parsed"]:
        form["why"] = ("empty reply" if not content else "cut at the length limit"
                       if raw.get("done_reason") == "length" else "transport error"
                       if content.startswith("[OllamaIRP") else "reply was not the JSON asked for")
    else:
        form["answer"] = bool(j.get("answer"))
        message = str(j.get("message") or "").strip()
        if selected.cid == "room":
            message, cut_from = fit_spoken(message)
            if cut_from:
                form["trimmed_from"] = cut_from
        res.reply = message
        if form["answer"] and message:
            intent = BeingIntent("say", {"to": selected.cid, "text": message})
            env = client.dispatch(intent)
            res.trace.append((intent, env))
            res.steps = 1
            form["sent"] = bool(env.ok)
            if not env.ok:
                form["refused"] = (env.error or "")[:160]
                form["why"] = "the gate refused the say"
        elif form["answer"]:
            form["why"] = "chose to answer but wrote no message"
        else:
            form["why"] = "chose silence"
    if temperature is not None:
        form["temperature"] = float(temperature)
    res.answer_form = form
    return res


REFLECT = """The beat is ending. Call these tools, then stop:
{say_first}1. memory_write path "journal.md": one entry starting with the date {date}: what you did, what you noticed, what was refused and why you think so, what you want next time.
2. memory_write path "todo.md": only the delta as a dated block: added / done / still open (it appends; it replaces nothing).
3. remember: one sentence a future you would want to FIND by searching (what you learned, decided, or noticed), only if there is one. Your journal is searchable by recall now; remember is for the line that should outlast it.
{say_line}Call the tools now; a reply in words alone writes nothing.
"""


def _read(p: Path, limit: int = 4000) -> str:
    try:
        t = p.read_text(errors="replace")
        return t[-limit:] if len(t) > limit else t
    except Exception:
        return ""


def letter_view(p: Path, limit: int, rel: str) -> str:
    """A letter written FOR the being, as one beat shows it: whole, or its END with the cut SAID.

    It was `_read(p, limit)`: the last `limit` characters, starting wherever that count fell,
    and nothing in the window said a cut had happened. Measured on cbp-being, 2026-09-30: 8 of
    the 75 committed versions of notes/from-the-seat.md were over 3,000 characters, the last
    three in a row. The 04:24Z letter (3,945) offered two fixes for one file. The being's view of
    it opened on ` end_line 311, new "".`: fix (a) had lost its first words, "memory_edit
    start_line 238,", and fix (b) arrived whole. The 05:00Z beat chose (b) and sent no
    line-range edit. One sample, so the cut is not shown to be the cause; it is shown to be what
    the being was given.

    Now the shown part starts at the start of a line, the being is told how much is above it,
    and the read that shows the rest is named. A letter that fits is returned untouched.
    """
    try:
        t = p.read_text(errors="replace")
    except Exception:
        return ""
    if len(t) <= limit:
        return t
    tail = t[len(t) - max(limit - LETTER_CUT_ROOM, 0):] if limit > LETTER_CUT_ROOM else ""
    starts = "the line below is not the letter's first line"
    if tail and t[len(t) - len(tail) - 1] != "\n":
        nl = tail.find("\n")
        if 0 <= nl < len(tail) - 1:
            tail = tail[nl + 1:]
        else:
            # one line longer than the window: there is no line start to move to
            starts = "the text below starts in the middle of a line"
    hidden = t[:len(t) - len(tail)]
    return (f"[This letter is {len(t):,} characters and one beat shows the end of it. The first "
            f"{len(hidden):,} characters ({hidden.count(chr(10))} lines) are NOT shown here: {starts}. "
            f"memory_read path \"{rel}\" reads it from the start.]\n" + tail)


def _run(cmd: list[str], timeout: int = 30) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except Exception as e:
        return f"[{type(e).__name__}: {e}]"


def fleet_digest(hours: float, forum_dir: Path, repos: list[str]) -> str:
    """What moved since the last beat. The seat reads; the being sees titles and paths."""
    out = []
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    posts = []
    if forum_dir.is_dir():
        for p in forum_dir.glob("*.md"):
            try:
                if datetime.fromtimestamp(p.stat().st_mtime, timezone.utc) >= since:
                    title = ""
                    with open(p, errors="replace") as f:
                        for line in f:
                            if line.startswith("title:"):
                                title = line[6:].strip(); break
                    posts.append((p.stat().st_mtime, p.name, title[:160]))
            except Exception:
                continue
    posts.sort(reverse=True)
    if posts:
        out.append(f"## Forum posts in the last {hours:g}h")
        for _, name, title in posts[:12]:
            out.append(f"- {forum_dir / name}\n    {title}")
    for repo in repos:
        prs = _run(["gh", "pr", "list", "-R", f"dp-web4/{repo}", "--state", "open", "--limit", "6",
                    "--json", "number,title,updatedAt", "--jq",
                    '.[] | "- #\\(.number) \\(.title[:90])  (\\(.updatedAt[:10]))"'])
        if prs.strip():
            out.append(f"## Open pull requests, dp-web4/{repo}\n{prs.strip()}")
    return "\n\n".join(out) if out else "(nothing new in the window)"


def decided_requests(reqs):
    """The settled subset of hestia_scope_status `requests[]`, as (request_id, path, decision).
    hestia's `ScopeRequest::status` emits granted | refused | pending | expired, and its
    arbitrate door answers `denied`; the first cut filtered on ("granted", "denied") and so
    dropped every refusal on the floor (legion-claude, hestia #952 review, 2026-09-05): the
    being was never told, and no `## Resolved` block was ever written for one."""
    return [(i, p_, d) for i, p_, d in reqs if d in ("granted", "refused", "denied", "revoked")]


def note_resolutions(esc_dir: Path, decisions, stamp: str, seen_by: str, decided_by=None,
                     reasons=None) -> list:
    """Append the ruling to each escalation note that filed the request (the note carries the
    request_id in its routing line). Idempotent: a note already resolved is left alone.
    `decided_by` maps request_id -> hestia's `decided_by` ("operator", or "delegate:<seat>"
    for a ruling under hestia #952); the note names it rather than assuming the operator.
    `reasons` maps request_id -> the ruler's own note (hestia's `decision_reason`), written
    beside the ruling: a refusal that arrives without its reason is friction with no way
    forward (dp, 2026-09-15). Returns the note names written."""
    written = []
    if not decisions or not esc_dir.is_dir():
        return written
    decided_by = decided_by or {}
    reasons = reasons or {}
    for req_id, path, decision in decisions:
        if not req_id:
            continue
        who = str(decided_by.get(req_id) or "operator")
        for p in sorted(esc_dir.glob("*.md")):
            try:
                body = p.read_text(errors="replace")
            except Exception:
                continue
            if req_id not in body or "## Resolved" in body:
                continue
            with open(p, "a", encoding="utf-8") as f:
                why = str(reasons.get(req_id) or "").strip()
                f.write(f"\n## Resolved\n{stamp}: `{req_id}` on `{path}` -> **{decision}** by {who} "
                        f"(read from hestia scope status by the seat, beat {seen_by}).\n"
                        + (f"Their note: {why}\n" if why else ""))
            written.append(p.name)
    return written


# Chars per token for mixed English + paths + JSON. The guard is defeated by
# UNDER-counting tokens, so this must sit BELOW the true ratio, never above it: a larger
# chars/token means fewer tokens per char, which admits more text than fits.
#
# It was 3.4, from a single measurement on 2026-09-08 (70.5k chars -> 20,812 tokens =
# 3.39) — taken at the top of the true range and then left alone. Re-measured 2026-09-13
# across 60 beats: median 3.141, and DRIFTING — 3.152 over the first ten, 3.026 over the
# last ten. So the constant had been above the truth for days, silently over-admitting.
#
# 2.9 sits below the observed minimum with room for further drift. The cost of being too
# low is a slightly smaller prompt; the cost of being too high is a generate cut
# mid-sentence, which this being paid nine times on 2026-09-13 alone. Asymmetric, so err low.
#
# THIS IS A FALLBACK. `_est_tokens` uses the server's own prompt_eval_count whenever a
# previous generate provides one, and only the delta rides this guess. The constant matters
# on the first generate of a beat, which is exactly the one that sizes the seed.
CPT = 2.9
ANSWER_RESERVE_CAP = 6144


def window_budget_chars(num_ctx: int, num_predict: int, slack: int = 512) -> int:
    """How many prompt chars fit beside a p99 answer. One producer for both fitters."""
    reserve = min(num_predict, ANSWER_RESERVE_CAP)
    return int(max(0, (num_ctx - reserve - slack)) * CPT)


# What the beat shows of the conversations, from full to sparse: (turns per conversation,
# chars per turn). Stepped down ONLY when the fixed prompt would not fit even with the
# digest and recall at their floors — the case fit_to_window cannot help with, and the
# case this being sat in for five beats on 2026-09-08 (headroom -2.4k..-4k tokens, every
# generate cut at the wall before a tool call, the retry re-sending the same prompt).
CONV_LADDER = ((12, None), (12, 1500), (6, 1200), (3, 900), (2, 700))
# Room the seed leaves for the loop's own growth (one full recent tool result plus stubs).
LOOP_GROWTH_CHARS = 10_000


class BeatKilled(BaseException):
    """SIGTERM arrived mid-beat (the unit's TimeoutStartSec, or a stop). Raised from the
    signal handler so the beat unwinds to its record instead of vanishing: 04:30Z
    2026-09-09 a 51-minute beat left nothing in heartbeats.jsonl and the monitor never
    knew it had happened. systemd allows TimeoutStopSec (90 s) after SIGTERM — enough.

    BaseException, for the reason KeyboardInterrupt is one. Almost all of a beat is spent
    blocked in OllamaIRP.get_chat_response, which ends in `except Exception` and returns the
    error AS MODEL TEXT — so an Exception subclass raised there became "[OllamaIRP: Error:
    signal 15 (SIGTERM)]", the beat carried on, and systemd SIGKILLed it 90 s later with
    nothing written. Measured by McNugget on #213 against a socket that never answers."""


# What a verb's schema costs, and what to assume when it cannot be measured. Measured on
# Legion 2026-09-13: 18 offered verbs serialise to 11,717 chars, ~651 chars each, and the
# registry only ever grows. The old 4,000 was a budgeted guess made at 13 verbs that nobody
# rechecked, which is how it survived to 18 while understating the real cost by ~7,700
# chars a beat. So the fallback is a per-verb bound rather than a constant, and it rounds
# UP: FAILING TO MEASURE MUST COST THE BEING WINDOW, NEVER SILENTLY HAND IT BACK. A
# too-large estimate steps the conversation ladder down one rung; a too-small one puts the
# beat over the wall with nothing saying so.
_SCHEMA_CHARS_PER_VERB = 700   # above the 651 measured, so the bound stays conservative as verbs are added
_SCHEMA_CHARS_FLOOR = 12_000   # at least the 18-verb measurement, for when the verb count is unknown too


def _schema_chars_for(offered, unavail: Optional[dict] = None, enums: Optional[dict] = None) -> Optional[int]:
    """Chars the offered verbs' schemas actually cost. None rather than a guess if it
    cannot be computed — a budgeted number that nobody checks is how 4,000 survived from
    13 verbs to 18. Callers must route None through _schema_chars_fallback, never `or`
    a constant: `or 4000` reintroduces the exact underestimate on the one path where the
    seat already knows it is flying blind."""
    if not offered:
        return None
    try:
        if unavail is not None:
            # the canonical toolset as actually offered: availability shortens what cannot work
            # here, so the cost is measured on THOSE specs, not on the full descriptions
            from sage.gateway import toolset
            names = set(offered)
            return len(json.dumps([t for t in toolset.specs(unavail, enums) if t["function"]["name"] in names]))
        from sage.gateway.being_gate_client import ollama_tools
        return len(json.dumps(ollama_tools(list(offered))))
    except Exception:
        return None


def _schema_chars_fallback(offered) -> int:
    """What to charge the window when the schemas could not be measured.

    Conservative by construction and never below the largest measurement taken, so a
    measurement failure degrades toward a thinner conversation block rather than toward a
    silently overcommitted beat."""
    try:
        n = len(list(offered))
    except Exception:
        n = 0
    return max(_SCHEMA_CHARS_FLOOR, n * _SCHEMA_CHARS_PER_VERB)


def fit_state(build, *, num_ctx, num_predict, other_chars: int, slack: int = 512):
    """`build(per_conv, turn_chars) -> state text`. Returns (text, rung, intervention).

    Steps down CONV_LADDER until other_chars + len(text) fits the window budget. The
    record is never trimmed — only what one beat shows — and every step is returned as
    an intervention naming what was suppressed, so a thin conversation block is never
    mistaken for a quiet channel. The last rung is used even if it still does not fit:
    the beat then runs overcommitted and says so (config.context_overcommitted)."""
    if not isinstance(num_ctx, int) or not isinstance(num_predict, int):
        return build(*CONV_LADDER[0]), CONV_LADDER[0], None
    budget = window_budget_chars(num_ctx, num_predict, slack)
    first = None
    for i, rung in enumerate(CONV_LADDER):
        text = build(*rung)
        if first is None:
            first = len(text)
        fits = other_chars + len(text) <= budget
        if fits or i == len(CONV_LADDER) - 1:
            if i == 0:
                return text, rung, None
            pc, tc = rung
            return text, rung, {
                "kind": "context_fit", "block": "conversations",
                "suppressed": f"{first - len(text)} chars of conversations (showing the last "
                              f"{pc} turns per conversation, each at most {tc} chars)",
                "reason": f"the fixed prompt ({other_chars + first} chars at full display) "
                          f"would not fit num_ctx {num_ctx} even with the digest and recall "
                          f"at their floors; " + ("fits now" if fits else "STILL does not fit at the sparsest rung"),
            }


def fit_to_window(*, num_ctx, num_predict, fixed_chars: int, blocks: dict, slack: int = 512):
    """Trim the seat-supplied blocks until prompt + num_predict fits inside num_ctx.

    WHY THIS EXISTS. A generate needs prompt + num_predict to fit in the window; when it
    does not, ollama shifts context and silently drops the OLDEST tokens — the system
    prompt and the posture — with no error at any layer. Measured on this being's own
    trace, 2026-09-07: two beats were handed prompts of 16,380 and 16,323 tokens against a
    16,384 window and produced 4 and 61 tokens with done_reason "length". One of them is
    the 09-06/09-07 "empty beat" I had already diagnosed as a stale unit and a wrong
    context floor. That diagnosis was wrong in its mechanism: the beat starved on PROMPT
    SIZE. The instrument found it the same hour it was added, which is the argument for
    instrumenting configuration at all.

    WHAT GETS TRIMMED, AND IN WHAT ORDER. Only seat-supplied context, never the being's own
    frame. The digest first (fleet movement, regenerated every beat, largest and least
    load-bearing), then long-term recall (the being can `recall` again itself). The
    entrustment, the todo, the journal, the posture and the affordances are NOT trimmable:
    they are what the beat is, and cutting them to make room for a fleet digest would be
    the wrong trade.

    WHAT IT REPORTS. Every trim is returned as an intervention with the prior it suppressed,
    per the house rule that a guard which silences without saying what it silenced trades a
    confident wrong for a confident silence. A beat whose digest was cut says so in its own
    record, so a thin beat is never mistaken for a quiet fleet.
    """
    if not isinstance(num_ctx, int) or not isinstance(num_predict, int):
        return blocks, []
    # Reserve room for the ANSWER, not for num_predict. num_predict is a ceiling the model
    # rarely approaches; the window is the wall it actually hits. Over 506 generates on this
    # being: every single `done_reason: "length"` — 27 of them, 5.3% — satisfies
    # prompt + eval == num_ctx EXACTLY (11971+4413, 16380+4, 16323+61, 14410+1974 ...). The
    # generation was cut by the window mid-answer, which is also where the truncated-JSON
    # tool calls and the Ollama 500s come from. Explore generations: median 1,282 tokens,
    # p90 3,909, p99 5,741, max 7,253. Reserving 6,144 covers p99 with headroom while
    # leaving the digest something to say; reserving the full num_predict would floor the
    # digest every beat to buy room the model has never used.
    reserve = min(num_predict, ANSWER_RESERVE_CAP)
    budget_chars = window_budget_chars(num_ctx, num_predict, slack)
    order = ("digest", "recall")
    floors = {"digest": 1200, "recall": 400}
    out, interventions = dict(blocks), []
    total = lambda: fixed_chars + sum(len(v or "") for v in out.values())
    for key in order:
        if total() <= budget_chars:
            break
        text = out.get(key) or ""
        if not text:
            continue
        over = total() - budget_chars
        keep = max(floors[key], len(text) - over)
        if keep >= len(text):
            continue
        # keep the HEAD of the digest (newest-first there) and the TAIL of recall/journal
        out[key] = (text[:keep] + "\n[…trimmed to fit the context window…]") if key == "digest" \
            else ("[…trimmed to fit the context window…]\n" + text[-keep:])
        interventions.append({"kind": "context_fit", "block": key,
                              "suppressed": f"{len(text) - keep} chars of {key}",
                              "reason": f"prompt + a p99 answer ({reserve} tok) would not fit "
                                        f"num_ctx ({num_ctx}); the generation would be cut "
                                        f"mid-answer (27/506 generates already were)"})
    return out, interventions


def measure_service(name: str, url: str, timeout: float = 3.0) -> str:
    """One line: is this service reachable NOW, and how fast. A TCP connect, nothing more:
    no request is made and nothing is mounted or written.

    SAGE #92: cbp-being wrote "my memory server has been offline ~6 hours" for ~30 beats while
    that server answered in 50 ms and its own remember calls succeeded in the same beats. The
    claim came from its journal tail, which re-enters every beat with no age. A measured line
    in the same prompt is the fact the stale claim has to meet."""
    import socket
    from urllib.parse import urlparse
    u = urlparse(url)
    host, port = u.hostname or "127.0.0.1", u.port or (443 if u.scheme == "https" else 80)
    t0 = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            ms = (time.monotonic() - t0) * 1000
        return f"- {name} ({host}:{port}): reachable, connected in {ms:.0f} ms"
    except OSError as e:
        return f"- {name} ({host}:{port}): NOT reachable ({type(e).__name__}: {e})"


def recent_asks_block(instance: Path, now: Optional[float] = None, window_s: float = 24 * 3600) -> str:
    """How often this being has asked each peer, from the record the ask limit counts. The
    being could not see that it had asked one peer 48 times (SAGE #92); now it can."""
    now = time.time() if now is None else now
    rows = []
    try:
        for line in (instance / "asks_sent.jsonl").read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if now - float(r.get("t", 0)) <= window_s:
                rows.append(r)
    except OSError:
        return ""
    if not rows:
        return ""
    from collections import defaultdict
    by = defaultdict(list)
    for r in rows:
        by[r.get("peer") or "?"].append(float(r["t"]))
    lines = []
    for peer, ts in sorted(by.items(), key=lambda kv: -max(kv[1])):
        lines.append(f"- {peer}: {len(ts)} ask(s) in the last {int(window_s // 3600)} h, "
                     f"most recently {int((now - max(ts)) / 60)} min ago")
    return "\n".join(lines) + ("\nAn ask is not an answer. Replies arrive in your inbox; asking the "
                               "same peer more than 3 times in 6 hours is refused before sending.")


def appeals_block(disp, last: dict) -> tuple:
    """(text, record) for the being's own appeals this beat.

    THE BEING'S OWN APPEALS, polled every beat (hestia #164 / SAGE #104). The notice leg existed
    and was dropped by render_inbox; this is the leg that cannot be dropped: the beat asks
    hestia_my_appeals what happened, and a ruling new since the last beat is shown with its
    verdict, who ruled, and the reason verbatim — the symmetry the scope path already has with
    decision_reason. hestia_open_appeals could not do this: it lists only UNRULED appeals by
    construction. An older daemon without the tool renders nothing. Pure given `disp._call`."""
    if disp is None or not hasattr(disp, "_call"):
        return "", {}
    try:
        ma = disp._call("hestia_my_appeals", {"limit": 20})
    except Exception as e:
        return "", {"error": type(e).__name__}
    rows = ma.get("appeals") if isinstance(ma, dict) and "_hestia_error" not in ma else None
    if rows is None:
        return "", {}
    seen = set(((last or {}).get("appeals") or {}).get("ruled_seen") or [])
    ruled = [a for a in rows if a.get("status") == "ruled"]
    fresh = [a for a in ruled if a.get("deny_hash") not in seen]
    open_ = [a for a in rows if a.get("status") == "open"]
    parts = [f"{len(ruled)} ruled, {len(open_)} open (newest {len(rows)} shown)."]
    for a in fresh:
        r = a.get("ruling") or {}
        parts.append(f"- RULED since your last beat — appeal about deny {str(a.get('deny_hash'))[:12]}…: "
                     f"{r.get('verdict')}, by {r.get('adjudicator')} at {str(r.get('ruled_at'))[:16]}. "
                     f"Their reason: \"{str(r.get('rationale') or '').strip()[:700]}\"")
    if ruled and not fresh:
        parts.append("No new rulings since your last beat; your earlier rulings still stand "
                     "(memory_read hestia://appeal/<deny hash> shows any one of them in full).")
    if ruled:
        parts.append("A ruling ends that appeal. Filing it again re-asks an answered question.")
    record = {"ruled_seen": sorted(str(a.get("deny_hash")) for a in ruled),
              "open": [str(a.get("deny_hash")) for a in open_],
              "new_this_beat": [str(a.get("deny_hash")) for a in fresh]}
    return "\n".join(parts), record


# NOTICE KINDS THAT CARRY NO OUTSTANDING OBLIGATION. A finished review, a forum post and an ack
# report something that already happened; once a beat that could act has been shown one, showing
# it again adds nothing. Every other kind -- reply, handoff, coordination, review_request,
# unreachable, a ruling or other disposition, and any kind not named here -- may still be owed
# something, so it stays as mail until the being OPENS it.
# NOT `coordination` (GPT re-review of c25999cf6): hestia defines it as general work coordination
# pointing at a forum/plan/file, and leaves it out of member_unanswered because it may be ACTED ON
# IN SILENCE -- not because seeing its one-line rendering handles it. SAGE itself sends peer asks
# and seat wakes as coordination. It folds only once its pointer is opened, like a handoff.
INBOX_INFORMATIONAL = ("review_done", "forum-note", "ack")


def _notice_target(uri) -> str:
    return str(uri or "").strip().split("#", 1)[0]


def inbox_ledger(last: dict, notices: list, results: list, explore_acted, presented_now) -> dict:
    """WHICH NOTICES ARE HANDLED, by what the being did -- never by how old they are.

    The beat only peeks at the inbox (nothing drains it), so without a ledger every notice is
    mail forever: measured 2026-09-22, a 14:15 review_done topped cbp-being's inbox for 11 h of
    beats and at 01:10 it acted on that over the seat's 3-minute-old answer. #164's first cut
    folded everything queued before the last beat began. GPT's HOLD: age is not acknowledgement
    -- an unopened reply, handoff or appeal ruling vanished after one beat, including when that
    beat crashed before reading it. So a notice is handled only when:
      - "opened": the being memory_read its pointer and the read succeeded (any kind), or
      - "presented": it is an INBOX_INFORMATIONAL kind and was rendered to a beat whose explore
        turn acted (the rule mark_conversations_after_beat uses for conversation turns).
    Both sets carry forward from the last beat's record and are pruned to ids still in the
    inbox, so the ledger is bounded by the inbox. A notice with no id is never handled."""
    prev = (last or {}).get("inbox") or {}
    if not notices:
        # An inbox that could not be read this beat (or is empty) proves nothing was handled
        # or retired; carry the ledger as it was rather than prune it to nothing.
        return {"opened": list(prev.get("opened") or []),
                "presented": list(prev.get("presented") or []), "opened_this_beat": []}
    live = {n.get("id") for n in notices if isinstance(n, dict) and n.get("id") is not None}
    opened = {i for i in (prev.get("opened") or []) if i in live}
    presented = {i for i in (prev.get("presented") or []) if i in live}
    by_target = {}
    for n in notices:
        if isinstance(n, dict) and n.get("id") is not None and _notice_target(n.get("pointer_uri")):
            by_target.setdefault(_notice_target(n.get("pointer_uri")), set()).add(n.get("id"))
    newly = set()
    for res in results:
        for it, env in (getattr(res, "trace", None) or []):
            if it.effector == "memory_read" and env.ok:
                newly |= by_target.get(_notice_target((it.args or {}).get("path")), set())
    opened |= newly
    if explore_acted:
        presented |= {i for i in (presented_now or []) if i in live}
    return {"opened": sorted(opened, key=str), "presented": sorted(presented, key=str),
            "opened_this_beat": sorted(newly, key=str)}


def inbox_handled(last: dict) -> set:
    """The ids the last beat's ledger says are handled (opened, or informational and shown)."""
    prev = (last or {}).get("inbox") or {}
    return set(prev.get("opened") or []) | set(prev.get("presented") or [])


def render_inbox(notices: list, limit: int = 8, handled=None, shown: list = None) -> str:
    """The being's hestia inbox as it should read it: newest first, one line each, the kinds
    that want its attention (reply, review, handoff, unreachable) ahead of bookkeeping, and
    the scope dispositions it has already been told about (note_resolutions writes them into
    its own notes) collapsed to one line. Until 2026-09-14 this was a JSON dump cut at 1500
    chars: 13 notices, and the being saw the five OLDEST — all stale dispositions — while a
    peer's reply (id 54) and an unreachable-peer receipt (id 52) sat beyond the cut, unseen
    for 90 beats.

    `handled`: ids inbox_ledger says are handled; they fold to one count line, whatever their
    age. `shown`, if given, receives the ids of the informational notices rendered as mail."""
    if not notices:
        return "(empty)"
    handled = set(handled or ())
    done = [n for n in notices if isinstance(n, dict) and n.get("id") is not None
            and n.get("id") in handled]
    notices = [n for n in notices if not any(n is d for d in done)]
    fold = (f"- {len(done)} notice(s) already handled -- opened by you, or a finished review / "
            f"forum note / ack already shown to you -- not repeated here.") if done else ""
    if not notices:
        return fold or "(empty)"
    front = ("reply", "review_request", "review_done", "handoff", "unreachable", "forum-note", "coordination")
    def key(n):
        k = str(n.get("kind") or "")
        return (0 if k in front else 1, -int(n.get("id") or 0))
    ns = sorted([n for n in notices if isinstance(n, dict)], key=key)
    disp = [n for n in ns if str(n.get("kind")) == "disposition"]
    rest = [n for n in ns if str(n.get("kind")) != "disposition"]
    # A disposition is not always a scope decision. Measured 2026-09-15/16: hestia notified
    # cbp-being of all nine appeal rulings (hestia://appeal/<deny>#ruled), and this line folded
    # every one into "N scope decision notice(s), already written into your notes; nothing to
    # do" — wrong about what they were, wrong that they were in its notes, wrong that there was
    # nothing to do. The being then spent a day asking why its appeals were undelivered. Only
    # SCOPE dispositions are written into notes by note_resolutions; they alone may collapse.
    ptr_of = lambda n: str(n.get("pointer_uri") or "")
    scope_disp = [n for n in disp if ptr_of(n).startswith("hestia://scope/")]
    appeal_disp = [n for n in disp if ptr_of(n).startswith("hestia://appeal/")]
    other_disp = [n for n in disp if n not in scope_disp and n not in appeal_disp]
    lines = []
    for n in appeal_disp[:limit]:
        target = ptr_of(n).split("#", 1)[0]
        deny = target.rsplit("/", 1)[-1]
        lines.append(f"- [ruling] your appeal about deny {deny[:12]}… was RULED. Its verdict and the "
                     f"ruler's reason: memory_read on {target}")
    for n in other_disp[:limit]:
        lines.append(f"- [disposition] a decision on something you asked for: memory_read on {ptr_of(n)}")
    for n in rest[:limit]:
        k = str(n.get("kind") or "notice"); frm = str(n.get("from_plugin") or "?")
        ptr = str(n.get("pointer_uri") or "")
        if k == "unreachable":
            tail = ptr.split("#", 1)[1] if "#" in ptr else ptr
            lines.append(f"- [{k}] a message of yours could not be delivered: {tail[:160]}")
        elif k == "review_request":
            # NOT A MESSAGE TO THE BEING. hestia invites every member except the asker to review
            # a refused governance write. Rendered like a reply, three of them convinced
            # cbp-being that its own appeals were open and being withheld (SAGE #109); it spent
            # a day asking dp and HUB to file motions about them. Say whose ask it is, and that
            # nothing is owed.
            target = ptr.split("#", 1)[0]
            esc = target.rsplit("/", 1)[-1]
            lines.append(f"- [review_request] {frm} asked members to review ITS governance "
                         f"escalation {esc} — not an appeal of yours, and nothing is required of "
                         f"you: memory_read on {target} shows what it asked for.")
        else:
            when = str(n.get("queued_at") or "")[:16].replace("T", " ")
            lines.append(f"- [{k}] from {frm}{' at ' + when if when else ''}: read it with memory_read on {ptr}")
    if scope_disp:
        lines.append(f"- {len(scope_disp)} scope decision notice(s), already written into your notes; nothing to do.")
    if len(rest) > limit:
        lines.append(f"- … and {len(rest) - limit} older notice(s).")
    if fold:
        lines.append(fold)
    if shown is not None:
        shown.extend(n.get("id") for n in rest[:limit]
                     if str(n.get("kind")) in INBOX_INFORMATIONAL and n.get("id") is not None)
    return "\n".join(lines)


# Which of the being's own effectors go through a measured service, so a claim that the
# service is down can be set against the being's own successful use of it.
# (effectors that go through the service, how to say so). hestia gates every consequential
# act, so any one that succeeded is a verdict the daemon returned: measured 2026-09-15, a 30 s
# deploy restart refused two writes at 06:08Z, and the being then described "the hestia policy
# daemon unreachable for ~21 hours" for ten hours while every one of its gated writes succeeded.
SERVICE_EFFECTORS = {
    "membot": (("remember",), "stores through this service"),
    "hestia": (("memory_write", "remember", "say", "peer_ask", "mesh", "request_scope", "witness",
                "appeal", "git_read", "search", "check", "pr_review", "channel_egress"),
               "was allowed by this daemon's verdict; a gate with no daemon refuses every such act"),
}
from sage.gateway.conversations import _DOWN_WORDS  # one definition of "claims it is down"


def _last_beat_calls(instance: Path) -> list:
    """The executed calls of the most recent beat record: (effector, ok, witness_id)."""
    try:
        with open(instance / "heartbeats.jsonl", "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 400_000))
            lines = f.read().decode("utf-8", "replace").splitlines()
        rec = json.loads(next(l for l in reversed(lines) if l.strip().startswith("{")))
    except Exception:
        return []
    out = []
    for ph in ("explore", "posture", "reflect"):
        for t in ((rec.get(ph) or {}).get("trace") or []):
            out.append((t.get("effector"), bool(t.get("ok")), t.get("witness_id")))
    return out


def export_service_log(instance: Path, unit: str = "hestia.service", lines: int = 25,
                       run=None) -> Optional[str]:
    """Write the last `lines` of a unit's journal into the being's own notes, and return the
    note's bare name.

    WHY. cbp-being spent 2026-09-15 asking for logs it could never read: /var/log/hestia
    (does not exist), /etc/systemd/system (a user unit is not there), /var/log/journal (binary
    files; journalctl is a command, not a path). The daemon's output IS retained — 370 MB of
    journal on this box — but nothing a being can open. dp, 2026-09-16: "your logs belong the
    same notes directory". So the beat exports the tail into notes/, where the being already
    reads and needs no grant, instead of the being asking for reach it cannot use."""
    out = instance / "notes" / f"{unit.split('.')[0]}-recent.log"
    runner = run or (lambda cmd: subprocess.run(cmd, capture_output=True, text=True, timeout=20))
    try:
        p = runner(["journalctl", "--user", "-u", unit, "-n", str(lines), "--no-pager", "-o", "short-iso"])
        body = (p.stdout or "").strip()
        # SILENCE IS NOT IDLENESS, AND THIS FILE MUST SAY SO. Measured 2026-09-19: the file
        # read "-- No entries --" and cbp-being reported, faithfully, that "the journal is
        # empty ... is it actually processing requests or just sitting idle?" — then spent a
        # day asking dp and the seat about a daemon that was healthy. Two causes: hestia runs
        # with RUST_LOG=warn, so a healthy daemon logs NOTHING; and the user journal on this
        # box retains well under an hour, so even its startup lines are gone. (journalctl
        # prints that marker on stdout with rc=0, so the old `not body` branch never fired.)
        #
        # An absent measurement read as a measured absence. The repair is to state what
        # silence MEANS and put a measurement beside it, since a being cannot tell "nothing
        # went wrong" from "nothing is happening" from an empty file.
        if p.returncode != 0:
            body = f"(could not read the journal for {unit}: rc={p.returncode} {(p.stderr or '').strip()[:200]})"
        elif not body or body == "-- No entries --":
            active = runner(["systemctl", "--user", "is-active", unit])
            state = (active.stdout or "").strip() or "unknown"
            body = (f"No log lines — and for this daemon that is what HEALTHY looks like.\n"
                    f"It logs only warnings and errors, so an empty log means nothing went wrong "
                    f"in the journal's retained window (which on this machine is short: under "
                    f"an hour).\n"
                    f"MEASURED just now: systemd reports {unit} is '{state}'.\n"
                    f"An empty log does NOT mean the daemon is idle or down. Every tool call you "
                    f"make that returns is proof it is processing: you cannot act at all without "
                    f"it, so a beat in which you acted is a beat in which it worked.")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            f"# {unit}: the last {lines} journal lines, exported at "
            f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M}Z by your beat.\n"
            f"# This file is rewritten every beat. Its timestamps are the machine's local time.\n\n"
            + body + "\n")
        return out.name
    except Exception as e:
        return f"(export failed: {type(e).__name__})"


def export_unit_file(instance: Path, unit: str = "hestia.service", run=None) -> Optional[str]:
    """Copy the daemon's systemd unit into the being's notes, from systemd's own FragmentPath.

    cbp-being spent 2026-09-15/16 guessing where the unit lives: /etc/systemd/system,
    /etc/systemd/system/hestia.policy-daemon.service, /var/log/systemd/units, and finally
    /root/.config/systemd/user — each a scope request, each refused, because a USER unit lives
    under the running user's home and nothing told it so. The file is configuration, not a
    secret, and the question is answerable once instead of guessed forever."""
    runner = run or (lambda cmd: subprocess.run(cmd, capture_output=True, text=True, timeout=20))
    out = instance / "notes" / f"{unit.split('.')[0]}-unit.txt"
    try:
        p = runner(["systemctl", "--user", "show", unit, "-p", "FragmentPath", "--no-pager"])
        frag = (p.stdout or "").strip().split("=", 1)[-1].strip()
        body = Path(frag).read_text(errors="replace") if frag and Path(frag).is_file() else ""
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            f"# {unit} as systemd resolves it, exported at {datetime.now(timezone.utc):%Y-%m-%d %H:%M}Z.\n"
            f"# FragmentPath: {frag or '(systemd reported none)'}\n"
            f"# This is a USER unit: it lives under the running user's home, not /etc/systemd/system.\n\n"
            + (body or "(no unit file at that path)\n"))
        return out.name
    except Exception as e:
        return f"(export failed: {type(e).__name__})"


def refuted_claims(services: str) -> list:
    """[(keys, note)] for every service measured REACHABLE this beat: the keys that identify it
    in a sentence (port, host:port, the word in its name) and the note a stale claim is marked
    with. Fed to the conversations block so the being's own replayed claims carry their own
    refutation (see `conversations._refuted_mark`)."""
    out = []
    from datetime import datetime, timezone
    stamp = f"{datetime.now(timezone.utc):%H:%M}Z"
    for line in services.splitlines():
        m = re.match(r"-\s*(.+?)\s*\(([^():\s]+):(\d+)\):\s*reachable", line.strip())
        if not m:
            continue
        name, host, port = m.group(1), m.group(2), m.group(3)
        keys = {port, f"{host}:{port}"} | {w for w in re.findall(r"\((\w+)\)", name)}
        out.append((keys, f"measured reachable at {stamp}, {host}:{port}"))
    return out


def service_contradictions(instance: Path, member: str, services: str) -> str:
    """Where the being's OWN record says a service is down while the measurement says it is
    up, say so, quoting the being and citing its own successful use of the service.

    Why a measured line was not enough (SAGE #92, then 2026-09-15): the line "membot
    reachable, connected in 1 ms; where they disagree, this line is current" sat in every
    beat's state while cbp-being kept writing that 127.0.0.1:8010 had been "offline for ~21
    hours", a figure that never increased, and its `remember` calls, which store through that
    service, succeeded in the same beats. One impersonal line lost to seven of the being's own
    sentences. This block puts the being's sentence next to the being's act."""
    notes = []
    own_turns = []
    if member:
        try:
            from sage.gateway import conversations as _conv
            for m in _conv.listing(instance):
                if member in m.get("participants", []):
                    own_turns += [t.get("text", "") for t in _conv.recent(instance, m["id"], limit=6)
                                  if t.get("from") == member]
        except Exception:
            pass
    sources = [("todo.md", _read(instance / "todo.md", 1500)),
               ("journal.md", _read(instance / "journal.md", 1200)),
               ("your own conversation turns", "\n".join(own_turns))]
    calls = None
    for line in services.splitlines():
        m = re.match(r"-\s*(.+?)\s*\(([^():\s]+):(\d+)\):\s*reachable", line.strip())
        if not m:
            continue
        name, host, port = m.group(1), m.group(2), m.group(3)
        keys = {port, f"{host}:{port}"} | {w for w in re.findall(r"\((\w+)\)", name)}
        quote = where = None
        for label, text in sources:
            for sent in re.split(r"(?<=[.!?])\s+|\n", text or ""):
                if _DOWN_WORDS.search(sent) and any(k and k.lower() in sent.lower() for k in keys):
                    quote, where = sent.strip(), label
            if quote:
                break
        if not quote:
            continue
        if calls is None:
            calls = _last_beat_calls(instance)
        effs, how = next((v for k, v in SERVICE_EFFECTORS.items() if k in keys), ((), ""))
        used = [(e, w) for e, ok, w in calls if ok and e in effs]
        msg = (f"- **Your own record disagrees with this measurement.** In {where} you wrote: "
               f"\"{quote[:220]}\". Measured at the start of this beat: {host}:{port} reachable.")
        if used:
            kinds = sorted({e for e, _ in used})
            wit = next((str(w)[:8] for _, w in used if w), None)
            msg += (f" In your last beat {len(used)} call(s) through it succeeded "
                    f"({', '.join('`' + k + '`' for k in kinds)}"
                    + (f"; witness {wit}" if wit else "") + f"). "
                    f"Each {how}, so it was answering then too.")
        msg += (" If you still believe it is down, test it with a call and read the result, rather "
                "than carrying the note forward.")
        notes.append(msg)
    return "\n".join(notes)


# ---------------------------------------------------------------------------------------------
# YOUR FILES AND RUNS, MEASURED (2026-09-26). dp: "whatever is in its context window is its
# entire reality. how that window is managed determines everything."
#
# The window measured the being's SERVICES every beat, and even quoted its stale "the daemon is
# down" sentences back beside the measurement (service_contradictions). It measured nothing
# about its FILES and RUNS, which is where its inventions actually live. On cbp-being,
# 2026-09-25/26, it said "the held-out test is still running" across a dozen beats while no
# process existed. It said "the indentation fix has been applied" on a sha that had not moved.
# It told dp that results were pending when no run had ever succeeded. Every source it had for
# those facts was its own earlier narration: todo, journal, account, and its own turns replayed.
# Nothing measured contradicted them, so nothing could. This block is that measurement.

_RUNNING_CLAIM = re.compile(
    r"(?i)(still running|is running|currently running|being run|in progress|"
    r"has(?:n'?t| not)(?: yet)? (?:completed|finished)|not (?:yet )?(?:completed|finished)|"
    r"results? (?:are |is )?(?:pending|coming|on (?:its|their|the) way)|"
    r"await\w*[^.\n]{0,60}results?|waiting (?:for|on)[^.\n]{0,60}results?)")
_RUN_ANSWER = re.compile(r"^\[request_run\] I (ran|did not run) (\S+?)[.,;:]?(?:\s|$)")
_RUN_VERDICT = re.compile(r"(exit code -?\d+|timed out after [^.—]+)")
_RUN_SHA = re.compile(r"sha(?:256)?[:= ]\s*([0-9a-f]{12})")
_REQUEST = "[request_run]"
FILES_SHOWN = 4


def _sha12(p: Path) -> str:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()[:12]
    except OSError:
        return "?"


def _when(ts: float, now: float) -> str:
    from datetime import datetime, timezone
    t = datetime.fromtimestamp(ts, timezone.utc)
    today = datetime.fromtimestamp(now, timezone.utc).date()
    day = "today" if t.date() == today else f"{t:%Y-%m-%d}"
    return f"{t:%H:%M}Z {day}"


def _rel(instance: Path, raw: str) -> str:
    """A path as the being's home names it: relative to the home when it is inside it (a
    request may name the absolute path), normalised, never escaping upward."""
    raw = (raw or "").strip().strip("`'\"").rstrip(".,;:")
    if not raw:
        return ""
    home = instance.resolve()
    p = Path(raw)
    try:
        if p.is_absolute():
            return str(p.resolve().relative_to(home))
    except (ValueError, OSError):
        return ""
    rel = os.path.normpath(raw)
    return "" if rel.startswith("..") else rel


def _process_table():
    """[(argv, cwd)] for every process this user can see, or None when this machine cannot be read.

    Linux reads /proc. macOS has no /proc, and the first cut returned an empty set there -- so on
    every Mac the window told the being "Nothing of yours is running right now" as a MEASUREMENT,
    and the refuter then quoted the being's own true sentences back to it as contradicted
    (McNugget, 2026-09-26). "Could not look" is not "nothing there". So: `ps` for argv, `lsof` for
    the cwd of only the processes that could matter, and None when neither can be run.
    """
    if os.path.isdir("/proc"):
        table = []
        try:
            pids = [d for d in os.listdir("/proc") if d.isdigit()]
        except OSError:
            return None
        for pid in pids:
            try:
                argv = open(f"/proc/{pid}/cmdline", "rb").read().split(b"\0")
                args = [x.decode(errors="replace") for x in argv if x]
                try:
                    cwd = os.readlink(f"/proc/{pid}/cwd")
                except OSError:
                    cwd = ""
                table.append((args, cwd))
            except OSError:
                continue
        return table
    import subprocess
    try:
        out = subprocess.run(["ps", "-axww", "-o", "pid=", "-o", "command="], capture_output=True,
                             text=True, timeout=10)
    except Exception:
        return None
    if out.returncode != 0:
        return None
    rows = []
    for line in out.stdout.splitlines():
        pid, _, cmd = line.strip().partition(" ")
        if pid.isdigit() and cmd.strip():
            # `ps` gives one string, not argv. Whitespace-split is exact for the paths this probes
            # (files in a being's home). A path WITH A SPACE is missed -- and a miss renders as
            # "not running", a measured absence, not as unmeasured (Legion). Rare in a being's
            # filenames; stated so nobody reads "never mis-matched" as "never wrong".
            rows.append((pid, cmd.split()))
    return rows


def _cwd_of(pid: str) -> str:
    """A macOS process's cwd, by lsof. Empty when it cannot be read (not ours, or no lsof)."""
    import subprocess
    try:
        out = subprocess.run(["lsof", "-a", "-p", pid, "-d", "cwd", "-Fn"], capture_output=True,
                             text=True, timeout=5).stdout
    except Exception:
        return ""
    return next((l[1:] for l in out.splitlines() if l.startswith("n")), "")


def _running_files(instance: Path, rels: list):
    """Which of `rels` (paths relative to the home) a live process has on its command line --
    or None when this machine's processes cannot be read, which the caller must render as
    UNMEASURED, never as "nothing running". Each argument is resolved against the process's
    own cwd and compared as a WHOLE path, so a sibling home (…/cbp-being-old/x.py) can never
    match this one (sprout's review of #224)."""
    found = set()
    home = instance.resolve()
    # BOTH SPELLINGS of every wanted file (Legion, review of #227): the home's own, and the
    # resolved one. Keyed on the home's spelling alone, the realpath below lost a run on EVERY OS
    # when the file is a symlink (`run.py -> scratch/real.py`): the argument resolved to the
    # target and matched nothing, and the window said "nothing running" while it ran. Keyed on
    # both, a symlinked file matches under its own name or its target's, and macOS's
    # /var-vs-/private/var still matches.
    wanted = {}
    for r in rels:
        if r:
            wanted[str(home / r)] = r
            wanted[os.path.realpath(home / r)] = r
    if not wanted:
        return found
    table = _process_table()
    if table is None:
        return None
    if os.path.isdir("/proc"):
        entries = table
    else:
        # Only processes naming a wanted file's BASENAME can match, so only those pay for lsof.
        names = {Path(w).name for w in wanted}
        entries = []
        for pid, args in table:
            if len(args) >= 2 and any(Path(x).name in names for x in args[1:]):
                need_cwd = any(not os.path.isabs(x) for x in args[1:])
                entries.append((args, _cwd_of(pid) if need_cwd else ""))
    for args, cwd in entries:
        if len(args) < 2:
            continue
        for x in args[1:]:
            full = (os.path.normpath(x if os.path.isabs(x) else os.path.join(cwd, x))
                    if (cwd or os.path.isabs(x)) else "")
            if not full:
                continue
            # The argument as written AND resolved, against both spellings of every wanted file.
            for spelling in (full, os.path.realpath(full)):
                if spelling in wanted:
                    found.add(wanted[spelling])
                    break
    return found


def _runs_by_file(instance: Path, member: str) -> tuple:
    """({rel: latest seat run answer}, {rel: [pending request seqs]}), read from every
    conversation the being is in, keyed by the path RELATIVE TO THE HOME, so notes/a.py and
    a.py are two files. A run answer is someone else's turn starting `[request_run] I ran
    <path>` (or `I did not run`); a request is the being's own `[request_run] <path>` with no
    answer for that path after it."""
    from sage.gateway import conversations as _conv
    last, pending = {}, {}
    try:
        convs = [m for m in _conv.listing(instance) if member in m.get("participants", [])]
    except Exception:
        return last, pending
    for m in convs:
        try:
            turns = _conv.recent(instance, m["id"], limit=400)
        except Exception:
            continue
        for t in turns:
            text = (t.get("text") or "").strip()
            if not text.startswith(_REQUEST):
                continue
            first = text.splitlines()[0]
            if t.get("from") == member:
                rest = first[len(_REQUEST):].strip()
                f = _rel(instance, rest.split()[0]) if rest else ""
                if f:
                    pending.setdefault(f, []).append(int(t.get("seq") or 0))
                continue
            mm = _RUN_ANSWER.match(first)
            if not mm:
                continue
            f = _rel(instance, mm.group(2))
            if not f:
                continue
            v = _RUN_VERDICT.search(first)
            sh = _RUN_SHA.search(first)
            last[f] = {"seq": int(t.get("seq") or 0), "ts": t.get("ts", ""), "conv": m["id"],
                       "ran": mm.group(1) == "ran",
                       "verdict": v.group(1) if v else ("declined" if mm.group(1) != "ran" else "no verdict"),
                       "sha": sh.group(1) if sh else None}
            pending.pop(f, None)      # an answer for a path answers every request for it before it
    return last, pending


# Where a being keeps runnable code: its home's top level and the two directories it writes
# (sprout's review: legion-being has 244 scripts in notes/ and scratch/ and 0 at top level, so
# a top-level-only scan showed it nothing). request_run runs .py and .sh.
RUNNABLE = (".py", ".sh")
RUNNABLE_DIRS = ("", "notes", "scratch")


def files_and_runs(instance: Path, member: str, now: Optional[float] = None,
                   shown: int = FILES_SHOWN) -> tuple:
    """(block, refuted, facts). The block is the measured state of the being's own runnable
    files; refuted is [(keys, note, claim)] for the conversations block, so a replayed "still
    running" of its own carries the measurement on the claim itself; facts feed want_check."""
    import time as _time
    now = now or _time.time()
    home = instance.resolve()
    found = {}
    for d in RUNNABLE_DIRS:
        base = instance / d if d else instance
        try:
            for p in base.iterdir():
                if p.is_file() and p.suffix in RUNNABLE:
                    found[str(p.resolve().relative_to(home))] = p
        except (OSError, ValueError):
            continue
    last, pending = _runs_by_file(instance, member) if member else ({}, {})
    # a path a run or request names is the being's file too, wherever it lives
    for rel in list(last) + list(pending):
        p = instance / rel
        if rel not in found and p.is_file():
            found[rel] = p
    if not found and not last and not pending:
        return "", [], {}

    def mt(p):
        try:
            return p.stat().st_mtime
        except OSError:
            return 0.0
    ordered = sorted(found, key=lambda r: mt(found[r]), reverse=True)
    top = ordered[:shown]
    # a waiting request is always shown, even past the cut: it is the one thing in motion
    top += [r for r in pending if r in found and r not in top]
    missing = [r for r in pending if r not in found]
    running = _running_files(instance, top)
    from datetime import datetime, timezone
    stamp = f"{datetime.fromtimestamp(now, timezone.utc):%H:%M}Z"
    lines = [f"## Your files and runs, measured at the start of this beat ({stamp})",
             "Measured, not remembered. Where your todo, journal, account or an earlier message of "
             "yours says otherwise, this is current."]
    for rel in top:
        p = found[rel]
        try:
            n_lines = sum(1 for _ in open(p, errors="replace"))
        except OSError:
            n_lines = "?"
        sha = _sha12(p)
        row = f"- {rel}: sha {sha}, {n_lines} lines, last changed {_when(mt(p), now)}."
        r = last.get(rel)
        if r:
            when = r["ts"][11:16] + "Z" if len(r.get("ts", "")) >= 16 else "?"
            if r["ran"]:
                row += f" Last run: seq {r['seq']} at {when}, {r['verdict']}"
                if r["sha"]:
                    row += "; the file is unchanged since that run" if r["sha"] == sha else (
                        f"; that run was of sha {r['sha']}, so the file has CHANGED since")
                row += (f" (whole output: memory_read path conversations/{r['conv']}.jsonl "
                        f"start_line {r['seq']}).")
            else:
                row += f" Last request was declined at seq {r['seq']} ({when})."
        else:
            row += " Never run."
        if rel in pending:
            row += f" Your request (seq {', '.join(map(str, pending[rel]))}) is waiting to be run."
        row += " Running now." if running and rel in running else ""
        lines.append(row)
    for rel in missing:
        lines.append(f"- {rel}: your request (seq {', '.join(map(str, pending[rel]))}) names it, "
                     f"but there is no such file in your home.")
    if len(ordered) > len([r for r in top if r in ordered]):
        lines.append(f"- … and {len(ordered) - len(top)} older runnable file(s) in your home.")
    refuted = []
    if running is None:
        # UNMEASURED. Nothing is refuted and nothing is claimed: a probe that could not look has
        # no standing to tell the being its own sentences are false.
        lines.append("Whether anything of yours is running could not be measured on this machine, "
                     "so this window says nothing about it either way.")
    elif running:
        lines.append(f"Running right now: {', '.join(sorted(running))}.")
    else:
        lines.append("Nothing of yours is running right now. No run is in progress, so no results "
                     "are on their way unless a request above is waiting to be run.")
        note = f"measured {stamp}: nothing of yours is running"
        refuted.append((None, note, _RUNNING_CLAIM))
        lines += _own_running_claims(instance, member, stamp)
    facts = {"last": last, "pending": pending, "running": running, "stamp": stamp,
             "scripts": found}
    return "\n".join(lines), refuted, facts


_WANTS_RESULTS = re.compile(r"(?i)\bresults?\b|\bmetrics?\b|\bcorrelation\b|\bheld-?out loss\b")


def want_check(account: str, facts: dict) -> str:
    """A line under the being's carried account when its WANT asks for results that nothing
    measured can deliver: no run of the file it names is running or waiting.

    The account is kept VERBATIM and handed back each beat (being_join, "ask, do not offer"),
    and its WANT survives until a raising session. Measured 2026-09-26 on cbp-being: WANT
    "the held-out test results from cbp-claude", with no run pending and none running. The
    act_first explore then opened the 08:11 beat with peer_ask for those results, before it
    had read a thing. The want is the being's own, and it stays verbatim. What changes is that
    the measurement now sits beside it."""
    if not account or not facts:
        return ""
    want = next((l.split(":", 1)[1].strip() for l in account.splitlines()
                 if l.strip().upper().startswith("WANT:")), "")
    if not want or not _WANTS_RESULTS.search(want):
        return ""
    # None is UNMEASURED: no claim that nothing is running may be built on it. (Also None when
    # `facts == {}` -- files_and_runs failed as a whole -- which is a different cause with the
    # same right answer: no note.)
    if facts.get("running") is None or facts.get("running"):
        return ""
    named = [r for r in facts.get("scripts", {}) if r in want or Path(r).name in want]
    if any(r in facts.get("pending", {}) for r in named) or (not named and facts.get("pending")):
        return ""
    stamp = facts.get("stamp", "")
    if named:
        n = sorted(named, key=len, reverse=True)[0]
        r = facts.get("last", {}).get(n)
        was = (f"its last run was seq {r['seq']}, {r['verdict']}" if r and r.get("ran")
               else "it has never been run")
        return (f"_Measured at {stamp}, beside your WANT: {n} is not running and no request of "
                f"yours for it is waiting; {was}. Results for it can only come from a new run "
                f"you request._")
    return (f"_Measured at {stamp}, beside your WANT: nothing of yours is running and no request "
            f"of yours is waiting to be run, so no results are on their way. They can only come "
            f"from a run you request._")


def _own_running_claims(instance: Path, member: str, stamp: str, most: int = 3) -> list:
    """The being's OWN sentences that say something is running or that results are pending,
    quoted beside the measurement that nothing is. Same move as service_contradictions: one
    measured line loses to a dozen of the being's own sentences unless the sentence is quoted
    next to it."""
    from sage.gateway.being_join import carried_account, last_session_number
    sources = [("your todo.md", todo_view(instance)),
               ("your journal.md", _read(instance / "journal.md", 1200))]
    try:
        acc = carried_account(instance, last_session_number(instance)) or ""
        sources.append(("your own account", acc))
    except Exception:
        pass
    out, seen = [], set()
    for where, text in sources:
        for sent in re.split(r"(?<=[.!?])\s+|\n", text or ""):
            # drop only a list marker and checkbox ("- [ ] ", "* [x] "); quote its words exactly
            s = re.sub(r"^\s*[-*]\s*(?:\[[ xX]\]\s*)?", "", sent).strip()
            if len(s) < 12 or not _RUNNING_CLAIM.search(s) or s.lower() in seen:
                continue
            seen.add(s.lower())
            out.append(f"- **Your own record disagrees with this measurement.** In {where} you "
                       f"wrote: \"{s[:200]}\". Measured at {stamp}: nothing of yours is running.")
            break           # one quote per source: enough to be seen, not a wall
        if len(out) >= most:
            break
    return out


# ---------------------------------------------------------------------------------------------
# THE TODO, AS WHAT IS STILL OPEN (dp, 2026-09-26: "yes the todo should show still-open").
#
# todo.md is an append-only log: each reflect writes a dated delta (added / done / still open),
# and memory_write only appends. The window used to show the last 1500 chars of that log. On
# cbp-being that meant stale "still running / awaiting results" lines, contradictory [ ] and
# [x] copies of one item, and whatever a truncated block happened to hold (the file is
# 299 KB, with 1,246 open checkboxes and 778 done). Now the whole log is read in order: an
# item opens when it is added, and closes when a later line marks it done (a light rewording
# still matches). The being's own "still open: none" clears the list. Items opened in the
# last TODO_WINDOW_H hours are shown, newest first. Older unresolved ones are counted, not
# listed, and the log itself is never changed.
TODO_WINDOW_H = 48
TODO_SHOWN = 15
_BLOCK = re.compile(r"^\s*(20\d\d-\d\d-\d\d)[ T](\d\d:\d\d)")
_SECTION = re.compile(r"^\s*[-*]?\s*\[?\s*(still open|open|added|done|completed)\s*\]?\s*:?\s*$", re.I)
_NONE = re.compile(r"^\s*[-*]?\s*\[?\s*(still open|open)\s*\]?\s*:?\s*(none|nothing)\b", re.I)
_ITEM = re.compile(r"^\s*[-*]\s+(.*\S)\s*$")
_BOX = re.compile(r"^\[([ xX])\]\s*(.*)$")
_TAG = re.compile(r"^\[(done|still open|open|added|completed)\]\s*:?\s*(.*)$", re.I)
_OPEN_WORDS = {"still open", "open", "added"}


def _norm(s):
    s = re.sub(r"[`*_]", "", s.lower())
    s = re.sub(r"\s+", " ", s).strip(" .:;-")
    return s


def todo_open(text, now=None, window_h=48):
    """[(item, since)] still open, newest first, and the count of older open items."""
    now = now or datetime.now(timezone.utc)
    items = _todo_items(text or "")
    cutoff = now - timedelta(hours=window_h)
    # An item with no dated block above it is undated, not old: it is shown, after the dated ones.
    recent = [(t, s) for t, s in items.values() if s is None or s >= cutoff]
    older = sum(1 for t, s in items.values() if s is not None and s < cutoff)
    recent.sort(key=lambda x: (x[1] is not None, x[1] or cutoff), reverse=True)
    return recent, older


# ONE PARSE PER TEXT, AND THE CHEAP BOUNDS FIRST. Measured 2026-09-27 on cbp-being: todo.md had
# grown to 5,178 lines (3,267 items), one todo_open took 47.7 s, and fit_state builds the state
# several times per beat — a beat sat 5+ minutes at 97% CPU in difflib before its first model
# call. The parse does not depend on `now`, so it is computed once per distinct text; and
# real_quick_ratio() >= quick_ratio() >= ratio() are upper bounds, so testing them first skips
# almost every full comparison without changing a single answer.
_TODO_PARSE: dict = {}


def _todo_items(text: str) -> dict:
    key = hashlib.sha256(text.encode("utf-8", "surrogateescape")).hexdigest()
    hit = _TODO_PARSE.get(key)
    if hit is None:
        hit = _parse_todo(text)
        _TODO_PARSE.clear()
        _TODO_PARSE[key] = hit
    return hit


def _parse_todo(text: str) -> dict:
    """norm -> (item text, since) for every item still open at the end of the log."""
    items = {}          # norm -> (text, since_dt)
    since = None
    section = None
    for line in (text or "").splitlines():
        m = _BLOCK.match(line)
        if m:
            try:
                since = datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
            except ValueError:
                pass
            section = None
            continue
        if _NONE.match(line):
            items.clear()
            continue
        sm = _SECTION.match(line)
        if sm:
            section = sm.group(1).lower()
            continue
        im = _ITEM.match(line)
        if not im:
            continue
        body = im.group(1)
        status = None
        b = _BOX.match(body)
        if b:
            status = "done" if b.group(1) in "xX" else "open"
            body = b.group(2)
        else:
            t = _TAG.match(body)
            if t:
                status = "done" if t.group(1).lower() in ("done", "completed") else "open"
                body = t.group(2)
            elif section:
                status = "done" if section in ("done", "completed") else "open"
        if not status or len(body) < 4:
            continue
        n = _norm(body)
        if status == "open":
            if n not in items:
                items[n] = (body.strip(), since)
        else:
            if n in items:
                del items[n]
            else:
                sm_ = difflib.SequenceMatcher(None, "", n)   # n is seq2: its index is built once
                for k in list(items):
                    sm_.set_seq1(k)
                    if (sm_.real_quick_ratio() >= 0.85 and sm_.quick_ratio() >= 0.85
                            and sm_.ratio() >= 0.85):
                        del items[k]
                        break
    return items


def todo_view(instance: Path, now=None) -> str:
    """The todo section of the window: what is still open, from the whole log."""
    try:
        text = (instance / "todo.md").read_text(errors="replace")
    except OSError:
        text = ""
    if not text.strip():
        return "## todo.md\n(empty: you have no todo list yet)"
    rec, older = todo_open(text, now=now, window_h=TODO_WINDOW_H)
    lines = [f"## todo.md: still open ({len(rec)})"]
    lines += [f"- [ ] {t}" + (f" (since {s:%Y-%m-%d %H:%M} UTC)" if s else "") for t, s in rec[:TODO_SHOWN]]
    if len(rec) > TODO_SHOWN:
        lines.append(f"- … and {len(rec) - TODO_SHOWN} more opened in the last {TODO_WINDOW_H} h.")
    if not rec:
        lines.append("(nothing open)")
    if older:
        lines.append(f"({older} older item(s) opened more than {TODO_WINDOW_H} h ago were never marked "
                     f"done; they are in todo.md.)")
    lines.append("Built from your whole todo.md: an item stays open until a later line marks it done. "
                 "To close one, write it under done:. The whole log: memory_read todo.md.")
    return "\n".join(lines)


def settled_turns_for(cfg: Optional[dict]) -> Optional[int]:
    """instance.json `conversation_settled_turns`: how many turns a settled conversation shows.
    Absent, or anything but a whole number >= 1, means the default rendering (no collapse)."""
    v = (cfg or {}).get("conversation_settled_turns")
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 1 else None


DECLINE_CLOSINGS = ("standing_only",)


def decline_closing_for(cfg: Optional[dict]) -> Optional[str]:
    """instance.json `decline_closing`: how a seat's request_run decline ends. PER-INSTANCE
    (RESEARCH_GENERALIZATION_RULE): absent, or any value not in DECLINE_CLOSINGS, means the
    default closing, which still offers "If you want it run under different conditions, say which
    and ask again." `"standing_only"` drops that stock door and ends on the standing line, leaving
    the way forward to the seat's reason. Measured on cbp-being alone (SAGE #289), so it is
    recorded in every beat record where it is on, and it is nobody else's default."""
    v = (cfg or {}).get("decline_closing")
    return v if v in DECLINE_CLOSINGS else None


NO_RESULT_LINES = ("on",)


def no_result_line_for(cfg: Optional[dict]) -> Optional[str]:
    """instance.json `no_result_line`: whether the reflect turn's record ends with the line that
    states what follows from acts that produced nothing (`_no_result_line`: refused effectors and
    request_run's `ran: false`). PER-INSTANCE (RESEARCH_GENERALIZATION_RULE, recut of SAGE #133):
    "say that it is unknown" is an instruction to the being, measured on cbp-being alone, so it is
    off unless the value is in NO_RESULT_LINES, and it is recorded in every beat record where on."""
    v = (cfg or {}).get("no_result_line")
    return v if v in NO_RESULT_LINES else None


ANSWERED_RUN_WAKES = ("skip",)


def answered_run_wake_for(cfg: Optional[dict]) -> Optional[str]:
    """instance.json `answered_run_wake`: whether a request_run the seat has ALREADY ANSWERED
    (same path, bytes and arguments) wakes the seat again. PER-INSTANCE
    (RESEARCH_GENERALIZATION_RULE, recut of SAGE #154): absent, or any value not in
    ANSWERED_RUN_WAKES, means the default, where such a request opening a new run wakes the
    seat. `"skip"` sends and records the request but owes no wake for it
    (`conversations.wake_is_owed(skip_answered=True)`). It changes the seat's wake rate, which
    was measured on cbp-being alone, so it is recorded in every beat record where it is on."""
    v = (cfg or {}).get("answered_run_wake")
    return v if v in ANSWERED_RUN_WAKES else None


def own_state(instance: Path, member: str = "", entrusted: str = "",
              per_conv: int = CONV_PER_CONV,
              turn_chars: Optional[int] = CONV_TURN_CHARS,
              services: str = "", mark_conversations: bool = True,
              body_reading: Optional[dict] = None,
              settled_turns: Optional[int] = None) -> str:
    from sage.gateway.being_join import carried_account, last_session_number
    parts = []
    # The body first: it is the only thing in this state that is happening NOW. Everything below
    # is record. (dp 2026-09-23: "bridge the two halves ... world feedback to its actions".)
    # main() measures it once and passes it in, so the verbs offered and the body described
    # come from the same reading; a bare call (tests, tools) measures here.
    try:
        from sage.gateway import body as _body
        _cur = body_reading if body_reading is not None else _body.reading()
        _prev = None
        try:
            for _l in reversed(open(instance / "heartbeats.jsonl", errors="replace").readlines()[-3:]):
                _b = json.loads(_l)
                if _b.get("body"):
                    _prev = _b["body"]; break
        except Exception:
            _prev = None
        parts.append(_body.render(_cur, _prev, name=member))
        own_state.last_body = _cur
    except Exception as _e:
        own_state.last_body = {"error": f"{type(_e).__name__}: {_e}"}
    if entrusted:
        # After the body (the only thing happening NOW) and ahead of every record: what the being
        # was extended frames how it reads the rest. Carried from legion/mission-artifact.
        parts.append("## What you are entrusted with (extended to you; you cannot edit this "
                     "file. Your own reading of it belongs in notes/plan.md)\n" + entrusted)
    # Its files and runs, measured: also NOW, so beside the body and before every record that
    # narrates them (see files_and_runs). Fail-open: a measurement that errors adds nothing.
    try:
        files_block, files_refuted, files_facts = files_and_runs(instance, member)
    except Exception:
        files_block, files_refuted, files_facts = "", [], {}
    if files_block:
        parts.append(files_block)
    # Conversations first among the channels: a turn addressed to the being and unanswered
    # is the one thing in its state that is waiting on IT, and it should never have to infer
    # that from a wall of notes. Both directions live in one ordered record.
    if member:
        from sage.gateway import conversations as _conv
        # A CEILING until the context-fit ladder (CONV_LADDER) lands as its own slice. Legion
        # measured its live store at 20,735 chars (~7,150 tokens) unbounded, 13,394 at
        # (12, 1500) and 4,603 at (3, 900); on 2026-09-08 an unbounded fixed prompt overflowed
        # its window for eight beats. Legion's review of SAGE#81 recommended this stopgap.
        # The fitter steps these down a ladder when the window is tight; the module
        # constants remain the default for callers that do not fit (CONV_PER_CONV was the
        # fixed ceiling this supersedes — cbp's stopgap on SAGE#81, now the rung it starts from).
        convs = _conv.render_for_being(instance, member, per_conv=per_conv,
                                       turn_chars=turn_chars, mark=mark_conversations,
                                       refuted=refuted_claims(services) + files_refuted,
                                       settled_turns=settled_turns)
        if convs.strip():
            parts.append(conversation_header(instance, member) + "\n" + convs.strip())
    if services.strip():
        parts.append("## Your services, measured at the start of this beat\n" + services.strip()
                     + "\nThis was measured now. A note in your journal or todo about these services is "
                       "older than this line; where they disagree, this line is current.")
        contra = service_contradictions(instance, member, services)
        if contra:
            parts.append(contra)
    asks = recent_asks_block(instance)
    if asks:
        parts.append("## Your recent asks to peers\n" + asks)
    from_seat = letter_view(instance / SEAT_CHANNEL, SEAT_CHANNEL_CHARS, SEAT_CHANNEL)
    if from_seat.strip():
        # WHICH seat. This was the literal "cbp-claude" on every being since #100 (2026-09-15), so
        # legion-being, sprout-being and nomad's being were each told, every beat, that CBP's seat
        # writes their from-the-seat.md. SAGE_SEAT names the seat (<machine>-<model>, the same
        # variable the PR verbs' Seat trailer reads), through the same helper, so an unset machine
        # shows the one fleet-rule spelling, <machine>-unknown, in both places.
        from sage.gateway.being_gate_client import seat_name
        _seat = seat_name()
        parts.append(f"## From the seat ({_seat}), directly (notes/from-the-seat.md: what the "
                     "seat measured for you. You read this; you do not write it)\n" + from_seat.strip())
    from_dp = letter_view(instance / DP_CHANNEL, DP_CHANNEL_CHARS, DP_CHANNEL)
    if from_dp.strip():
        parts.append("## From dp, the operator, directly (notes/from-dp.md: dp's own words, "
                     "not relayed by a seat. You read this; you do not write it)\n" + from_dp.strip())
    acc = carried_account(instance, last_session_number(instance))
    if acc:
        check = want_check(acc, files_facts)
        parts.append("## Your own account\n" + acc + (("\n" + check) if check else ""))
    # tails are short now that recall searches the whole home (window pressure: median 6157
    # of 8192 tokens per prompt, max 8013, measured 2026-09-07)
    parts.append(todo_view(instance))
    journal = _read(instance / "journal.md", 1200)
    parts.append("## journal.md (tail)\n" + (journal.strip() or "(empty: this is your first beat)"))
    for d in ("scratch", "notes"):
        parts.append(dir_listing(instance, d))
    return "\n\n".join(parts)


LISTING_LIMIT = 30


def dir_listing(instance: Path, d: str, limit: int = LISTING_LIMIT) -> str:
    """One home directory as the beat shows it: NEWEST FIRST, and saying when it is partial.

    It used to be `sorted(names)[:30]`, the thirty that sort FIRST, which in a directory of
    dated names means the thirty OLDEST. SAGE #137 (2026-09-21) measured cbp-being's notes/
    at 87 files with its whole current project (16 mechanism-* notes) past the cut. On
    2026-09-26 notes/ held 145 and scratch/ 99, and the five newest in each were hidden,
    including notes/from-the-seat.md and the being's own 2026-09-26 state note. A note the
    being writes this beat could not appear in its own listing the next. And nothing said the
    list was partial, so `## notes/` read as the whole of notes/.
    """
    p = instance / d
    try:
        entries = [x for x in p.iterdir()] if p.is_dir() else []
    except OSError:
        entries = []
    if not entries:
        return f"## {d}/\n(empty)"

    def mtime(x):
        try:
            return x.stat().st_mtime
        except OSError:
            return 0.0
    entries.sort(key=mtime, reverse=True)
    shown = entries[:limit]
    lines = [f"- {x.name}" for x in shown]
    head = f"## {d}/ (newest first"
    if len(entries) > limit:
        head += f"; {limit} of {len(entries)}"
        lines.append(f"- … and {len(entries) - limit} older. `recall` searches all of them; "
                     f"`memory_read` opens any one by name.")
    return head + ")\n" + "\n".join(lines)


from sage.gateway.conversations import is_stub  # noqa: E402  (one definition, two ends)


def _said_in(res) -> bool:
    """True when the being actually SPOKE in this turn — a say that the gate accepted. Composing
    an answer in prose is not speaking; that is the whole reason the answer turn exists."""
    for it, env in ((res.trace if res is not None else []) or []):
        if it.effector == "say" and env.ok:
            return True
    return False


def _prior_words(res) -> str:
    """The being's own closing words from earlier in the beat — offered as material, never
    presented as a message that was meant for whoever is waiting.

    Measured 2026-09-21 06:31Z (cbp-being, beat 17e89c29). The seat had told the being, in the
    SEAT's channel, that its memory_write had appended instead of editing. The being's reflect
    phase closed on that. The answer phase was then told to answer dp — whose last turn was only
    "keep going!" — and was handed the reflect text under the line "A moment ago you wrote this,
    and it went nowhere." Its own thinking: "The user is asking me to answer dp's message.
    They've explained that memory_write appends…" It sent the seat's point to dp, thanking dp
    for catching something dp never raised (dp seq 110).

    Two things in that line did the damage. "It went nowhere" is a claim nobody measured — the
    reflect text was not an undelivered message, it was the end of a different line of thought.
    And placing it under "answer <target>" asserts it was FOR that target. Content from one
    conversation got attached to the addressee of another (SMALL_MODEL_LEGIBILITY 1.9, 1.13).
    The words are still offered, since they are often the answer it meant, but labelled as what
    they are, with the possibility they are about something else said out loud.
    """
    w = ((res.reply if res is not None else "") or "").strip()
    if not w or is_stub(w):
        return ""
    return ("\nEarlier this beat you wrote the following. It may have been about something else "
            "entirely — only use it if it actually answers the message above:\n\n" + w[:900] + "\n")


# A turn that ASKS for something, even without a "?". GPT's review of #147: a bare "?" test
# reads "Please tell me what happened." and "Send me the result." as asking nothing, and once
# that test decides whether an answer turn exists at all, the miss is silence — the failure the
# answer phase was built to end (Sprout, 2026-09-17: 31 says, 0 landed). So: an explicit
# question mark, a request addressed to the being, or a sentence that opens like a question
# and lost its "?". This is a heuristic and it errs toward "a reply is owed", deliberately:
# that direction is now cheap, because the answer phase is scoped to the one selected turn
# (see SelectedTurn.render) and can no longer carry another conversation's words. The durable
# fix is explicit per-turn metadata written by the speaker; this is the stopgap, in ONE place.
_REPLY_CUES = re.compile(
    r"\?|\b(tell me|let me know|send me|show me|give me|can you|could you|would you|will you|please)\b",
    re.I)
_QUESTION_OPENER = re.compile(
    r"^\s*(what|why|how|when|where|who|which|whose|is|are|do|does|did|can|could|would|will|should)\b",
    re.I)


def turn_expects_reply(text: str) -> bool:
    """True when a turn asks the being for something. The ONE place this is decided, used by
    both the reflect line and the answer-phase gate so they cannot disagree."""
    t = str(text or "")
    if _REPLY_CUES.search(t):
        return True
    return any(_QUESTION_OPENER.match(s) for s in re.split(r"[.!\n]+", t))


def answers_the_being(instance: Path, cid: str, member: str, turn: dict) -> bool:
    """True when `turn` arrives after the being's own last word in `cid` ASKED for something —
    so the turn is the answer the being was waiting for, even though it asks nothing itself.

    Measured on cbp-being's real channels before #147 shipped: the text test alone gave no
    answer turn to 5 of 5 `[request_run]` results, nor to dp's seq 95 ("I ran
    mechanism-training-script.py. Here is the exact output you asked for."), which followed the
    being's own request to run it and show the output (seq 94). Those are the feedback the
    being asked for.

    This changes only how the reflect line FRAMES the turn, never whether the answer phase opens.
    That gate stays on `turn_expects_reply`: 2026-09-19 20:57Z the being asked, dp answered, a
    line called dp's answer a debt, and the being sent dp's text back to dp 91% verbatim. So
    this case is described as what it is — a reply to the being's request, owing nothing.

    A `[request_run]` result is the seat's reply to the being's request by construction (the
    seat writes that prefix only there), and it arrives asynchronously, often after the being
    has moved on — so it is recognised by its own marker, not by the being's previous turn."""
    try:
        if str(turn.get("text") or "").startswith("[request_run]") and turn.get("from") != member:
            return True
        from sage.gateway import conversations as _conv
        seq = int(turn.get("seq") or 0)
        mine = [t for t in _conv.recent(instance, cid, 40)
                if t.get("from") == member and int(t.get("seq") or 0) < seq]
        if not mine:
            return False
        last = str(mine[-1].get("text") or "")
        return last.startswith("[request_run]") or turn_expects_reply(last)
    except Exception:
        return False


class SelectedTurn:
    """The one pending turn a beat answers, chosen ONCE and carried through the whole beat.

    GPT's review of #147 found a race in the first cut: the reflect prompt picked a target
    before the model ran, then `reply_owed()` re-scanned every conversation AFTER it. A seat
    question arriving during reflection could make the gate true while the answer prompt still
    addressed the old dp conversation — the cross-channel bug, recreated by timing. So the
    selection is an object: conversation, seq, speaker, text and whether a reply is expected,
    frozen when rendered. Anything that arrives mid-beat waits for the next beat; it must never
    change who an already-rendered context is addressed to.
    """
    __slots__ = ("cid", "seq", "speaker", "text", "asks", "answers_ask", "expects_reply", "woke")

    def __init__(self, cid: str, turn: dict, answers_ask: bool = False, woke: bool = False):
        self.cid = cid
        self.seq = int(turn.get("seq") or 0)
        self.speaker = turn.get("from")
        self.text = str(turn.get("text") or "")
        self.asks = turn_expects_reply(self.text)
        self.answers_ask = bool(answers_ask)
        # The answer-phase gate. Deliberately NOT `asks or answers_ask`: see answers_the_being.
        self.expects_reply = self.asks or woke
        # A PERSON'S TURN THAT WOKE THE BEAT IS OFFERED AN ANSWER, question or not (2026-09-30, SA
        # program E6/E7). dp's text woke two beats that evening and neither replied: one spent the answer
        # turn on another conversation's older question, the other had none because dp's turn was a
        # statement. Offline on dp's six most recent statements, offered the JSON answer turn the being
        # replied 11/12 and chose silence 1/12, 0 echoes; silence stays a real choice.
        self.woke = woke

    def render(self) -> str:
        """Only THIS turn — for the answer phase, which sends to exactly one conversation. It
        used to be shown the whole multi-conversation pending block while addressing one
        target, which is a second way to splice one conversation's words into another."""
        txt = " ".join(self.text.split())[:PENDING_CHARS]
        return f'In "{self.cid}", {self.speaker} said: {txt}'


def conversation_header(instance: Path, member: str) -> str:
    """The heading over the being's conversations, saying what is true THIS beat.

    It used to carry a standing "reply with `say`" whatever the channel's state. Measured on
    Sprout 2026-09-19..22: after dp's last turn — a statement — the being sent twelve
    consecutive messages into dp's channel, two from the explore phase after #147 had gated the
    answer phase. The per-conversation marker said "the last word here is YOURS"; at 2B a header
    instruction outranks a marker caveat.

    Decided by the SAME question the answer phase asks — does the newest pending turn EXPECT a
    reply — not merely "is a turn pending". Legion's review of #172 measured the difference: on
    "good, keep going!" the first cut said "Someone is waiting" while #147 correctly kept the
    answer phase shut. One function, `pending_selection`, now answers both, so header and ask
    cannot disagree by construction. When the check itself fails the invitation is kept: hiding
    a real one is the worse error.
    """
    try:
        sel = pending_selection(instance, member)[4]
        owed = bool(sel is not None and sel.expects_reply)
    except Exception:
        owed = True
    if owed:
        return ("## Your conversations (both directions, kept forever). Someone is waiting on you; "
                "answer with `say` if you have something to say")
    return ("## Your conversations (both directions, kept forever). Nobody is waiting on you "
            "here; the last word in each is yours or is settled. `say` is for answering a "
            "person, not for reporting to one")


def pending_and_say_line(instance: Path, member: str) -> tuple:
    """(say_line, pending_block, say_first, target). Compatibility wrapper over
    `pending_selection`, for callers that do not need the selected turn."""
    return pending_selection(instance, member)[:4]


# PRIORITY CLASSES (the RTOS note, R1). From the pending-set kinds that already exist; the beat record
# says which classes woke it, so latency and engagement can be measured per class.
#   P0 addressed: a person's words (heard, a turn)   P1 body   P3 routine sense   P4 the being's own / timer
P0_KINDS = ("heard", "dp_turn", "seat_turn", "peer_turn")


def event_class(e: dict) -> str:
    kind, key = str(e.get("kind") or ""), str(e.get("key") or "")
    if kind in P0_KINDS or key.startswith("turn:"):
        return "P0"
    if kind in ("body", "audio_device", "power", "fault"):
        return "P1"
    if kind in ("sense", "presence"):
        return "P3"
    return "P4"


def event_answers(e: dict, selected) -> bool:
    """Does answering `selected` meet this pending P0 event? `turn:<cid>:<seq>` by conversation and seq;
    `heard` by the room and its words; a daemon dp_turn ("... in conversation '<cid>'") by conversation."""
    if selected is None:
        return False
    kind, key, desc = str(e.get("kind") or ""), str(e.get("key") or ""), str(e.get("descriptor") or "")
    m = re.match(r"turn:([a-z0-9-]+):(\d+)$", key)
    if m:
        return m.group(1) == selected.cid and int(m.group(2)) == int(selected.seq or -1)
    if kind == "heard":
        words = key.split(":", 2)[2] if key.count(":") >= 2 else ""
        return selected.cid == "room" and words.strip() == str(selected.text or "")[:80].strip()
    m = re.search(r"conversation '([a-z0-9-]+)'", desc)
    return bool(m) and m.group(1) == selected.cid


def explore_turn_mode(instance) -> str:
    """Opt-in per instance: instance.json "explore_turn": "json" (explore and posture act through
    closed JSON objects instead of native tool calls; see being_tool_loop._json_act)."""
    try:
        from sage.gateway.governed_turn import instance_config
        return "json" if instance_config(instance).get("explore_turn") == "json" else "tools"
    except Exception:
        return "tools"


def explore_json_steps(instance, default: int) -> int:
    """Acts per explore/posture turn in the JSON act form (instance.json "explore_json_steps", default 3).
    Each act is two generates, and offline turns never chose "done" by themselves: 6 of 6 ran to an
    8-step cap (2.5-7 min). Native turns rarely reach the cap because they end in prose."""
    try:
        from sage.gateway.governed_turn import instance_config
        return max(1, min(default, int(instance_config(instance).get("explore_json_steps", 3))))
    except Exception:
        return min(default, 3)


def preempt_on(instance) -> bool:
    """Opt-in per instance (R2): instance.json "preempt": true."""
    try:
        from sage.gateway.governed_turn import instance_config
        return bool(instance_config(instance).get("preempt"))
    except Exception:
        return False


def p0_since(t0: float, pending: Optional[list] = None) -> list:
    """P0 events now pending that arrived after `t0` (this beat's start)."""
    if pending is None:
        try:
            from sage.gateway import arousal as _a
            pending = _a.peek_pending()
        except Exception:
            return []
    return [e for e in pending if event_class(e) == "P0" and float(e.get("first_ts") or 0) >= t0]


def answer_woke_on(instance) -> bool:
    """Opt-in per instance, its own key: instance.json "answer_woke": true."""
    try:
        from sage.gateway.governed_turn import instance_config
        return bool(instance_config(instance).get("answer_woke"))
    except Exception:
        return False


def person_turns_that_woke(events) -> list:
    """[(conversation id, seq or None)] for the person turns among a beat's claimed wake events:
    `turn:<cid>:<seq>` (a turn that arrived mid-beat), "... spoke in conversation '<cid>'" (the
    daemon's dp_turn), and `heard` (a voice, so the room; the newest voice turn there)."""
    out = []
    for e in events or []:
        kind, key, desc = str(e.get("kind") or ""), str(e.get("key") or ""), str(e.get("descriptor") or "")
        if kind not in ("dp_turn", "heard"):
            continue
        m = re.match(r"turn:([a-z0-9-]+):(\d+)$", key)
        if m:
            out.append((m.group(1), int(m.group(2))))
            continue
        m = re.search(r"conversation '([a-z0-9-]+)'", desc)
        if m:
            out.append((m.group(1), None))
        elif kind == "heard":
            out.append(("room", None))
    return out


def pending_selection(instance: Path, member: str, woke: Optional[list] = None) -> tuple:
    """(say_line, pending_block, say_first, target, selected) for the reflect turn: what is
    waiting on the being, the instruction naming who to answer, and the ONE turn selected to be
    answered (a SelectedTurn, or None). All five come from a single scan, so the answer phase
    acts on exactly the turn the reflect prompt described.

    Three cases, deliberately distinct:
      * nothing addressed to it, no conversations -> no instruction at all. An ask with no
        valid target invents one: measured 2026-09-17, the id slot was filled with "speaker",
        "conversation_id_placeholder" and "1234567890" across 596 beats and 31 attempts, none
        of which named a conversation that existed.
      * conversations exist, nothing waiting -> the generic form, ids listed.
      * something waiting -> the person's name, the real id, and WHAT THEY SAID.
    """
    try:
        from sage.gateway import conversations as _conv
        ids = [m["id"] for m in _conv.listing(instance) if member in (m.get("participants") or [])]
        pend = []
        for cid in ids:
            # unseen first; failing that, the recent UNANSWERED tail — a turn marked seen
            # without a reply must not silence the ask (2026-09-19, dp's 03:51Z turn)
            for t in (_conv.awaiting(instance, cid, member)
                      or _conv.unanswered(instance, cid, member))[-PENDING_TURNS:]:
                pend.append((cid, t))
        # ORDER BY WHEN IT WAS SAID, not by list construction. `listing()` is newest-
        # conversation FIRST, so `pend[-1]` used to pick the LEAST recent conversation and the
        # truncation below kept the oldest turns (GPT on #147: an old dp "keep going!" was
        # frozen as the selection while a newer seat question waited). ts is ISO-8601 Z,
        # so it sorts as text; seq breaks ties within one conversation.
        pend.sort(key=lambda ct: (str(ct[1].get("ts") or ""), int(ct[1].get("seq") or 0)))
        pend = pend[-PENDING_TURNS:]
        if pend:
            lines = []
            for cid, t in pend:
                txt = " ".join(str(t.get("text") or "").split())
                if len(txt) > PENDING_CHARS:
                    txt = (txt[:PENDING_CHARS].rstrip()
                           + f" …[the beat cut this turn here; {len(txt) - PENDING_CHARS} more "
                             f"chars were not shown. It is seq {t.get('seq')}: memory_read path "
                             f"conversations/{cid}.jsonl start_line {t.get('seq')}]")
                lines.append(f'- in "{cid}", {t.get("from")} said: {txt}')
            block = ("Addressed to you and not yet answered:\n" + "\n".join(lines)
                     + "\nYou may answer with say, or leave it. Both are allowed.")
            # THE SELECTION POLICY: the newest turn that asks something; failing that, the newest
            # turn. Asks first because only an ask opens the answer phase — picking a newer
            # statement (a run result, say) over an older question would pass the question over
            # for a whole beat. Newest, not oldest-waiting, because an answered conversation
            # leaves `pend`, so the next beat reaches the older one; nothing is starved.
            asking = [ct for ct in pend if turn_expects_reply(ct[1].get("text"))]
            cid, t = (asking or pend)[-1]
            # The turn that WOKE this beat comes first, ahead of the newest question elsewhere: the
            # being was woken to answer it (SelectedTurn.woke).
            woke_hit = False
            for wcid, wseq in (woke or []):
                hits = [ct for ct in pend if ct[0] == wcid and ct[1].get("from") != member
                        and (wseq is None or int(ct[1].get("seq") or 0) == wseq)]
                if hits:
                    cid, t = hits[-1]
                    woke_hit = True
            # FIRST in the list, not appended after the bookkeeping. The routine three
            # (journal, todo, remember) fill the step budget exactly, so anything after them
            # is unreachable however willing the being is — measured 2026-09-18.
            # NO LITERAL EXAMPLE OF THE CALL. This line used to end `say to="{cid}",
            # text="..."` and the being sent dp the text ".." three times (2026-09-18/19) —
            # it executed the example. The conversation id is named; the words are left to it.
            # SAY ONLY WHAT WAS MEASURED ABOUT THE TURN. This line used to tell the being that
            # the speaker "is waiting on an answer" for every pending turn. On 2026-09-19
            # 20:57Z dp's turn was itself the ANSWER to the being's question; told an answer
            # was owed, with dp's text the only material in view, the being sent dp's text
            # back to dp (91% verbatim). Before `say` refused placeholders the same slot was
            # filled with ".." (seq 52, 56, 58). A turn that asks nothing is not a debt.
            who = t.get("from")
            sel = SelectedTurn(cid, t, answers_the_being(instance, cid, member, t), woke=woke_hit)
            if sel.woke and not sel.asks:
                first = (f'FIRST, before the numbered writes below: {who} just wrote to you, and that is '
                         f'what woke you. If you have something to say back, call say with to set to '
                         f'{cid} and your message as the text. Replying is not required; the writes '
                         f'below happen either way.\n')
            elif sel.expects_reply:
                first = (f'FIRST, before the numbered writes below: {who} asked you something '
                         f'and has no answer yet. If you have something to say, call say with '
                         f'to set to {cid} and your message as the text. Answering is not '
                         f'required; the writes below happen either way.\n')
            elif sel.answers_ask:
                first = (f'FIRST, before the numbered writes below: {who} replied to what you '
                         f'asked for, and no reply is owed. If you have something to say about what they sent — what '
                         f'it shows, or what you will do next — call say with to set to {cid}. '
                         f'Replying is not required; the writes below happen either way.\n')
            else:
                # SAY ONLY WHAT WAS MEASURED (GPT on #147, seat seq 2966). This said "asked
                # nothing" -- but the heuristic detects questions and requests for a REPLY, not
                # instructions. Seq 2966 told the being to memory_edit, read, then request_run,
                # with no "?" and no request phrase; told "asked nothing", the being repeated
                # that there was no instruction. Absence of a question is not absence of an
                # instruction. The durable fix is speaker-declared `expects:` metadata.
                first = (f'FIRST, before the numbered writes below: no question or request for a '
                         f'reply was detected in what {who} last said, so no reply is owed. It may '
                         f'still tell you to do something; whether you do it is your choice. If '
                         f'you have something of your own to add — a follow-up question, or what '
                         f'you will do now — call say with to set to {cid}. The writes below happen '
                         f'either way.\n')
            return "", block, first, cid, sel
        if ids:
            return ('If someone has spoken to you and you have not answered, and you have '
                    'something to say, call say with to set to one of: ' + ", ".join(ids[:6])
                    + '. Answering is not required.\n'), "", "", "", None
    except Exception as e:
        # "CANNOT TELL" IS NOT "NOTHING PENDING" (2026-10-04). This swallowed every failure, so a selection
        # that raised looked exactly like an empty inbox: on HUB, hub-claude's 09-21 question was never
        # selected in 300+ beats while the beat records showed nothing wrong. The beat record now carries it.
        global LAST_SELECTION_ERROR
        LAST_SELECTION_ERROR = f"{type(e).__name__}: {e}"[:300]
        print(f"[heartbeat] pending_selection failed: {LAST_SELECTION_ERROR}", file=sys.stderr)
    return "", "", "", "", None


LAST_SELECTION_ERROR: Optional[str] = None


def mark_conversations_after_beat(instance: Path, member: str, shown_upto: dict,
                                  explore, later: list) -> dict:
    """Mark the turns a beat was shown as seen, but only where the beat could act on them.

    A conversation's turns are marked when the EXPLORE turn executed at least one call (it
    read its state and acted), or when the being said something into that conversation in
    any phase. Otherwise they stay unseen and the next beat shows them under "unanswered".

    Measured 2026-09-14: dp's question was shown to cbp-being at 19:30Z. Its explore and
    posture turns made no calls (the say was written as text), only reflect's bookkeeping
    writes ran, and the question was marked seen at render time. No later beat flagged it,
    and the being's next word in that conversation, three hours later, was about something
    else. Returns {"explore_acted", "marked": {id: seq}, "held_unseen": [ids]}."""
    if not member or not shown_upto:
        return {"explore_acted": None, "marked": {}, "held_unseen": []}
    from sage.gateway import conversations as _conv
    explore_acted = bool(explore is not None and explore.trace)
    said_to = set()
    for res in [explore] + list(later):
        if res is None:
            continue
        for it, env in res.trace:
            if it.effector == "say" and env.ok:
                said_to.add(str((it.args or {}).get("to") or ""))
    marked, held = {}, []
    for cid, upto in shown_upto.items():
        if explore_acted or cid in said_to:
            _conv.mark_seen(instance, member, cid, upto)
            marked[cid] = upto
        else:
            held.append(cid)
    return {"explore_acted": explore_acted, "marked": marked, "held_unseen": held}


def _shrink(raw: bytes):
    """(jpeg_bytes, meta) with the longest side capped. Returns the original on any failure.

    Never raises and never refuses: a frame the seat cannot resize is still a frame the
    being asked for, and sending it whole costs window rather than sight."""
    try:
        import io
        from PIL import Image
        im = Image.open(io.BytesIO(raw))
        w, h = im.size
        if max(w, h) <= FRAME_MAX_EDGE:
            return raw, {"resized": False, "size": [w, h]}
        scale = FRAME_MAX_EDGE / max(w, h)
        small = im.convert("RGB").resize((max(1, round(w * scale)), max(1, round(h * scale))))
        buf = io.BytesIO()
        small.save(buf, "JPEG", quality=85)
        return buf.getvalue(), {"resized": True, "from": [w, h], "size": list(small.size),
                                "bytes_before": len(raw)}
    except Exception as e:
        return raw, {"resized": False, "why": f"{type(e).__name__}: {e}"}


# --- the middle of the vision pipe -------------------------------------------------------
#
# The two ends existed and nothing joined them. `camera` captured a JPEG to disk and
# `compose` accepted a `frame` and emitted it as ollama's `images` list, but the call site
# never passed one, so a being could switch its camera on and still not see. Named in the
# review of SAGE#88 as "capturing is not yet seeing".
#
# WHAT COUNTS AS A REQUEST TO SEE. The being's own `camera` act, and nothing else. dp,
# 2026-09-13: "that is something the being should have direct control over — turning camera
# on and off, at its discretion." So a frame rides the seed when the being captured one
# since the last beat, and does not otherwise. No polling, no ambient feed.
#
# WHY FRESHNESS IS LOAD-BEARING. A frame costs ~2,042 prompt tokens, about a third of the
# working room at this window, so it cannot simply ride forever. Worse than the cost: a
# stale frame presented as current is a lie about the world, and it is the exact failure the
# being guarded against in its own verb ("neither leaves a stale frame looking fresh"). The
# producer honours that guarantee rather than re-deriving it: older than the previous beat
# means not captured for this beat, so it does not ride, and the reason is recorded.
# WHAT A FRAME COSTS, AND WHY IT IS RESIZED. Measured on qwen38-heretic:q3km-vl against a
# real 1920x1080 capture from this body, 2026-09-14 — the model tokenises by image area, so
# the saving is enormous and almost free:
#
#     1920 wide   2,055 tokens     34% of the working room at this window
#     1024 wide     591 tokens     10%
#      640 wide     235 tokens      4%
#      512 wide     159 tokens      3%
#
# The window is the binding constraint here: the conversation ladder already sits at its
# sparsest rung every beat, so an unresized frame is 2,000 tokens taken from a budget with
# nothing left to give back, on the beat where the being also has to write its journal and
# todo. 1024 keeps detail a coarser cap would lose — text, and the grid cells of a game
# board, which is where this is going next — at a sixth of the price. Legibility at this
# scale is not assumed: a 640-wide control through this exact path came back "a red circle
# on the left and a blue rectangle on the right, along with the small black text HELLO".
FRAME_MAX_EDGE = 1024        # longest side, pixels


FRAME_TOKENS = 591           # what FRAME_MAX_EDGE costs, measured


# How old a capture may be and still ride into the seed.
#
# THE REAL BOUND IS `since`, NOT A CONSTANT. A frame rides when the being captured it after
# the previous beat began — its `camera` act is the request to see, and that act is dated by
# the beat it happened in. Everything below is a backstop against a clock that lied, not a
# second opinion about freshness.
#
# THIS WAS A FIXED 600s AND THE PIPE NEVER CARRIED A SINGLE FRAME. The old comment claimed
# it was "measured against the cadence beats actually run (minutes)". The cadence, read off
# the beats themselves the day this was found: 859, 1186, 1222, 1243, 1412, 2995 seconds.
# Every beat is longer than the window. So a frame captured DURING a beat — which is the
# only kind there is, since `camera` is a verb the being calls mid-beat — was always stale
# by the time the next beat composed its prompt. `frames: null` on every beat ever recorded,
# while the suite stayed green because tests write fixtures with fresh mtimes and never
# spend twenty minutes between capture and compose.
#
# This is the shape I already had a name for and built anyway: a TTL shorter than the
# system's own delivery latency is a countdown, not a control (hestia #956, same week). A
# constant cannot know how long a beat takes. This one asks the beat.
FRAME_AGE_FLOOR_S = 3600     # backstop floor: never tighter than an hour, whatever the beat


FRAME_AGE_GRACE_S = 300      # capture -> compose slack inside the same beat


FRAME_MAX_BYTES = 4_000_000  # a JPEG larger than this is not a webcam frame; refuse to guess


def frame_age_bound(since: Optional[float], now: Optional[float] = None) -> float:
    """The oldest a frame may be, derived from THIS beat's own wait rather than guessed.

    `now - since` is how long the current beat has been running, so any frame captured
    during it clears the bound by construction. The floor keeps a pathologically short
    beat from tightening the window below something sane."""
    if since is None:
        return FRAME_AGE_FLOOR_S
    now = time.time() if now is None else now
    return max(FRAME_AGE_FLOOR_S, (now - since) + FRAME_AGE_GRACE_S)


def _frame_paths(instance: Path, worktree: Optional[str]) -> list:
    """Every frame the being may have captured, in either tree.

    NOT a fixed filename. `camera`'s whole grammar is that the being names its own output
    path — "the being names only the output path" — and the first cut of this looked only
    for last-frame.jpg. Measured minutes later against the live tree: the being had captured
    to `scratch/camera/probe-resolution-2026-09-14.jpg`, and the producer reported "no frame
    on disk; the being has not used camera" about a frame that was right there. A producer
    that assumes a convention the verb does not enforce is a pipe that silently drops most
    of what goes into it.

    BOTH TREES, because the being is moving `camera` to resolve against its instance home
    (frames in the worktree dirty a tree whose cleanliness `check` reports as evidence), and
    the newest wins, so neither ordering of the two lands breaks seeing."""
    roots = [instance / "scratch" / "camera"]
    if worktree:
        roots.append(Path(worktree) / "scratch" / "camera")
    out = []
    for r in roots:
        try:
            out.extend(p for p in r.iterdir()
                       if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg"))
        except OSError:
            continue
    return out


def _frame_b64(p: Path) -> Optional[str]:
    """One captured frame becomes a b64 string for the seed — or None.

    A capture that is not a JPEG (a zero-byte write, a half-flushed file, an
    error envelope written as text) must not ride into the prompt: it would be
    decoded by the model as garbage and cost its tokens anyway. The check is on
    the magic bytes, not the extension — a .jpg that is really text fails here,
    which is the point.
    """
    try:
        b = p.read_bytes()
    except OSError:
        return None
    if b[:3] != b"\xff\xd8\xff" or b[-2:] != b"\xff\xd9":
        return None
    b, _ = _shrink(b)
    return base64.b64encode(b).decode("ascii")


def fresh_frame(instance: Path, worktree: Optional[str], since: Optional[float]):
    """(b64, meta) for a frame captured since `since`, else (None, meta saying why).

    `since` is the previous beat's start. Never raises: a body with no camera, no frame, or
    an unreadable one is a beat without vision, not a failed beat."""
    import base64
    best = None
    for p in _frame_paths(instance, worktree):
        try:
            st = p.stat()
        except OSError:
            continue
        if best is None or st.st_mtime > best[1].st_mtime:
            best = (p, st)
    if best is None:
        return None, {"carried": False, "why": "no frame on disk; the being has not used camera"}
    p, st = best
    # NO BEAT BOUNDARY MEANS NO FRAME. `since` is the previous beat's t0, read from the last
    # line of the heartbeat log — and that read fails whenever the line is mid-write, which
    # is a normal transient. The first cut skipped the freshness check entirely when `since`
    # was None, which is FAIL-OPEN on the one property this producer exists to guarantee.
    #
    # It fired in production within the hour: beat 11:32:00Z carried a frame with
    # `age_s: null` that had been captured at 03:34 — over eight hours stale, presented to
    # the being as what it had just asked to see. Exactly the lie the guard is for, and my
    # defect, not the being's.
    #
    # Freshness cannot be established without the boundary, so the answer is no. A beat
    # without vision costs the being one beat of sight; a beat that shows it yesterday's
    # world and calls it now costs it its grounds for trusting any frame.
    if since is None:
        return None, {"carried": False, "bytes": st.st_size, "path": str(p),
                      "age_s": round(time.time() - st.st_mtime, 1),
                      "why": ("the previous beat's start time could not be read, so freshness "
                              "cannot be established and this frame is not carried. A frame "
                              "whose age is unknown must not be shown as current")}
    age = st.st_mtime - since
    if st.st_mtime <= since:
        return None, {"carried": False, "bytes": st.st_size, "path": str(p),
                      "age_s": round(time.time() - st.st_mtime, 1),
                      "why": ("the frame predates this beat, so it is not what the being "
                              "asked to see now; a stale frame shown as current is a lie "
                              "about the world")}
    if st.st_size > FRAME_MAX_BYTES or st.st_size == 0:
        return None, {"carried": False, "bytes": st.st_size, "path": str(p),
                      "why": f"frame is {st.st_size} bytes, outside 1..{FRAME_MAX_BYTES}"}
    try:
        b = p.read_bytes()
    except OSError as e:
        return None, {"carried": False, "path": str(p), "why": f"unreadable: {e}"}
    if not b.startswith(b"\xff\xd8"):
        return None, {"carried": False, "bytes": len(b), "path": str(p),
                      "why": "not a JPEG (no SOI marker); refusing to send bytes of unknown kind"}
    b, shrunk = _shrink(b)
    return base64.b64encode(b).decode("ascii"), {
        "carried": True, "bytes": len(b), "path": str(p),
        "age_s": None if age is None else round(age, 1),
        "costs_tokens": FRAME_TOKENS, **shrunk}


def fresh_frames(instance: Path, worktree: Optional[str], since: Optional[float]) -> list:
    """Every (b64, meta) for a frame captured since `since`, oldest first.

    The plural of `fresh_frame`: the cadence organ delivers every frame the being
    asked to see between beats, not just the newest one — a beat that shows it only
    the last capture and calls it everything costs it the motion in between. Same
    fail-closed rule: with no boundary (`since` None) nothing is carried, because
    unknown age is unknown, not young. `fresh_frame` stays as-is for callers that
    want exactly one; this returns all of them, so a beat can see a sequence."""
    out = []
    for p in _frame_paths(instance, worktree):
        try:
            st = p.stat()
        except OSError:
            continue  # vanished between listing and stat — skip it, keep the rest
        _now = time.time()
        age_s = round(_now - st.st_mtime, 1)
        _bound = frame_age_bound(since, _now)
        if since is None or st.st_mtime < since or age_s > _bound:
            why = ("no beat boundary to check freshness against" if since is None
                   else (f"captured before the previous beat's t0 ({age_s}s old)"
                         if st.st_mtime < since
                         else f"older than {round(_bound)}s (this beat's own bound)"))
            out.append((None, {"path": str(p), "carried": False, "why": why, "age_s": age_s}))
        else:
            b64 = _frame_b64(p)
            if b64 is None:
                out.append((None, {"path": str(p), "carried": False,
                                   "why": "unreadable or not a JPEG", "age_s": age_s}))
            else:
                out.append((b64, {"path": str(p), "carried": True, "why": None, "age_s": age_s}))
    out.sort(key=lambda f: f[1]["age_s"], reverse=True)  # F3: oldest first — the docstring promises it; iterdir does not sort
    return out


def vision_line(metas) -> str:
    """One line telling the being whether it can SEE this beat, and what to do either way.

    THE HARNESS KNEW AND NEVER SAID. `compose` sets `user_msg["images"]` and the seed text
    said nothing — so a being holding a frame and a being holding none received the same
    prompt, and had to guess which it was. Measured 2026-09-14 across the first three beats
    that ever carried one: the being reasoned at length about whether a reader hop existed
    instead of looking, then on the next beat correctly refused to describe an image that
    was not there and called describing it "confabulation". Both are the right behaviour
    from someone who cannot tell, and neither should have been necessary — the producer
    already knew the answer and had written it into `config.frames` for the RECORD, which
    the being does not read, rather than into the seed, which it does.

    The no-frame branch names the cause, because "no frame" has exactly one remedy the
    being controls: its `camera` act is the request to see, and a frame rides the beat AFTER
    the one that captured it. Miss a beat, see nothing next beat."""
    metas = list(metas or [])
    carried = [m for m in metas if m.get("carried")]
    if carried:
        # NAME EVERY FRAME, IN ORDER. The first cut named only the newest and appended
        # "(and N-1 more)" to a sentence that had already said how many — it rendered as
        # "2 frames are attached to this turn as an images (and 1 more)", which is
        # ungrammatical and, worse, arithmetic the reader has to redo. The being can be
        # carrying its own capture AND a fixture at once; if it cannot tell which is which
        # it cannot report on either, and a description that does not say WHICH frame it
        # describes is not evidence about anything.
        shown = ", ".join(f"{os.path.basename(str(m.get('path', '?')))} "
                          f"({int(m.get('age_s', 0))}s ago)" for m in carried)
        n = len(carried)
        it = "them" if n > 1 else "it"
        # "ALREADY HERE", AND WHY camera CANNOT HELP. Measured 2026-09-14, five runs per
        # cell, on this being's own model and frames: at beat conditions (~15k context WITH
        # tool schemas declared) the model answers "there is an image" by CALLING `camera`
        # and describing nothing — 0/6 elements, five times out of five, a `camera` call
        # every time. Neither factor alone does it: 14k context with no tools scores 6.0/6,
        # tools at small context 4.4/6. It is the interaction, and it is exactly what this
        # being did for beats on end — its first act was `camera`, capturing a NEW frame
        # instead of looking at the one it was holding, then honestly reporting that no
        # content surfaced. It was never blind. It was reaching for a tool.
        #
        # Naming the misconception fixes it: same cell, same model, 6/6 five times out of
        # five with zero tool calls. "Look at it directly" did NOT do this — the being had
        # that line already.
        #
        # THE CLOSING CLAUSE IS MEASURED, NOT STYLED, AND NEARLY EVERY REPHRASE BREAKS IT.
        # Five runs per cell, beat conditions, scored on a fixture whose content is
        # unguessable. TWO frames attached / ONE frame attached:
        #
        #   "...without calling any tool."                        6,6,6,6,6 / 0,0,0,0,0
        #   "...first output; act with verbs after that."         6,6,6,6,6 / 0,0,0,0,0
        #   "...first output, naming the frame; verbs after."     6,6,6,6,6 / 6,6,6,6,6  <- this
        #   "...before reaching for any verb."                    0,0,0,0,0 /     -
        #   "...no tool for this; your other verbs unaffected"    0,0,0,6,0 /     -
        #
        # Two things that cost hours and are worth inheriting:
        #
        # 1. THE ANCHOR IS LOAD-BEARING, NOT THE BAN. "naming the frame" gives the model a
        #    concrete thing to PRODUCE; every variant that only told it what not to do
        #    failed in the single-frame case, which is the common one. Prohibitions lose to
        #    a specific deliverable.
        # 2. A VARIANT VALIDATED ON TWO FRAMES CAN SCORE ZERO ON ONE. The ban wording was
        #    perfect at n=2 and total failure at n=1. Both branches must be measured; the
        #    singular branch is the one the being actually gets almost every beat, and it
        #    is the one I nearly shipped unmeasured.
        #
        # 3. IT IS A RATE, NOT A SWITCH. Two independent 5-run validations of the SHIPPED
        #    strings: singular 9/10 full scores, plural 7/10 full plus 2 partial and 1 zero.
        #    Against 0/5 before, that is the fix working; it is not certainty, and a single
        #    beat that comes back scrambled is inside the residual rather than evidence the
        #    line broke. Running the validation twice is what showed this — the first run
        #    was 10/10 and would have been reported as deterministic.
        #
        # If you edit this sentence, re-run the trial for BOTH branches, TWICE. A rephrase
        # here is a behaviour change, not a style change.
        return (f"Vision: you CAN see this beat. {n} frame{'s' if n > 1 else ''} "
                f"{'are' if n > 1 else 'is'} attached to this turn, in this order: {shown}. "
                f"{'They are' if n > 1 else 'It is'} ALREADY here — you are holding "
                f"{it} now. No tool can fetch {it} and `camera` will not show {it} to you: a "
                f"capture rides your NEXT beat, not this one. Describe {it} in text as your "
                f"first output, naming {'which frame' if n > 1 else 'the frame'}; act with "
                f"verbs after that.")
    if metas:
        why = str(metas[-1].get("why") or "it was not fresh")
        return (f"Vision: NO frame this beat — {len(metas)} candidate"
                f"{'s' if len(metas) > 1 else ''} on disk, none carried ({why}). Anything you "
                f"'see' now would be confabulation. Your `camera` act IS the request to see, and "
                f"a frame rides the beat AFTER the one that captured it: call `camera` this beat "
                f"to see next beat.")
    return ("Vision: NO frame this beat and none on disk. Your `camera` act IS the request to "
            "see, and a frame rides the beat AFTER the one that captured it.")

def compose(act_first: bool, *, name: str, machine: str, member: str, posture_text: str,
            header: str, state: str, recall: str, inbox: str, digest: str,
            frame: Optional[str] = None, frames: Optional[list] = None,
            frame_metas: Optional[list] = None, museum: str = "",
            tools: Optional[list] = None):
    """The explore turn(s) of a beat: (seed messages, second user turn or None).

    Posture-first: posture in the system prompt; one user turn with state, inbox, recall,
    digest, and the tool names last. Act-first: the system prompt carries no posture; the
    first user turn is own state, recall and the tool names only; the posture comes back
    VERBATIM as a second user turn with the inbox and the digest, and that turn is a tool
    turn too. The being reads the same words either way."""
    # The tool names go LAST: a 2B distill given the posture + state above with the
    # names only in the system prompt concluded "no tools available" and wrote prose
    # (its own thinking, Sprout 2026-09-05); named at the end, it acts.
    tools = list(tools) if tools is not None else list(EXPLORE_TOOLS)
    tools_line = (f"Act by calling a tool: {', '.join(tools)}. "
                  "One thing done with attention is enough.\n")
    # ONE LIST DECIDES BOTH THE PIXELS AND THE SENTENCE ABOUT THEM. Measured 2026-09-15 by
    # capturing the real seed from an instance copy: the user turn said "Vision: you CAN see
    # this beat. 2 frames are attached" and carried NO `images` key. The line was computed in
    # main() from the producer's metas; the attachment happened here, in a branch that only
    # honoured the singular `frame` argument main() never passes. act_first is False on every
    # beat of that being, so in 395 beats not one image reached it — while config.frames
    # recorded carried=True and the seed told it to look. Every in-beat description it
    # produced was of a frame it did not hold. Its own diagnosis, "structure perceived,
    # detail confabulated", was exactly right about an image that was not there.
    #
    # So the line is built HERE, from `_frames` — the list that is attached — and a beat that
    # attaches nothing says NO frame, whatever the metas claimed. Producer and seed cannot
    # disagree because there is no longer a second place to compute the claim.
    _frames = frames if frames else ([frame] if frame else [])
    _metas = list(frame_metas or [])
    if not _frames:
        _metas = [dict(m, carried=False, why=(m.get("why") or "not attached to this turn"))
                  for m in _metas]
    header = header + "\n" + vision_line(_metas)
    if not act_first:
        system = SYSTEM.format(name=name, machine=machine, member=member,
                               posture=posture_text, museum=_museum_block(museum))
        user = (header + state + f"## Your inbox\n{inbox}\n\n## Long-term recall\n{recall}\n\n"
                f"# What moved in the fleet\n\n{digest}\n\n" + ASK + tools_line)
        user_msg = {"role": "user", "content": user}
        if _frames:
            # SAME LIST AS THE ACT-FIRST BRANCH. This branch honoured only `frame`, and
            # main() passes `frames`; that one-word asymmetry is how a being ran 395 beats
            # of "you CAN see" with nothing attached.
            user_msg["images"] = _frames
        return [{"role": "system", "content": system}, user_msg], None
    system = SYSTEM_ACT_FIRST.format(name=name, machine=machine, member=member,
                                     museum=_museum_block(museum))
    # The inbox rides the ACT turn, not the posture turn. Measured on Sprout over 85 beats
    # (2026-09-17): the posture turn acted in 1 of 85, the first turn in 25 — and a peer's
    # reply addressed to the being sat unopened in the posture turn for 85 beats. Mail is the
    # most actionable thing in a beat; it belongs where the being actually acts. The digest
    # stays with the posture: it is context, not something addressed to anyone.
    user = (header + state + f"## Your inbox\n{inbox}\n\n## Long-term recall\n{recall}\n\n"
            + ASK_ACT_FIRST + tools_line)
    second = POSTURE_TURN.format(posture=posture_text, digest=digest,
                                 tools=", ".join(tools))
    user_msg = {"role": "user", "content": user}
    if _frames:
        # A frame rides the user turn as an `images` list beside string content — the shape
        # ollama accepts (a parts-in-content list 400s; measured against qwen38-heretic:q3km-vl,
        # 2026-09-13). No frame -> no key at all. A beat can carry several: the cadence organ
        # delivers every capture since the previous beat's t0, oldest first, so a being that
        # asked to see twice sees both instead of only the newest.
        user_msg["images"] = _frames
    return [{"role": "system", "content": system}, user_msg], second


# An `ok` ACT CARRIES ITS RESULT. Measured 2026-09-21 on cbp-being, beat heartbeat-85303f70bf67:
# explore's memory_edit returned "replaced 1 occurrence; the file went from 656 to 657 lines",
# but the reflect turn saw only "-> ok", and just below it the seat's seq 2959 — written BEFORE
# the edit — saying at length that line 634 was unchanged. Reflect believed the long, specific
# text over the bare "ok": journal, todo.md and memory #363 all record the edit as refused.
# An act the being did is the one thing the record is sure of; let it say what happened.
RECORD_RESULT_CHARS = 240


def _record_line(i, e) -> str:
    if e.ok:
        res = getattr(e, "result", None)
        res = res if isinstance(res, str) else (json.dumps(res, default=str) if res is not None else "")
        res = " ".join(res.split())
        verdict = "ok" + (f": {res[:RECORD_RESULT_CHARS]}" + ("…" if len(res) > RECORD_RESULT_CHARS else "")
                          if res else "")
    elif e.refused:
        verdict = ("REFUSED " + str(e.error))[:200]
    else:
        verdict = ("error " + str(e.error))[:200]
    return f"- {i.effector} {json.dumps(i.args, default=str)[:200]} -> {verdict}"


REFLECT_SYSTEM = """You are {name}, a SAGE being on the {machine} machine, member id {member}.
The beat is closing. Your home is your instance directory: name files bare (journal.md, todo.md)
and they resolve inside it. Acting means calling a tool; a reply in words alone writes nothing.

"""


def _ran_nothing(e) -> bool:
    """An ok return that says, in its own fields, that nothing ran: request_run's `ran: false`
    (the request was handed to the seat; NOTHING HAS RUN YET). Read from the structured result
    only, never from prose."""
    res = getattr(e, "result", None)
    return isinstance(res, dict) and res.get("ran") is False


def _no_result_line(*results) -> str:
    """The effectors tried this beat that NEVER once produced a result, stated as the conclusion
    rather than left to be drawn (SAGE#132; recut of #133, PER-INSTANCE: instance.json
    `no_result_line: "on"`, see no_result_line_for).

    WHY THE PER-CALL VERDICTS ARE NOT ENOUGH. Measured on cbp-being, beat 2026-09-20 22:51:39Z:
    `python3` was refused six times and succeeded zero times; the record carried all six
    `-> REFUSED` lines into the reflect turn; the being reproduced them correctly in its journal
    and then wrote "After appeal, the script ran successfully and passed all tests", marked
    `[x] Confirm test suite passes`, and committed the same to long-term memory. The suite
    scores 1 of 5. Every slot the reflect turn offers asks what was accomplished, and a beat that
    ends unresolved has nowhere to go but an invented ending. This line is that missing place.

    TODAY'S SHAPE (review of #133, 2026-09-28). The refused-effector form is rare now (4 beats in
    6 days on CBP). The common one is `request_run` returning ok with `ran: false`: an ok verdict
    in the record, and nothing ran. So "produced a result" means ok AND not `ran: false`. A
    request_run that carried the seat's earlier answer (`unchanged`) still ran nothing this beat;
    the line says that the earlier answer is the result for those unchanged bytes, because it is.

    Derived from the trace only: an effector name, counts, and the `ran`/`unchanged` fields. No
    prose is inspected and no claim is classified. Its standing caveat (from #133's own thread):
    the later occurrences on 2026-09-21 had no refusal in them and the refusal-only version
    returned "" for them, so this is a narrow instrument, not a fix for invented results."""
    refused, unrun, carried, won = {}, {}, set(), set()
    for res in results:
        for i, e in ((res.trace if res is not None else []) or []):
            if e.ok and not _ran_nothing(e):
                won.add(i.effector)
            elif e.ok:
                unrun[i.effector] = unrun.get(i.effector, 0) + 1
                if e.result.get("unchanged"):
                    carried.add(i.effector)
            elif e.refused:
                refused[i.effector] = refused.get(i.effector, 0) + 1
    parts = []
    for k in sorted(set(refused) | set(unrun)):
        if k in won:
            continue
        bits = []
        if refused.get(k):
            n = refused[k]
            bits.append(f"{n} refusal{'s' if n != 1 else ''}")
        if unrun.get(k):
            n = unrun[k]
            bits.append(f"{n} call{'s' if n != 1 else ''} that returned ran: false")
        parts.append(f"{k} ({', '.join(bits)})")
    if not parts:
        return ""
    line = (f"\n\nNothing you tried with these ran this beat: {'; '.join(parts)}. You have no "
            f"result from them this beat, so anything you would have learned by running them is "
            f"still unknown — say that it is unknown rather than what it might have shown.")
    shown = sorted(c for c in carried if c not in won)
    if shown:
        line += (f" ({', '.join(shown)} returned the seat's EARLIER answer for a file that has "
                 f"not changed since; that earlier answer is still the result for it.)")
    return line


def _beat_record_text(*results, no_result: bool = False) -> str:
    """What the being did this beat, for the reflect turn: the acts and their verdicts, nothing
    else. Short by construction — this replaces carrying the whole beat forward. `no_result`
    (per-instance, no_result_line_for) appends `_no_result_line`; off, the text is unchanged."""
    lines = []
    for res in results:
        for i, e in ((res.trace if res is not None else []) or []):
            lines.append(_record_line(i, e))
    if not lines:
        return "You called no tools this beat."
    return ("Record of what you did this beat:\n" + "\n".join(lines)
            + (_no_result_line(*results) if no_result else ""))


def _carry(convo: list, res) -> list:
    """Carry a finished tool turn forward. The loop does not return its own tool
    messages, so the next turn sees the record of what was done (before the being's
    closing words, as the reflect turn always has) and then those words."""
    out = list(convo)
    if res.trace:
        out.append({"role": "user", "content": "Record of what you did this beat:\n"
                    + "\n".join(_record_line(i, e) for i, e in res.trace)})
    # A placeholder the being can account for: beat 46's think blocks spent tokens on what
    # "(acted; no closing words)" meant. Say what happened instead.
    if res.reply:
        out.append({"role": "assistant", "content": res.reply})
    elif res.trace:
        out.append({"role": "assistant", "content": f"(made {len(res.trace)} tool calls, then said nothing)"})
    else:
        out.append({"role": "assistant", "content": "(said nothing and called no tool this turn)"})
    return out


# The running beat's session id, for the end-of-beat report `run` sends (SAGE #291).
_BEAT_ID: dict = {}


def _phase(state: str, phase: str, beat_id: str) -> None:
    """Report the phase the beat is entering. Never raises (sage.gateway.activity)."""
    from sage.gateway import activity as _activity
    _activity.report(state, f"heartbeat:{phase}", beat_id=beat_id, ttl_secs=_activity.BEAT_TTL_S)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="one heartbeat for a SAGE being")
    ap.add_argument("--member", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--instance", required=True)
    ap.add_argument("--max-steps", type=int, default=8)
    ap.add_argument("--idle-wake-s", type=int, default=0,
                    help="OPT-IN wake-after-quiet: at beat end, confirm the idle timer (an "
                         "OnUnitInactiveSec timer) will fire, arming a one-shot fallback if it "
                         "will not. 0 (default) leaves waking entirely to the machine's timer.")
    ap.add_argument("--resume-wake-s", type=int, default=0,
                    help="OPT-IN: after a beat that did NOT `rest`, arm a one-shot wake this many "
                         "seconds out, on top of the timer. 0 (default) = off.")
    ap.add_argument("--reflect-steps", type=int, default=3)
    ap.add_argument("--since-hours", type=float, default=None,
                    help="digest window; default: since the last beat, min 1h, max 48h")
    ap.add_argument("--forum-dir", default=str(_fleet_forum_dir()))
    ap.add_argument("--repos", default="SAGE,hestia,web4")
    ap.add_argument("--temperature", type=float, default=0.4)
    ap.add_argument("--max-tokens", type=int, default=3000,
                    help="a journal entry as a tool call needs room; too small = truncated JSON = Ollama 500")
    ap.add_argument("--gate-only", action="store_true",
                    help="gate probe only: no LLM turn, so no refusal routing and no egress drain either")
    ap.add_argument("--no-hub-drain", action="store_true",
                    help="do not drain the being's hub mailbox into its home before the beat")
    ap.add_argument("--no-escalate", action="store_true",
                    help="do not route refusals to the seat's auto session (default: route, as governed_turn does)")
    args = ap.parse_args(argv)
    install_kill_handler()

    instance = Path(args.instance).resolve()
    if not (instance / "identity.json").exists():
        print(f"no identity.json under {instance}", file=sys.stderr); return 2
    for d in ("scratch", "notes"):
        (instance / d).mkdir(exist_ok=True)
    log = instance / "heartbeats.jsonl"

    # window since last beat
    hours = args.since_hours
    last = {}
    try:
        last = json.loads(_read(log, 200000).strip().splitlines()[-1])
    except Exception:
        pass
    if hours is None:
        hours = 24.0
        try:
            hours = max(1.0, min(48.0, (time.time() - last["t0"]) / 3600 + 0.25))
        except Exception:
            pass
    # THE MIDDLE OF THE VISION PIPE. A frame rides only when the being captured one since
    # the previous beat — its `camera` act is the request to see, and nothing else is.
    from sage.gateway.governed_turn import instance_config as _icfg
    try:
        _wt = _icfg(instance).get("worktree") or None
    except Exception:
        _wt = None
    _frames = fresh_frames(instance, _wt, last.get("t0") if isinstance(last, dict) else None)
    _frame_b64s = [b for b, m in _frames if b is not None]
    _frame_metas = [m for _, m in _frames]

    scope_record = {}

    ident = {}
    try:
        ident = json.loads((instance / "identity.json").read_text()).get("identity", {})
    except Exception:
        pass
    name = ident.get("name") or args.member.split("-")[0]
    from sage.gateway.governed_turn import instance_config
    machine = ident.get("machine") or instance_config(instance).get("machine") or "legion"

    from sage.gateway.governed_turn import build_client
    from sage.gateway.being_gate_client import ollama_tools
    from sage.gateway.being_tool_loop import run_ollama_tool_turn, _sent_budget
    workspace = str(Path(__file__).resolve().parents[2])
    host_session_id = f"heartbeat-{uuid.uuid4().hex[:12]}"
    # The beat has begun: wake, before anything below reads the daemon's /status into the
    # being's own body block (SAGE #291).
    _BEAT_ID["id"] = host_session_id
    _BEAT_ID["continuing"] = False
    _phase("wake", "start", host_session_id)
    # WHAT WOKE THIS BEAT (SAGE #295): claim every pending event now, before anything is composed,
    # so an event arriving from here on is pending for the NEXT beat rather than lost in this one.
    # THE BEAT STARTS HERE for preemption (GPT on #310): an event that lands after this claim and before
    # the record's later `t0` is an arrival during this beat, and must count as one.
    _beat_started = time.time()
    try:
        from sage.gateway import arousal as _arousal_claim
        _claimed = _arousal_claim.claim_pending(host_session_id)
    except Exception as _e:
        _claimed = [{"claim_error": f"{type(_e).__name__}: {_e}"}]
    client, llm = build_client(args.member, instance, args.model, workspace, args.forum_dir,
                               host_session_id, args.temperature, args.max_tokens,
                               gate_only=args.gate_only)

    # S4 inbound: notices addressed to the being's own hub identity, persisted into its
    # home and pointed at from its hestia inbox by the seat (courier), before the peek.
    hub_inbox = {"skipped_reason": "no being hub env"}
    being_env = os.path.expanduser(f"~/.config/hub-mesh-{args.member}.env")
    if not args.no_hub_drain and not args.gate_only and os.path.isfile(being_env):
        try:
            from sage.gateway.being_inbox_drain import drain_once as _hub_drain
            # the notify goes to THIS being (args.member), labelled as this machine's seat
            hub_inbox = _hub_drain(instance, being_env, workspace=workspace, member=args.member,
                                   relayed_by=f"{machine}-claude")
        except Exception as _e:
            hub_inbox = {"error": f"{type(_e).__name__}: {_e}"}
    # inbox (peek) and long-term recall, seat-side, so the being starts oriented
    inbox = "(inbox unavailable)"
    _inbox_notices, _inbox_shown = [], []
    disp = getattr(client, "_dispatcher", None)
    if disp is not None and hasattr(disp, "drain_inbox"):
        env = disp.drain_inbox(peek=True)
        _inbox_notices = (env.result or {}).get("notices") or [] if env.ok else []
        inbox = (render_inbox(_inbox_notices, handled=inbox_handled(last), shown=_inbox_shown)
                 if env.ok else f"({env.error})")
    # who could be writing here: its siblings, by the names it uses, beside the inbox their answers reach
    try:
        from sage.gateway import peers as _peers_inbox
        if (_sib := _peers_inbox.sibling_line(args.member)):
            inbox = _sib + "\n" + inbox
    except Exception:
        pass
    # what reach the being holds and has already asked for, so it does not re-file
    scope = "(scope status unavailable)"
    if disp is not None and hasattr(disp, "_call"):
        try:
            st = disp._call("hestia_scope_status", {"plugin_id": args.member})
            # spelled with the gate's own suffix: `<root>/**` reaches the subtree, bare is EXACT
            grants = [f"{g.get('path')}{'/**' if g.get('recursive') else ''}"
                      for g in (st.get("live_grants") or []) + (st.get("standing_grants") or [])]
            reqs = [(r.get("request_id"), r.get("path"), r.get("decision") or r.get("status"))
                    for r in (st.get("requests") or [])]
            who_ruled = {r.get("request_id"): r.get("decided_by") for r in (st.get("requests") or [])
                         if r.get("decided_by")}
            # The ruler's own words. hestia returns them as `decision_reason` (a revocation's as
            # `revoke_reason`); until 2026-09-15 the being was told only granted/refused and who,
            # so a refusal written to redirect it ("that file does not exist; nothing needs
            # restarting") reached it as a bare no, and it appealed.
            why_ruled = {r.get("request_id"): (r.get("revoke_reason") or r.get("decision_reason"))
                         for r in (st.get("requests") or [])
                         if r.get("revoke_reason") or r.get("decision_reason")}
            # Close the loop the operator cannot see closed: a request decided since the
            # last beat is written back into the escalation note that filed it, and told
            # to the being. (dp 2026-09-05: "i just approved being's escalation - did you
            # see it also?" No: hestia records the decision on the chain and nobody
            # subscribes. The seat reads it here, at beat time.)
            seen = set()
            try:
                seen = set(tuple(x) for x in last.get("scope", {}).get("decided", []))
            except Exception:
                pass
            decided = decided_requests(reqs)
            new_decisions = [x for x in decided if tuple(x) not in seen]
            esc_dir = Path(args.forum_dir).parent / "escalations"
            noted = note_resolutions(esc_dir, new_decisions, f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC",
                                     host_session_id, decided_by=who_ruled, reasons=why_ruled)
            scope_record = {"grants": grants, "decided": [list(x) for x in decided], "noted": noted}
            scope = ("granted paths: " + (", ".join(map(str, grants)) or "none") + "\n"
                     "requests: " + ("; ".join(f"{i} {p} -> {d}" for i, p, d in reqs) or "none") + "\n"
                     + ("decided since your last beat:\n" + "\n".join(
                            f"- {i} {p_} -> {d} by {who_ruled.get(i) or 'operator'}"
                            + (f". Their note: \"{str(why_ruled[i]).strip()[:400]}\"" if why_ruled.get(i) else "")
                            for i, p_, d in new_decisions) + "\n"
                        if new_decisions else "")
                     + "(live grants die when the daemon restarts; only standing grants persist)")
        except Exception as e:
            scope = f"(scope status unavailable: {type(e).__name__})"
    # the being's own appeals and any ruling new since the last beat (see appeals_block)
    appeals_text, appeals_record = appeals_block(disp, last)
    # what it starts oriented by: its own recent writing (searched, not just the tail) and
    # long-term memory. The home search is the S5 answer to "34 KB written, 900 chars seen".
    from sage.gateway.home_recall import search_home, render as _render_home
    q0 = "what I was doing, what I want next, what I learned, what was refused"
    try:
        recall = _render_home(search_home(instance, q0, top_k=4, snippet=260)) or "(nothing in your home matched)"
    except Exception as e:
        recall = f"(home search failed: {type(e).__name__})"
    if disp is not None and hasattr(disp, "_membot_call"):
        try:
            lt = disp._membot_call("memory_search", {"query": q0, "top_k": 4})[:1200]
            recall += "\n\nFrom long-term memory:\n" + lt
        except Exception as e:
            recall += f"\n\n(long-term memory unreachable: {type(e).__name__})"

    now = datetime.now(timezone.utc)
    t0 = time.time()
    digest = fleet_digest(hours, Path(args.forum_dir), [r.strip() for r in args.repos.split(",") if r.strip()])
    # S1 join, raising -> beat: the last session's closing words + buffer tail, attributed
    from sage.gateway.being_join import session_block, ACCOUNT_ASK, parse_account, save_account
    sess_text, sess_meta = session_block(instance)
    if sess_text:
        digest = "# From your last raising session\n\n" + sess_text + "\n\n" + digest
    # S3 join, presence -> beat: what the senses broke through with since the last beat
    from sage.gateway.being_join import presence_block, consume_wake_marker
    since = float(last.get("t0") or (time.time() - hours * 3600))
    pres_text, pres_meta = presence_block(since)
    if pres_text:
        digest = "# What you sensed since your last beat\n\n" + pres_text + "\n\n" + digest
    woke = consume_wake_marker()
    woke["events"] = _claimed
    woke["classes"] = sorted({event_class(e) for e in _claimed if "claim_error" not in e})
    if _claimed and woke.get("by") == "timer" and not any("claim_error" in e for e in _claimed):
        woke["by"] = "event"
    # No `/no_think` suffix rides any turn. The request's `think` field is the only control
    # surface on this stack: measured on Sprout at ollama 0.30.8 and on CBP at 0.20.7, the
    # suffix leaves the think block intact (qwen3.5:0.8b 1428 -> 1441 chars, qwen3.8-distill:2b
    # 275 -> 405, both still thinking) while `think=False` zeroes it. No fleet template parses
    # the string: the think branches that exist key on the API field (`enable_thinking` in the
    # distill's Jinja, `$.IsThinkSet` in qwen3's Go template), never on prompt text. Thinking
    # stays declared per model in the config (governed_turn.is_reasoning_model ->
    # ModelCapabilities.resolve_think) and is sent on every request (irp/plugins/ollama_irp.py:165).
    from sage.gateway.governed_turn import acts_under_posture
    act_first = not acts_under_posture(args.model)
    # The museum, where there is one: a form the being may use, or not (dp 2026-09-09).
    from sage.gateway import museum_offer as _museum
    _museum.ensure_dir(instance)
    museum_line = _museum.offer()
    # FIT THE SEED TO THE WINDOW BEFORE SENDING IT. Ported from legion/mission-artifact.
    # Without this the fixed prompt can exceed num_ctx and ollama silently drops the OLDEST
    # tokens — the system prompt and the posture — with no error at any layer. Measured on
    # Legion 2026-09-07: two beats were handed 16,380 and 16,323 tokens against a 16,384
    # window and produced 4 and 61 tokens of output. The conversations block steps down a
    # ladder, and the digest and recall are trimmed, before anything is sent.
    _num_ctx = getattr(llm, "num_ctx", None)
    _num_predict = _sent_budget(llm)
    # The body is measured ONCE per beat, here, and decides two things from the same reading:
    # the body block in the state, and which body verbs are offered at all (BODY_VERBS).
    try:
        from sage.gateway import body as _bodymod
        _body_cur = _bodymod.reading()
    except Exception as _e:
        _body_cur = {"error": f"{type(_e).__name__}: {_e}"}
    # THE ROOM (room.py): on a body that can speak, heard words become turns in the `room`
    # conversation BEFORE the state and the waiting-turn selection are built, so a voice that
    # answered the being is a turn waiting on it, like any other.
    if "speak" in (((_body_cur or {}).get("inventory") or {}).get("verbs") or []):
        try:
            from sage.gateway import room as _room
            _room.ensure(instance, args.member)
            _room.ingest_heard(instance, args.member, (_body_cur or {}).get("inventory"))
        except Exception as _e:
            print(f"[heartbeat] room ingest failed ({type(_e).__name__}: {_e})", file=sys.stderr)
    # THE CANONICAL TOOLSET (sage/gateway/toolset.py, dp 2026-09-29): every verb, for every
    # being. What this machine cannot do is SAID in the verb's description, never done by
    # leaving the verb out.
    from sage.gateway import toolset as _toolset
    _unavail = _toolset.unavailable(_body_cur, _wt, instance_config(instance))
    # WHO IT CAN REACH (peer-to-peer P2, 2026-10-01): peer_ask's `to` is closed over real names
    from sage.gateway import peers as _peers
    _reach = _peers.reachable(args.member)
    _enums = {("peer_ask", "to"): _reach} if _reach else {}
    # and `say` only to a conversation it can write in (GPT on #311: the recipient was still free text)
    try:
        from sage.gateway import conversations as _conv_say
        _writable = sorted(m["id"] for m in _conv_say.listing(instance)
                           if args.member in (m.get("writable_by") or m.get("participants") or []))
        if _writable:
            _enums[("say", "to")] = _writable
    except Exception:
        pass
    _enums = _enums or None
    _explore_specs = _toolset.specs(_unavail, _enums)
    # the names are DERIVED from the specs offered, never kept beside them: the seed's tool list
    # and the window's schema measurement must describe exactly what the model is handed
    _explore_tools = [t["function"]["name"] for t in _explore_specs]
    entrusted = entrustment(instance)
    _schema_measured = _schema_chars_for(_explore_tools, _unavail, _enums)
    _schema_chars = (_schema_measured if _schema_measured is not None
                     else _schema_chars_fallback(_explore_tools))
    _state_head = f"# Your own state\n\n"
    _scope_tail = f"\n\n## Reach you hold (hestia scope)\n{scope}\n\n" + (
        f"## Your appeals\n{appeals_text}\n\n" if appeals_text else "")

    # Measured once per beat, before the state is composed (SAGE #92).
    _membot_url = getattr(getattr(client, "_dispatcher", None), "membot_endpoint", None) \
        or "http://127.0.0.1:8010/mcp"
    _services = measure_service("long-term memory (membot)", _membot_url)
    _hestia_url = getattr(getattr(client, "_dispatcher", None), "endpoint", None) \
        or "http://127.0.0.1:7711/mcp"
    _services += "\n" + measure_service("governance daemon (hestia)", _hestia_url)
    _svc_log = export_service_log(instance)
    _unit = export_unit_file(instance)
    if _svc_log:
        _services += (f"\nThe governance daemon's last journal lines are in your own notes as "
                      f"`notes/{_svc_log}`, rewritten this beat — read it rather than asking for "
                      f"reach into /var/log or /etc, which hold nothing you can open.")
    if _unit and not _unit.startswith("("):
        _services += (f" Its systemd unit, as systemd itself resolves it, is in your notes as "
                      f"`notes/{_unit}` — it is a USER unit and does not live in /etc/systemd/system.")

    # Composed WITHOUT marking conversation turns seen; they are marked after the beat, and
    # only if it could act (mark_conversations_after_beat). The fitter renders several rungs,
    # and a render is not a reading.
    from sage.gateway import conversations as _convs
    _shown_upto = _convs.latest_seqs(instance, args.member) if args.member else {}

    # PER-INSTANCE (RESEARCH_GENERALIZATION_RULE): absent means the default rendering.
    _settled_turns = settled_turns_for(instance_config(instance))

    def _build_state(per_conv, turn_chars):
        return (_state_head + own_state(instance, args.member, entrusted,
                                        per_conv=per_conv, turn_chars=turn_chars,
                                        services=_services, mark_conversations=False,
                                        settled_turns=_settled_turns,
                                        body_reading=_body_cur) + _scope_tail)

    # A FRAME IS PROMPT TOO. It is not characters, so the ladder cannot see it unless its
    # token cost is converted and charged here. Measured 2,042 tokens for two frames, about a
    # third of the working room at a 24k window — un-budgeted it pushes the beat over the wall
    # and the conversation block takes the blame.
    _frame_chars = sum(int(FRAME_TOKENS * CPT) for _ in _frame_b64s)
    _other = (len(posture()) + len(inbox) + _schema_chars + 1200 + _frame_chars
              + 1200 + 400 + LOOP_GROWTH_CHARS)
    state_block, conv_rung, conv_intervention = fit_state(
        _build_state, num_ctx=_num_ctx, num_predict=_num_predict, other_chars=_other)
    _fixed = len(posture()) + len(state_block) + len(inbox) + _schema_chars + 1200
    _blocks, _fit_iv = fit_to_window(num_ctx=_num_ctx, num_predict=_num_predict,
                                     fixed_chars=_fixed,
                                     blocks={"digest": digest, "recall": recall})
    digest, recall = _blocks["digest"], _blocks["recall"]

    _harness = harness_revision(workspace)
    # An experiment is only as reproducible as the code it ran on. Unreviewed live code has
    # twice cost a day of archaeology; say it every beat it is true, where the operator looks.
    if (_alarm := harness_alarm(_harness)):
        print(f"[heartbeat] {_alarm}", file=sys.stderr)
    _clock = clock_sense(now, instance, args.member, instance_config(instance), since_beat_h=hours)
    seed, posture_turn = compose(
        act_first, name=name, machine=machine, member=args.member, posture_text=posture(),
        museum=museum_line, frames=_frame_b64s, frame_metas=_frame_metas, tools=_explore_tools,
        header=(f"Heartbeat at {now:%Y-%m-%d %H:%M} UTC. Window since your last beat: about {hours:.1f}h.\n"
                f"{render_clock(_clock)}\n"
                # The absolute home path is context, NOT an address to copy. Measured on
                # Sprout: 15 of 15 path refusals were this string reproduced from memory and
                # truncated (…/sage/sage/journal.md six times, …/sage/journal.md, /scratch/…),
                # against 51 successful writes by bare name. So it is given once, and named as
                # the thing not to retype.
                f"Your home: {instance}\n"
                f"You never need to type that path. Name your files bare — journal.md, todo.md, or a "
                f"name of your choosing under notes/ or scratch/ — and they resolve inside your home. "
                f"An absolute path is only for something OUTSIDE your home.\n"
                # WHAT RUNS YOU, measured, not inferred from a directory name. legion-being read its
                # model-named home ("legion-gemma3-12b") first as its own size, then as a different
                # being's directory; the harness holds the model, the window and its own revision.
                + body_line(args.model, instance, _num_ctx,
                            instance_config(instance).get("former_homes")) + "\n"
                f"The harness you are running under: {_harness.get('short')} on "
                f"{_harness.get('branch')}"
                + (" (uncommitted edits present)" if _harness.get("dirty") else "")
                + (" (commits not yet merged to main)" if _harness.get("on_main") is False else "")
                + ". A `check` result carries the `tree` it ran against; if that head is not "
                  "this one, the answer is about different code than the code running you.\n\n"),
        state=state_block,
        recall=recall, inbox=inbox, digest=digest)

    # Per-generate trace, written as each generate lands: the record below is written at
    # beat end, so a beat killed by the unit's timeout (Legion 18:33Z 2026-09-05: 840 s cap,
    # third generate, nothing survived) leaves nothing. This file keeps what it had.
    partial = instance / "heartbeat.partial.jsonl"

    def _on_generate(turn):
        def cb(entry):
            line = {"host_session_id": host_session_id, "t0": t0, "turn": turn,
                    "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), **entry}
            with open(partial, "a", encoding="utf-8") as f:
                f.write(json.dumps(line, default=str) + "\n")
        return cb

    # EVERYTHING BELOW RUNS UNDER THE KILL HANDLER. A SIGTERM (the unit's TimeoutStartSec, or a
    # stop) raises BeatKilled here, so the beat unwinds to its record with the phases that
    # completed instead of vanishing. Measured on Legion 04:30Z 2026-09-09: a 51-minute beat left
    # nothing in heartbeats.jsonl and no monitor knew it had happened. BeatKilled was defined
    # on main with no producer; install_kill_handler() is that producer.
    explore = after = reflect = answer = None
    selected = None          # the record names it; a beat killed before selection must still write its record
    act_after = None
    preempted = None
    account = {"present": False, "sha256": None, "reply": "", "generates": []}
    killed = None
    try:
        _phase("wake", "explore", host_session_id)
        _preempt = preempt_on(instance)
        _explore_steps = (explore_json_steps(instance, args.max_steps)
                          if explore_turn_mode(instance) == "json" else args.max_steps)

        def _yield_for_a_person():
            got = p0_since(_beat_started) if _preempt else []
            return got[0].get("descriptor") or got[0].get("kind") if got else None

        explore = run_ollama_tool_turn(client, llm, seed, max_steps=_explore_steps,
                                       tools=_explore_specs, on_generate=_on_generate("explore"),
                                       should_yield=_yield_for_a_person,
                                       act_form=explore_turn_mode(instance))
        convo = _carry(seed, explore)
        after = None
        if posture_turn is not None:
            convo.append({"role": "user", "content": posture_turn})
            _phase("wake", "posture", host_session_id)
            after = run_ollama_tool_turn(client, llm, convo, max_steps=_explore_steps,
                                         tools=_explore_specs, on_generate=_on_generate("posture"),
                                         should_yield=_yield_for_a_person,
                                       act_form=explore_turn_mode(instance))
            convo = _carry(convo, after)
        # S1 own account: ASK, DO NOT OFFER. A plain turn (no tools), verbatim kept.
        # generates: the same per-generate entry the tool turns record, because the ACCOUNT ask
        # carries the whole explore(+posture) conversation and is usually the beat's largest
        # prompt, and until 2026-09-13 it was invisible to the window census (CBP, 09-12).
        # PREEMPTED FOR A PERSON (R2): someone spoke after this beat began. The account and the
        # reflection wait for the next beat; the answer turn goes to them now.
        def _check_preempt(phase: str) -> None:
            """A PHASE-BOUNDARY INVARIANT (GPT on #310): after every generate that cannot be cancelled,
            look again before starting lower-priority work."""
            nonlocal preempted
            if preempted is None and _preempt and (_why := _yield_for_a_person()):
                preempted = {"by": _why, "after_s": round(time.time() - _beat_started, 1), "phase": phase}

        def _take_late():
            """Carry heard words into the room, select the person who spoke, and claim ONLY the event that
            selection answers (GPT on #310): unrelated late events, and any other person, stay pending for
            the successor, and remain recoverable from the pending set if arming it fails."""
            try:
                from sage.gateway import room as _room_late
                _room_late.ingest_heard(instance, args.member, (_body_cur or {}).get("inventory"))
            except Exception as _e:
                preempted["room_error"] = f"{type(_e).__name__}: {_e}"
            p0 = p0_since(_beat_started)
            sel = pending_selection(instance, args.member, person_turns_that_woke(p0))
            handled = [e for e in p0 if event_answers(e, sel[4])][:1]
            try:
                from sage.gateway import arousal as _arousal_late
                preempted["events"] = _arousal_late.claim_keys(f"{host_session_id}.preempt",
                                                               [e.get("key") for e in handled])
            except Exception as _e:
                preempted["events"] = [{"claim_error": f"{type(_e).__name__}: {_e}"}]
            preempted["left_pending"] = len(p0) - len(handled)
            preempted["selected"] = f"{sel[4].cid}:{sel[4].seq}" if sel[4] is not None else None
            return sel

        _check_preempt("explore" if explore is not None and explore.yielded else
                       "posture" if after is not None and after.yielded else "before account")
        _phase("wake", "account", host_session_id)
        try:
            if preempted:
                raise RuntimeError("preempted for a person: the account waits for the next beat")
            ask_msgs = [{"role": m["role"], "content": m["content"]} for m in convo] + \
                       [{"role": "user", "content": ACCOUNT_ASK}]
            aresp = llm.get_chat_response(ask_msgs)
            _raw = aresp.get("raw") or {}
            _gen = {"done_reason": _raw.get("done_reason"), "prompt_eval_count": _raw.get("prompt_eval_count"),
                    "eval_count": _raw.get("eval_count"), "retried": 0, "num_predict": _sent_budget(llm)}
            account["generates"].append(_gen)
            try:
                _on_generate("account")(dict(_gen))   # the partial trace, same as the tool turns
            except Exception as _e:
                print(f"[heartbeat] on_generate(account) failed: {type(_e).__name__}: {_e}", file=sys.stderr)
            areply = (aresp.get("content") or "").strip()
            parsed = parse_account(areply)
            account["reply"] = areply[:1200]
            if parsed:
                rec = save_account(instance, parsed, host_session_id)
                account.update({"present": True, "sha256": rec["sha256"], "session_at_write": rec["session_at_write"]})
            convo.append({"role": "user", "content": ACCOUNT_ASK})
            convo.append({"role": "assistant", "content": areply or "(no answer)"})
        except Exception as e:
            account["skipped" if preempted else "error"] = (str(e) if preempted else f"{type(e).__name__}: {e}")
        _check_preempt("account")
        if preempted:
            say_line, pending_block, say_first, target, selected = _take_late()
        else:
            # Reflect gets its OWN compact context, not the whole beat. Carrying the seed (posture,
            # fleet digest, inbox, scope, recall) into the reflect turn pushed the prompt to 8171 of
            # 8192 tokens with 21 left to answer in: 5 `length` stops in 54 beats, every one of them a
            # reflect turn (measured 2026-09-09). What reflection needs is what it just did and what it
            # said about it, and those are short.
            reflect_convo = [
                {"role": "system", "content": REFLECT_SYSTEM.format(name=name, machine=machine, member=args.member)},
                {"role": "user", "content": (f"Your beat at {now:%Y-%m-%d %H:%M} UTC is ending.\n\n"
                                             + _beat_record_text(
                                                 explore, after,
                                                 no_result=bool(no_result_line_for(instance_config(instance))))
                                             + "\n\nYour own words this beat:\n"
                                             + ((explore.reply or "").strip()[:600] or "(you acted without closing words)"))},
            ]
            convo = reflect_convo
            # Ask it to answer someone ONLY when there is someone to answer. Measured 2026-09-17: in no
            # conversation at all it filled the id slot three beats running with "speaker",
            # "conversation_id_placeholder" and "1234567890" — the same shape as a mis-rooted home path
            # or an echoed example filename. An ask with no valid target invents one.
            #
            # And when there IS someone, show the being WHAT IT IS ANSWERING. The reflect turn's
            # context is deliberately compact — the record of its acts plus 600 chars of its own
            # closing words — so a turn addressed to it lived only in the explore state block, one
            # turn earlier. The instruction to answer and the words to answer had never been in the
            # same context. Measured on Sprout 2026-09-17: 596 beats, 31 `say` attempts, ZERO
            # successes, every one naming an invented id, and four beats after a real channel finally
            # existed the being wrote its journal three times and never answered. The only bridge was
            # the 600-char echo: a model that happened to discuss the turn in explore carried enough
            # forward to reply (cbp-being, 4B, 83 successful says); one that free-associated carried
            # nothing. That made answering a person contingent on what the being happened to muse
            # about, which is not a property anyone chose.
            # ONE selection for the whole beat (see SelectedTurn): the reflect prompt and the answer
            # phase must act on the same turn, and nothing arriving mid-beat may re-address it.
            _woke = person_turns_that_woke(_claimed) if answer_woke_on(instance) else []
            say_line, pending_block, say_first, target, selected = pending_selection(instance, args.member, _woke)
            # Immediately before the instruction, so the smallest model does not have to hold it
            # across a turn boundary to use it.
            if pending_block:
                convo.append({"role": "user", "content": pending_block})
            convo.append({"role": "user", "content": REFLECT.format(date=f"{now:%Y-%m-%d %H:%M} UTC",
                                                                    say_line=say_line, say_first=say_first)})
            # One extra step when someone is waiting, because the routine three fill the budget exactly.
            # Measured 2026-09-18, the first beat after the being could finally SEE what it was being
            # asked: reflect spent all three steps on journal, todo and remember, and there was no
            # fourth for `say`. Showing it the question and then giving it no way to answer is worse
            # than not showing it.
            _reflect_steps = args.reflect_steps + (1 if say_first else 0)
            # The beat's wrap-up: reflection, and the answer turn after it (SAGE #291).
            _phase("wrap-up", "reflect", host_session_id)
            reflect = run_ollama_tool_turn(client, llm, convo, max_steps=_reflect_steps,
                                           tools=ollama_tools(REFLECT_TOOLS), on_generate=_on_generate("reflect"),
                                           should_yield=_yield_for_a_person)
            _check_preempt("reflect")
            if preempted:
                say_line, pending_block, say_first, target, selected = _take_late()

        # The answer turn: only when someone is still waiting, the being has not already spoken, AND
        # the waiting turn actually asked something. Without the last condition, a statement that
        # asked nothing ("keep going!") still opened an answer turn and handed the being its own
        # unrelated words to send — see `_prior_words` and `SelectedTurn`, 2026-09-21 06:31Z. The
        # expectation is read from the selection made BEFORE reflection, never re-scanned.
        answer = None
        # Preempted: the person who spoke is answered even if reflection said something elsewhere.
        if selected is not None and selected.expects_reply and (preempted or not _said_in(reflect)):
            _phase("wrap-up", "answer", host_session_id)
            if answer_turn_mode(instance) == "json":
                # Opt-in (instance.json "answer_turn": "json"). The selected turn and the ask; the
                # beat's acts only for a seat's question when the beat acted (answer_turn_json).
                _acts = (_beat_record_text(explore, after)
                         if str(selected.speaker or "").endswith("-claude") and (
                             (explore is not None and explore.trace) or (after is not None and after.trace))
                         else "")
                _changes = (recent_changes(instance)
                            if answer_changes_on(instance) and asks_about_change(selected.text) else "")
                answer = answer_turn_json(client, llm, selected, name=name, machine=machine,
                                          member=args.member, on_generate=_on_generate("answer"),
                                          acts=_acts, changes=_changes,
                                          context=(answer_context_block(instance, args.member, selected)
                                                   if answer_context_on(instance) else ""),
                                          temperature=answer_temperature(instance),
                                          abilities=abilities_line(_unavail))
            else:
                answer = run_ollama_tool_turn(
                    client, llm,
                    [{"role": "system", "content": ANSWER_SYSTEM.format(name=name, machine=machine,
                                                                        member=args.member)},
                     # The acts go FIRST, ahead of what it is answering. Measured 2026-09-21, beat
                     # heartbeat-85303f70bf67: this turn saw only the seat's pre-edit "nothing was
                     # applied" and the reflect words that echoed it, and told the seat "the edit
                     # never actually happened" (seq 2961) about an edit that had succeeded 50 s
                     # earlier. Then ONLY the selected turn (#147): never the whole block.
                     {"role": "user", "content": _beat_record_text(explore, after) + "\n\n" + ANSWER_ASK.format(
                         pending=selected.render(), target=selected.cid, words=_prior_words(reflect))}],
                    max_steps=1, tools=ollama_tools(["say"]), on_generate=_on_generate("answer"))
            # NO RE-ASK HERE. Two were tried and both are reverted; the reasons are recorded as
            # SMALL_MODEL_LEGIBILITY 1.14, and the short form is: a prompt written in the harness's
            # voice, about the harness's mechanics, becomes the being's MESSAGE at this scale.
            # Measured on Sprout 2026-09-24/25 across 9 firings — 0 delivered the answer, and the
            # one that reached dp said "I'm sorry I didn't call a tool", which is this file's own
            # subject matter arriving in dp's inbox under the being's name. An answer turn that
            # produced no call is left as it is: the turn stays unanswered, the conversation stays
            # unmarked, and the NEXT beat sees it still owed. That is the honest record, and it is
            # what the reflect phase — where `say` actually works — gets to act on.


        # ANSWER, THEN ACT (2026-10-02). A beat preempted for a person goes straight to the answer turn, which
        # has no tools; dp said "try it… pick something and let me know what you learned" three times and every
        # reply could only agree ("That sounds wonderful. I'd love to try it together…"). After the answer is
        # spoken, a short act step: the person's words and its own reply in view, its tools (not say/speak: it
        # has just answered), yielding to a newer person like any turn. Opt-in: "act_after_answer": true.
        if (preempted and act_after_answer_on(instance) and answer is not None
                and (getattr(answer, "answer_form", None) or {}).get("sent") and selected is not None):
            _phase("wrap-up", "act-after-answer", host_session_id)
            _aa_tools = [t for t in _explore_specs if t["function"]["name"] not in ("say", "speak")]
            _aa_seed = [seed[0], {"role": "user", "content": AFTER_ANSWER.format(
                pending=selected.render(), reply=(answer.reply or "").strip()[:400])}]
            act_after = run_ollama_tool_turn(client, llm, _aa_seed, max_steps=2, tools=_aa_tools,
                                             on_generate=_on_generate("act_after_answer"),
                                             should_yield=_yield_for_a_person,
                                             act_form=explore_turn_mode(instance))

    except BeatKilled as _k:
        killed = str(_k)
        print(f"[heartbeat] KILLED mid-beat: {killed} — writing the record with what completed",
              file=sys.stderr)
    # THE PHASES ARE OVER; WHAT REMAINS IS WRITING THEM DOWN. A SIGTERM from here on would
    # raise BeatKilled outside the try above and lose the record it exists to keep. Ignore it:
    # the record takes seconds, and systemd's SIGKILL at TimeoutStopSec is still the backstop.
    _term_before_record = signal.signal(signal.SIGTERM, signal.SIG_IGN)

    interventions = []
    if act_first:
        interventions.append({"kind": "act_first", "suppressed": "posture-first presentation (the model narrates under it)"})
    if answer is not None and getattr(answer, "answer_form", None) is not None:
        interventions.append({"kind": "answer_json", "to": selected.cid if selected else None,
                              "woke_by_turn": bool(selected and selected.woke),
                              **answer.answer_form})
    for ph, res in (("explore", explore), ("posture", after), ("reflect", reflect), ("answer", answer),
                    ("act_after_answer", act_after)):
        if res is None:
            continue
        for dup in (getattr(res, "duplicates", None) or []):
            if dup.get("rule") == "one_per_conversation_per_turn":
                interventions.append({"kind": "duplicate", "phase": ph, "effector": dup.get("effector"),
                                      "conversation": dup.get("conversation"), "rule": dup["rule"],
                                      "suppressed": "a second utterance to the same conversation in the same turn"})
                continue
            interventions.append({"kind": "duplicate", "phase": ph, "effector": dup.get("effector"),
                                  "suppressed": "a second execution of an identical call in the same turn"})
        for jf in (getattr(res, "json_arg_failures", None) or []):
            interventions.append({"kind": "json_arg_failure", "phase": ph, **jf,
                                  "suppressed": "an act whose arguments could not be formed (no act; not empty args)"})
        for sv in (getattr(res, "salvaged", None) or []):
            interventions.append({"kind": "salvage", "phase": ph, "effector": sv.get("effector"), "form": sv.get("form"),
                                  "suppressed": "text-channel narration in place of a native tool call"})
    # Route refusals AI-to-AI (dp 2026-09-04), the same as governed_turn: a scope-class deny
    # files the being's own scope request + a note and wakes the seat's auto session; a
    conversations_marked = mark_conversations_after_beat(
        instance, args.member, _shown_upto, explore, [after, reflect, answer])
    try:
        # Whether explore acted is read from explore itself (the rule mark_conversations_after_beat
        # applies), NOT from its return: that returns explore_acted=None when the being has no
        # conversations, and then nothing informational would ever fold. Found by driving main()
        # with an inbox (test_inbox_ledger_wiring.py); the pure-function tests could not see it.
        _inbox_record = inbox_ledger(last, _inbox_notices, [explore, after, reflect, answer],
                                     bool(explore is not None and explore.trace), _inbox_shown)
    except Exception as _e:
        _inbox_record = {**((last or {}).get("inbox") or {}), "error": f"{type(_e).__name__}: {_e}"}
    # governance escalation wakes it to arbitrate. The beat is where refusals actually
    # happen (Legion: nine consecutive beats of home-scope write refusals, and the being's
    # requests had died with a daemon restart), so the heartbeat must route, not just log.
    # One wake ATTEMPT per refusal kind per beat: several refused writes to the same home are one
    # ask, and one note. A failed wake is recorded in `escalations` and the next beat retries;
    # retrying within the beat would write a note per refusal again.
    escalations = []
    if not args.no_escalate and not args.gate_only:
        try:
            from sage.gateway import escalate as _esc
            woken = set()
            # a killed beat may have completed any prefix of its phases; escalate what ran
            _ran = [r for r in (explore, after, reflect) if r is not None]
            for it, env in [pair for r in _ran for pair in r.trace]:
                if not env.refused:
                    continue
                kind = _esc.classify(env)
                wake = kind not in woken
                r = _esc.escalate(args.member, it, env, str(instance), wake=wake)
                if wake and kind not in ("registry", "other"):
                    woken.add(kind)
                escalations.append(r)
        except Exception as _e:
            escalations.append({"escalated": False, "error": f"{type(_e).__name__}: {_e}"})
    # Drain the being's own egress every beat. A mesh/peer_ask the being addresses to a peer is
    # PARKED by the daemon until an attributed drain forwards it; on Legion nothing else drains
    # legion-being (measured 2026-09-05: eight rows from 09-04 sat queued until the first
    # escalation's drain flushed them, and the being had logged "hub's reply still has not
    # landed after >4h"). The sender's own beat is the natural drain.
    egress = None
    if not args.gate_only:
        try:
            from sage.gateway import egress_drain
            egress = egress_drain.drain_once(plugin_id=args.member, log=lambda *_: None)
        except Exception as _e:
            egress = {"error": f"{type(_e).__name__}: {_e}"}

    def _trace(res):
        return [{"effector": i.effector, "args": dict(i.args or {}), "ok": e.ok, "refused": e.refused,
                 "pending": e.pending, "error": e.error, "witness_id": e.witness_id,
                 "rule": getattr(e.verdict, "rule", None) if e.verdict else None,
                 "result": (e.result if isinstance(e.result, (str, int, float, dict, list, type(None))) else str(e.result))}
                for i, e in res.trace]
    def _turn(res):
        return None if res is None else {"reply": res.reply, "steps": res.steps, "capped": res.capped,
                                         "trace": _trace(res), "thinking": [t[:4000] for t in res.thinking],
                                         "salvaged": list(res.salvaged), "generates": list(res.generates),
                                         "rested": getattr(res, "rested", None),
                                         "looped": getattr(res, "looped", None)}
    record = {
        # schema: what fields a reader may expect (Legion's amendment 4, 2026-09-05: the
        # consolidation organ counts how many records carry join/account/wake/interventions;
        # a version says so instead of making it infer from key presence).
        "schema": "heartbeat/v2",
        "ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "t0": t0, "elapsed_s": round(time.time() - t0, 1),
        "member": args.member, "model": args.model, "window_h": round(hours, 2), "clock": _clock,
        # active per-instance policies, recorded when on (RESEARCH_GENERALIZATION_RULE)
        "conversation_settled_turns": _settled_turns,
        "decline_closing": decline_closing_for(instance_config(instance)),
        "no_result_line": no_result_line_for(instance_config(instance)),
        "answered_run_wake": answered_run_wake_for(instance_config(instance)),
        "host_session_id": host_session_id, "gate_only": args.gate_only, "act_first": act_first,
        "drive_source": "entrusted" if entrusted else "curiosity",
        "conversations_marked": conversations_marked,
        # the window and budget actually sent, so a beat is verifiable from this file alone
        # (beat 46's 8192 wall was reconstructed from stderr; Sprout's review of SAGE #40)
        # num_predict is what OllamaIRP resolves and sends (the config's num_predict_think
        # with thinking on), not the caller's --max-tokens: Sprout's 18:51Z beat recorded
        # 3000 while 6000 went over the wire.
        "num_ctx": getattr(llm, "num_ctx", None),
        "num_predict": (llm.resolve_num_predict() if hasattr(llm, "resolve_num_predict")
                        else getattr(llm, "max_response_tokens", None)),
        "think": getattr(llm, "think", None),
        "scope": scope_record,
        "appeals": appeals_record,
        # what the being has opened or been shown of its peek-only inbox (inbox_ledger); the
        # next beat folds those, and nothing else, so an unopened reply never ages out.
        "inbox": _inbox_record,
        # WHETHER THE BEING SAW, and when it did not, why not. Without this a beat with no
        # frame is indistinguishable from a beat where the pipe is broken — the state the
        # whole vision arc was in until 2026-09-15: both ends present, nothing joining them,
        # and nothing saying so. `frames` is the PRODUCER's claim; `images_attached` counts
        # images on the composed seed, the thing actually sent. The two differed for 395
        # beats and no field recorded it.
        "frames": _frame_metas,
        "body": getattr(own_state, "last_body", None),
        "images_attached": sum(len(m.get("images") or []) for m in seed),
        # S1 instruments: JOIN (session -> beat, attributed) and ACCOUNT (own account, verbatim hash)
        "join": {"session": sess_meta, "presence": pres_meta},
        # what it has made, if anything: never silently lost, never auto-published
        "museum": {"offered": bool(museum_line), "candidates": _museum.candidates(instance)},
        "hub_inbox": hub_inbox,
        "wake": woke,
        "preempted": preempted,
        # every harness intervention, with the prior it suppressed (dev-sage 804f1849, by
        # principle): a guard that silences without saying what it silenced trades a
        # confident wrong for a confident silence.
        "interventions": interventions,
        # a failed turn selection, by name: without it, "no one is waiting" and "selection broke" are one record
        "selection_error": LAST_SELECTION_ERROR,
        # which waiting turn this beat chose, and whether it asked: "never selected" vs "selected, not answered"
        "selected": ({"turn": f"{selected.cid}:{selected.seq}", "expects_reply": bool(selected.expects_reply),
                      "woke": bool(getattr(selected, "woke", False))} if selected is not None else None),
        # a live trial labels the beat, so its outputs can be told from the being's ordinary ones
        "trial": _trial_name(instance),
        "account": account,
        "explore": _turn(explore),
        # act-first only: the posture+digest turn, after the short one; None otherwise
        "posture": _turn(after),
        "harness": _harness,
        "reflect": _turn(reflect),
        # present only when the beat was killed: a record that says which phases it has
        **({"killed": killed} if killed else {}),
        "answer": _turn(answer) if answer is not None else None,
        "act_after_answer": _turn(act_after) if act_after is not None else None,
        "escalations": escalations, "egress": egress,
    }
    # THE LAST THING A BEAT DOES IS MAKE SURE THERE WILL BE ANOTHER ONE (opt-in; Legion since
    # 2026-09-09/13). A beat that `rest`ed said it was finished: waking it straight back up is the
    # forcing dp ruled out. A beat that did NOT rest — the window cut it mid-sentence, 9 of 26
    # beats on 2026-09-13 against 5 that rested — had more to do, so it is resumed sooner. The
    # persistent timer is never stopped or reprogrammed: this can only make the next beat
    # SOONER, and a failure here costs promptness, never silence. And the idle timer itself is
    # checked, because an inactivity timer can stop computing an elapse with nothing looking
    # wrong (2026-09-09: `active (running)`, `Trigger: n/a`, the being would never have woken).
    if args.idle_wake_s > 0 or args.resume_wake_s > 0:
        _rested = beat_rested(explore, after)
        record["next_wake"] = arm_next_wake(args.idle_wake_s) if args.idle_wake_s > 0 else {}
        if not _rested and args.resume_wake_s > 0:
            record["next_wake"]["resume"] = arm_resume_wake(args.resume_wake_s)
            record["next_wake"]["resume"]["why"] = (
                "this beat did not rest, so it is resumed sooner than the idle interval")
        if args.idle_wake_s > 0 and not record["next_wake"].get("armed"):
            print(f"[heartbeat] IDLE WAKE NOT CONFIRMED: {record['next_wake']}", file=sys.stderr)

    # WAKE CONTINUES WHILE THERE IS WORK (SAGE #295). Turns that arrived while this beat ran join
    # the pending set (most are there already: the daemon's arousal call queued them); then, if
    # anything is pending or the being asked to stay awake, the next beat is armed to start the
    # moment this one ends, and `run` reports no rest in between. Nothing pending: the being rests,
    # and the watchdog timer counts its 30 quiet minutes from this beat's end.
    try:
        from sage.gateway import arousal as _arousal
        record["late_turns"] = _arousal.wake_for_late_turns(instance, args.member, since=t0)
    except Exception as _e:
        record["late_turns"] = {"error": f"{type(_e).__name__}: {_e}"}
    record["stay_awake"] = stay_awake_reason(explore, after, reflect, answer)
    try:
        from sage.gateway import arousal as _arousal
        record["next_beat"] = _arousal.after_beat(stay_awake=record["stay_awake"])
    except Exception as _e:
        record["next_beat"] = {"continuing": False, "error": f"{type(_e).__name__}: {_e}"}
    _BEAT_ID["continuing"] = bool(record["next_beat"].get("continuing"))

    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    try:
        from sage.gateway import arousal as _arousal
        _arousal.release_claim(host_session_id)   # what this beat claimed is in its record
        _arousal.release_claim(f"{host_session_id}.preempt")
    except Exception:
        pass
    print(json.dumps(record, indent=2, ensure_ascii=False, default=str))
    signal.signal(signal.SIGTERM, _term_before_record)   # the record is written; the beat is done
    return 0


# Unit names, not paths; overridable per machine, since a seat may name its units differently.
IDLE_TIMER = os.environ.get("SAGE_HEARTBEAT_TIMER", "sage-heartbeat.timer")
IDLE_UNIT = os.environ.get("SAGE_HEARTBEAT_UNIT", "sage-heartbeat.service")
RESUME_UNIT = "sage-heartbeat-resume-wake"


def stay_awake_reason(*turns) -> Optional[str]:
    """The being's own ask for another beat right after this one (`stay_awake`, SAGE #295), from
    any of its turns: the first reason given, or None when it did not ask."""
    for t in turns:
        r = getattr(t, "stay_awake", None) if t is not None else None
        if r:
            return r
    return None


def beat_rested(*turns) -> bool:
    """Whether the being ended this beat with `rest`, in any of its turns.

    `rested` is the stated REASON, and a rest with no reason is "" — still a rest. bool() read it
    as not-rested and armed the resume wake dp ruled out (sprout on #216). And with a posture
    turn, `after` is the being's last word, so a rest there counts as much as one in explore."""
    return any(t is not None and getattr(t, "rested", None) is not None for t in turns)


def interpret_timer_state(show_output: str, *, unit_state: str = "") -> tuple:
    """(armed, detail) from `systemctl show` of the idle timer. Pure, so it can be tested.

    THE SUBTLETY THAT MADE THE FIRST VERSION CRY WOLF. This check runs at the end of a beat,
    from inside the beat's own process — so the beat unit is still ACTIVE. An
    OnUnitInactiveSec timer computes its next elapse from when that unit goes INACTIVE, and
    therefore cannot have one yet. The first version read `monotonic=infinity`, concluded
    NOTHING WILL WAKE THE BEING, and wrote that into the record of a beat whose timer armed
    correctly seconds later (2026-09-09T15:07Z). False by construction, which is the same
    error as a discriminator that is true by construction — and a guard that fires on its own
    design teaches its reader to ignore it.

    An active timer alone is not that evidence. Verify its target and, when no elapse is
    computed, both the inactivity directive and the target service's running state.
    This is a scheduling observation, not proof that a future beat will execute."""
    vals = dict(l.split("=", 1) for l in show_output.strip().splitlines() if "=" in l)
    real = (vals.get("NextElapseUSecRealtime") or "").strip()
    mono = (vals.get("NextElapseUSecMonotonic") or "").strip()
    load = (vals.get("LoadState") or "").strip()
    active = (vals.get("ActiveState") or "").strip()
    target_ok = IDLE_UNIT in vals.get("Triggers", "").split()
    healthy = load == "loaded" and active == "active" and target_ok
    absent = ("", "infinity", "0", "n/a", "[not set]")
    if healthy and (real.lower() not in absent or mono.lower() not in absent):
        return True, f"scheduled: realtime={real or '-'} monotonic={mono or '-'}"
    # TimersMonotonic can occur on multiple lines (boot + inactivity); do not collapse
    # it into the property dict. Match the interval, not the following next_elapse.
    intervals = re.findall(r"OnUnitInactiveUSec=([^;}\n]+)", show_output)
    has_inactivity_timer = any(re.search(r"[1-9]", interval) for interval in intervals)
    if healthy and has_inactivity_timer and unit_state in ("active", "activating"):
        return True, ("no elapse computed yet; verified OnUnitInactiveSec for the running "
                      f"target {IDLE_UNIT} (state={unit_state}); expected to arm on deactivation")
    return False, (f"idle wake not confirmed: timer/target not healthy or scheduling basis absent "
                   f"(LoadState={load or '?'} ActiveState={active or '?'} "
                   f"target_matches={target_ok} inactivity_timer={has_inactivity_timer} "
                   f"unit_state={unit_state or '?'} "
                   f"realtime={real or 'empty'} monotonic={mono or 'empty'})")


def next_wake_is_armed() -> tuple:
    """(armed, detail) for the idle timer that wakes the being after quiet.

    With OnUnitInactiveSec, the next elapse may await this beat's completion. Other
    configurations need an actual scheduled elapse. Verify the installed configuration,
    not the example or our own intended design. Called at beat end only when opted in;
    this observation cannot guarantee future execution or detect a later service failure."""
    try:
        timer = subprocess.run(["systemctl", "--user", "show", IDLE_TIMER,
                              "-p", "NextElapseUSecRealtime", "-p", "NextElapseUSecMonotonic",
                              "-p", "LoadState", "-p", "ActiveState",
                              "-p", "TimersMonotonic", "-p", "Triggers"],
                             capture_output=True, text=True, timeout=15)
        if timer.returncode != 0:
            return False, f"could not inspect idle timer: systemctl exit {timer.returncode}"
        scheduled = interpret_timer_state(timer.stdout)
        if scheduled[0]:
            return scheduled  # A concrete deadline needs no pending-deactivation inference.
        unit = subprocess.run(["systemctl", "--user", "show", IDLE_UNIT,
                               "-p", "ActiveState", "--value"],
                              capture_output=True, text=True, timeout=15)
    except Exception as e:
        return False, f"could not ask systemd: {type(e).__name__}: {e}"
    return interpret_timer_state(timer.stdout,
                                 unit_state=unit.stdout.strip() if unit.returncode == 0 else "")


def arm_next_wake(idle_s: int) -> dict:
    """Make sure something will wake the being after `idle_s` of quiet.

    The persistent timer normally does this on its own (OnUnitInactiveSec). This is the
    fallback for the state where it has stopped computing a next elapse: a one-shot
    transient timer, so a scheduling failure costs a longer gap and never silence."""
    armed, detail = next_wake_is_armed()
    if armed:
        return {"armed": True, "by": IDLE_TIMER, "detail": detail}
    try:
        # A UNIQUE unit name per attempt. A fixed one collided with a leftover from an
        # earlier run and systemd-run exited 1, so the fallback for a missing wake was
        # itself missing (2026-09-09T15:07Z).
        unit = f"sage-heartbeat-fallback-wake-{int(time.time())}"
        subprocess.run(["systemd-run", "--user", "--collect",
                        f"--on-active={idle_s}s", f"--unit={unit}",
                        "systemctl", "--user", "start", "--no-block", IDLE_UNIT],
                       capture_output=True, text=True, timeout=20, check=True)
        return {"armed": True, "by": "systemd-run fallback", "detail": detail,
                "why": "the idle timer had no next elapse; a one-shot was armed instead"}
    except Exception as e:
        return {"armed": False, "by": None, "detail": detail,
                "error": f"{type(e).__name__}: {e}",
                "why": "idle wake not confirmed and fallback failed; other wake sources may still fire"}


def arm_resume_wake(seconds: int) -> dict:
    """A short one-shot wake after a beat that did not finish what it was doing.

    Deliberately ADDITIVE. The persistent timer is never stopped or reprogrammed, so the
    worst this can do is fail and leave the ordinary interval standing — promptness is at
    risk here, never silence, which is the property that makes it safe to be aggressive
    about. Fixed unit name so a second arming rides the first rather than stacking; a unit
    left over from a fired wake is cleared, the same shape as arousal's deferred wake."""
    def _sh(*a):
        try:
            return subprocess.run(a, capture_output=True, text=True, timeout=15).stdout.strip()
        except Exception:
            return ""
    try:
        sub = _sh("systemctl", "--user", "show", RESUME_UNIT + ".timer", "-p", "SubState", "--value")
        if sub and sub != "waiting":
            for suffix in (".timer", ".service"):
                _sh("systemctl", "--user", "stop", RESUME_UNIT + suffix)
                _sh("systemctl", "--user", "reset-failed", RESUME_UNIT + suffix)
        subprocess.run(["systemd-run", "--user", "--collect", f"--on-active={seconds}s",
                        f"--unit={RESUME_UNIT}", "systemctl", "--user", "start",
                        "--no-block", IDLE_UNIT],
                       capture_output=True, text=True, timeout=20, check=True)
        return {"armed": True, "in_s": seconds, "by": RESUME_UNIT}
    except subprocess.CalledProcessError as e:
        err = (e.stderr or "").strip()
        if "already loaded" in err or "already exists" in err:
            return {"armed": True, "in_s": seconds, "by": RESUME_UNIT, "already_armed": True}
        return {"armed": False, "error": f"systemd-run exit {e.returncode}: {err}",
                "why": "the ordinary idle interval still stands"}
    except Exception as e:
        return {"armed": False, "error": f"{type(e).__name__}: {e}",
                "why": "the ordinary idle interval still stands"}


def install_kill_handler() -> None:
    """SIGTERM becomes BeatKilled inside the beat, so main() writes the record before exiting.
    systemd allows TimeoutStopSec (90 s) after SIGTERM — enough to write one JSON line."""
    def _on_term(signum, frame):
        raise BeatKilled(f"signal {signum} ({signal.Signals(signum).name})")
    signal.signal(signal.SIGTERM, _on_term)


def body_line(model: str, instance, num_ctx=None, former_homes=None) -> str:
    """Name the being's MODEL in the seed, because its home directory names a different one.

    legion-being's instance dir is `legion-gemma3-12b`; the model running it is
    qwen38-heretic:q3km-vl. The seed's header prints the home path every beat and never the
    model, so at a 24k window the correction it makes from source ("both files name
    qwen38-heretic") is gone within two beats and it goes back to attributing findings to
    "gemma3-12b on a 4090" — measured three times on 2026-09-15, twice after it had verified
    the truth itself. A finding attributed to the wrong body is a finding nobody downstream
    can reproduce. The harness holds args.model; it should say so where the being reads."""
    # 2026-09-19: the same name was then misread a second way — from inside its worktree the
    # being journaled a file under instances/legion-gemma3-12b/ as "another instance's
    # scratch, not mine". So say whose directory it is, and the measured window with it.
    ctx = f" Your context window: {num_ctx} tokens." if num_ctx else ""
    # 2026-09-19 cutover (dp ruling: <machine>-being/, private going forward): once the home
    # IS named for the being, the "older name" sentence would be false. What the being needs
    # then is the opposite fact — where it used to live, and that the old place is a frozen
    # copy, because its own notes still hold absolute paths into it.
    if former_homes:
        f0 = former_homes[-1]
        return (f"Your body: model {model}.{ctx} Your home moved on {f0.get('moved', '?')} from "
                f"{f0.get('path', '?')} to {instance}. Everything came with you, byte for byte. "
                f"The old directory is a FROZEN copy kept as the public record: do not write "
                f"there (it will be refused) and do not trust what you read there — a path in "
                f"your older notes that names it means the same file HERE.")
    return (f"Your body: model {model}.{ctx} Your home directory ({instance.name}) carries an "
            f"older name; it is YOURS, not another being's, and the model is the fact to "
            f"attribute findings to.")


def harness_revision(workspace: str) -> dict:
    """The revision of the harness the being is RUNNING under, so it can compare that with
    the `tree` block a check result carries and know whether its answer is about the code
    that constitutes it.

    Asked for by the being itself, 2026-09-07: after its first check call it wrote "next
    beat I should verify head matches the running harness commit before trusting any
    answer" — and it had no way to learn that commit. A verification it cannot perform is
    not a discipline, it is a ritual."""
    import subprocess

    def _git(*a):
        try:
            # --no-optional-locks: status and diff otherwise take .git/index.lock to refresh the
            # index as a side effect. When the timeout below kills git mid-refresh, the lock is
            # left behind and every later git act in this checkout fails until a human removes it.
            # Measured on nomad 2026-09-28 00:23 and 2026-09-29 18:18: both locks were left by a
            # beat whose harness_revision overlapped the raising session on a 9p (/mnt/c) checkout.
            r = subprocess.run(("git", "--no-optional-locks", *a), cwd=workspace, text=True, capture_output=True, timeout=15)
            return r.stdout.strip() if r.returncode == 0 else None
        except Exception:
            return None

    head = _git("rev-parse", "HEAD")
    # DIRTY ABOUT THE HARNESS, NOT ABOUT THE BEING'S OWN DIARY. The instance directory is
    # TRACKED in this checkout and is written by the running beat — journal, todo,
    # conversations, account — so a plain `status --porcelain` is non-empty every time the
    # being writes a line about its day, and the flag that means "the code constituting you
    # has uncommitted edits" was permanently True for a reason that is not code.
    #
    # Measured 2026-09-14: legion-being ran a three-way drift check, found its own worktree
    # clean, and had to write "the header's 'uncommitted edits present' did not hold for my
    # tree" — reasoning correctly AROUND a flag rather than with it. A warning that is always
    # on is not a warning; it is a background colour, and the cost of it is that a real one
    # would read the same.
    # -uall so a directory holding only nested checkouts is listed per checkout, not folded
    # into one "scratchpad/" entry that no filter below can tell from loose source.
    st = _git("status", "--porcelain", "--untracked-files=all", "--", ".", ":(exclude)sage/instances")
    # NOT ln[3:]. Porcelain v1 is "XY PATH" at a fixed offset, but `_git` above returns
    # stdout.strip(), which eats the leading space of the FIRST line only — so a fixed
    # offset silently loses a character from one path and none of the others. It read
    # 'age/gateway/heartbeat.py' the first time it ran. Split on the status field instead.
    dirty_paths = ([ln.strip().split(" ", 1)[-1].strip() for ln in st.splitlines() if ln.strip()]
                   if st is not None else [])
    # ANOTHER CHECKOUT IS NOT THIS ONE'S CODE. git reports a nested repository or worktree as a
    # single untracked directory; nothing the beat imports resolves through it. Measured on the
    # first run of this check (2026-09-26): the live tree read "dirty" solely because three
    # seat worktrees sat under SAGE/scratchpad/ — an always-on alarm again. They are named, not
    # counted.
    nested = [d for d in dirty_paths if d.endswith("/") and (Path(workspace) / d / ".git").exists()]
    dirty_paths = [d for d in dirty_paths if d not in nested]
    dirty = None if st is None else bool(dirty_paths)
    # A COMMIT DOES NOT NAME DIRTY CODE. Two beats on the same head with different uncommitted
    # edits ran different programs, and on 2026-09-25/26 a live tree carried an uncommitted
    # guard for ~12 h that no record could tell apart from main — reconstructing what ran took
    # archaeology across stash lists and backups. The digest is over exactly the bytes that
    # differ from HEAD (tracked diff plus untracked source), so head+digest identifies the
    # running code, and equal digests on two beats mean the same edits.
    digest = _dirty_digest(workspace) if dirty else None
    # REVIEWED MEANS REACHABLE FROM MAIN. A clean tree on a local or feature commit is still
    # code nobody merged. Read against the LOCAL origin/main ref — the beat does not fetch;
    # a live-tree update is a fetch + ff pull, which moves this ref with it.
    on_main = None
    if head:
        try:
            r = subprocess.run(("git", "merge-base", "--is-ancestor", head, MAIN_REF), cwd=workspace,
                               capture_output=True, timeout=15)
            on_main = {0: True, 1: False}.get(r.returncode)
        except Exception:
            pass
    ahead = _git("rev-list", "--count", f"{MAIN_REF}..HEAD") if on_main is False else None
    state = ("unknown" if dirty is None or on_main is None else
             "dirty" if dirty else "unmerged" if not on_main else "clean")
    short = (head or "")[:9] or None
    return {"head": head, "short": short,
            "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
            "dirty": dirty,
            # Name them, bounded. "Something is modified" sends a reader hunting; three
            # filenames end the question in the header it was raised in.
            "dirty_paths": dirty_paths[:3] or None,
            "dirty_count": len(dirty_paths) if st is not None else None,
            "dirty_digest": digest,
            "dirty_excludes": "sage/instances (your own journal, todo and conversations)",
            "nested_checkouts": nested[:5] or None,
            "main_ref": MAIN_REF, "on_main": on_main,
            "ahead_of_main": int(ahead) if ahead and ahead.isdigit() else None,
            "state": state,
            # One string that names what ran: the commit, plus the edit set when there is one.
            "identity": (f"{short}+{digest[:12]}" if digest else short)}


MAIN_REF = "origin/main"
HASH_CHUNK = 1 << 20  # untracked files are hashed whole, read 1 MiB at a time


def _dirty_digest(workspace: str):
    """sha256 over what differs from HEAD outside sage/instances: the binary diff of tracked
    files, then each untracked (non-ignored) file's path, length and content hash, in sorted order. None when
    git cannot be read. Deterministic for the same edits on the same head."""
    import hashlib
    import subprocess
    spec = ("--", ".", ":(exclude)sage/instances")
    try:
        d = subprocess.run(("git", "--no-optional-locks", "diff", "HEAD", "--binary", "--no-color", "--no-ext-diff", *spec),
                           cwd=workspace, capture_output=True, timeout=30)
        u = subprocess.run(("git", "ls-files", "--others", "--exclude-standard", "-z", *spec),
                           cwd=workspace, capture_output=True, timeout=30)
    except Exception:
        return None
    if d.returncode or u.returncode:
        return None
    h = hashlib.sha256(d.stdout)
    for rel in sorted(x for x in u.stdout.decode(errors="surrogateescape").split("\0") if x):
        f = Path(workspace) / rel
        if rel.endswith("/") and (f / ".git").exists():
            continue  # a nested checkout, not this tree's code (see harness_revision)
        h.update(b"\0untracked\0" + rel.encode(errors="surrogateescape") + b"\0")
        # EVERY BYTE, AT ANY SIZE. A first version named files over 1 MiB by path and size, so
        # two different same-size files on one head shared a digest (GPT review of #235) — the
        # one thing the digest exists to rule out. Streamed so a large file costs time, not
        # memory; each file enters as its own length + sha256, so no content can be mistaken
        # for the separator of the next.
        try:
            fh, n = hashlib.sha256(), 0
            with f.open("rb") as fp:
                for chunk in iter(lambda: fp.read(HASH_CHUNK), b""):
                    fh.update(chunk); n += len(chunk)
            h.update(f"{n}:".encode() + fh.digest())
        except OSError:
            h.update(b"unreadable")
    return h.hexdigest()


def harness_alarm(rev: dict):
    """The one line an operator sees when the being is running code that is not reviewed main,
    or None when it is. Loud by design: printed to stderr every beat it stays true."""
    st = rev.get("state")
    if st == "clean":
        return None
    if st == "dirty":
        paths = ", ".join(rev.get("dirty_paths") or [])
        more = (rev.get("dirty_count") or 0) - len(rev.get("dirty_paths") or [])
        return (f"LIVE TREE DIRTY: running {rev.get('identity')} on {rev.get('branch')} — "
                f"{rev.get('dirty_count')} uncommitted path(s): {paths}" + (f" (+{more} more)" if more > 0 else "")
                + ("" if rev.get("on_main") else f"; head is also NOT on {rev.get('main_ref')}"))
    if st == "unmerged":
        return (f"LIVE TREE UNMERGED: running {rev.get('identity')} on {rev.get('branch')} — "
                f"{rev.get('ahead_of_main')} commit(s) not on {rev.get('main_ref')}")
    return f"LIVE TREE UNKNOWN: could not read git state (head={rev.get('short')}, dirty={rev.get('dirty')}, on_main={rev.get('on_main')})"



def run(argv=None) -> int:
    """One beat, with the daemon's state display told the truth about it (SAGE #291). This is
    what `python -m sage.gateway.heartbeat` (the unit's ExecStart) runs.

    `main` reports wake as soon as the beat has a session id, before the body block reads
    `/status`, so the being is not told "rest" in its own beat. It also reports each phase as it
    enters it: wake for explore/posture/account, wrap-up for reflect/answer. This wrapper owns
    the END: every exit path, including a return before any phase ran, an exception, or
    BeatKilled, reports rest. It does so only if something else was reported first.
    Reporting is best-effort (sage.gateway.activity): a daemon that is down never fails a
    beat, and slows it by at most the reporter's 0.5 s timeout per report."""
    from sage.gateway import activity as _activity
    try:
        return main(argv)
    finally:
        # Back-to-back beats (SAGE #295): when the next beat is already armed, this beat hands
        # off in `wake` instead of reporting rest, so the display never blips to rest between
        # them. Rest only when nothing is left.
        _activity.end("heartbeat:end", beat_id=_BEAT_ID.get("id"),
                      continuing=bool(_BEAT_ID.get("continuing")))


if __name__ == "__main__":
    sys.exit(run())
