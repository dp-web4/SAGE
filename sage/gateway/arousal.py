"""
Arousal: every event wakes the being.

dp, 2026-09-30 (SAGE #295):
  "events wake the being, and wake state continues for as long as it has something to do. the
   rest timer is a watchdog that wakes it if nothing else has. but a message from me, you, mesh
   watcher, words detected on audio, motion on video or imu - all should wake it."
  "wake indicates an active beat. there should not be artificial cap on beats, and if the being
   decides to stay awake continously because of environment or curiosity, then so be it."
  "the state display is an indicator not a control" / "the snarc is likewise an indicator not a
   control."

WHAT THIS REPLACES. Until #295 this module was a GRADED, REFRACTORY policy (dp, 2026-09-07:
"world inputs require engagement"): a fixed per-kind salience table with a 0.6 bar (a mesh
digest at 0.1 and any unknown kind at 0.2 never woke the being), an 8-minute refractory, a
"beat already due in 4 min" hold-back, a 60 s conversing refractory and an 8-beats-an-hour
cap. Each of those decided WHETHER or WHEN an event got a beat. They are gone. The salience
table stays, as a recorded value on each event, never as a gate.

WHAT DECIDES NOW. One thing only: whether a beat is already running.
  * No beat running: the event starts one now.
  * A beat running: the event is QUEUED. It goes into the pending set, and a successor is
    armed so the next beat starts as soon as the running one ends (`arm_next`). At beat end
    the heartbeat also checks the pending set itself, so an event is never left for the
    watchdog timer.

THE PENDING SET (`PENDING_PATH`, one per machine, like the wake marker). Every event is written
here first, before any start is attempted, so a failed start or a crashed caller leaves work
behind rather than losing it. A beat CLAIMS the set when it starts (it is moved aside and read,
so what arrives after the claim is pending for the next beat) and releases its claim when its
record is written. A claim left by a beat that died is absorbed by the next claim.

THE ONE FLOOD MECHANISM, and it drops nothing: an event whose `key` matches one already pending
is COALESCED into it (count and last time move). A sustained identical event is one entry, not
a hundred. Nothing else limits how often the being wakes; a beat that runs back-to-back with the
next is the being staying awake because there is something to do.

ON macOS THE SCHEDULER IS launchd, NOT systemd (McNugget, 2026-10-05). Until then every wake on
a Mac failed with "no systemctl", including dp's turns through the daemon. The being ran only on
its 30-minute launchd timer. The same three acts have launchd forms here, selected by `_backend()`:
  * start a beat: `launchctl kickstart gui/<uid>/<heartbeat label>`, with no -k, so a running
    beat is never killed;
  * is a beat running: `launchctl print` reports `state = running`;
  * start the next beat when this one ends: launchd has no transient unit ordered After= another,
    and a helper process started by the beat is killed with the beat's job. So arm_next drops one
    file named for the heartbeat label into a QueueDirectories folder. A separate launchd agent
    (`sage/scripts/launchd_next_beat.sh`, example plist in sage/gateway/launchd/) waits for the
    running beat to end, empties the queue and kickstarts the next beat. Two requests write the
    same file, so they coalesce into one next beat, as the systemd successor does.
"""
from __future__ import annotations

import fcntl
import json
import glob
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

# What a kind of event is worth, 0..1. RECORDED on the event and shown; never a gate (#295).
# A kind missing from the table is recorded at DEFAULT_SALIENCE and wakes the being like
# every other kind.
SALIENCE = {
    "dp_turn": 0.9,        # the operator speaking directly
    "peer_turn": 0.7,      # another being across the mesh
    "scope_decided": 0.7,  # an operator ruling the being asked for
    "seat_turn": 0.6,      # its seat leaving a turn
    "digest": 0.1,         # ambient fleet movement (a mesh watcher's digest)
    "sense": 0.3,          # a sense event from the cortex (presence); its own score is recorded when known
    "heard": 1.0,          # words heard on audio
}
DEFAULT_SALIENCE = 0.2

