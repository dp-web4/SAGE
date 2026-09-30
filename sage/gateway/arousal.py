"""
Arousal — a metabolic response to world input.

dp, 2026-09-07: *"we should have metabolic response to events. beat is default idle state.
world inputs require engagement."*

That is a correction to what the heartbeat had become. A 30-minute timer is a fine IDLE
rhythm — it exists so a being has a reason to look around when nothing is happening — but
it had become the ONLY rhythm, which makes every arriving thing wait an average of fifteen
minutes for attention regardless of what it is. dp posted a turn and immediately asked how
frequent the beats were, which is the question you ask when the system has no answer to
"something just happened".

So: the timer is the floor, not the clock. A world input carries salience, and salience
above the engagement threshold wakes the being now.

WHAT MAKES THIS METABOLIC RATHER THAN AN INTERRUPT.

  * It is GRADED. Not everything that arrives deserves a beat. dp speaking directly is not
    the same event as a seat leaving a note, and neither is the same as a peer digest
    moving. Each carries a weight, and only weights above the threshold spend a beat.
  * It is REFRACTORY. After engaging, there is a period in which the being does not engage
    again, however loud the world gets. Without it a burst of five turns is five beats, the
    GPU thrashes, and the being's attention is shredded across fragments of the same
    conversation — the opposite of engagement.
  * It COSTS something. A beat is ~18 minutes of the only GPU on this machine. Waking is
    an expenditure and the record says what it was spent on, so "was that worth a beat"
    stays an answerable question instead of a feeling.

WHAT IT IS NOT: a way for anything outside to seize the being's attention on demand. The
threshold, the refractory period and the weights live here, in the seat's code, not in the
event. A caller says what happened; this decides what it is worth.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

# What a kind of world input is worth, 0..1. These are a starting posture, not a finding:
# they are the seat's guess at what deserves ~18 minutes of GPU, and they should move when
# the record says they are wrong.
SALIENCE = {
    # The operator speaking directly. dp is asynchronous by rule, so a turn from dp is rare
    # and is the strongest signal the being gets that someone is actually present.
    "dp_turn": 0.9,
    # A peer being reaching across the mesh: another body, which is the only source of
    # facts this being cannot gather itself.
    "peer_turn": 0.7,
    # An operator ruling on something it asked for — it has been waiting, sometimes days.
    "scope_decided": 0.7,
    # A seat leaving a turn. This sat at 0.4, below the threshold, on the argument that a
    # seat can reach the being at the next beat anyway. dp's stated vision of the beat
    # (2026-09-12) is the opposite: "a message from you or me wakes it immediately to
    # respond." The refractory period, not a low salience, is what stops a seat that sends
    # three turns in a row from spending three beats; and a seat turn that is not worth a
    # beat is a turn the seat should not have sent.
    "seat_turn": 0.6,
    # Ambient fleet movement. Real information, no urgency.
    "digest": 0.1,
}

ENGAGE_AT = 0.6          # at or above this, spend a beat now
REFRACTORY_S = 8 * 60    # after engaging, do not engage again this soon
IMMINENT_S = 4 * 60      # a beat already this close: let it arrive rather than racing it
UNIT = os.environ.get("SAGE_HEARTBEAT_UNIT", "sage-heartbeat.service")
TIMER = os.environ.get("SAGE_HEARTBEAT_TIMER", "sage-heartbeat.timer")


def _sh(*args: str) -> str:
    try:
        return subprocess.run(args, text=True, capture_output=True, timeout=10).stdout.strip()
    except Exception:
        return ""


def _start_wake() -> dict:
    """Start the beat unit now, and say whether that actually happened.

    `_sh` discards the exit code and turns every exception into "", so `started` used to be
    True whenever the POLICY said engage, including on a host with no systemctl (McNugget is
    launchd-managed), with no such user unit (CBP runs its beats from cron), or with a unit
    that failed to start (GPT review of SAGE#81). The record and the UI said "waking now"
    when nothing woke. Now `started` is the observed result, and a failure carries the
    reason; the turn is still recorded and waits for the ordinary beat."""
    try:
        p = subprocess.run(["systemctl", "--user", "start", "--no-block", UNIT],
                           text=True, capture_output=True, timeout=10)
    except FileNotFoundError:
        return {"started": False,
                "wake_error": "no systemctl on this host: its beats are not systemd user units "
                              "(launchd on macOS, or cron); the turn waits for the ordinary beat"}
    except Exception as e:
        return {"started": False, "wake_error": f"{type(e).__name__}: {e}"}
    if p.returncode != 0:
        detail = (p.stderr or p.stdout or "").strip()[:300]
        return {"started": False, "wake_error": f"systemctl exit {p.returncode}: {detail}"}
    return {"started": True}


def beat_running() -> bool:
    return _sh("systemctl", "--user", "is-active", UNIT) in ("active", "activating")


def seconds_to_next_beat() -> Optional[int]:
    """From `list-timers --output=json`, which reports raw microseconds. The `show -p`
    forms are not usable here: NextElapseUSecRealtime is empty for an OnUnitActiveSec
    timer, and the monotonic one renders a human-readable duration."""
    try:
        rows = json.loads(_sh("systemctl", "--user", "list-timers", TIMER, "--output=json") or "[]")
        return int(int(rows[0]["next"]) / 1_000_000 - time.time())
    except (ValueError, KeyError, IndexError, TypeError):
        return None


def last_beat_end(instance: Path) -> Optional[float]:
    try:
        rec = json.loads((Path(instance) / "heartbeats.jsonl")
                         .read_text(errors="replace").strip().splitlines()[-1])
        return float(rec["t0"]) + float(rec.get("elapsed_s") or 0)
    except Exception:
        return None


def _parse_iso(v) -> Optional[float]:
    from datetime import datetime, timezone
    try:
        return datetime.strptime(str(v)[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
    except Exception:
        return None


def decide(instance: Path, kind: str, *, now: Optional[float] = None) -> dict:
    """Should this event spend a beat? Returns the decision AND its reasoning, because a
    wake policy that cannot say why it declined is indistinguishable from one that is
    broken — the failure this codebase keeps meeting from the other side."""
    now = now if now is not None else time.time()
    sal = SALIENCE.get(kind, 0.2)
    d = {"kind": kind, "salience": sal, "engage": False, "reason": ""}

    if sal < ENGAGE_AT:
        d["reason"] = (f"salience {sal} is below the engagement threshold {ENGAGE_AT}; "
                       f"it will be read at the next scheduled beat")
        return d
    if beat_running():
        # This used to be a consolation ("it will see this when it reads its state") that
        # was not true within the beat: the conversation block is composed at beat start,
        # so a turn arriving mid-beat waited for the next one. Since 2026-09-09 the loop
        # drains new turns between steps (conversations.drain_new_for via an `interject`
        # hook) and an already-awake being is the FASTEST case, not the slowest.
        #
        # RECONCILIATION 2026-09-18: main carried the opposite claim, correctly, because
        # the interject slice had not landed there ("saying it here would be a claim about
        # a capability this tree does not have", GPT review of SAGE#81). This merge lands
        # it, so the capability is present and the claim is true again. main's
        # test_a_running_beat_does_not_claim_in_flight_delivery is inverted with it.
        d["reason"] = ("a beat is already running: the turn is delivered into it between "
                       "steps, so the being sees this within seconds without a new beat")
        d["beat_running"] = True
        d["delivered_in_flight"] = True
        return d

    since = None
    end = last_beat_end(instance)
    if end is not None:
        since = now - end
        refr, why = refractory_s(instance, now)
        d["refractory"] = why
        if since < refr:
            d["reason"] = (f"refractory: only {int(since)}s since the last beat ended "
                           f"({refr}s; {why}). Engaging again this soon shreds attention "
                           f"across fragments of the same exchange")
            d["refractory_s_left"] = int(refr - since)
            # DEFER, do not drop. This used to return here and the input waited for the
            # idle timer — up to 30 minutes for a turn that had earned a beat, because it
            # arrived 3 minutes too early. Measured 2026-09-13T07:45Z: two seat turns
            # correcting a broken fixture, declined at 298s, nothing armed. dp's vision is
            # "a message wakes it immediately"; the refractory bounds HOW SOON, it must
            # not decide WHETHER.
            d["deferred_s"] = d["refractory_s_left"] + 1
            return d

    nxt = seconds_to_next_beat()
    if nxt is not None and 0 <= nxt <= IMMINENT_S:
        d["reason"] = f"a beat is already due in {nxt}s; racing it would waste one"
        d["next_beat_s"] = nxt
        return d

    d["engage"] = True
    d["reason"] = f"salience {sal} >= {ENGAGE_AT} and the being is idle"
    if since is not None:
        d["idle_s"] = int(since)
    return d


def respond(instance: Path, kind: str, *, descriptor: str) -> dict:
    """Register a world input and, if it earns one, wake the being now.

    The wake marker is written whatever the decision, so a beat that arrives on the timer
    still learns that something specific happened and what it was. Only the systemd start
    is conditional."""
    from sage.gateway.being_join import write_wake_marker
    d = decide(instance, kind)
    d["descriptor"] = descriptor
    try:
        write_wake_marker(descriptor, d["salience"])
    except Exception as e:
        d["marker_error"] = f"{type(e).__name__}: {e}"
    if d["engage"]:
        d.update(_start_wake())
        if not d["started"]:
            d["fallback"] = "recorded; it will be read at the next scheduled beat"
    elif d.get("deferred_s"):
        d.update(_arm_deferred_wake(d["deferred_s"]))
    return d


DEFERRED_UNIT = "sage-heartbeat-deferred-wake"


def _arm_deferred_wake(seconds: int, *, retry: bool = True) -> dict:
    """One-shot transient timer that starts the beat when the refractory period ends.

    ONE pending at a time: the unit name is fixed on purpose, so a second engage-worthy
    input inside the same refractory window finds the timer already armed and rides it.
    heartbeat.py's fallback wake uses a unique name for the opposite reason — there a
    collision meant a missing wake; here it means the wake is already coming.

    `--no-block` on the start is load-bearing. Without it the transient service blocks
    until the BEAT finishes (measured 2026-09-13T07:48Z: timer and service both
    active/running two minutes after firing, the whole beat long), the pair is never
    collected, and the next deferral collides with a timer that has already fired — an
    `already_armed` for a wake that is not coming. So a collision is believed only if the
    timer is actually WAITING; a stale pair is cleared and the arm retried once."""
    try:
        subprocess.run(["systemd-run", "--user", "--collect", f"--on-active={seconds}s",
                        f"--unit={DEFERRED_UNIT}",
                        "systemctl", "--user", "start", "--no-block", UNIT],
                       capture_output=True, text=True, timeout=20, check=True)
        return {"deferred": True, "deferred_by": DEFERRED_UNIT}
    except subprocess.CalledProcessError as e:
        err = (e.stderr or "").strip()
        if "already loaded" in err or "already exists" in err:
            if _deferred_timer_waiting():
                return {"deferred": True, "deferred_by": DEFERRED_UNIT, "already_armed": True}
            if retry:
                for suffix in (".timer", ".service"):
                    _sh("systemctl", "--user", "stop", DEFERRED_UNIT + suffix)
                    _sh("systemctl", "--user", "reset-failed", DEFERRED_UNIT + suffix)
                d = _arm_deferred_wake(seconds, retry=False)
                d["cleared_stale"] = True
                return d
        return {"deferred": False, "error": f"systemd-run exit {e.returncode}: {err}",
                "why": "the input waits for the idle timer"}
    except Exception as e:
        return {"deferred": False, "error": f"{type(e).__name__}: {e}",
                "why": "the input waits for the idle timer"}


def _deferred_timer_waiting() -> bool:
    """True only if the deferred timer exists AND has not fired yet."""
    try:
        out = subprocess.run(["systemctl", "--user", "show", DEFERRED_UNIT + ".timer",
                              "-p", "SubState", "--value"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return False
    return out == "waiting"


# THE HELD WAKE AND CONVERSATION MODE (dp, 2026-09-27: "should we speed up the beat cadence?" ->
# not the timer). Both are OPT-IN per instance (cbp-claude's pre-review of #239: fleet-wide they
# would lower CBP's refractory to 60 s on 77% of beats, because its being `say`s to its seat
# nearly every beat, on a shared GPU that has crashed from VRAM starvation). instance.json:
#   "arousal": {"held_wake": true, "conversation_mode": true, "people": ["dp"]}
CONVERSING_WINDOW_S = 15 * 60
CONVERSING_REFRACTORY_S = 60
MAX_BEATS_PER_HOUR = 8          # conversation mode's brake: past this, the ordinary pause returns
PEOPLE = ("dp",)                # operators; instance.json "people" adds to them


def _parse_iso(v) -> Optional[float]:
    from datetime import datetime, timezone
    try:
        return datetime.strptime(str(v)[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
    except Exception:
        return None


def flags(instance: Path) -> dict:
    """The instance's arousal opt-ins. Absent -> all off, which is today's behaviour."""
    try:
        d = json.loads((Path(instance) / "instance.json").read_text()).get("arousal") or {}
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def people(instance: Path) -> set:
    return set(PEOPLE) | {str(p) for p in (flags(instance).get("people") or [])}


def sender_kind(instance: Path, sender: str) -> Optional[str]:
    """What a turn from `sender` is worth, as a SALIENCE kind. None: not this path's to wake
    (a heard voice: presence holds that wake itself, with the heard words)."""
    if sender == "voice":
        return None
    if sender in people(instance):
        return "dp_turn"
    if sender.endswith("-claude"):
        return "seat_turn"
    return "peer_turn"


def _recent_turns(instance: Path, since: float, until: Optional[float] = None):
    from sage.gateway import conversations as conv
    for m in conv.listing(Path(instance)):
        for t in conv.recent(Path(instance), m["id"], limit=200):
            ts = _parse_iso(t.get("ts"))
            if ts is not None and ts >= since and (until is None or ts <= until):
                yield m, t, ts


def beats_last_hour(instance: Path, now: float) -> int:
    n = 0
    try:
        for line in (Path(instance) / "heartbeats.jsonl").read_text(errors="replace").splitlines()[-40:]:
            try:
                if now - float(json.loads(line).get("t0") or 0) <= 3600:
                    n += 1
            except Exception:
                continue
    except Exception:
        return 0
    return n


def conversing(instance: Path, now: Optional[float] = None) -> tuple:
    """(bool, why). A live exchange with a PERSON: within CONVERSING_WINDOW_S a person wrote to
    the being AND the being spoke (say/speak). The being talking to its seat is not this."""
    now = now if now is not None else time.time()
    if not flags(instance).get("conversation_mode"):
        return False, "conversation mode is off for this instance"
    ppl = people(instance)
    heard_person = spoke = False
    try:
        for m, t, ts in _recent_turns(instance, now - CONVERSING_WINDOW_S, now):
            if t.get("from") in ppl:
                heard_person = True
            if t.get("via") in ("say", "speak") and not str(m["id"]).endswith("-claude"):
                spoke = True          # the being's own turn, anywhere but a seat's channel
    except Exception:
        return False, "conversations unreadable"
    if heard_person and spoke:
        return True, f"a person wrote and the being spoke within {CONVERSING_WINDOW_S // 60} min"
    return False, "no live exchange with a person"


def refractory_s(instance: Path, now: Optional[float] = None) -> tuple:
    """(seconds, why): short in a live exchange with a person, unless the beat cap is reached."""
    now = now if now is not None else time.time()
    live, why = conversing(instance, now)
    if live:
        n = beats_last_hour(instance, now)
        if n >= MAX_BEATS_PER_HOUR:
            return REFRACTORY_S, f"{why}, but {n} beats in the last hour (cap {MAX_BEATS_PER_HOUR})"
        return CONVERSING_REFRACTORY_S, f"conversing: {why}"
    return REFRACTORY_S, why


def late_turns(instance: Path, member: str, since: float) -> list:
    """Turns from someone else that arrived after `since` (the beat's start) and that the beat
    never showed the being. [(conversation id, turn)]. Bounded by `since` on purpose: an older
    unseen turn (one the context-fit ladder trimmed, say) must not re-arm a wake every beat.
    Heard voice is left to presence, which holds that wake with the words."""
    from sage.gateway import conversations as conv
    out = []
    try:
        for m in conv.listing(Path(instance)):
            if member not in (m.get("participants") or []) or m["id"] == "room":
                continue
            for t in conv.awaiting(Path(instance), m["id"], member):
                ts = _parse_iso(t.get("ts"))
                if t.get("from") not in (member, "voice") and ts is not None and ts >= since:
                    out.append((m["id"], t))
    except Exception:
        return []
    return out


def wake_for_late_turns(instance: Path, member: str, since: float, now: Optional[float] = None) -> dict:
    """THE HELD WAKE. A turn that arrives while a beat runs is declined by decide() ("a beat is
    already running ... read at the next beat") and nothing re-arms it: measured on Sprout, 2 of
    13 dp turns since 09-25 waited ~31 min for the idle timer. The beat that just ran knows which
    turns it never showed; it arms the deferred wake for them, held to the same salience bar as
    decide() and after the refractory pause. Opt-in (instance.json arousal.held_wake).
    Not a complete close: a turn landing after this runs but before the unit exits, or a beat
    killed before it gets here, still falls back to the idle timer."""
    late = late_turns(instance, member, since)
    if not late:
        return {"late": 0}
    if not flags(instance).get("held_wake"):
        return {"late": len(late), "armed": False, "why": "held_wake is off for this instance"}
    now = now if now is not None else time.time()
    kinds = {k for k in (sender_kind(instance, str(t.get("from"))) for _, t in late) if k}
    sal = max((SALIENCE.get(k, 0.2) for k in kinds), default=0.0)
    who = sorted({str(t.get("from")) for _, t in late})
    d = {"late": len(late), "from": who, "kinds": sorted(kinds), "salience": sal}
    if sal < ENGAGE_AT:
        d.update(armed=False, why=f"salience {sal} is below {ENGAGE_AT}; read at the next beat")
        return d
    refr, why = refractory_s(instance, now)
    d["refractory"] = why
    d.update(_arm_deferred_wake(max(1, int(refr))))
    if d.get("deferred"):
        try:
            from sage.gateway.being_join import write_wake_marker
            write_wake_marker(f"{', '.join(who)} wrote while your last beat was running", sal)
        except Exception:
            pass
    return d


def main(argv=None) -> int:
    """CLI so a non-Python caller uses THIS policy instead of reimplementing it.

    The Rust daemon (sage-rs conversations::arouse) runs
        python3 -m sage.gateway.arousal --instance <dir> --kind <kind> --descriptor <line>
    when a turn arrives through /chat or /conversations/:id/say, and reads the decision as
    JSON on stdout. Encoding the weights and the refractory period a second time in Rust
    would make two producers of one fact. Exit 0 whether or not it engaged: "declined, and
    here is why" is a successful answer.

    This entry point existed (042ef5eae) and was lost when 723c04d73 rewrote the end of the
    file on legion/mission-artifact; the daemon then read empty stdout, reported "arousal
    policy unreadable", and never woke the being (GPT review of SAGE#81). Pinned now by a
    real module invocation in test_arousal.py and a real daemon turn in
    test_daemon_conversations.py.

    --dry-run (or SAGE_AROUSAL_DRY_RUN=1 in the process environment, which the daemon
    passes through to this subprocess) decides and reports only: no wake marker, no
    systemd start, no deferred timer.
    """
    import argparse
    import os as _os
    ap = argparse.ArgumentParser(description="metabolic response to a world input")
    ap.add_argument("--instance", required=True)
    ap.add_argument("--kind", required=True, help=f"one of {sorted(SALIENCE)} (unknown = quiet)")
    ap.add_argument("--descriptor", required=True, help="what happened, in one line")
    ap.add_argument("--dry-run", action="store_true", help="decide and report; never start a beat")
    a = ap.parse_args(argv)
    inst = Path(a.instance)
    flag = _os.getenv("SAGE_AROUSAL_DRY_RUN", "").strip().lower()
    dry = a.dry_run or flag in ("1", "true", "yes")
    d = decide(inst, a.kind) if dry else respond(inst, a.kind, descriptor=a.descriptor)
    d.setdefault("descriptor", a.descriptor)
    if dry:
        d["dry_run"] = True
    print(json.dumps(d))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
