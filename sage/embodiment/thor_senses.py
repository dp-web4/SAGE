#!/usr/bin/env python3
"""thor_senses — thor's sensorium, written in the contract `presence.py` already reads.

WHY THIS EXISTS. thor's `sage-daemon` has run 15.2 days with **total_cycles = 0**. Its model (qwen3.5:27b,
19.9 GB) is pulled but never loaded, ATP sits at exactly 100%, metabolic_state is `wake`, and five SNARC detectors
are armed. Nothing is wrong with the body. There was no input path: the only feeder in the tree, `presence.py`,
reads a visual cortex at ~/.sprout/perception.json, and thor has no cameras and never will.

WHAT THOR ACTUALLY PERCEIVES. Not a room — the work it does. Every field below is something thor already measures
and that already mattered today:

  * the model server it thinks with     (/health on :8899 — ok / degraded / busy / reserved GB)
  * whether a game is being played      (a live harness process, and the last game's result)
  * how a game ENDED                    (levels cleared, actions spent, budget death vs game over)
  * its own body's pressure             (memory available; the 60 GB reservation vs the being's 19.9 GB)
  * the fleet it belongs to             (peers answering on :8760 — the phone book was wrong for 3 months)

SALIENCE IS COMPUTED FROM CHANGE, NOT FROM LEVEL. A healthy idle machine is not interesting and must not wake
anything; a level cleared, a server going degraded, a peer appearing or vanishing is. Salience is deliberately
conservative because `presence.py` owns the wake discipline (bar, cooldown, hourly cap, dedup, gaze/rest) and this
file must not smuggle a second policy in beside it. Each SNARC axis is reported separately so the being's own
detectors do the interpreting:

  surprise — a state that contradicts the last one (server fell over, a run died)
  novelty  — a state not seen before in this process's memory
  arousal  — how much is happening at once (a run in flight, memory tight)
  conflict — two readings that cannot both be comfortable (a run active while the server is degraded)

WHAT IT DOES NOT DO. It never invents a reading. A source that cannot be read contributes NOTHING rather than a
zero — an unreachable peer is unknown, not absent, which is the same rule that cost this fleet three months when a
dead port read as a quiet fleet. Fields it could not read are named in `unread` so the being is never told a
silence is a fact.

Usage:
    SAGE_PERCEPTION=~/.thor/perception.json python3 -m sage.embodiment.thor_senses
    # then, reading the same file:
    SAGE_PERCEPTION=~/.thor/perception.json SAGE_PRESENCE_LOG=~/.thor/presence_log.jsonl \
      SAGE_SYS_ENGAGED="$(cat ...)" python3 -m sage.embodiment.presence
"""
from __future__ import annotations

import glob
import json
import os
import subprocess
import time
import urllib.request

OUT = os.path.expanduser(os.environ.get("SAGE_PERCEPTION", "~/.thor/perception.json"))
DIFFUSION = "http://127.0.0.1:8899/health"
RUNS = "/home/dp/ai-workspace/blackbox/runs"
FLEET = "/home/dp/ai-workspace/SAGE/sage/federation/fleet.json"
POLL_S = float(os.environ.get("THOR_SENSE_POLL_S", "5"))
# HEARTBEAT. A calm machine scores 0.0 and wakes nothing — correct, and indistinguishable from a dead wire. After
# this long with nothing salient, emit ONE reading at the wake bar that says it is a heartbeat. 0 disables it.
HEARTBEAT_S = float(os.environ.get("THOR_HEARTBEAT_S", "3600"))
HEARTBEAT_SALIENCE = float(os.environ.get("THOR_HEARTBEAT_SALIENCE", "0.50"))   # just over presence's 0.45 bar


def _get(url: str, timeout: float = 4.0):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None


def sense_model() -> tuple[dict, list[str]]:
    d = _get(DIFFUSION)
    if d is None:
        return {}, ["model_server"]
    return {"model_ok": bool(d.get("ok")), "model_degraded": bool(d.get("degraded")),
            "model_busy": bool(d.get("busy")), "model_reserved_gb": round(float(d.get("mem_reserved_gb") or 0), 1)}, []