UNIT = os.environ.get("SAGE_HEARTBEAT_UNIT", "sage-heartbeat.service")
TIMER = os.environ.get("SAGE_HEARTBEAT_TIMER", "sage-heartbeat.timer")

# The successor: a transient unit, ordered After= the beat unit, that starts the beat unit.
# Measured on CBP 2026-09-30 with throwaway units (SAGE #295):
#   * a transient started with `systemd-run --no-block -p After=<beat>.service` waits while the
#     beat's start job runs, including its ExecStopPost, and runs 22 ms after it finishes. So
#     "start the next beat right after this one" does not race the running beat. (A plain
#     `systemctl start` on the running oneshot would be merged into its job and do nothing.)
#   * a second `systemd-run` with the same unit name while the first is waiting fails with
#     "already loaded", and the successor runs ONCE: two requests coalesce into one next beat.
#     While waiting, the unit shows LoadState=loaded, ActiveState=inactive and a Job id.
NEXT_UNIT = "sage-heartbeat-next"

# launchd (macOS). The heartbeat's label: $SAGE_HEARTBEAT_LABEL; else com.web4.sage-heartbeat.<SAGE_MACHINE>;
# else the one com.web4.sage-heartbeat.* agent installed for this user. The successor agent is the
# same label with "sage-heartbeat" -> "sage-heartbeat-next", watching NEXT_QUEUE_DIR.
NEXT_QUEUE_DIR = os.path.expanduser(os.getenv("SAGE_NEXT_BEAT_QUEUE", "~/.local/state/sage/next-beat"))


def _backend() -> str:
    """'systemd' or 'launchd'. $SAGE_WAKE_BACKEND decides when set (tests pin it). Otherwise
    launchd only where there is launchctl and no systemctl, which is a Mac."""
    explicit = os.getenv("SAGE_WAKE_BACKEND", "").strip().lower()
    if explicit in ("systemd", "launchd"):
        return explicit
    import shutil
    if shutil.which("systemctl") is None and shutil.which("launchctl") is not None:
        return "launchd"
    return "systemd"


def heartbeat_label() -> Optional[str]:
    explicit = os.getenv("SAGE_HEARTBEAT_LABEL", "").strip()
    if explicit:
        return explicit
    machine = os.getenv("SAGE_MACHINE", "").strip()
    if machine:
        return f"com.web4.sage-heartbeat.{machine}"
    found = sorted(glob.glob(os.path.expanduser("~/Library/LaunchAgents/com.web4.sage-heartbeat.*.plist")))
    found = [f for f in found if "sage-heartbeat-next." not in f]
    if len(found) == 1:
        return Path(found[0]).name[:-len(".plist")]
    return None


def _next_label(label: str) -> str:
    return label.replace("sage-heartbeat.", "sage-heartbeat-next.", 1)


def _gui(label: str) -> str:
    return f"gui/{os.getuid()}/{label}"


PENDING_PATH = os.path.expanduser(os.getenv("SAGE_PENDING_EVENTS", "~/.sprout/pending_events.json"))

# How long the successor may take to be collected after it fired, before a new one is armed.
# Firing is a single `systemctl start --no-block`; it is gone in well under a second.
_NEXT_SETTLE_S = 3.0


# ---------------------------------------------------------------------------------------------
# systemd, in one place, so tests can see (and refuse) every call

def _systemd_disabled() -> bool:
    """SAGE_NO_SYSTEMD=1: never run systemctl or systemd-run. The gateway and embodiment test
    conftests set it for every test (and subprocesses inherit it), so no test can start the real
    beat unit or arm a real successor on the machine it runs on."""
    return os.getenv("SAGE_NO_SYSTEMD", "") not in ("", "0")


def _systemd(args: list, timeout: float = 10) -> subprocess.CompletedProcess:
    """The one door to the scheduler, systemd or launchd: SAGE_NO_SYSTEMD closes both."""
    if _systemd_disabled():
        raise FileNotFoundError("systemd calls are disabled here (SAGE_NO_SYSTEMD)")
    return subprocess.run(args, text=True, capture_output=True, timeout=timeout)


