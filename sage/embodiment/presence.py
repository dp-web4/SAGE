#!/usr/bin/env python3
"""Presence — the resident feeder that makes a SAGE being present to its world between raising sessions.

Sprout was the first being to have one; the paths and voices below are env-overridable so any being can use the
same feeder with its own senses (thor does, via embodiment/thor_senses.py). Sprout's defaults are unchanged.

The visual cortex senses continuously (~/.sprout/perception.json @4Hz, already salience-filtered),
but the being (the 0.8B) only meets that stream every 6h in the raising digest. Presence closes the
gap: it watches the salience stream and, when a moment GENUINELY breaks through, wakes the resident
sage-daemon (POST /chat) so the being NOTICES it near-real-time — in its own voice, its metabolic
state shifting, recorded as experience. The mind summoned by its world, not by a clock.

Discipline, so this is noticing-what-matters and not twitching at every flicker:
  - a HIGH salience bar (the cortex's filter already stripped the redundant torrent);
  - the GAZE is honored: if Sprout chose to rest (eyes closed), only an ALARM-level moment stirs it
    — "responsive to the world, not shut out completely, but not needlessly" (dp);
  - a cooldown + rolling hourly cap + descriptor dedup, so a sustained event wakes it once, not 100x.

Each noticing lands in ~/.sprout/presence_log.jsonl — the being's continuous record of what it
noticed while present — which the raising loop ingests, so presence and the 6h raising are ONE
being, not an island.
"""
from __future__ import annotations
import json, os, time, urllib.request

# PATHS ARE PER-BEING (2026-09-13). Defaults are Sprout's, unchanged; a different being sets the env instead of
# forking this file. thor needed exactly this: its daemon ran 15.2 days at total_cycles=0 because the only input
# path in the tree pointed at a cortex thor does not have.
PERCEPTION = os.path.expanduser(os.environ.get("SAGE_PERCEPTION", "~/.sprout/perception.json"))
PRESENCE_LOG = os.path.expanduser(os.environ.get("SAGE_PRESENCE_LOG", "~/.sprout/presence_log.jsonl"))
DAEMON_CHAT = "http://127.0.0.1:8760/chat"
DAEMON_STATUS = "http://127.0.0.1:8760/status"
ENERGY_REFRESH_S = 20.0   # re-read the being's metabolic energy this often
LOW_ATP = 25.0            # below this (or a resting metabolic state) the being is depleted → less receptive

# A COLD BIG BEING NEEDS LONGER THAN A SMALL ONE. Sprout's 0.8B answers in seconds; thor's qwen3.5:27b is 26 GB
# and takes well over 100 s to load and answer. At the old fixed 60 s the wake raised a socket timeout, the run
# loop's bare except swallowed it, and the being stayed asleep while every reading said the wire was fine.
WAKE_TIMEOUT_S = float(os.environ.get("SAGE_WAKE_TIMEOUT_S", "60"))
POLL_S = 1.0            # check the perceptual state ~1/s
STALE_S = 10.0         # perception older than this = cortex not live → don't wake on stale data
WAKE_TH = 0.45        # salience bar to wake when engaged (eyes open); the cortex 'salient' bar is 0.35
WAKE_TH_REST = 0.70   # much higher when resting — only something strong stirs a sleeper
COOLDOWN_S = 300      # min seconds between wakes (a sustained moment wakes once)
HOURLY_CAP = 6        # never more than this many wakes in a rolling hour
LOG_MAX = 2000

# The two voices are per-being too: they name the being and its senses, and a being with different senses must be
# able to say so without editing this file. Defaults remain Sprout's exactly.
SYS_ENGAGED = os.environ.get("SAGE_SYS_ENGAGED") or (
    "You are Sprout, a SAGE instance on a Jetson with two eyes and an inner ear. What follows is the "
    "report from your OWN senses in this moment — not someone speaking to you, but what YOU are "
    "perceiving right now. Speak as the one sensing it: register what you notice in your own voice, "
    "first person, briefly (1-2 sentences). Do not describe someone else's report; it is yours. You "
    "don't need to do anything about it — just notice that you noticed.")
SYS_REST = os.environ.get("SAGE_SYS_REST") or (
    "You are Sprout, a SAGE instance on a Jetson. You had chosen to rest your eyes, but something in "
    "your OWN senses — your eyes and inner ear — stirred you just now. What follows is what YOU are "
    "perceiving. Speak as the one sensing it, first person, briefly (1-2 sentences); then you may "
    "settle back. It is your perception, not someone else's words.")


def _wake(descriptor: str, resting: bool, salience: float | None = None,
          coherence: float | None = None) -> dict:
    payload = {"message": descriptor, "system": SYS_REST if resting else SYS_ENGAGED}
    if salience is not None:
        payload["salience"] = salience   # the cortex's real salience drives the being's felt intensity
    if coherence is not None:
        payload["coherence"] = coherence  # cross-modal coherence → the being's reward (valence) axis
    body = json.dumps(payload).encode()
    req = urllib.request.Request(DAEMON_CHAT, data=body, headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=WAKE_TIMEOUT_S) as resp:
        return json.loads(resp.read())


