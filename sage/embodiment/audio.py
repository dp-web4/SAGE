#!/usr/bin/env python3
"""Hearing — the Airhug mic as Sprout's ear.

Continuous ambient sound level + onset detection, folded into perception (see + feel + HEAR) and
salience (a sudden sound is a surprise). Enables cross-modal binding: a sound AND a visual motion
together is more real than either alone — the second cross-check, after vision↔IMU.

Captures via `pw-record` (pipewire) from the Airhug HFP source, 16 kHz mono s16le, in fixed 0.1s
windows, computing RMS loudness. The mic is mono, so hearing gives LEVEL + ONSET, not direction.

Self-heals with the same liveness discipline as the camera: `ok` is a *liveness* signal (audio
received recently), and if the stream dies (BT drop / pw-record exit) it respawns on a cooldown —
just as `_recover_camera` reopens a stalled eye. Fails open: no mic → vision/IMU still work.
"""
from __future__ import annotations
import subprocess, threading, time, struct, math

SOURCE = "bluez_input.41_42_5A_A0_6B_ED.0"   # Airhug HFP mic (stable node name)
RATE = 16000
WIN = 1600                # 0.1s windows
FULL_SCALE = 3000.0       # RMS ~this reads as "loud" (level 1.0); ambient quiet room ~30
ONSET_JUMP = 0.08         # level rising this far above the running ambient baseline = a sound onset
ONSET_FLOOR = 0.04        # ...and only if it's above this absolute level (ignore noise-floor jitter)
LIVE_TIMEOUT_S = 2.0      # no fresh audio for this long → not live (ok=False), like a stale eye
RESPAWN_COOLDOWN_S = 5.0  # min seconds between pw-record respawns (avoid thrash on a flapping BT link)


def _pw_record_cmd():
    return ["pw-record", "--target", SOURCE, "--rate", str(RATE),
            "--channels", "1", "--format", "s16", "-"]


class Hearing(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.level = 0.0       # normalized current loudness 0..1
        self.baseline = 0.0    # EMA ambient level
        self.onset = False     # a sudden sound above the ambient baseline this window
        self.running = True
        self.proc = None
        self._warmed = False
        self._live_ts = 0.0        # last time we got a window of audio (liveness)
        self._last_respawn = 0.0
        # WORDS, only in a listening window after the being speaks (listening.py). The ear keeps
        # its level/onset job unchanged; this rides the same windows and fails open.
        from sage.embodiment import listening as _listening
        self._listening = _listening
        self.segmenter = _listening.Segmenter(win_s=WIN / RATE)
        self.transcriber = _listening.Transcriber(source=SOURCE)
        self._win = {"listening": False, "speaking": False}
        self._win_checked = 0.0

    def _spawn(self) -> bool:
        try:
            if self.proc:
                try:
                    self.proc.terminate()
                except Exception:
                    pass
            self.proc = subprocess.Popen(_pw_record_cmd(),
                                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
            self._last_respawn = time.time()
            return True
        except Exception:
            self.proc = None
            return False

    def _read_exact(self, nbytes: int) -> bytes:
        buf = b""
        while self.running and len(buf) < nbytes:
            try:
                chunk = self.proc.stdout.read(nbytes - len(buf))
            except Exception:
                return b""
            if not chunk:
                return b""   # EOF → pw-record died (BT drop)
            buf += chunk
        return buf

    def _listen(self, chunk: bytes, level: float, baseline: float):
        """Hand voiced audio to the transcriber, only inside a window and never while speaking."""
        now = time.time()
        if now - self._win_checked > 0.5:
            self._win = self._listening.window(now)
            self._win_checked = now
        if not self._win["listening"] or self._win["speaking"]:
            self.segmenter.reset()
            return
        utt = self.segmenter.feed(chunk, level, baseline)
        if utt:
            self.transcriber.submit(utt)

    def run(self):
        leftover = b""
        header_done = False
        try:
            self.transcriber.start()
        except Exception:
            pass
        while self.running:
            # (re)spawn the capture if it's dead — the self-heal, on a cooldown
            if self.proc is None or self.proc.poll() is not None:
                if time.time() - self._last_respawn < RESPAWN_COOLDOWN_S:
                    time.sleep(0.5); continue
                if not self._spawn():
                    time.sleep(1.0); continue
                header_done = False; leftover = b""; self._warmed = False
            # pw-record writes a WAV header before the PCM; skip past the 'data' chunk once per spawn
            if not header_done:
                head = self._read_exact(64)
                if not head:
                    self.proc = None; continue   # died during header → respawn
                i = head.find(b"data")
                leftover = head[i + 8:] if i >= 0 else head[44:]
                header_done = True
            need = WIN * 2 - len(leftover)
            data = self._read_exact(need) if need > 0 else b""
            if need > 0 and not data:
                self.proc = None; continue        # stream died → will respawn on cooldown
            buf = (leftover + data)[:WIN * 2]
            leftover = b""
            n = len(buf) // 2
            if n == 0:
                continue
            s = struct.unpack("<%dh" % n, buf[:n * 2])
            rms = math.sqrt(sum(x * x for x in s) / n)
            level = min(1.0, rms / FULL_SCALE)
            self._warmed = self._warmed or level > 0.0   # HFP link warms up (level 0) for ~0.5s
            self.onset = self._warmed and level > self.baseline + ONSET_JUMP and level > ONSET_FLOOR
            if self._warmed:
                try:
                    self._listen(buf[:n * 2], level, self.baseline)
                except Exception:
                    pass   # the ear's level/onset must never depend on the listener
            self.level = round(level, 3)
            self.baseline = 0.95 * self.baseline + 0.05 * level
            self._live_ts = time.time()

    def state(self) -> dict:
        live = (time.time() - self._live_ts) < LIVE_TIMEOUT_S
        return {"level": round(self.level, 3) if live else 0.0,
                "onset": bool(self.onset) if live else False,
                "baseline": round(self.baseline, 3),
                "ok": live, "trust": 1.0 if live else 0.0,
                "listening": bool(self._win.get("listening")),
                "words": self.transcriber.status}

    def stop(self):
        self.running = False
        self.transcriber.running = False
        time.sleep(0.05)
        try:
            self.proc.terminate()
        except Exception:
            pass