def _sh(*args: str) -> str:
    try:
        return _systemd(list(args)).stdout.strip()
    except Exception:
        return ""


def _start_wake() -> dict:
    """Request a beat, reporting scheduler acceptance separately from execution.

    A successful nonblocking start only verifies/enqueues a job. It may coalesce with an
    existing job, or the service may subsequently fail. `started` is retained as null for
    compatibility: this caller has no beat-entry receipt, on success OR failure. A timeout
    leaves acceptance unknown; it must not cause an automatic retry of an uncertain request.
    """
    evidence = {"wake_evidence_version": 2, "started": None}
    if _backend() == "launchd":
        return {**evidence, **_start_wake_launchd()}
    try:
        p = _systemd(["systemctl", "--user", "start", "--no-block", UNIT])
    except FileNotFoundError:
        return {**evidence, "start_accepted": False,
                "wake_error": "no systemctl: wake request could not be submitted"}
    except Exception as e:
        return {**evidence, "start_accepted": None, "wake_error": f"{type(e).__name__}: {e}"}
    if p.returncode != 0:
        detail = (p.stderr or p.stdout or "").strip()[:300]
        # A client error can occur after submission (for example, losing the reply).
        # Without a structured rejection receipt, a nonzero exit is not proof of rejection.
        return {**evidence, "start_accepted": None,
                "wake_error": f"systemctl exit {p.returncode}: {detail}"}
    return {**evidence, "start_accepted": True}


def _start_wake_launchd() -> dict:
    """`launchctl kickstart` without -k: it starts the job if it is not running and never kills a
    running one. Same evidence contract as systemd: exit 0 is acceptance (not beat entry), no
    launchctl or no label is a definite non-submission, and any other failure is unknown."""
    label = heartbeat_label()
    if not label:
        return {"start_accepted": False,
                "wake_error": "no launchd heartbeat label (set SAGE_HEARTBEAT_LABEL or SAGE_MACHINE)"}
    try:
        p = _systemd(["launchctl", "kickstart", _gui(label)])
    except FileNotFoundError:
        return {"start_accepted": False, "wake_error": "no launchctl: wake request could not be submitted"}
    except Exception as e:
        return {"start_accepted": None, "wake_error": f"{type(e).__name__}: {e}"}
    if p.returncode != 0:
        detail = (p.stderr or p.stdout or "").strip()[:300]
        return {"start_accepted": None, "wake_error": f"launchctl exit {p.returncode}: {detail}"}
    return {"start_accepted": True}


def _launchd_state(label: str) -> str:
    """The job's `state = ...` line from `launchctl print`, or "" when it cannot be read."""
    for line in _sh("launchctl", "print", _gui(label)).splitlines():
        k, _, v = line.strip().partition(" = ")
        if k == "state":
            return v.strip()
    return ""


def delivery_text(woke: dict) -> str:
    """Plain-text delivery evidence, shared by the console and contract-tested with Rust.

    Old producers used started=true for scheduler acceptance. Never upgrade that legacy
    field to observed beat entry. An explicit new field, including null, takes precedence.
    """
    accepted = (woke.get("start_accepted") if "start_accepted" in woke
                else True if woke.get("started") is True else None)
    if accepted is True:
        return "recorded; wake request accepted; beat entry unconfirmed"
    why = woke.get("wake_error")
    why = why if isinstance(why, str) else "unknown reason"
    if accepted is False:
        return f"recorded; wake request was not accepted ({why}); awaiting a later beat"
    if woke.get("engage") is True:
        return f"recorded; wake request outcome unknown ({why}); beat entry unconfirmed"
    return "recorded; awaiting the next beat"


def beat_running() -> bool:
    if _backend() == "launchd":
        label = heartbeat_label()
        return bool(label) and _launchd_state(label) == "running"
    return _sh("systemctl", "--user", "is-active", UNIT) in ("active", "activating")