def sense_play() -> tuple[dict, list[str]]:
    """Is a game being played, and how did the last one end?"""
    out: dict = {}
    unread: list[str] = []
    try:
        rc = subprocess.run(["pgrep", "-f", "^/usr/bin/python3 -u -c import harness" + "_runner"],
                            capture_output=True, text=True, timeout=8)
        out["playing"] = rc.returncode == 0
    except Exception:
        unread.append("playing")
    dirs = sorted(glob.glob(os.path.join(RUNS, "*", "harness_diag.json")), key=os.path.getmtime, reverse=True)
    if not dirs:
        unread.append("last_game")
        return out, unread
    try:
        ev = json.load(open(dirs[0])).get("events", [])
    except Exception:
        unread.append("last_game")
        return out, unread
    done = [e for e in ev if e.get("k") == "game_done"]
    if done:
        g = done[-1]
        out["last_game"] = str(g.get("gid", "?")).split("-")[0]
        out["last_levels"] = g.get("levels")
        out["last_actions"] = g.get("actions")
    else:
        unread.append("last_game")
    # how it ended: the loop files these three separately and a GAME OVER files none of them
    kinds = [e.get("k") for e in ev]
    out["ended_budget"] = "budget_death" in kinds or "budget_exhausted" in kinds
    out["ended_game_over"] = any(e.get("k") == "loop_exit" and e.get("why") == "game_over_outer" for e in ev)
    return out, unread


def sense_body() -> tuple[dict, list[str]]:
    try:
        mem = {}
        for line in open("/proc/meminfo"):
            k, _, v = line.partition(":")
            mem[k] = int(v.split()[0])
        avail_gb = mem.get("MemAvailable", 0) / 1048576.0
        return {"mem_available_gb": round(avail_gb, 1)}, []
    except Exception:
        return {}, ["body"]


def sense_fleet() -> tuple[dict, list[str]]:
    """Peers answering. An unreachable peer is UNKNOWN, never 'absent' — that conflation cost 3 months."""
    try:
        machines = json.load(open(FLEET))["machines"]
    except Exception:
        return {}, ["fleet"]
    answering, silent = [], []
    me = os.uname().nodename.lower()
    for name, info in machines.items():
        host, port = info.get("gateway_host"), info.get("gateway_port")
        if not host or name == me:
            continue
        d = _get(f"http://{host}:{port}/health", timeout=2.0)
        (answering if d else silent).append(name)
    return {"peers_answering": sorted(answering), "peers_silent": sorted(silent)}, []


