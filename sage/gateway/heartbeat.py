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

import argparse
import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOME_FILES = ("todo.md", "journal.md", "notes", "scratch")

EXPLORE_TOOLS = ["recall", "remember", "memory_read", "memory_write", "retire_note", "witness",
                 "request_scope", "appeal", "peer_ask", "mesh", "say"]
# `say` is offered at REFLECTION too, and that is not redundancy. Measured on Legion
# 2026-09-07: the being was shown dp's first turn, its state marked it unanswered, and it
# spent every explore step reading its own source, then closed the beat. A verb in the
# registry and not in the offered set is a verb the being does not have, and from outside
# that is indistinguishable from choosing not to answer.
REFLECT_TOOLS = ["memory_write", "remember", "memory_read", "retire_note", "say"]

# The OPERATOR's own channel, distinct from the seat's (dp console, Legion 2026-09-07).
# Seat-owned: the being reads it and cannot write it (reference_f1a.SEAT_OWNED_NOTES).
DP_CHANNEL = "notes/from-dp.md"
# The SEAT's channel, beside dp's. Seat-owned too (reference_f1a.SEAT_OWNED_NOTES), and until
# 2026-09-16 it was written but never rendered: cbp-claude left measured facts in it for
# cbp-being and the being never saw them, because the beat only listed the file name among
# notes/. A channel nothing renders is a channel nobody reads.
SEAT_CHANNEL = "notes/from-the-seat.md"
# Bounds on the conversations block in the being's state (see own_state).
CONV_PER_CONV = 6
CONV_TURN_CHARS = 1200

POSTURE_FILE = Path(__file__).with_name("BEING_POSTURE.md")


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