def _next_state() -> dict:
    out = _sh("systemctl", "--user", "show", NEXT_UNIT + ".service",
              "-p", "LoadState", "-p", "ActiveState", "-p", "Job")
    return dict(l.split("=", 1) for l in out.splitlines() if "=" in l)


def arm_next(*, _retry: bool = True) -> dict:
    """Make the next beat start as soon as the running one ends. Never raises.

    {"armed": True} when a successor is waiting on the beat unit, including one that was already
    waiting ("already_armed": the requests coalesced). A successor that has already fired but not
    yet been collected is not a waiting one: wait for it to go (bounded), then arm a new one."""
    if _backend() == "launchd":
        return _arm_next_launchd()
    cmd = ["systemd-run", "--user", "--no-block", "--collect", f"--unit={NEXT_UNIT}",
           "-p", f"After={UNIT}", "systemctl", "--user", "start", "--no-block", UNIT]
    try:
        p = _systemd(cmd, timeout=20)
    except FileNotFoundError as e:
        return {"armed": False, "error": str(e), "why": "the event stays pending for the next beat"}
    except Exception as e:
        return {"armed": False, "error": f"{type(e).__name__}: {e}",
                "why": "the event stays pending for the next beat"}
    if p.returncode == 0:
        return {"armed": True, "by": NEXT_UNIT}
    err = (p.stderr or p.stdout or "").strip()
    if "already loaded" in err or "already exists" in err:
        st = _next_state()
        if st.get("Job"):
            return {"armed": True, "by": NEXT_UNIT, "already_armed": True}
        if _retry:
            deadline = time.time() + _NEXT_SETTLE_S
            while time.time() < deadline and _next_state().get("LoadState") == "loaded":
                time.sleep(0.2)
            d = arm_next(_retry=False)
            d["after_a_fired_successor"] = True
            return d
    return {"armed": False, "error": f"systemd-run exit {p.returncode}: {err[:300]}",
            "why": "the event stays pending for the next beat"}


def _arm_next_launchd() -> dict:
    """One file per heartbeat label in NEXT_QUEUE_DIR: the successor agent's QueueDirectories
    starts it, it waits for the running beat to end, empties the queue and kickstarts the beat.
    Reports armed only when that agent is loaded: a queued file nobody watches is not a successor."""
    label = heartbeat_label()
    if not label:
        return {"armed": False, "error": "no launchd heartbeat label",
                "why": "the event stays pending for the next beat"}
    nxt = _next_label(label)
    try:
        q = Path(NEXT_QUEUE_DIR)
        q.mkdir(parents=True, exist_ok=True)
        f = q / label
        already = f.exists()
        f.write_text(f"{time.time():.3f}\n")
    except Exception as e:
        return {"armed": False, "error": f"{type(e).__name__}: {e}",
                "why": "the event stays pending for the next beat"}
    if not _launchd_state(nxt):
        return {"armed": False, "error": f"successor agent {nxt} is not loaded",
                "queued_file": str(f), "why": "the event stays pending for the next beat"}
    d = {"armed": True, "by": nxt}
    if already:
        d["already_armed"] = True
    return d


# ---------------------------------------------------------------------------------------------
# the pending set

def _pending_path(path: Optional[str] = None) -> Path:
    return Path(path or PENDING_PATH)


@contextmanager
def _locked(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path) + ".lock", "a+") as lk:
        fcntl.flock(lk.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lk.fileno(), fcntl.LOCK_UN)


def _read_set(p: Path) -> dict:
    try:
        d = json.loads(p.read_text())
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _write_set(p: Path, d: dict) -> None:
    tmp = p.with_name(p.name + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(d))
    os.replace(tmp, p)


def event_key(kind: str, descriptor: str) -> str:
    return f"{kind}:{' '.join(str(descriptor).split())}"


