"""activity — tell the daemon what the being is doing, so its state display is true (SAGE #291).

dp, 2026-09-30: "only actual state should be shown, and it should reflect what the being is
doing. the state display is an indicator not a control."

The beat runs here, in the gateway, and calls Ollama directly. Until #291 it never told the
daemon anything, so `:8760/status` showed a free-running 10-second ATP oscillator instead.
Now the beat reports as it goes:

    beat start, explore, posture, account  -> wake
    reflect, answer                        -> wrap-up
    beat end (every exit path)             -> rest, or wake ("heartbeat:end:continuing") when
                                              the next beat is already armed (SAGE #295)

and the consolidation unit reports dream while `sage.memory.consolidation` runs, then rest
(from its ExecStartPre/ExecStopPost: consolidation.py itself is pre-registered to make no
network calls, F4).

BEST-EFFORT, ALWAYS. The display is an indicator; a beat must never wait on it or fail
because of it. Every report has a short timeout, swallows every error, and logs one line to
stderr. A daemon that is down costs a beat at most REPORT_TIMEOUT_S per report. A report
that never lands is covered by the daemon's own staleness decay: an unrefreshed wake decays
to rest after its TTL.

CLI (for systemd units):  python3 -m sage.gateway.activity <state> <source> [--ttl SECONDS]
Always exits 0.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from typing import Optional

# Loopback only: the daemon refuses /activity from anywhere else.
ACTIVITY_URL = f"http://127.0.0.1:{os.getenv('SAGE_PORT', '8760')}/activity"

# A report is a few hundred bytes to loopback. Anything slower means the daemon is not
# answering, and the beat must not wait on it.
REPORT_TIMEOUT_S = 0.5

# How long a beat's report stands without a refresh before the daemon decays it to rest.
# The beat unit's own bound: sage/gateway/systemd/sage-heartbeat.service.example sets
# TimeoutStartSec=1500, and systemd's default TimeoutStopSec (90 s) is the window a killed
# beat has to write its record (heartbeat.BeatKilled). A machine whose unit sets a different
# TimeoutStartSec exports SAGE_BEAT_TIMEOUT_S to match.
BEAT_TTL_S = int(os.getenv("SAGE_BEAT_TIMEOUT_S", "1500")) + 90

STATES = ("wake", "wrap-up", "dream", "rest", "crisis")



def enabled() -> bool:
    """SAGE_ACTIVITY_REPORT=0 turns reporting off. sage/gateway/tests/conftest.py sets it for
    every test, so no suite ever reports to the live daemon on this machine's :8760. Read at
    call time, so a test can turn it back on against its own fake daemon."""
    return os.getenv("SAGE_ACTIVITY_REPORT", "1") != "0"

_reported_active = False


def report(state: str, source: str, beat_id: Optional[str] = None,
           ttl_secs: Optional[int] = None, url: Optional[str] = None,
           timeout: float = REPORT_TIMEOUT_S) -> bool:
    """Tell the daemon what the being is doing. True if it was accepted. Never raises."""
    global _reported_active
    if not enabled():
        return False
    try:
        if state not in STATES:
            raise ValueError(f"unknown state {state!r}")
        body = {"state": state, "source": source}
        if beat_id:
            body["beat_id"] = beat_id
        if ttl_secs:
            body["ttl_secs"] = int(ttl_secs)
        req = urllib.request.Request(url or ACTIVITY_URL, data=json.dumps(body).encode(),
                                     headers={"content-type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            ok = 200 <= r.status < 300
        if ok and state != "rest":
            _reported_active = True
        return ok
    except Exception as e:  # the indicator must never break what it indicates
        print(f"[activity] report {state} ({source}) not delivered: {type(e).__name__}: {e}",
              file=sys.stderr)
        return False


def reported_active() -> bool:
    """Whether this process has reported a non-rest state (so it owes a rest at its end)."""
    return _reported_active


# How long a hand-off to the next beat stands before it decays to rest. The next beat reports
# wake within seconds of starting; if it never starts (its ExecCondition failed, the unit is
# broken), the display must not say wake for a whole beat's TTL.
HANDOFF_TTL_S = 300


def end(source: str, beat_id: Optional[str] = None, url: Optional[str] = None,
        continuing: bool = False) -> bool:
    """The beat is over. Report rest, but only if this process reported something else first: a
    beat that exited before it began (no identity.json) must not overwrite another reporter's state.

    `continuing` (SAGE #295): the next beat is already armed because work is pending or the being
    asked to stay awake. Wake continues: report wake as a hand-off (`<source>:continuing`, bounded by
    HANDOFF_TTL_S), never rest, so back-to-back beats show no rest between them. The daemon counts a
    beat as ended on either report (a source whose phase starts with "end")."""
    global _reported_active
    if not _reported_active:
        return False
    if continuing:
        ok = report("wake", f"{source}:continuing", beat_id=beat_id, ttl_secs=HANDOFF_TTL_S, url=url)
    else:
        ok = report("rest", source, beat_id=beat_id, url=url)
    _reported_active = False
    return ok


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="report the being's activity to the local daemon (best-effort)")
    ap.add_argument("state", choices=STATES)
    ap.add_argument("source")
    ap.add_argument("--ttl", type=int, default=None, help="seconds this report stands unrefreshed")
    ap.add_argument("--beat-id", default=None)
    try:
        a = ap.parse_args(argv)
    except SystemExit:
        return 0   # a unit's ExecStartPre must not fail the job over its indicator
    report(a.state, a.source, beat_id=a.beat_id, ttl_secs=a.ttl)
    return 0


if __name__ == "__main__":
    sys.exit(main())