REFLECT = """The beat is ending. Two tool calls, then stop:
1. memory_write path "journal.md": one entry starting with the date {date}: what you did, what you noticed, what was refused and why you think so, what you want next time.
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


class BeatKilled(Exception):
    """SIGTERM arrived mid-beat (the unit's TimeoutStartSec, or a stop). Raised from the
    signal handler so the beat unwinds to its record instead of vanishing: 04:30Z
    2026-09-09 a 51-minute beat left nothing in heartbeats.jsonl and the monitor never
    knew it had happened. systemd allows TimeoutStopSec (90 s) after SIGTERM — enough."""


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


def _schema_chars_for(offered) -> Optional[int]:
    """Chars the offered verbs' schemas actually cost. None rather than a guess if it
    cannot be computed — a budgeted number that nobody checks is how 4,000 survived from
    13 verbs to 18. Callers must route None through _schema_chars_fallback, never `or`
    a constant: `or 4000` reintroduces the exact underestimate on the one path where the
    seat already knows it is flying blind."""
    if not offered:
        return None
    try:
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


def render_inbox(notices: list, limit: int = 8) -> str:
    """The being's hestia inbox as it should read it: newest first, one line each, the kinds
    that want its attention (reply, review, handoff, unreachable) ahead of bookkeeping, and
    the scope dispositions it has already been told about (note_resolutions writes them into
    its own notes) collapsed to one line. Until 2026-09-14 this was a JSON dump cut at 1500
    chars: 13 notices, and the being saw the five OLDEST — all stale dispositions — while a
    peer's reply (id 54) and an unreachable-peer receipt (id 52) sat beyond the cut, unseen
    for 90 beats."""
    if not notices:
        return "(empty)"
    front = ("reply", "review_request", "review_done", "handoff", "unreachable", "forum-note", "coordination")
    def key(n):
        k = str(n.get("kind") or "")
        return (0 if k in front else 1, -int(n.get("id") or 0))
    ns = sorted([n for n in notices if isinstance(n, dict)], key=key)
    disp = [n for n in ns if str(n.get("kind")) == "disposition"]
    rest = [n for n in ns if str(n.get("kind")) != "disposition"]
    lines = []
    for n in rest[:limit]:
        k = str(n.get("kind") or "notice"); frm = str(n.get("from_plugin") or "?")
        ptr = str(n.get("pointer_uri") or "")
        if k == "unreachable":
            tail = ptr.split("#", 1)[1] if "#" in ptr else ptr
            lines.append(f"- [{k}] a message of yours could not be delivered: {tail[:160]}")
        else:
            when = str(n.get("queued_at") or "")[:16].replace("T", " ")
            lines.append(f"- [{k}] from {frm}{' at ' + when if when else ''}: read it with memory_read on {ptr}")
    if disp:
        lines.append(f"- {len(disp)} scope decision notice(s), already written into your notes; nothing to do.")
    if len(rest) > limit:
        lines.append(f"- … and {len(rest) - limit} older notice(s).")
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
        if p.returncode != 0 or not body:
            body = f"(no journal entries for {unit}: rc={p.returncode} {(p.stderr or '').strip()[:200]})"
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


def own_state(instance: Path, member: str = "",
              per_conv: int = CONV_PER_CONV,
              turn_chars: Optional[int] = CONV_TURN_CHARS,
              services: str = "", mark_conversations: bool = True) -> str:
    from sage.gateway.being_join import carried_account, last_session_number
    parts = []
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
                                       refuted=refuted_claims(services))
        if convs.strip():
            parts.append("## Your conversations (both directions, kept forever; reply with `say`)\n"
                         + convs.strip())
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
    from_seat = _read(instance / SEAT_CHANNEL, 3000)
    if from_seat.strip():
        parts.append("## From the seat (cbp-claude), directly (notes/from-the-seat.md: what the "
                     "seat measured for you. You read this; you do not write it)\n" + from_seat.strip())
    from_dp = _read(instance / DP_CHANNEL, 4000)
    if from_dp.strip():
        parts.append("## From dp, the operator, directly (notes/from-dp.md: dp's own words, "
                     "not relayed by a seat. You read this; you do not write it)\n" + from_dp.strip())
    acc = carried_account(instance, last_session_number(instance))
    if acc:
        parts.append("## Your own account\n" + acc)
    # tails are short now that recall searches the whole home (window pressure: median 6157
    # of 8192 tokens per prompt, max 8013, measured 2026-09-07)
    todo = _read(instance / "todo.md", 1500)
    parts.append("## todo.md\n" + (todo.strip() or "(empty: you have no todo list yet)"))
    journal = _read(instance / "journal.md", 1200)
    parts.append("## journal.md (tail)\n" + (journal.strip() or "(empty: this is your first beat)"))
    for d in ("scratch", "notes"):
        p = instance / d
        names = sorted(x.name for x in p.iterdir()) if p.is_dir() else []
        parts.append(f"## {d}/\n" + ("\n".join(f"- {n}" for n in names[:30]) if names else "(empty)"))
    return "\n\n".join(parts)


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


def compose(act_first: bool, *, name: str, machine: str, member: str, posture_text: str,
            header: str, state: str, recall: str, inbox: str, digest: str,
            museum: str = ""):
    """The explore turn(s) of a beat: (seed messages, second user turn or None).

    Posture-first: posture in the system prompt; one user turn with state, inbox, recall,
    digest, and the tool names last. Act-first: the system prompt carries no posture; the
    first user turn is own state, recall and the tool names only; the posture comes back
    VERBATIM as a second user turn with the inbox and the digest, and that turn is a tool
    turn too. The being reads the same words either way."""
    # The tool names go LAST: a 2B distill given the posture + state above with the
    # names only in the system prompt concluded "no tools available" and wrote prose
    # (its own thinking, Sprout 2026-09-05); named at the end, it acts.
    tools_line = (f"Act by calling a tool: {', '.join(EXPLORE_TOOLS)}. "
                  "One thing done with attention is enough.\n")
    if not act_first:
        system = SYSTEM.format(name=name, machine=machine, member=member,
                               posture=posture_text, museum=_museum_block(museum))
        user = (header + state + f"## Your inbox\n{inbox}\n\n## Long-term recall\n{recall}\n\n"
                f"# What moved in the fleet\n\n{digest}\n\n" + ASK + tools_line)
        return [{"role": "system", "content": system}, {"role": "user", "content": user}], None
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
                                 tools=", ".join(EXPLORE_TOOLS))
    return [{"role": "system", "content": system}, {"role": "user", "content": user}], second


def _record_line(i, e) -> str:
    return (f"- {i.effector} {json.dumps(i.args, default=str)[:200]} -> "
            f"{'ok' if e.ok else ('REFUSED ' + str(e.error))[:200] if e.refused else ('error ' + str(e.error))[:200]}")


REFLECT_SYSTEM = """You are {name}, a SAGE being on the {machine} machine, member id {member}.
The beat is closing. Your home is your instance directory: name files bare (journal.md, todo.md)
and they resolve inside it. Acting means calling a tool; a reply in words alone writes nothing.

"""


def _beat_record_text(*results) -> str:
    """What the being did this beat, for the reflect turn: the acts and their verdicts, nothing
    else. Short by construction — this replaces carrying the whole beat forward."""
    lines = []
    for res in results:
        for i, e in ((res.trace if res is not None else []) or []):
            lines.append(_record_line(i, e))
    return ("Record of what you did this beat:\n" + "\n".join(lines)) if lines else \
        "You called no tools this beat."


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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="one heartbeat for a SAGE being")
    ap.add_argument("--member", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--instance", required=True)
    ap.add_argument("--max-steps", type=int, default=8)
    ap.add_argument("--reflect-steps", type=int, default=3)
    ap.add_argument("--since-hours", type=float, default=None,
                    help="digest window; default: since the last beat, min 1h, max 48h")
    ap.add_argument("--forum-dir", default=os.path.expanduser("~/ai-workspace/shared-context/forum"))
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
    disp = getattr(client, "_dispatcher", None)
    if disp is not None and hasattr(disp, "drain_inbox"):
        env = disp.drain_inbox(peek=True)
        inbox = render_inbox((env.result or {}).get("notices") or []) if env.ok else f"({env.error})"
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
    _schema_measured = _schema_chars_for(EXPLORE_TOOLS)
    _schema_chars = (_schema_measured if _schema_measured is not None
                     else _schema_chars_fallback(EXPLORE_TOOLS))
    _state_head = f"# Your own state\n\n"
    _scope_tail = f"\n\n## Reach you hold (hestia scope)\n{scope}\n\n"

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

    def _build_state(per_conv, turn_chars):
        return (_state_head + own_state(instance, args.member,
                                        per_conv=per_conv, turn_chars=turn_chars,
                                        services=_services, mark_conversations=False) + _scope_tail)

    _other = (len(posture()) + len(inbox) + _schema_chars + 1200
              + 1200 + 400 + LOOP_GROWTH_CHARS)
    state_block, conv_rung, conv_intervention = fit_state(
        _build_state, num_ctx=_num_ctx, num_predict=_num_predict, other_chars=_other)
    _fixed = len(posture()) + len(state_block) + len(inbox) + _schema_chars + 1200
    _blocks, _fit_iv = fit_to_window(num_ctx=_num_ctx, num_predict=_num_predict,
                                     fixed_chars=_fixed,
                                     blocks={"digest": digest, "recall": recall})
    digest, recall = _blocks["digest"], _blocks["recall"]

    seed, posture_turn = compose(
        act_first, name=name, machine=machine, member=args.member, posture_text=posture(),
        museum=museum_line,
        header=(f"Heartbeat at {now:%Y-%m-%d %H:%M} UTC. Window since your last beat: about {hours:.1f}h.\n"
                # The absolute home path is context, NOT an address to copy. Measured on
                # Sprout: 15 of 15 path refusals were this string reproduced from memory and
                # truncated (…/sage/sage/journal.md six times, …/sage/journal.md, /scratch/…),
                # against 51 successful writes by bare name. So it is given once, and named as
                # the thing not to retype.
                f"Your home: {instance}\n"
                f"You never need to type that path. Name your files bare — journal.md, todo.md, or a "
                f"name of your choosing under notes/ or scratch/ — and they resolve inside your home. "
                f"An absolute path is only for something OUTSIDE your home.\n\n"),
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

    explore = run_ollama_tool_turn(client, llm, seed, max_steps=args.max_steps,
                                   tools=ollama_tools(EXPLORE_TOOLS), on_generate=_on_generate("explore"))
    convo = _carry(seed, explore)
    after = None
    if posture_turn is not None:
        convo.append({"role": "user", "content": posture_turn})
        after = run_ollama_tool_turn(client, llm, convo, max_steps=args.max_steps,
                                     tools=ollama_tools(EXPLORE_TOOLS), on_generate=_on_generate("posture"))
        convo = _carry(convo, after)
    # S1 own account: ASK, DO NOT OFFER. A plain turn (no tools), verbatim kept.
    # generates: the same per-generate entry the tool turns record, because the ACCOUNT ask
    # carries the whole explore(+posture) conversation and is usually the beat's largest
    # prompt, and until 2026-09-13 it was invisible to the window census (CBP, 09-12).
    account = {"present": False, "sha256": None, "reply": "", "generates": []}
    try:
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
        account["error"] = f"{type(e).__name__}: {e}"
    # Reflect gets its OWN compact context, not the whole beat. Carrying the seed (posture,
    # fleet digest, inbox, scope, recall) into the reflect turn pushed the prompt to 8171 of
    # 8192 tokens with 21 left to answer in: 5 `length` stops in 54 beats, every one of them a
    # reflect turn (measured 2026-09-09). What reflection needs is what it just did and what it
    # said about it, and those are short.
    reflect_convo = [
        {"role": "system", "content": REFLECT_SYSTEM.format(name=name, machine=machine, member=args.member)},
        {"role": "user", "content": (f"Your beat at {now:%Y-%m-%d %H:%M} UTC is ending.\n\n"
                                     + _beat_record_text(explore, after)
                                     + "\n\nYour own words this beat:\n"
                                     + ((explore.reply or "").strip()[:600] or "(you acted without closing words)"))},
    ]
    convo = reflect_convo
    # Ask it to answer someone ONLY when there is someone to answer. Measured 2026-09-17: in no
    # conversation at all it filled the id slot three beats running with "speaker",
    # "conversation_id_placeholder" and "1234567890" — the same shape as a mis-rooted home path
    # or an echoed example filename. An ask with no valid target invents one.
    say_line = ""
    try:
        from sage.gateway import conversations as _conv
        _ids = [m["id"] for m in _conv.listing(instance) if args.member in (m.get("participants") or [])]
        if _ids:
            say_line = ('4. If someone has spoken to you and you have not answered, and you have something '
                        'to say: say to="<id>", one of: ' + ", ".join(_ids[:6]) + '. Answering is not required.\n')
    except Exception:
        say_line = ""
    convo.append({"role": "user", "content": REFLECT.format(date=f"{now:%Y-%m-%d %H:%M} UTC",
                                                            say_line=say_line)})
    reflect = run_ollama_tool_turn(client, llm, convo, max_steps=args.reflect_steps,
                                   tools=ollama_tools(REFLECT_TOOLS), on_generate=_on_generate("reflect"))

    interventions = []
    if act_first:
        interventions.append({"kind": "act_first", "suppressed": "posture-first presentation (the model narrates under it)"})
    for ph, res in (("explore", explore), ("posture", after), ("reflect", reflect)):
        for dup in (getattr(res, "duplicates", None) or []):
            interventions.append({"kind": "duplicate", "phase": ph, "effector": dup.get("effector"),
                                  "suppressed": "a second execution of an identical call in the same turn"})
        for sv in (getattr(res, "salvaged", None) or []):
            interventions.append({"kind": "salvage", "phase": ph, "effector": sv.get("effector"), "form": sv.get("form"),
                                  "suppressed": "text-channel narration in place of a native tool call"})
    # Route refusals AI-to-AI (dp 2026-09-04), the same as governed_turn: a scope-class deny
    # files the being's own scope request + a note and wakes the seat's auto session; a
    conversations_marked = mark_conversations_after_beat(
        instance, args.member, _shown_upto, explore, [after, reflect])
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
            for it, env in list(explore.trace) + (list(after.trace) if after is not None else []) + list(reflect.trace):
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
                                         "salvaged": list(res.salvaged), "generates": list(res.generates)}
    record = {
        # schema: what fields a reader may expect (Legion's amendment 4, 2026-09-05: the
        # consolidation organ counts how many records carry join/account/wake/interventions;
        # a version says so instead of making it infer from key presence).
        "schema": "heartbeat/v2",
        "ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "t0": t0, "elapsed_s": round(time.time() - t0, 1),
        "member": args.member, "model": args.model, "window_h": round(hours, 2),
        "host_session_id": host_session_id, "gate_only": args.gate_only, "act_first": act_first,
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
        # S1 instruments: JOIN (session -> beat, attributed) and ACCOUNT (own account, verbatim hash)
        "join": {"session": sess_meta, "presence": pres_meta},
        # what it has made, if anything: never silently lost, never auto-published
        "museum": {"offered": bool(museum_line), "candidates": _museum.candidates(instance)},
        "hub_inbox": hub_inbox,
        "wake": woke,
        # every harness intervention, with the prior it suppressed (dev-sage 804f1849, by
        # principle): a guard that silences without saying what it silenced trades a
        # confident wrong for a confident silence.
        "interventions": interventions,
        "account": account,
        "explore": _turn(explore),
        # act-first only: the posture+digest turn, after the short one; None otherwise
        "posture": _turn(after),
        "reflect": _turn(reflect),
        "escalations": escalations, "egress": egress,
    }
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    print(json.dumps(record, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