def add_pending(kind: str, descriptor: str, *, salience=None, key: Optional[str] = None,
                source: str = "", now: Optional[float] = None, path: Optional[str] = None) -> dict:
    """Put an event in the pending set, coalescing it into an identical one already there."""
    now = time.time() if now is None else now
    key = key or event_key(kind, descriptor)
    p = _pending_path(path)
    with _locked(p):
        s = _read_set(p)
        e = s.get(key)
        if e:
            e["count"] = int(e.get("count", 1)) + 1
            e["last_ts"] = round(now, 2)
        else:
            e = {"kind": kind, "descriptor": descriptor,
                 "salience": SALIENCE.get(kind, DEFAULT_SALIENCE) if salience is None else salience,
                 "source": source, "first_ts": round(now, 2), "last_ts": round(now, 2), "count": 1}
            s[key] = e
        _write_set(p, s)
    return dict(e, key=key)


def touch_pending(key: str, *, now: Optional[float] = None, path: Optional[str] = None) -> bool:
    """A sustained event persisting: count it into its pending entry if that is still pending.
    False when it is not (a beat has already claimed it): the persisting event is not new work."""
    p = _pending_path(path)
    with _locked(p):
        s = _read_set(p)
        if key not in s:
            return False
        s[key]["count"] = int(s[key].get("count", 1)) + 1
        s[key]["last_ts"] = round(time.time() if now is None else now, 2)
        _write_set(p, s)
    return True


def peek_pending(path: Optional[str] = None) -> list:
    p = _pending_path(path)
    with _locked(p):
        return [dict(v, key=k) for k, v in _read_set(p).items()]


def claim_pending(beat_id: str, path: Optional[str] = None) -> list:
    """At beat start: take everything pending, so what arrives from here on is pending for the
    NEXT beat. The set is moved to a claim file named for this beat; claims left by a beat that
    died before releasing them are absorbed into this one."""
    p = _pending_path(path)
    claim = p.with_name(f"{p.name}.claimed.{beat_id}")
    with _locked(p):
        merged = {}
        for orphan in sorted(p.parent.glob(p.name + ".claimed.*")):
            if orphan != claim:
                merged.update(_read_set(orphan))
                orphan.unlink(missing_ok=True)
        merged.update(_read_set(p))
        _write_set(claim, merged)
        p.unlink(missing_ok=True)
    return [dict(v, key=k) for k, v in merged.items()]


def claim_keys(beat_id: str, keys, path: Optional[str] = None) -> list:
    """Claim ONLY these pending events for `beat_id` (merged into its claim file); everything else stays
    pending for the next beat. GPT on #310: a preemption that answers one person must not consume
    unrelated late work, or a second person, as if this beat had met it. Returns what was claimed."""
    p = _pending_path(path)
    claim = p.with_name(f"{p.name}.claimed.{beat_id}")
    keys = [k for k in (keys or []) if k]
    with _locked(p):
        s = _read_set(p)
        took = {k: s.pop(k) for k in keys if k in s}
        if took:
            c = _read_set(claim)
            c.update(took)
            _write_set(claim, c)
            _write_set(p, s)
    return [dict(v, key=k) for k, v in took.items()]


def release_claim(beat_id: str, path: Optional[str] = None) -> None:
    """The beat's record is written: what it claimed has been met."""
    p = _pending_path(path)
    with _locked(p):
        p.with_name(f"{p.name}.claimed.{beat_id}").unlink(missing_ok=True)


# ---------------------------------------------------------------------------------------------
# the decision, and the response

# The kinds the running beat can hear mid-beat: turns in its conversations, which the loop's
# `interject` hook drains between steps (Legion carrier). Everything else waits for the next beat.
IN_FLIGHT_KINDS = frozenset({"dp_turn", "seat_turn"})


