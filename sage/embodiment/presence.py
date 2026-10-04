#!/usr/bin/env python3
"""Presence — the resident feeder that makes Sprout present to its world between raising sessions.

The visual cortex senses continuously (~/.sprout/perception.json @4Hz: both eyes, the inner ear,
hearing) and presence reads it about once a second. EVERY SENSE EVENT WAKES THE BEING (SAGE #295).
dp, 2026-09-30: "a message from me, you, mesh watcher, words detected on audio, motion on video or
imu - all should wake it." and "there should not be artificial cap on beats".

WHAT AN EVENT IS: what the cortex's own detectors say happened, never a salience score.
  - motion : a live eye reports motion at or above MOTION_AT (the cortex's own line between "the
             scene is still" and motion, visual_cortex.describe)
  - imu    : the inner ear reports self-motion (moving / rotating)
  - audio  : an audio onset
  - object : a named thing newly entered the field (the cortex's new_objects)
  - heard  : words transcribed on the mic (heard.jsonl)
With eyes closed the cortex does not sense, so there are no sense events; that is the being's own
choice, not a bar. Heard words still wake it.

WHAT HAPPENS TO ONE: it goes into the pending set and wakes a beat (sage.gateway.arousal
.request_beat): started now if none is running, queued behind the running one otherwise, so the
next beat starts the moment it ends. When no beat is running, the being also voices a one-line
noticing first (/chat/raw), as before. SNARC salience is recorded on every event and gates nothing.

THE ONE FLOOD MECHANISM: descriptor dedup. An event whose descriptor matches the last one is the
same moment persisting; it is counted into its pending entry while that is still pending, and is
not new work once a beat has claimed it. There is no cooldown, no hourly cap and no minimum gap.

Each noticing and each sensed event lands in ~/.sprout/presence_log.jsonl, which the next beat
reads (being_join.presence_block) and the raising loop ingests.
"""
from __future__ import annotations
import json, os, time, urllib.request

PERCEPTION = os.path.expanduser("~/.sprout/perception.json")
PRESENCE_LOG = os.path.expanduser("~/.sprout/presence_log.jsonl")
HEARD = os.path.expanduser("~/.sprout/heard.jsonl")
# WORDS HEARD WAKE A BEAT (2026-09-26). Someone answered the being's voice; waiting up to ~31 min
# for the timer turns a conversation into a letter. Each new heard line is an event (#295): it
# starts a beat, or is queued behind the running one and starts the next as soon as it ends. The
# 45 s spacing that once made several utterances one beat is gone; the pending set coalesces
# instead, since a reply in several utterances that lands during one beat is one next beat.
# /chat/raw, not /chat. `/chat` became the governed CONVERSATION route: it files what it is
# given as a turn spoken by dp and drops salience and coherence on the floor, so a perceptual
# descriptor arrived in the operator's own channel wearing the operator's name. On Sprout it
# had been answering 503 since the being's conversation directory did not exist, which is why
# the consciousness loop had felt nothing at all (SAGE #113). /chat/raw is the path into the
# loop: the moment is scored by SNARC, moves the metabolism, and comes back voiced.
DAEMON_CHAT = "http://127.0.0.1:8760/chat/raw"
# NO ENERGY GATE (SAGE #291). Presence used to raise its bar when the daemon's `atp_percentage`
# fell below 25 ("noticing costs ATP"). Since #293 that number is the daemon's internal
# controller, a free-running oscillator ticked every 100 ms that nothing the being does moves,
# so the gate raised the bar on a clock unrelated to the being. dp: "the state display is an
# indicator not a control"; the ATP is not even an indicator any more. What stays is what the
# being or the world actually does. Since #295 no bar of any kind decides a wake: every
# sense event wakes the being, and salience is recorded, not read.