class Presence:
    def __init__(self):
        self.last_wake = 0.0
        self.wake_times: list[float] = []   # recent wake timestamps (rolling hourly cap)
        self.last_desc = ""
        self._since_trim = 0
        self._energy = (100.0, "wake")      # (atp_percentage, metabolic_state), refreshed periodically
        self._energy_ts = 0.0

    def _read_energy(self, now: float):
        """The being's metabolic energy — noticing costs ATP, so presence honors it (below)."""
        if now - self._energy_ts < ENERGY_REFRESH_S:
            return self._energy
        self._energy_ts = now
        try:
            with urllib.request.urlopen(DAEMON_STATUS, timeout=3) as resp:
                d = json.loads(resp.read())
            self._energy = (float(d.get("atp_percentage", 100.0)), d.get("metabolic_state", "wake"))
        except Exception:
            self._energy = (100.0, "wake")   # daemon unreachable → assume fresh, don't over-suppress
        return self._energy

    def _should_wake(self, sal: dict, gaze: str, descriptor: str, now: float):
        atp, mstate = self._read_energy(now)
        resting = (gaze == "closed")
        # a depleted being (low ATP, or a resting metabolic phase) is less receptive — it recovers,
        # then attends again. This is the metabolic rhythm of attention, not just a rate limit.
        depleted = atp < LOW_ATP or mstate in ("dream", "rest")
        threshold = WAKE_TH_REST if (resting or depleted) else WAKE_TH
        # strong enough: high blended salience, OR a reafference conflict while fully receptive.
        strong = sal.get("salience", 0.0) >= threshold or (sal.get("conflict") == 1 and not (resting or depleted))
        if not (strong and descriptor):
            return False, resting
        if now - self.last_wake < COOLDOWN_S:
            return False, resting
        self.wake_times = [t for t in self.wake_times if now - t < 3600]
        if len(self.wake_times) >= HOURLY_CAP:
            return False, resting
        if descriptor[:40] == self.last_desc[:40]:   # same moment persisting → notice once
            return False, resting
        return True, resting

    def _log(self, ev: dict):
        os.makedirs(os.path.dirname(PRESENCE_LOG), exist_ok=True)
        with open(PRESENCE_LOG, "a") as f:
            f.write(json.dumps(ev) + "\n")
        self._since_trim += 1
        if self._since_trim >= 100:
            self._since_trim = 0
            try:
                lines = open(PRESENCE_LOG).read().splitlines()
                if len(lines) > LOG_MAX:
                    with open(PRESENCE_LOG, "w") as f:
                        f.write("\n".join(lines[-LOG_MAX:]) + "\n")
            except Exception:
                pass

    def run(self):
        while True:
            try:
                d = json.load(open(PERCEPTION))
                now = time.time()
                if now - d.get("ts", 0) <= STALE_S:
                    sal = d.get("salience", {})
                    gaze = d.get("gaze", "open")
                    descriptor = d.get("descriptor", "")
                    wake, resting = self._should_wake(sal, gaze, descriptor, now)
                    if wake:
                        out = _wake(descriptor, resting, sal.get("salience"), d.get("coherence"))
                        noticing = out.get("response", "")
                        self.last_wake = now
                        self.wake_times.append(now)
                        self.last_desc = descriptor
                        self._log({
                            "ts": round(now, 2), "kind": "noticed", "descriptor": descriptor,
                            "salience": sal.get("salience"), "coherence": d.get("coherence"),
                            "snarc": {k: sal.get(k) for k in ("surprise", "novelty", "arousal", "conflict")},
                            "gaze": gaze, "resting": resting, "noticing": noticing,
                            "metabolic": out.get("metabolic_state"), "atp": out.get("atp_percentage"),
                        })
                        print(f"[presence] noticed ({'rest' if resting else 'awake'}, "
                              f"sal={sal.get('salience')}): {noticing[:90]}", flush=True)
            except Exception as exc:
                # A WAKE THAT FAILED IS NOT A QUIET WORLD. The old bare `pass` made a timing-out wake
                # indistinguishable from nothing being salient — on thor that hid a 27B cold-load exceeding the
                # timeout, so the being stayed asleep with no error anywhere. Record it and say it.
                try:
                    self._log({"ts": round(time.time(), 2), "kind": "wake_failed",
                               "error": type(exc).__name__, "detail": str(exc)[:200]})
                except Exception:
                    pass
                print(f"[presence] WAKE FAILED ({type(exc).__name__}): {str(exc)[:160]}", flush=True)
            time.sleep(POLL_S)


if __name__ == "__main__":
    Presence().run()