def decide(instance: Path, kind: str, *, now: Optional[float] = None) -> dict:
    """What an event gets. There is no threshold: every event gets a beat. The only question is
    whether one is running (then this event is queued behind it) or not (then it starts one).

    `engage` means "start a beat now", as the daemon (`delivery_text`) and the dp console read
    it. A queued event is `engage: False, queued: True`, and its reason says the next beat starts
    as soon as the running one ends."""
    sal = SALIENCE.get(kind, DEFAULT_SALIENCE)
    d = {"kind": kind, "salience": sal, "engage": False, "queued": False, "reason": ""}
    if beat_running():
        # QUEUED, ALWAYS (main #296): the next beat starts as soon as the running one ends, so no
        # event is dropped. AND, on this carrier, a CONVERSATION turn is also delivered INTO the
        # running beat: the loop drains new turns between steps (conversations.drain_new_for via
        # the `interject` hook, since 2026-09-09), so an already-awake being sees it within
        # seconds. Only conversation turns ride that hook; a sense event, a digest or a peer's
        # forum post does not, and claiming it would be a claim about a capability this tree does
        # not have (GPT review of SAGE#81).
        inflight = kind in IN_FLIGHT_KINDS
        d["queued"] = True
        d["beat_running"] = True
        d["delivered_in_flight"] = inflight
        d["reason"] = (("a beat is already running: the turn is delivered into it between steps, "
                        "so the being sees this within seconds; and the next beat starts as soon "
                        "as the running one ends") if inflight else
                       ("a beat is already running; this is queued, and the next beat starts as "
                        "soon as the running one ends"))
        return d
    d["engage"] = True
    d["reason"] = "every event wakes the being, and no beat is running"
    return d


def request_beat(kind: str, descriptor: str, *, salience=None, key: Optional[str] = None,
                 source: str = "", instance: Optional[Path] = None) -> dict:
    """An event happened: record it as pending, then start a beat or queue behind the running one.

    The wake marker (being_join) is written too, so the beat's record says who woke it."""
    d = decide(Path(instance or "."), kind)
    if salience is not None:
        d["salience"] = salience
    d["descriptor"] = descriptor
    try:
        d["pending"] = add_pending(kind, descriptor, salience=d["salience"], key=key, source=source)
    except Exception as e:
        d["pending_error"] = f"{type(e).__name__}: {e}"
    try:
        from sage.gateway.being_join import write_wake_marker
        write_wake_marker(descriptor, d["salience"])
    except Exception as e:
        d["marker_error"] = f"{type(e).__name__}: {e}"
    if d["engage"]:
        d.update(_start_wake())
        if d["start_accepted"] is not True:
            # An unsuccessful client may already have submitted the job. Do not turn
            # uncertain acceptance into a second request through the successor path.
            # The pending event remains available to a later event/beat/watchdog.
            d["fallback"] = "recorded; awaiting a later beat"
    else:
        d["next"] = arm_next()
    return d


def respond(instance: Path, kind: str, *, descriptor: str) -> dict:
    """A world input (a turn through /chat or /say, a dp console turn, anything a watcher sends).
    Every one wakes the being (#295)."""
    return request_beat(kind, descriptor, instance=instance, source=f"arousal:{kind}")


def after_beat(*, stay_awake: Optional[str] = None, path: Optional[str] = None) -> dict:
    """Called by the heartbeat as its last act before writing its record. If anything is pending
    (events that arrived during the beat), or the being asked to stay awake, the next beat is
    armed to start the moment this one ends. Otherwise nothing: the being rests, and the watchdog
    timer (OnUnitInactiveSec) counts 30 quiet minutes from this beat's end."""
    try:
        pending = peek_pending(path)
    except Exception as e:
        pending = []
        err = f"{type(e).__name__}: {e}"
    else:
        err = None
    d = {"pending": len(pending), "kinds": sorted({str(e.get("kind")) for e in pending}),
         "stay_awake": stay_awake}
    if err:
        d["pending_error"] = err
    if not pending and not stay_awake:
        d["continuing"] = False
        d["why"] = "nothing pending and the being did not ask to stay awake: rest"
        return d
    d["next"] = arm_next()
    d["continuing"] = bool(d["next"].get("armed"))
    d["why"] = ("the being asked to stay awake" if stay_awake and not pending
                else f"{len(pending)} event(s) pending" + ("; the being also asked to stay awake"
                                                           if stay_awake else ""))
    return d


