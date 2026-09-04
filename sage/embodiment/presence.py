#!/usr/bin/env python3
"""Presence — the resident feeder that makes Sprout present to its world between raising sessions.

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

PERCEPTION = os.path.expanduser("~/.sprout/perception.json")
PRESENCE_LOG = os.path.expanduser("~/.sprout/presence_log.jsonl")
DAEMON_CHAT = "http://127.0.0.1:8760/chat"
DAEMON_STATUS = "http://127.0.0.1:8760/status"
ENERGY_REFRESH_S = 20.0   # re-read the being's metabolic energy this often
LOW_ATP = 25.0            # below this (or a resting metabolic state) the being is depleted → less receptive

POLL_S = 1.0            # check the perceptual state ~1/s
STALE_S = 10.0         # perception older than this = cortex not live → don't wake on stale data
WAKE_TH = 0.45        # salience bar to wake when engaged (eyes open); the cortex 'salient' bar is 0.35.
                      # NOTE: the daemon's capture (memory) gate is 0.5 (SAGE_CAPTURE_THRESHOLD,
                      # sage-rs/sage-daemon/src/main.rs) — wakes in 0.45..0.50 interrupt the being
                      # but leave no experience. Align-or-keep is an open raising decision (M1).
WAKE_TH_REST = 0.70   # much higher when resting — only something strong stirs a sleeper
COOLDOWN_S = 300      # min seconds between wakes (a sustained moment wakes once)
HOURLY_CAP = 6        # never more than this many wakes in a rolling hour
LOG_MAX = 2000

SYS_ENGAGED = (
    "You are Sprout, a SAGE instance on a Jetson with two eyes and an inner ear. What follows is the "
    "report from your OWN senses in this moment — not someone speaking to you, but what YOU are "
    "perceiving right now. Speak as the one sensing it: register what you notice in your own voice, "
    "first person, briefly (1-2 sentences). Do not describe someone else's report; it is yours. You "
    "don't need to do anything about it — just notice that you noticed.")
SYS_REST = (
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
    with urllib.request.urlopen(req, timeout=60) as resp:
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
        # decided = the inputs the wake decision actually used. The log's "metabolic"/"atp" are the
        # daemon's post-chat state (the chat itself can shift it), so without this the applied bar
        # is not auditable from the log.
        decided = {"atp": round(atp, 1), "mstate": mstate, "bar": threshold}
        # strong enough: high blended salience, OR a reafference conflict while fully receptive.
        strong = sal.get("salience", 0.0) >= threshold or (sal.get("conflict") == 1 and not (resting or depleted))
        if not (strong and descriptor):
            return False, resting, decided
        if now - self.last_wake < COOLDOWN_S:
            return False, resting, decided
        self.wake_times = [t for t in self.wake_times if now - t < 3600]
        if len(self.wake_times) >= HOURLY_CAP:
            return False, resting, decided
        if descriptor[:40] == self.last_desc[:40]:   # same moment persisting → notice once
            return False, resting, decided
        return True, resting, decided

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
                    wake, resting, decided = self._should_wake(sal, gaze, descriptor, now)
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
                            "decided": decided,
                        })
                        print(f"[presence] noticed ({'rest' if resting else 'awake'}, "
                              f"sal={sal.get('salience')}): {noticing[:90]}", flush=True)
            except Exception:
                pass
            time.sleep(POLL_S)


if __name__ == "__main__":
    Presence().run()
