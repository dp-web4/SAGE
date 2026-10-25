#!/usr/bin/env python3
"""The ear without a cortex: Hearing (audio.py) and presence's heard-words wake, as one process.

On Sprout the ear rides inside the visual cortex (visual_cortex.py starts Hearing; perception.json carries
its state) and presence.py turns each heard line into a beat. A body with no cortex -- McNugget, a Mac with a
USB mic and no Jetson cameras (2026-10-17) -- had no host for the ear at all. This is that host, and nothing
more: the same Hearing, the same listening bounds, the same presence wake.

  * The ear's state is published to <body dir>/ear.json every PUBLISH_S, so the body block can say whether
    the ear is hearing and why not (body.perception reads it when no cortex reports).
  * Only WORDS wake the being. There is no perception.json here, so presence has no motion, onset or
    object events: a sound onset (music, a door) never wakes anything. dp, 2026-10-17, with music playing in
    the room: "only being directly addressed should wake it" -- run with SAGE_LISTEN=wake and SAGE_WAKE_NAME,
    so words become heard lines only after the being's name (listening.py).

Run as a service:  python -m sage.embodiment.ear   (SAGE_INSTANCE / SAGE_MEMBER as for presence.py)
"""
from __future__ import annotations

import json
import os
import threading
import time

from sage.embodiment import listening

EAR_STATE_PATH = os.path.join(listening.BODY_DIR, "ear.json")
PUBLISH_S = 0.5


def publish(state: dict, path: str = EAR_STATE_PATH) -> None:
    """Write the ear's state atomically (temp + rename), stamped with the time."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(dict(state, ts=round(time.time(), 2)), f)
    os.replace(tmp, path)


def _publisher(hearing, stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            publish(hearing.state())
        except Exception:
            pass   # the ear keeps hearing; the body block will call the state stale
        stop.wait(PUBLISH_S)


def _exit_on_term(signum, frame):
    raise SystemExit(0)


def main() -> int:
    from sage.embodiment.audio import Hearing
    from sage.embodiment.presence import Presence
    # STOPPING THE EAR STOPS ITS CAPTURE (McNugget, 2026-10-18). launchd stops a job with SIGTERM, whose
    # default ends the process without running `finally`, so hearing.stop() never ran and the ffmpeg child
    # kept the mic: the restarted ear's own capture then received ~30% of the audio (a 20 s recording beside
    # it got 5.7 s), and every addressed utterance reached whisper as fragments ("Okay." x28, dropped as
    # silence). SIGTERM is turned into SystemExit, so the finally below runs.
    import signal
    signal.signal(signal.SIGTERM, _exit_on_term)
    hearing = Hearing()
    hearing.start()
    stop = threading.Event()
    threading.Thread(target=_publisher, args=(hearing, stop), daemon=True).start()
    print(f"[ear] hearing; mode={'wake' if listening.wake_listening() else 'always' if listening.always_listening() else 'window'}"
          f" name={listening.WAKE_SAY!r} backend={listening.BACKEND} model={listening.MODEL_NAME}", flush=True)
    try:
        Presence().run()        # heard.jsonl -> a beat; no perception.json here, so words are the only events
    finally:
        stop.set()
        hearing.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