class Senses:
    def __init__(self):
        self.prev: dict = {}
        self.seen: set = set()
        self.last_salient = time.time()   # a fresh sensor is not owed a heartbeat in its first interval
        self.beats = 0

    def snarc(self, cur: dict) -> dict:
        """surprise/novelty/arousal/conflict from CHANGE. A calm machine scores near zero on purpose."""
        p = self.prev
        surprise = 0.0
        # a reading that contradicts the previous one
        for k, weight in (("model_ok", 0.9), ("model_degraded", 0.9), ("playing", 0.3)):
            if k in cur and k in p and cur[k] != p[k]:
                surprise = max(surprise, weight)
        if "last_levels" in cur and "last_levels" in p and cur["last_levels"] != p["last_levels"]:
            surprise = max(surprise, 0.6)
        # a peer appearing or going silent
        if "peers_answering" in cur and "peers_answering" in p and cur["peers_answering"] != p["peers_answering"]:
            surprise = max(surprise, 0.7)

        key = json.dumps({k: cur.get(k) for k in
                          ("model_ok", "model_degraded", "playing", "last_game", "last_levels",
                           "ended_game_over", "peers_answering")}, sort_keys=True)
        novelty = 0.0 if key in self.seen else 0.8
        self.seen.add(key)

        arousal = 0.0
        if cur.get("playing"):
            arousal += 0.4
        if cur.get("model_busy"):
            arousal += 0.2
        if (cur.get("mem_available_gb") or 99) < 12:
            arousal += 0.4
        arousal = min(1.0, arousal)

        # two readings that cannot both be comfortable
        conflict = int(bool(cur.get("playing") and (cur.get("model_degraded") or not cur.get("model_ok"))))

        blended = min(1.0, max(surprise, novelty * 0.75, arousal * 0.6, conflict * 1.0))
        return {"salience": round(blended, 3), "surprise": round(surprise, 3),
                "novelty": round(novelty, 3), "arousal": round(arousal, 3), "conflict": conflict}

    def descriptor(self, cur: dict, unread: list[str]) -> str:
        """What thor would say it is sensing. Plain, first-person-able, and never asserts an unread field."""
        bits = []
        if "model_ok" in cur:
            if not cur["model_ok"] or cur.get("model_degraded"):
                bits.append("the model I think with is degraded")
            elif cur.get("model_busy"):
                bits.append("the model I think with is mid-thought")
            else:
                bits.append(f"the model I think with is steady, holding {cur.get('model_reserved_gb')} GB")
        if cur.get("playing"):
            bits.append("a game is being played through me right now")
        elif "playing" in cur:
            bits.append("no game is running")
        if cur.get("last_game"):
            lv, ac = cur.get("last_levels"), cur.get("last_actions")
            how = ("it ran out of its action budget" if cur.get("ended_budget")
                   else "the game ended on me" if cur.get("ended_game_over") else "it stopped")
            bits.append(f"the last world I played was {cur['last_game']}: {lv} level(s) in {ac} actions, {how}")
        if "mem_available_gb" in cur:
            bits.append(f"{cur['mem_available_gb']} GB of room left in this body")
        if cur.get("peers_answering"):
            bits.append("peers answering: " + ", ".join(cur["peers_answering"]))
        if cur.get("peers_silent"):
            bits.append("silent (unknown, not absent): " + ", ".join(cur["peers_silent"]))
        if unread:
            bits.append("could not sense: " + ", ".join(unread))
        return "; ".join(bits)

    def tick(self) -> dict:
        cur: dict = {}
        unread: list[str] = []
        for fn in (sense_model, sense_play, sense_body, sense_fleet):
            try:
                d, u = fn()
            except Exception:
                d, u = {}, [fn.__name__]
            cur.update(d)
            unread.extend(u)
        sal = self.snarc(cur)
        now = time.time()
        desc = self.descriptor(cur, unread)
        beat = False
        if sal["salience"] >= 0.45:
            self.last_salient = now
        elif HEARTBEAT_S > 0 and (now - self.last_salient) >= HEARTBEAT_S:
            # Raise ONLY the blended salience, and say what it is. surprise/novelty/arousal/conflict keep their
            # true values so no axis is ever falsified, and the descriptor states its own nature — a heartbeat
            # must not be readable as an event.
            self.beats += 1
            beat = True
            self.last_salient = now
            quiet_min = int((now - (self.prev.get("_hb_at") or now)) // 60) if False else int(HEARTBEAT_S // 60)
            sal = dict(sal)
            sal["salience"] = HEARTBEAT_SALIENCE
            # The BEAT NUMBER LEADS, because presence dedups on descriptor[:40] — with a fixed opening every
            # beat after the first is silently suppressed, which would turn the liveness signal back into the
            # silence it exists to break.
            desc = (f"Heartbeat {self.beats}: nothing has changed for about {quiet_min} minutes. This is a "
                    f"liveness beat, not an event — my senses are connected and the world they watch is quiet. "
                    f"What I can still see: {desc}")
        rec = {"ts": round(now, 2),
               "gaze": "open",                      # thor has no eyelids; it is always receptive
               "descriptor": desc,
               "coherence": None if unread else 1.0,  # nothing unread = the senses agree they are complete
               "salience": sal,
               "heartbeat": beat,
               "state": cur,
               "unread": unread}
        self.prev = cur
        return rec

    def run(self):
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        print(f"[thor_senses] writing {OUT} every {POLL_S}s", flush=True)
        while True:
            rec = self.tick()
            tmp = OUT + ".tmp"
            with open(tmp, "w") as f:
                json.dump(rec, f)
            os.replace(tmp, OUT)                    # atomic: presence.py must never read a half file
            time.sleep(POLL_S)


if __name__ == "__main__":
    import sys
    if "--once" in sys.argv:
        print(json.dumps(Senses().tick(), indent=1))
    else:
        Senses().run()
