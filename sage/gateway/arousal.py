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

UNIT = "sage-heartbeat.service"
TIMER = "sage-heartbeat.timer"


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
        # The conversation block is composed at beat START, so a turn arriving mid-beat is
        # not in the beat that is running. On legion/mission-artifact the tool loop drains
        # new turns between steps (conversations.drain_new_for via an `interject` hook) and
        # this branch said so; that hook is not on main, so saying it here would be a claim
        # about a capability this tree does not have (GPT review of SAGE#81). Until the
        # interject slice lands: recorded, read at the next beat, and no in-flight delivery.
        d["reason"] = ("a beat is already running and composed its state before this turn "
                       "arrived; the turn is recorded and will be read at the next beat")
        d["beat_running"] = True
        d["delivered_in_flight"] = False
        return d

    since = None
    end = last_beat_end(instance)
    if end is not None:
        since = now - end
        if since < REFRACTORY_S:
            d["reason"] = (f"refractory: only {int(since)}s since the last beat ended "
                           f"({REFRACTORY_S}s). Engaging again this soon shreds attention "
                           f"across fragments of the same exchange")
            d["refractory_s_left"] = int(REFRACTORY_S - since)
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
