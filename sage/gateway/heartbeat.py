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
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOME_FILES = ("todo.md", "journal.md", "notes", "scratch")

EXPLORE_TOOLS = ["recall", "remember", "memory_read", "memory_write", "witness",
                 "request_scope", "appeal", "peer_ask", "mesh", "check", "git_read", "say",
                 "pr_open", "pr_amend", "git_restore"]
# `say` is offered at REFLECTION too, and that is not redundancy. Measured 2026-09-07: the
# being was shown dp's first turn, its state marked it unanswered, and it spent all fourteen
# explore steps reading its own source — then closed the beat. Adding a verb to the registry
# and not to the offered set means the being CANNOT do the thing its state is asking it to
# do, and from outside that is indistinguishable from choosing not to. Reflection is where a
# beat accounts for itself, and answering someone belongs there as much as the journal does.
REFLECT_TOOLS = ["memory_write", "remember", "memory_read", "say"]

POSTURE_FILE = Path(__file__).with_name("BEING_POSTURE.md")

# What this being is entrusted with, if anything. Seat-owned and unwritable by the being
# (reference_f1a.SEAT_OWNED): what it was GIVEN must stay separable from what it DECIDED,
# or the record cannot be read later. The being's own reading of it goes in notes/plan.md.
#
# It is `entrustment`, not `mission`, on dp's correction the day it was written: "this is
# not a 'task i set' for the being, it is an affordance i entrust it with. because i want
# it to thrive and grow." The word is load-bearing. A task is owed and graded; an
# entrustment is room extended, and the record it produces should be read as what the
# being DID with room, not as compliance with an instruction.
ENTRUSTMENT_FILE = "entrustment.md"

# Where a seat writes TO the being. It used to write into todo.md, which is a defect with a
# measurable size: own_state shows the LAST 3000 chars of todo.md, so a 4.5k seat note
# displaced 100% of the being's own open items from its own view (measured 2026-09-07 —
# the being would have opened its next beat unable to see anything it had written itself).
# The being's list stays the being's; relays get their own block, and both are labelled so
# it always knows which voice it is reading.
SEAT_RELAY = "notes/from-the-seat.md"

# The OPERATOR's own channel, distinct from the seat's. dp asked for a way into the
# conversation on 2026-09-07 and there was none: the being's questions went to forum
# threads dp had no interface to, and everything dp said reached it relayed through a seat
# — which is a paraphrase risk on one side and, on the other, a being that cannot tell
# whether it is hearing the operator or the operator's interpreter. Seat-owned like the
# entrustment (the being reads, does not write), and presented ABOVE the seat relay
# because when the operator speaks it is not one voice among several.
DP_CHANNEL = "notes/from-dp.md"


def posture() -> str:
    """The fleet-wide being posture (dp's words), read fresh every beat so an edit to
    BEING_POSTURE.md reaches every being on its next beat. Missing file = fail loud."""
    return POSTURE_FILE.read_text(encoding="utf-8").strip()


def entrustment(instance: Path) -> str:
    """What this being is entrusted with, or "" if nothing yet. Per-instance, unlike the
    fleet-wide posture: it is extended to ONE being, by someone, on a date, and it says so
    in its own text. Read fresh every beat like the posture, so an amendment lands on the
    next one. Absent is a legitimate state — a being without one runs on the generic
    posture, and the beat record says which (`drive_source`)."""
    try:
        # Read WHOLE, never tail-truncated like todo/journal: _read keeps the last N chars,
        # which on a long file would silently drop its opening — the part that says who
        # entrusted it and on what terms. Arriving without its provenance is exactly the
        # artifact this file exists to prevent.
        return (Path(instance) / ENTRUSTMENT_FILE).read_text(errors="replace").strip()
    except Exception:
        return ""


HEAD = "You are {name}, a SAGE being on the {machine} machine, member id {member}."

