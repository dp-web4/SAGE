"""gpu_window: a beat that rests for a held GPU courtesy window (scheme:
shared-context/machines/cbp-gpu-windows.md).

A requester (kimi, a seat's measurement run) writes a window file

    holder=<who>
    reason=<why>
    until_epoch=<unix seconds>

and while `now < until_epoch` a beat does not run: it rests. dp sanctioned this: "you can
suspend it for bounded periods of time (extend its rest between beats)". An expired or malformed
window is ignored, so a forgotten window cannot strand the being.

WHAT THIS ADDS TO THE REST (SAGE #295/#296). Under #296 every event starts a beat, so a beat
that rests for a window may be resting with work pending. Two things were missing:

  * WAKE AT THE WINDOW'S END. The events stay pending (never dropped), but nothing started a
    beat when the window expired, so they waited for the 30-minute watchdog. Now, when events
    are pending, a transient timer (`WINDOW_UNIT`) starts the beat unit at `until_epoch`. One
    fixed unit name, so every rest during one window coalesces into one timer. If the window has
    been extended by the time it fires, that beat rests again and arms again.
  * SAY WHY. The indicator showed plain rest. Now it is rest with source
    `heartbeat:gpu-window:<holder>` and a TTL to the window's end, so `/status` shows why.
    Owner `heartbeat`, not `gpu-window`: the daemon applies a rest only from the reporter that
    set the standing state (activity.rs), and what stands when a window-rested beat starts is
    often the previous beat's `heartbeat:end:continuing` hand-off. No beat_id is sent, so the
    daemon's beat counter (#298) does not count a rested beat as a beat.

CLI:  python3 -m sage.gateway.gpu_window check [--window PATH] [--now EPOCH]
  exit 3  a window is held: the beat rests (the rest is logged, reported, and armed)
  exit 0  no window, an expired or malformed one, or ANY error: the beat runs
Why 3, not 1: a Python crash (an import error, say) also exits 1. Keyed on 3, a broken helper
fails OPEN, and the being beats as it did before windows existed. Keyed on 1, a broken helper
would rest the being forever. The courtesy is the thing to lose, not the being.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone
from typing import Callable, Optional

HELD = 3

# Where the window lives. The requester and the beat must agree on it; SAGE_GPU_WINDOW moves it.
DEFAULT_WINDOW = "~/.local/state/cbp-gpu-window"

# The transient timer that starts the beat unit when the window ends.
WINDOW_UNIT = "sage-heartbeat-window"

# Start the beat this long after until_epoch, so the beat's own check sees the window expired
# (it rests while now < until_epoch).
WAKE_MARGIN_S = 2


def window_path(path: Optional[str] = None) -> str:
    return os.path.expanduser(path or os.getenv("SAGE_GPU_WINDOW") or DEFAULT_WINDOW)


def read_window(path: Optional[str] = None, now: Optional[float] = None) -> Optional[dict]:
    """The held window, or None (no file, unreadable, no integer until_epoch, or expired)."""
    now = time.time() if now is None else now
    try:
        with open(window_path(path)) as f:
            lines = f.read().splitlines()
    except OSError:
        return None
    kv = {}
    for line in lines:
        if "=" in line:
            k, v = line.split("=", 1)
            kv.setdefault(k.strip(), v.strip())   # first line wins, as the old `head -1` did
    try:
        until = int(kv.get("until_epoch", ""))
    except ValueError:
        return None
    if now >= until:
        return None
    return {"holder": kv.get("holder") or "unknown", "reason": kv.get("reason") or "no reason given",
            "until_epoch": until}


def arm_at_window_end(until_epoch: int, now: Optional[float] = None, systemd: Optional[Callable] = None) -> dict:
    """Start the beat unit when the window ends. Never raises.

    {"armed": True} when a timer is waiting, including one another rest in this window already
    armed ("already_armed": the requests coalesced)."""
    from sage.gateway import arousal
    run = systemd or arousal._systemd
    now = time.time() if now is None else now
    secs = max(1, int(until_epoch - now) + WAKE_MARGIN_S)
    cmd = ["systemd-run", "--user", "--no-block", "--collect", f"--unit={WINDOW_UNIT}",
           f"--on-active={secs}s",
           # accuracy: the default is a minute; the being waits on this
           "--timer-property=AccuracySec=1s",
           # an elapsed timer must unload, so the next window can arm under the same name
           "--timer-property=RemainAfterElapsed=no",
           "systemctl", "--user", "start", "--no-block", arousal.UNIT]
    why = "the events stay pending; the watchdog timer or the next event starts the beat"
    try:
        p = run(cmd, timeout=20)
    except Exception as e:
        return {"armed": False, "error": f"{type(e).__name__}: {e}", "why": why}
    if p.returncode == 0:
        return {"armed": True, "by": WINDOW_UNIT, "in_secs": secs}
    err = (p.stderr or p.stdout or "").strip()
    if "already loaded" in err or "already exists" in err:
        try:
            st = run(["systemctl", "--user", "show", WINDOW_UNIT + ".timer", "-p", "ActiveState"]).stdout
        except Exception:
            st = ""
        if "ActiveState=active" in st:
            return {"armed": True, "by": WINDOW_UNIT, "already_armed": True}
    return {"armed": False, "error": f"systemd-run exit {p.returncode}: {err[:300]}", "why": why}


def rest_for_window(w: dict, now: Optional[float] = None, *, pending: Optional[Callable] = None,
                    systemd: Optional[Callable] = None, report: Optional[Callable] = None) -> dict:
    """This beat rests for window `w`. Arm a beat at its end if work is pending; report why."""
    from sage.gateway import activity, arousal
    now = time.time() if now is None else now
    d = {"resting": True, "holder": w["holder"], "until_epoch": w["until_epoch"]}
    try:
        items = (pending or arousal.peek_pending)()
    except Exception as e:
        items = []
        d["pending_error"] = f"{type(e).__name__}: {e}"
    d["pending"] = len(items)
    if items:
        d["next"] = arm_at_window_end(w["until_epoch"], now=now, systemd=systemd)
    ttl = max(1, int(w["until_epoch"] - now))
    try:
        d["reported"] = bool((report or activity.report)(
            "rest", f"heartbeat:gpu-window:{w['holder']}", ttl_secs=ttl))
    except Exception:
        d["reported"] = False
    return d


def log_line(w: dict, d: dict, now: float) -> str:
    t = lambda e: datetime.fromtimestamp(e, timezone.utc)
    line = (f"[cbp-heartbeat] {t(now):%Y-%m-%dT%H:%MZ} resting: GPU window held by {w['holder']} "
            f"until {t(w['until_epoch']):%H:%MZ} ({w['reason']})")
    if d.get("pending"):
        nxt = d.get("next") or {}
        line += (f"; {d['pending']} event(s) pending, "
                 + ("a beat is armed for the window's end" if nxt.get("armed")
                    else f"NOT armed ({nxt.get('error', 'unknown')}): {nxt.get('why', '')}"))
    return line


def main(argv=None) -> int:
    try:
        import argparse
        ap = argparse.ArgumentParser(description="rest a beat for a held GPU courtesy window")
        ap.add_argument("cmd", choices=["check"])
        ap.add_argument("--window", default=None, help=f"window file (default ${{SAGE_GPU_WINDOW}} or {DEFAULT_WINDOW})")
        ap.add_argument("--now", type=float, default=None, help=argparse.SUPPRESS)
        a = ap.parse_args(argv)
        now = time.time() if a.now is None else a.now
        w = read_window(a.window, now)
        if not w:
            return 0
        d = rest_for_window(w, now)
        print(log_line(w, d, now), flush=True)
        return HELD
    except BaseException as e:   # fail OPEN: a broken helper must not rest the being
        try:
            print(f"[gpu_window] check failed, the beat runs: {type(e).__name__}: {e}", file=sys.stderr)
        except Exception:
            pass
        return 0


if __name__ == "__main__":
    sys.exit(main())