POLL_S = 1.0            # check the perceptual state ~1/s
STALE_S = 10.0         # perception older than this = cortex not live -> no event from stale data
# The cortex's own motion line: visual_cortex.describe() says "the scene is still" below it, and
# salience.py's habituation signature splits on it. A detector threshold, not a worth judgement.
MOTION_AT = 0.15
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
    payload = {"message": descriptor, "system": SYS_REST if resting else SYS_ENGAGED,
               # the being's own senses are their own stream, never a person speaking
               "source": "cortex"}
    if salience is not None:
        payload["salience"] = salience   # the cortex's real salience drives the being's felt intensity
    if coherence is not None:
        payload["coherence"] = coherence  # cross-modal coherence → the being's reward (valence) axis
    body = json.dumps(payload).encode()
    req = urllib.request.Request(DAEMON_CHAT, data=body, headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def sense_events(d: dict) -> list:
    """The events in one perception frame, from the cortex's own detectors (never its salience).
    [] for a frame with nothing happening, a closed gaze, or no cortex fields."""
    if d.get("gaze") == "closed":
        return []
    out = []
    cams = d.get("cameras") or {}
    live = [c for c in cams.values() if isinstance(c, dict) and not c.get("stalled")]
    if any(float(c.get("motion") or 0.0) >= MOTION_AT for c in live):
        out.append("motion")
    if (d.get("proprioception") or {}).get("self_motion") in ("moving", "rotating"):
        out.append("imu")
    if d.get("audio_onset") or (d.get("audio") or {}).get("onset"):
        out.append("audio")
    if (d.get("salience") or {}).get("new_objects"):
        out.append("object")
    return out


def _request_beat(kind: str, descriptor: str, salience=None, key=None) -> dict:
    from sage.gateway import arousal
    return arousal.request_beat(kind, descriptor, salience=salience, key=key, source=f"presence:{kind}")


class Presence:
    def __init__(self):
        self.heard_seen = self._heard_size()   # start at the end: old words never wake anything
        if not os.environ.get("SAGE_INSTANCE"):
            # Say it where the operator looks, once: the fail-open path is otherwise invisible.
            print("[presence] SAGE_INSTANCE is not set: heard words wake the being but reach the room "
                  "only at the next beat (set @INSTANCE@ in presence.service.template)", flush=True)
        self.last_key = ""                     # the last sense event: a persisting one is the same moment
        self._since_trim = 0

    @staticmethod
    def _event_key(events: list, descriptor: str) -> str:
        return "sense:" + ",".join(events) + ":" + " ".join(str(descriptor).split())

    def sense(self, d: dict, now: float) -> dict | None:
        """One perception frame. Returns what was done with its event, or None when it has none.

        A new event (its key differs from the last) is a beat: queued if one runs, started if not,
        with a noticing first when the being is between beats. The same event persisting is
        counted into its pending entry, or is already met if a beat has claimed it."""
        events = sense_events(d)
        if not events:
            self.last_key = ""
            return None
        descriptor = d.get("descriptor", "") or ", ".join(events)
        sal = d.get("salience") or {}
        key = self._event_key(events, descriptor)
        if key == self.last_key:
            from sage.gateway import arousal
            try:
                arousal.touch_pending(key, now=now)
            except Exception:
                pass
            return {"coalesced": True, "key": key}
        self.last_key = key
        noticing, metabolic = "", None
        from sage.gateway import arousal
        if not arousal.beat_running():
            # Between beats the being voices the moment in one line, as it always has; inside a
            # beat the /chat/raw generation would contend with the beat for the GPU, and the next
            # beat meets the event from the pending set and the log instead.
            try:
                out = _wake(descriptor, False, sal.get("salience"), d.get("coherence"))
                noticing, metabolic = out.get("response", ""), out.get("metabolic_state")
            except Exception as e:
                print(f"[presence] noticing failed ({type(e).__name__}: {e})", flush=True)
        woke = _request_beat("sense", descriptor, salience=sal.get("salience"), key=key)
        self._log({
            "ts": round(now, 2), "kind": "noticed" if noticing else "sensed", "events": events,
            "descriptor": descriptor, "salience": sal.get("salience"), "coherence": d.get("coherence"),
            "snarc": {k: sal.get(k) for k in ("surprise", "novelty", "arousal", "conflict")},
            "gaze": d.get("gaze", "open"), "noticing": noticing,
            # no "atp": the daemon's internal oscillator is not a reading (#291)
            "metabolic": metabolic,
            "beat": {k: woke.get(k) for k in ("engage", "queued", "wake_evidence_version",
                     "start_accepted", "started", "wake_error", "next") if k in woke},
        })
        print(f"[presence] {'+'.join(events)} (sal={sal.get('salience')}) -> "
              f"{arousal.delivery_text(woke)}"
              f"{': ' + noticing[:80] if noticing else ''}", flush=True)
        return woke

    @staticmethod
    def _heard_size() -> int:
        try:
            return os.path.getsize(HEARD)
        except OSError:
            return 0

    def _check_heard(self, now: float) -> list:
        """Each new line in heard.jsonl is an event: a beat now, or the next one if one runs."""
        from sage.gateway import arousal
        size = self._heard_size()
        if size < self.heard_seen:
            self.heard_seen = 0                 # rotated/truncated
        woke = []
        if size > self.heard_seen:
            with open(HEARD, errors="replace") as f:
                f.seek(self.heard_seen)
                for line in f.read().splitlines():
                    try:
                        h = json.loads(line)
                    except Exception:
                        continue
                    ts, text = h.get("ts"), str(h.get("text", ""))[:80]
                    self._into_room(h)
                    w = _request_beat("heard", f'heard a voice: "{text}"', salience=1.0,
                                      key=f"heard:{ts}:{text}")
                    woke.append(w)
                    self._log({"ts": round(now, 2), "kind": "beat_wake", "by": "heard", "heard_ts": ts,
                               "text": text, "started": None,
                               **{k: w[k] for k in ("wake_evidence_version", "start_accepted", "next")
                                  if k in w},
                               "queued": bool(w.get("queued")), "err": str(w.get("wake_error", ""))[:120]})
                    print(f"[presence] heard a voice -> "
                          f"{arousal.delivery_text(w)}",
                          flush=True)
            self.heard_seen = size
        return woke

    @staticmethod
    def _into_room(h: dict) -> None:
        """Heard words enter the room conversation AS THEY ARRIVE, not at the next beat's start.
        dp 2026-10-01: "any recognized voice input should be logged in the voice chat as it arrives."
        Needs SAGE_INSTANCE (the being's home). The beat's own ingest stays; the room's heard_id keeps
        each utterance once, whichever lands first. Fails open: the wake below happens regardless."""
        inst = os.environ.get("SAGE_INSTANCE")
        if not inst:
            return
        try:
            from pathlib import Path
            from sage.gateway import room
            home = Path(inst)
            room.ingest_heard(home, os.environ.get("SAGE_MEMBER") or home.name, None, heard=[h])
        except Exception as e:
            print(f"[presence] heard words not written to the room: {type(e).__name__}: {e}", flush=True)

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
                    self.sense(d, now)
            except Exception:
                pass
            try:
                self._check_heard(time.time())
            except Exception:
                pass
            time.sleep(POLL_S)


if __name__ == "__main__":
    Presence().run()