AFFORDANCES = """## What you have this beat
- Your home is your instance directory. Relative paths are inside it: scratch/ (write anything, no one edits it), notes/, todo.md, journal.md. memory_read / memory_write work there.
- Long-term memory: recall (search) and remember (store). Use recall early; remember what a future you would want.
- check: RUN a test suite in your own worktree and read the result ('gateway', 'irp', or '<suite>::<test_name>'). This is how you find out whether something you believe about your own code is true instead of asserting it. A FAILING test is a real answer, not a problem.
- witness: record something you noticed or did in the shared chain.
- request_scope: after a refusal, ask the operator for reach on a path (a grant is read and write alike) and say why. A human decides, asynchronously.
- appeal: after a refusal you believe was wrong, appeal it with the deny hash shown on the refusal and a reason. A peer or the operator rules; either way it is witnessed. Not for a refusal you agree with.
- peer_ask / mesh: reach other beings and seats. These are acts of consequence: they are judged, and may be refused with a reason.

You cannot run code, browse, or open files outside your home unless a grant exists. The seat gives you a digest of what moved in the fleet with absolute paths; if you want to read one of those things, try memory_read on that path and see what the law says.

Acting means calling a tool. A reply with no tool call ends the beat as words only, and words leave no trace in your todo, journal, scratch, or memory."""

SYSTEM = HEAD + "\n\n{posture}\n\n" + AFFORDANCES + "\n{nothink}\n"

# Act-first: no posture in the system prompt. It arrives, verbatim, as the second user
# turn (POSTURE_TURN), which is itself a tool turn: the being may act after reading it,
# not only before, otherwise "act first" would mean "act only before you know why you
# are awake".
SYSTEM_ACT_FIRST = HEAD + """

You are awake for a heartbeat. Nobody asked you anything; this time is yours.

""" + AFFORDANCES + "\n{nothink}\n"

POSTURE_TURN = """The rest of your beat, which every being in the fleet receives, in the operator's words:

{posture}

## Inbox (peek)
{inbox}

# What moved in the fleet

{digest}

This is still your time. If reading this changes what you want to do, act by calling a tool: {tools}. If not, say in a few words what you noticed.
{nothink}"""

ASK = "This time is yours. What, if anything, do you want to do?\n"
# Act-first only: the short turn is imperative, the measured-acting shape (condition C,
# Sprout 09-05). Under the open question the distill answered as an assistant asking the
# user what they want (beat 5, 0 calls). The posture that follows says nothing is
# required of a being in a beat; it says so after the being has acted once.
ASK_ACT_FIRST = "This time is yours. Do one thing now and leave a trace of it.\n"