# ---------------------------------------------------------------------------------------------
# turns that arrived while a beat ran

PEOPLE = ("dp",)                # operators; instance.json "arousal.people" adds to them


def _parse_iso(v) -> Optional[float]:
    from datetime import datetime, timezone
    try:
        return datetime.strptime(str(v)[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
    except Exception:
        return None


def flags(instance: Path) -> dict:
    try:
        d = json.loads((Path(instance) / "instance.json").read_text()).get("arousal") or {}
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def people(instance: Path) -> set:
    return set(PEOPLE) | {str(p) for p in (flags(instance).get("people") or [])}


def sender_kind(instance: Path, sender: str) -> Optional[str]:
    """The SALIENCE kind of a turn from `sender`. None: a heard voice, which presence queues
    itself, with the heard words."""
    if sender == "voice":
        return None
    if sender in people(instance):
        return "dp_turn"
    if sender.endswith("-claude"):
        return "seat_turn"
    return "peer_turn"


def late_turns(instance: Path, member: str, since: float) -> list:
    """Turns from someone else that arrived after `since` (the beat's start) and that the beat
    never showed the being. [(conversation id, turn)]. Bounded by `since` on purpose: an older
    unseen turn (one the context-fit ladder trimmed, say) must not re-queue a beat every beat."""
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
    """Turns that arrived while this beat ran go into the pending set, so `after_beat` starts the
    next beat for them. No opt-in, no salience bar, no refractory (#295; this was the opt-in
    "held wake" of 2026-09-27). Most of them are already pending, because the daemon's arousal
    call queued them when they arrived; this catches the ones that came in by another path.
    Coalesced by conversation and turn, so a turn is one entry however it got here."""
    late = late_turns(instance, member, since)
    if not late:
        return {"late": 0}
    kinds = []
    for cid, t in late:
        k = sender_kind(instance, str(t.get("from"))) or "peer_turn"
        kinds.append(k)
        try:
            add_pending(k, f"{t.get('from')} wrote in '{cid}' while your last beat was running",
                        key=f"turn:{cid}:{t.get('seq')}", source="heartbeat:late_turns", now=now)
        except Exception:
            pass
    return {"late": len(late), "from": sorted({str(t.get("from")) for _, t in late}),
            "kinds": sorted(set(kinds)), "queued": True}


def main(argv=None) -> int:
    """CLI so a non-Python caller uses THIS policy instead of reimplementing it.

    The Rust daemon (sage-rs conversations::arouse) runs
        python3 -m sage.gateway.arousal --instance <dir> --kind <kind> --descriptor <line>
    when a turn arrives through /chat or /conversations/:id/say, and reads the decision as JSON
    on stdout. A mesh watcher, or anything else that sees an event for the being, can run the
    same line with its own --kind (any kind wakes the being). Exit 0 always.

    --dry-run (or SAGE_AROUSAL_DRY_RUN=1, which the daemon passes through) decides and reports
    only: nothing is made pending, no marker, no unit started or armed.
    """
    import argparse
    ap = argparse.ArgumentParser(description="an event for the being: every one wakes it")
    ap.add_argument("--instance", required=True)
    ap.add_argument("--kind", required=True,
                    help=f"what happened; the recorded weights are {sorted(SALIENCE)}, any kind wakes")
    ap.add_argument("--descriptor", required=True, help="what happened, in one line")
    ap.add_argument("--dry-run", action="store_true", help="decide and report; never start a beat")
    a = ap.parse_args(argv)
    inst = Path(a.instance)
    flag = os.getenv("SAGE_AROUSAL_DRY_RUN", "").strip().lower()
    dry = a.dry_run or flag in ("1", "true", "yes")
    d = decide(inst, a.kind) if dry else respond(inst, a.kind, descriptor=a.descriptor)
    d.setdefault("descriptor", a.descriptor)
    if dry:
        d["dry_run"] = True
    print(json.dumps(d))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
