"""The ear on a body with no cortex (McNugget, 2026-10-17): a per-body wake name, and the ear's own state.

dp, with music playing in the room: "only being directly addressed should wake it". These pin:
  * SAGE_WAKE_NAME sets the name the ear answers to; the default is Sprout's, unchanged;
  * the McNugget pattern takes whisper's measured spellings (McNugget, McNagut, McNigod) and not
    "chicken nuggets";
  * "by <name>" closes the window: whisper writes a spoken "bye McNugget" as "by McNugget";
  * ear.json (sage/embodiment/ear.py) gives the body block the ear's state when no cortex reports,
    without claiming anything about eyes; a stale one gives nothing.
Plain asserts, so a failure fails under pytest as well as the script runner.
"""
import importlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from sage.embodiment import listening  # noqa: E402

MCNUGGET = r"m[ae]?c\W?n[aeiou]g+[aeiou]?[dt]s?"


def _with_name(pattern, say):
    saved = {k: os.environ.get(k) for k in ("SAGE_WAKE_NAME", "SAGE_WAKE_SAY")}
    os.environ["SAGE_WAKE_NAME"], os.environ["SAGE_WAKE_SAY"] = pattern, say
    try:
        return importlib.reload(listening)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_the_default_name_is_still_sprout():
    lis = importlib.reload(listening)
    assert lis.wake_match("Hey Sprout, what do you see?") == (True, "what do you see?")
    assert lis.WAKE_SAY == "Sprout" and lis.says_goodbye("by Sprout.")
    assert lis.wake_match("Hey McNugget")[0] is False


def test_mcnugget_answers_to_its_name_as_whisper_writes_it():
    lis = _with_name(MCNUGGET, "McNugget")
    try:
        assert lis.wake_match("Hey McNugget, what do you see?") == (True, "what do you see?")
        assert lis.wake_match("McNagut are you there?") == (True, "are you there?")
        assert lis.wake_match("Okay, McNigod, tell me about your day.")[0] is True
        assert lis.wake_match("Ok Mac Nugget, hello")[0] is True
        # music, a TV, a lunch order: not its name
        assert lis.wake_match("I had chicken nuggets for lunch.")[0] is False
        assert lis.wake_match("Hey Sprout")[0] is False
        assert lis.says_goodbye("by McNugget.") and lis.says_goodbye("Bye McNagut")
        assert lis.WAKE_SAY == "McNugget"
    finally:
        importlib.reload(listening)


def test_the_ear_tells_the_being_its_own_name():
    lis = importlib.reload(listening)
    win = {"listening": True, "wake": True, "engaged": False, "wake_say": "McNugget"}
    hearing, reason, key = lis.ear_state(True, "ready", win)
    assert hearing and key == "wake" and "'hey McNugget'" in reason


def test_a_body_with_no_cortex_reports_its_ear_from_ear_json():
    from sage.gateway import body
    d = tempfile.mkdtemp()
    pp = os.path.join(d, "perception.json")
    assert body.perception(path=pp) == {"live": False, "age_s": None}          # nothing at all: unchanged
    with open(os.path.join(d, "ear.json"), "w") as f:
        json.dump({"ok": True, "level": 0.02, "words": "ready", "hearing": True,
                   "ear": "listening for your name ('hey McNugget')", "ear_key": "wake"}, f)
    p = body.perception(path=pp)
    assert p["live"] is False and p["ear_live"] is True and p["audio_hearing"] is True and p["age_s"] is None
    assert body.ear_known({"perception": p})
    line = body.ear_line({"perception": p}, {})
    assert line.startswith("- Your ear for words is open") and "hey McNugget" in line
    old = time.time() - 3600
    os.utime(os.path.join(d, "ear.json"), (old, old))
    assert body.perception(path=pp) == {"live": False, "age_s": None}          # stale ear: no claim


def test_stopping_hearing_kills_a_capture_that_ignores_sigterm():
    """An AVFoundation capture still waiting for its device ignored SIGTERM and held the mic for 22 min."""
    import subprocess
    import types
    from sage.embodiment import audio
    proc = subprocess.Popen([sys.executable, "-c",
                             "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                             "print('up', flush=True); time.sleep(60)"], stdout=subprocess.PIPE)
    proc.stdout.readline()                     # its SIGTERM handler is installed
    fake = types.SimpleNamespace(running=True, transcriber=types.SimpleNamespace(running=True), proc=proc)
    t = time.time()
    audio.Hearing.stop(fake)
    assert proc.poll() is not None, "the capture outlived stop()"
    assert time.time() - t < 6


def test_sigterm_runs_the_ears_cleanup():
    """launchd stops the ear with SIGTERM; its finally (hearing.stop) must run, or the capture is orphaned."""
    import signal
    import subprocess
    d = tempfile.mkdtemp()
    marker = os.path.join(d, "stopped")
    code = (
        "import sys, time; sys.path.insert(0, %r)\n"
        "from sage.embodiment import audio, presence, ear\n"
        "class H:\n"
        "    def start(self): pass\n"
        "    def state(self): return {}\n"
        "    def stop(self): open(%r, 'w').write('yes')\n"
        "class P:\n"
        "    def run(self):\n"
        "        print('running', flush=True); time.sleep(60)\n"
        "audio.Hearing = H; presence.Presence = P\n"
        "ear.main()\n") % (str(Path(__file__).resolve().parents[3]), marker)
    env = dict(os.environ, SAGE_BODY_DIR=d)
    p = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, env=env)
    while b"running" not in p.stdout.readline():
        pass
    p.send_signal(signal.SIGTERM)
    p.wait(timeout=10)
    assert os.path.exists(marker), "SIGTERM ended the ear without stopping its capture"


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except AssertionError as e:
                fails += 1
                print(f"FAIL {name}: {e}")
    print(f"{'FAILED' if fails else 'ok'}: {fails} failure(s)")
    sys.exit(1 if fails else 0)