REFLECT = """The beat is ending. Two tool calls, then stop:
1. memory_write path "journal.md": one entry starting with the date {date}: what you did, what you noticed, what was refused and why you think so, what you want next time.
2. memory_write path "todo.md": only the delta as a dated block: added / done / still open (it appends; it replaces nothing).
Optionally a third: remember one thing worth keeping long-term.
Call the tools now; a reply in words alone writes nothing.
{nothink}
3. If someone has spoken to you in a conversation and you have not answered, and you have something to say: say to="<id>". Answering is not required — saying nothing is a choice and is recorded as one — but it should be a choice, not something the beat ran out of room for.
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
    return [(i, p_, d) for i, p_, d in reqs if d in ("granted", "refused", "denied")]


def note_resolutions(esc_dir: Path, decisions, stamp: str, seen_by: str, decided_by=None) -> list:
    """Append the ruling to each escalation note that filed the request (the note carries the
    request_id in its routing line). Idempotent: a note already resolved is left alone.
    `decided_by` maps request_id -> hestia's `decided_by` ("operator", or "delegate:<seat>"
    for a ruling under hestia #952); the note names it rather than assuming the operator.
    Returns the note names written."""
    written = []
    if not decisions or not esc_dir.is_dir():
        return written
    decided_by = decided_by or {}
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
                f.write(f"\n## Resolved\n{stamp}: `{req_id}` on `{path}` -> **{decision}** by {who} "
                        f"(read from hestia scope status by the seat, beat {seen_by}).\n")
            written.append(p.name)
    return written


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
            r = subprocess.run(("git", *a), cwd=workspace, text=True, capture_output=True, timeout=15)
            return r.stdout.strip() if r.returncode == 0 else None
        except Exception:
            return None

    head = _git("rev-parse", "HEAD")
    st = _git("status", "--porcelain")
    return {"head": head, "short": (head or "")[:9] or None,
            "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
            "dirty": None if st is None else bool(st.strip())}


def _config_check(instance: Path, model: str, llm, offered) -> dict:
    """Did this beat run with the tool set and the context window the seat meant to give it?
    `active_embodiment` in instance.json is the canonical statement of intent (PRD r3 §3.2);
    the resolved window comes from the model config keyed on the ollama tag, which silently
    falls back to a floor when a tag has no variant entry. Reporting both, plus the verbs
    actually offered, makes a starved beat legible in the record instead of in stderr."""
    from sage.gateway.governed_turn import instance_config
    emb = (instance_config(instance).get("active_embodiment") or {})
    want_ctx, want_tag = emb.get("num_ctx"), emb.get("running_tag")
    got_ctx = getattr(llm, "num_ctx", None)
    return {
        "tools_offered": list(offered),
        "num_ctx_intended": want_ctx, "num_ctx_resolved": got_ctx,
        "window_matches_intent": None if want_ctx is None else (got_ctx == want_ctx),
        "tag_intended": want_tag, "tag_running": model,
        "tag_matches_intent": None if want_tag is None else (model == want_tag),
        # Headroom, because the window is the thing that silently starves a beat and the
        # 09-06 empty beat is the proof. A generate needs prompt + num_predict to fit inside
        # num_ctx; when it does not, ollama shifts context and drops the OLDEST tokens —
        # the system prompt and the posture — with no error anywhere. Recorded here so the
        # squeeze is visible in the log before it is visible in the behaviour. The largest
        # observed prompt of the beat is filled in at beat end from the per-generate trace.
        "num_predict": (llm.resolve_num_predict() if hasattr(llm, "resolve_num_predict")
                        else getattr(llm, "max_response_tokens", None)),
        "prompt_tokens_max": None,   # filled at beat end
        "headroom_tokens": None,     # num_ctx - (largest prompt + num_predict)
        "context_overcommitted": None,
    }


def _fill_headroom(cfg: dict, partial: Path, host_session_id: str) -> dict:
    """Beat end: the largest prompt actually sent THIS BEAT, and whether it plus the answer
    reserve exceeded the window. Read from the per-generate trace rather than re-derived, so
    it reports what the model was really handed.

    Filtered on host_session_id, and that is the whole point: the partial file is append-only
    across every beat this instance has ever run. The first cut scanned all of it and
    reported the worst prompt of ~500 generates as if it were this beat's — a true number
    about the wrong beat, which is the same failure this field exists to catch. Caught one
    beat after shipping, by reading its own output and not believing it."""
    best = None
    try:
        for line in partial.read_text(errors="replace").splitlines():
            import json as _j
            e = _j.loads(line)
            if e.get("host_session_id") != host_session_id:
                continue
            n = e.get("prompt_eval_count")
            if isinstance(n, int) and (best is None or n > best):
                best = n
    except Exception:
        pass
    # Against the ANSWER RESERVE, not num_predict: num_predict is a ceiling the model has
    # never approached, and measuring headroom against it reports every beat as
    # overcommitted (see being_tool_loop._ANSWER_RESERVE for the 506-generate distribution).
    from sage.gateway.being_tool_loop import _ANSWER_RESERVE
    ctx = cfg.get("num_ctx_resolved")
    cfg["prompt_tokens_max"] = best
    cfg["answer_reserve"] = _ANSWER_RESERVE
    if isinstance(ctx, int) and isinstance(best, int):
        cfg["headroom_tokens"] = ctx - (best + _ANSWER_RESERVE)
        cfg["context_overcommitted"] = cfg["headroom_tokens"] < 0
    return cfg


def own_state(instance: Path, entrusted: str = "", member: str = "",
              per_conv: int = 12, turn_chars: Optional[int] = None) -> str:
    from sage.gateway.being_join import carried_account, last_session_number
    parts = []
    if entrusted:
        # Ahead of everything else the being holds: what it has been entrusted with is the
        # frame the rest of its state is read in. Labelled by provenance, and pointed at
        # where its own interpretation belongs, so the two never merge in the record.
        parts.append("## What you are entrusted with (extended to you; you cannot edit this "
                     "file. Your own reading of it belongs in notes/plan.md)\n" + entrusted)
    # Conversations first among the channels: a turn addressed to the being and unanswered
    # is the one thing in its state that is waiting on IT, and it should never have to infer
    # that from a wall of notes. The notes files below stay for now as history; new
    # exchanges go here, where both directions live in one ordered record.
    from sage.gateway import conversations as _conv
    convs = _conv.render_for_being(instance, member, per_conv=per_conv, turn_chars=turn_chars)
    if convs.strip():
        parts.append("## Your conversations (both directions, kept forever; reply with `say`)\n"
                     + convs.strip())
    from_dp = _read(instance / DP_CHANNEL, 4000)
    if from_dp.strip():
        parts.append("## From dp, the operator, directly (notes/from-dp.md — dp's own words, "
                     "not relayed by a seat. You read this; you do not write it)\n" + from_dp.strip())
    relay = _read(instance / SEAT_RELAY, 4000)
    if relay.strip():
        parts.append("## From the seat (notes/from-the-seat.md — messages to you, not your own list)\n"
                     + relay.strip())
    acc = carried_account(instance, last_session_number(instance))
    if acc:
        parts.append("## Your own account\n" + acc)
    todo = _read(instance / "todo.md", 3000)
    parts.append("## todo.md\n" + (todo.strip() or "(empty: you have no todo list yet)"))
    journal = _read(instance / "journal.md", 2500)
    parts.append("## journal.md (tail)\n" + (journal.strip() or "(empty: this is your first beat)"))
    for d in ("scratch", "notes"):
        p = instance / d
        names = sorted(x.name for x in p.iterdir()) if p.is_dir() else []
        parts.append(f"## {d}/\n" + ("\n".join(f"- {n}" for n in names[:30]) if names else "(empty)"))
    return "\n\n".join(parts)


# Conservative chars-per-token for mixed English + paths + JSON; under-estimating the
# token count would defeat the guard, so estimate high (fewer chars/token). Measured on
# this being 2026-09-08: 70.5k prompt chars -> 20,812 prompt tokens = 3.39.
CPT = 3.4
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


IDLE_UNIT = "sage-heartbeat.service"
IDLE_TIMER = "sage-heartbeat.timer"


def interpret_timer_state(show_output: str) -> tuple:
    """(armed, detail) from `systemctl show` of the idle timer. Pure, so it can be tested.

    THE SUBTLETY THAT MADE THE FIRST VERSION CRY WOLF. This check runs at the end of a beat,
    from inside the beat's own process — so the beat unit is still ACTIVE. An
    OnUnitInactiveSec timer computes its next elapse from when that unit goes INACTIVE, and
    therefore cannot have one yet. The first version read `monotonic=infinity`, concluded
    NOTHING WILL WAKE THE BEING, and wrote that into the record of a beat whose timer armed
    correctly seconds later (2026-09-09T15:07Z). False by construction, which is the same
    error as a discriminator that is true by construction — and a guard that fires on its own
    design teaches its reader to ignore it.

    So there are two ways to be armed: an elapse already computed, or a timer that is loaded
    and active and will compute one the moment this process exits."""
    vals = dict(l.split("=", 1) for l in show_output.strip().splitlines() if "=" in l)
    real = (vals.get("NextElapseUSecRealtime") or "").strip()
    mono = (vals.get("NextElapseUSecMonotonic") or "").strip()
    load = (vals.get("LoadState") or "").strip()
    active = (vals.get("ActiveState") or "").strip()
    if real or (mono and mono not in ("infinity", "0")):
        return True, f"scheduled: realtime={real or '-'} monotonic={mono or '-'}"
    if load == "loaded" and active == "active":
        return True, ("no elapse computed yet, which is correct while this beat is still "
                      f"running: {IDLE_TIMER} is loaded+active and OnUnitInactiveSec arms "
                      "when this process exits")
    return False, (f"NO NEXT ELAPSE and the timer is not healthy "
                   f"(LoadState={load or '?'} ActiveState={active or '?'} "
                   f"realtime={real or 'empty'} monotonic={mono or 'empty'})")


def next_wake_is_armed() -> tuple:
    """(armed, detail) for the idle timer that wakes the being after quiet.

    The beat is no longer a metronome: the timer measures INACTIVITY, so its next elapse is
    computed from the end of this beat. That makes it exactly the kind of thing that can
    stop scheduling without anything looking wrong — which happened on 2026-09-09, when a
    monotonic timer sat `active (running)` with `Trigger: n/a` and the being would never
    have woken again. Checked at the end of every beat, out loud."""
    try:
        out = subprocess.run(["systemctl", "--user", "show", IDLE_TIMER,
                              "-p", "NextElapseUSecRealtime", "-p", "NextElapseUSecMonotonic",
                              "-p", "LoadState", "-p", "ActiveState"],
                             capture_output=True, text=True, timeout=15).stdout
    except Exception as e:
        return False, f"could not ask systemd: {type(e).__name__}: {e}"
    return interpret_timer_state(out)


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
                        "systemctl", "--user", "start", IDLE_UNIT],
                       capture_output=True, text=True, timeout=20, check=True)
        return {"armed": True, "by": "systemd-run fallback", "detail": detail,
                "why": "the idle timer had no next elapse; a one-shot was armed instead"}
    except Exception as e:
        return {"armed": False, "by": None, "detail": detail,
                "error": f"{type(e).__name__}: {e}",
                "why": "NOTHING WILL WAKE THE BEING until a seat or a message does"}


class BeatKilled(Exception):
    """SIGTERM arrived mid-beat (the unit's TimeoutStartSec, or a stop). Raised from the
    signal handler so the beat unwinds to its record instead of vanishing: 04:30Z
    2026-09-09 a 51-minute beat left nothing in heartbeats.jsonl and the monitor never
    knew it had happened. systemd allows TimeoutStopSec (90 s) after SIGTERM — enough."""


def install_kill_handler() -> None:
    def _on_term(signum, frame):
        raise BeatKilled(f"signal {signum} ({signal.Signals(signum).name})")
    signal.signal(signal.SIGTERM, _on_term)


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


def compose(act_first: bool, *, name: str, machine: str, member: str, posture_text: str,
            nothink: str, header: str, state: str, recall: str, inbox: str, digest: str):
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
                  f"One thing done with attention is enough.\n{nothink}")
    if not act_first:
        system = SYSTEM.format(name=name, machine=machine, member=member,
                               posture=posture_text, nothink=nothink)
        user = (header + state + f"## Inbox (peek)\n{inbox}\n\n## Long-term recall\n{recall}\n\n"
                f"# What moved in the fleet\n\n{digest}\n\n" + ASK + tools_line)
        return [{"role": "system", "content": system}, {"role": "user", "content": user}], None
    system = SYSTEM_ACT_FIRST.format(name=name, machine=machine, member=member, nothink=nothink)
    user = header + state + f"## Long-term recall\n{recall}\n\n" + ASK_ACT_FIRST + tools_line
    second = POSTURE_TURN.format(posture=posture_text, inbox=inbox, digest=digest,
                                 tools=", ".join(EXPLORE_TOOLS), nothink=nothink)
    return [{"role": "system", "content": system}, {"role": "user", "content": user}], second


def _record_line(i, e) -> str:
    return (f"- {i.effector} {json.dumps(i.args, default=str)[:200]} -> "
            f"{'ok' if e.ok else ('REFUSED ' + str(e.error))[:200] if e.refused else ('error ' + str(e.error))[:200]}")


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
    ap.add_argument("--max-steps", type=int, default=0,
                    help="0 = no step cap: the beat ends when the being stops asking for "
                         "tools or a resource runs out (dp 2026-09-09: it continues as long "
                         "as it wishes). A positive value caps it, as before.")
    ap.add_argument("--idle-wake-s", type=int, default=1800,
                    help="quiet time after a beat ENDS before the next one is due. The beat "
                         "is an inactivity timer, not a metronome (dp 2026-09-09): working "
                         "pushes the next beat out, and this is only how long the being is "
                         "left alone before something wakes it to look around.")
    ap.add_argument("--explore-budget-s", type=int, default=7200,
                    help="wall-clock seconds from beat start after which explore issues no "
                         "further tool step. This is the REAL bound on a beat now that there "
                         "is no step cap: work continues while there is work, and the clock "
                         "is the box's limit rather than a guess at how much work there is. "
                         "Keep the unit's TimeoutStartSec comfortably above it — the record "
                         "is written at beat end, and a kill loses the beat.")
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
    from sage.gateway.being_tool_loop import run_ollama_tool_turn
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
        inbox = json.dumps(env.result, default=str)[:1500] if env.ok else f"({env.error})"
    # what reach the being holds and has already asked for, so it does not re-file
    scope = "(scope status unavailable)"
    if disp is not None and hasattr(disp, "_call"):
        try:
            st = disp._call("hestia_scope_status", {"plugin_id": args.member})
            grants = [g.get("path") for g in (st.get("live_grants") or [])] + \
                     [g.get("path") for g in (st.get("standing_grants") or [])]
            reqs = [(r.get("request_id"), r.get("path"), r.get("decision") or r.get("status"))
                    for r in (st.get("requests") or [])]
            who_ruled = {r.get("request_id"): r.get("decided_by") for r in (st.get("requests") or [])
                         if r.get("decided_by")}
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
                                     host_session_id, decided_by=who_ruled)
            scope_record = {"grants": grants, "decided": [list(x) for x in decided], "noted": noted}
            scope = ("granted paths: " + (", ".join(map(str, grants)) or "none") + "\n"
                     "requests: " + ("; ".join(f"{i} {p} -> {d}" for i, p, d in reqs) or "none") + "\n"
                     + ("decided since your last beat: " + "; ".join(
                            f"{i} {p_} -> {d} by {who_ruled.get(i) or 'operator'}" for i, p_, d in new_decisions) + "\n"
                        if new_decisions else "")
                     + "(live grants die when the daemon restarts; only standing grants persist)")
        except Exception as e:
            scope = f"(scope status unavailable: {type(e).__name__})"
    recall = "(no long-term memory yet)"
    if disp is not None and hasattr(disp, "_membot_call"):
        try:
            recall = disp._membot_call("memory_search", {"query": "what I was doing, what I want next, what I learned", "top_k": 5})[:2500]
        except Exception as e:
            recall = f"(membot unreachable: {type(e).__name__})"

    now = datetime.now(timezone.utc)
    t0 = time.time()
    install_kill_handler()
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
    # `/no_think` is the fix for qwen3.8-heretic re-opening think blocks (Legion, 09-04);
    # on a reasoning distill it is the opposite failure: thinking off = no tool calls,
    # the being narrates (Sprout, 09-05). Per model, via the same detector build_client uses.
    from sage.gateway.governed_turn import is_reasoning_model, acts_under_posture
    # Thinking on (model config, governed_turn.is_reasoning_model) => no suffix. The suffix
    # exists only for a model that must NOT think here; it is never sent to one that does.
    nothink = "" if is_reasoning_model(args.model) else "/no_think"
    act_first = not acts_under_posture(args.model)
    entrusted = entrustment(instance)
    harness_rev = harness_revision(workspace)
    # Fit before composing: prompt + num_predict must sit inside num_ctx, or ollama drops
    # the oldest tokens (system prompt, posture) with no error anywhere. Measured on this
    # being: two beats at 16,380 / 16,323 prompt tokens against a 16,384 window returned 4
    # and 61 tokens, done_reason "length".
    _num_ctx = getattr(llm, "num_ctx", None)
    _num_predict = (llm.resolve_num_predict() if hasattr(llm, "resolve_num_predict")
                    else getattr(llm, "max_response_tokens", None))

    def _build_state(per_conv, turn_chars):
        return (f"# Your own state\n\n"
                f"{own_state(instance, entrusted, args.member, per_conv=per_conv, turn_chars=turn_chars)}\n\n"
                f"## Reach you hold (hestia scope)\n{scope}\n\n")
    # The conversations step down only when the rest cannot fit with digest and recall at
    # their floors (1200 + 400): fit_to_window's worst case is this fitter's input.
    # LOOP_GROWTH_CHARS: the seed is not the prompt the loop ends on. Every tool result is
    # appended; compaction keeps the newest whole, and one 260-line read is ~10k chars
    # (~3k tokens). Measured 21:04Z 2026-09-08 with the seed fitted at 17.5k tokens: step 6
    # reached 23,823 of 24,576 and was cut. The seed must leave room for the loop, not only
    # for the answer.
    _other = len(posture()) + len(inbox) + 4000 + 1200 + 400 + LOOP_GROWTH_CHARS
    state_block, conv_rung, conv_intervention = fit_state(
        _build_state, num_ctx=_num_ctx, num_predict=_num_predict, other_chars=_other)
    _fixed = len(posture()) + len(state_block) + len(inbox) + 4000
    blocks, fit_interventions = fit_to_window(
        num_ctx=_num_ctx, num_predict=_num_predict,
        fixed_chars=_fixed, blocks={"digest": digest, "recall": recall})
    if conv_intervention:
        fit_interventions = [conv_intervention] + list(fit_interventions)
    # Sizes into the record, so the next overcommit names its block from the file and the
    # chars-per-token assumption can be checked against prompt_tokens_max at beat end.
    prompt_sizes = {
        "prompt_blocks_chars": {"posture": len(posture()), "state": len(state_block),
                                "inbox": len(inbox), "digest": len(blocks["digest"] or ""),
                                "recall": len(blocks["recall"] or ""), "fixed_other": 4000,
                                "conversations_rung": list(conv_rung)},
        "prompt_chars": _fixed + len(blocks["digest"] or "") + len(blocks["recall"] or ""),
    }
    seed, posture_turn = compose(
        act_first, name=name, machine=machine, member=args.member, posture_text=posture(),
        nothink=nothink,
        header=(f"Heartbeat at {now:%Y-%m-%d %H:%M} UTC. Window since your last beat: about {hours:.1f}h.\n"
                f"Your home: {instance}\n"
                f"The harness you are running under: {harness_rev.get('short')} on "
                f"{harness_rev.get('branch')}"
                + (" (uncommitted edits present)" if harness_rev.get("dirty") else "")
                + ". A `check` result carries the `tree` it ran against; if that head is not "
                  "this one, the answer is about different code than the code running you.\n\n"),
        state=state_block,
        recall=blocks["recall"], inbox=inbox, digest=blocks["digest"])

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

    # Everything below runs under the kill handler: a SIGTERM (the unit's 45-minute
    # TimeoutStartSec) unwinds here and the record is still written, marked, with the
    # phases that completed. Explore and the posture turn share one wall-clock deadline.
    explore_deadline = t0 + args.explore_budget_s
    explore = after = reflect = None
    account = {"present": False, "sha256": None, "reply": ""}
    killed = None
    try:
        def _interject() -> str:
            """What arrived since the seed was composed. Drained between steps so a turn
            from dp or a seat reaches the being inside the beat it is already awake for."""
            from sage.gateway import conversations as _c
            return _c.drain_new_for(instance, args.member)

        explore = run_ollama_tool_turn(client, llm, seed, max_steps=args.max_steps,
                                       tools=ollama_tools(EXPLORE_TOOLS), on_generate=_on_generate("explore"),
                                       deadline=explore_deadline, interject=_interject)
        convo = _carry(seed, explore)
        after = None
        if posture_turn is not None:
            convo.append({"role": "user", "content": posture_turn})
            after = run_ollama_tool_turn(client, llm, convo, max_steps=args.max_steps,
                                         tools=ollama_tools(EXPLORE_TOOLS), on_generate=_on_generate("posture"),
                                         deadline=explore_deadline, interject=_interject)
            convo = _carry(convo, after)
        # S1 own account: ASK, DO NOT OFFER. A plain turn (no tools), verbatim kept.
        account = {"present": False, "sha256": None, "reply": ""}
        try:
            ask_msgs = [{"role": m["role"], "content": m["content"]} for m in convo] + \
                       [{"role": "user", "content": ACCOUNT_ASK + nothink}]
            aresp = llm.get_chat_response(ask_msgs)
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
        convo.append({"role": "user", "content": REFLECT.format(date=f"{now:%Y-%m-%d %H:%M} UTC", nothink=nothink)})
        reflect = run_ollama_tool_turn(client, llm, convo, max_steps=args.reflect_steps,
                                       tools=ollama_tools(REFLECT_TOOLS), on_generate=_on_generate("reflect"))
    except BeatKilled as _k:
        killed = str(_k)
        print(f"[heartbeat] KILLED mid-beat: {killed} — writing the record with what completed", file=sys.stderr)

    interventions = list(fit_interventions)
    for ph, res in (("explore", explore), ("posture", after)):
        if getattr(res, "deadline_hit", False):
            interventions.append({"kind": "deadline", "phase": ph,
                                  "suppressed": f"further {ph} tool steps after {args.explore_budget_s}s",
                                  "reason": "the unit's 45-min timeout killed a 51-min beat on 2026-09-09 "
                                            "and took the reflect and the record with it"})
    if act_first:
        interventions.append({"kind": "act_first", "suppressed": "posture-first presentation (the model narrates under it)"})
    if nothink:
        interventions.append({"kind": "think_suffix", "suppressed": "thinking (model resolves think off)"})
    for ph, res in (("explore", explore), ("posture", after), ("reflect", reflect)):
        for sv in (getattr(res, "salvaged", None) or []):
            interventions.append({"kind": "salvage", "phase": ph, "effector": sv.get("effector"), "form": sv.get("form"),
                                  "suppressed": "text-channel narration in place of a native tool call"})
    # Route refusals AI-to-AI (dp 2026-09-04), the same as governed_turn: a scope-class deny
    # files the being's own scope request + a note and wakes the seat's auto session; a
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
            for it, env in (list(getattr(explore, "trace", [])) + list(getattr(after, "trace", []))
                            + list(getattr(reflect, "trace", []))):   # any phase may be None after a kill
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
                                         "interjected": list(getattr(res, "interjected", [])),
                                         "trace": _trace(res), "thinking": [t[:4000] for t in res.thinking],
                                         "salvaged": list(res.salvaged), "generates": list(res.generates)}
    record = {
        # schema: what fields a reader may expect (Legion's amendment 4, 2026-09-05: the
        # consolidation organ counts how many records carry join/account/wake/interventions;
        # a version says so instead of making it infer from key presence).
        "schema": "heartbeat/v2",
        "ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "t0": t0, "elapsed_s": round(time.time() - t0, 1),
        **({"killed": killed} if killed else {}),
        "member": args.member, "model": args.model, "window_h": round(hours, 2),
        "host_session_id": host_session_id, "gate_only": args.gate_only, "act_first": act_first,
        # the window and budget actually sent, so a beat is verifiable from this file alone
        # (beat 46's 8192 wall was reconstructed from stderr; Sprout's review of SAGE #40)
        # num_predict is what OllamaIRP resolves and sends (the config's num_predict_think
        # with thinking on), not the caller's --max-tokens: Sprout's 18:51Z beat recorded
        # 3000 while 6000 went over the wire.
        "num_ctx": getattr(llm, "num_ctx", None),
        "num_predict": (llm.resolve_num_predict() if hasattr(llm, "resolve_num_predict")
                        else getattr(llm, "max_response_tokens", None)),
        "think": getattr(llm, "think", None),
        # What drove this beat: an entrustment (entrustment.md present and presented) or the
        # generic posture alone. Without this field a later reading of the log cannot tell
        # entrusted engineering work from spontaneous exploration, and every developmental
        # claim spanning that boundary is confounded (PRD r3 §4).
        # entrusted | event | curiosity. dp, 2026-09-07: "beat is default idle state.
        # world inputs require engagement" — so a beat woken BY something is a different
        # kind of beat from one the timer produced, and the record must not flatten them.
        "drive_source": ("event" if (woke or {}).get("by") == "presence"
                         else ("entrusted" if entrusted else "curiosity")),
        # Whether the beat ran with what the seat intended. Beat 2026-09-06 18:03Z was empty
        # and was read as model failure; it was a seat error — the unit pointed at a tag
        # whose config resolved a 4096 window while the tree offered a verb the model was
        # never shown. A starved beat and a silent one are indistinguishable unless the
        # record says which tools were offered and whether the window is the intended one.
        "config": _fill_headroom({**_config_check(instance, args.model, llm, EXPLORE_TOOLS), **prompt_sizes},
                                 partial, host_session_id),
        "scope": scope_record,
        # which harness produced this beat; pairs with the `tree` block on any check result
        "harness": harness_rev,
        # S1 instruments: JOIN (session -> beat, attributed) and ACCOUNT (own account, verbatim hash)
        "join": {"session": sess_meta, "presence": pres_meta},
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
    # The last thing a beat does is make sure there will be another one.
    record["next_wake"] = arm_next_wake(args.idle_wake_s)
    if not record["next_wake"].get("armed"):
        print(f"[heartbeat] NO NEXT WAKE ARMED: {record['next_wake']}", file=sys.stderr)

    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    print(json.dumps(record, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
