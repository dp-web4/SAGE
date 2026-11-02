"""`camera` from the cortex (sage/embodiment/look.py; dp 2026-10-12, "the goal is to have it understand
directly what it's looking at"). On Sprout the eyes are CSI sensors only the running cortex can read, so a
seat declaring `camera_source: "cortex"` gets its frame from the cortex's current image.

The responder runs on real numpy frames and real OpenCV; the client runs as the real subprocess the seat
would run (`python3 -m sage.embodiment.look`), against a responder thread standing in for the cortex loop.
One file per request (GPT's hold on #425): concurrent clients, an overlapping timeout and racing
responders are pinned below."""
import json
import os
import subprocess
import sys
import threading
import time
import types
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from sage.embodiment import look  # noqa: E402
from sage.gateway import toolset  # noqa: E402
from sage.gateway.being_gate_client import BeingIntent, camera_command  # noqa: E402
from sage.gateway.hestia_dispatch import HestiaF1aDispatcher  # noqa: E402

FRAME = np.full((720, 1280, 3), 90, np.uint8)


def _ask(body, rid="r1", age=0.0):
    req, _, _ = look._dirs(str(body))
    p = Path(req) / f"{rid}.json"
    p.write_text(json.dumps({"id": rid, "ts": time.time() - age}))
    if age:
        os.utime(p, (time.time() - age, time.time() - age))
    return p


def _result(body, rid):
    return json.loads((Path(body) / look.LOOK_DIR / "results" / f"{rid}.json").read_text())


def _client_env(body):
    env = dict(os.environ)
    env.update(SAGE_BODY_DIR=str(body), PYTHONPATH=str(ROOT))
    return env


# ---- the cortex's half --------------------------------------------------------------------------

def test_the_cortex_answers_with_a_resized_jpeg_of_the_open_eye(tmp_path):
    req = _ask(tmp_path)
    (r,) = look.respond([None, FRAME], [0, 1], "open", body_dir=str(tmp_path))
    assert r["ok"] and r["eye"] == "right" and r["width"] == look.WIDTH and r["height"] == 576
    data = Path(r["path"]).read_bytes()
    assert data[:3] == b"\xff\xd8\xff" and data[-2:] == b"\xff\xd9"
    assert _result(tmp_path, "r1")["id"] == "r1" and not req.exists()


def test_closed_eyes_are_respected_not_overridden(tmp_path):
    _ask(tmp_path)
    (r,) = look.respond([FRAME], [1], "closed", body_dir=str(tmp_path))
    assert r["ok"] is False and "eyes are closed" in r["why"]
    assert not list((tmp_path / look.LOOK_DIR / "frames").iterdir())


def test_no_frame_yet_stale_and_mislabelled_requests(tmp_path):
    _ask(tmp_path)
    assert look.respond([None], [1], "open", body_dir=str(tmp_path))[0]["why"] == "no eye has delivered a frame yet"
    old = _ask(tmp_path, rid="old", age=look.STALE_S + 5)
    assert look.respond([FRAME], [1], "open", body_dir=str(tmp_path)) == [] and not old.exists()
    req, _, _ = look._dirs(str(tmp_path))
    (Path(req) / "aaa.json").write_text(json.dumps({"id": "bbb", "ts": time.time()}))   # names someone else
    assert look.respond([FRAME], [1], "open", body_dir=str(tmp_path)) == []
    assert not (tmp_path / look.LOOK_DIR / "results" / "bbb.json").exists()


def test_old_results_and_frames_are_removed_by_age_only(tmp_path):
    _ask(tmp_path, rid="a")
    look.respond([FRAME], [1], "open", body_dir=str(tmp_path))
    old = time.time() - look.RESULT_TTL_S - 1
    for sub, name in (("results", "a.json"), ("frames", "a.jpg")):     # a's answer was never collected
        os.utime(tmp_path / look.LOOK_DIR / sub / name, (old, old))
    _ask(tmp_path, rid="b")
    look.respond([FRAME], [1], "open", body_dir=str(tmp_path))
    assert {p.name for p in (tmp_path / look.LOOK_DIR / "results").iterdir()} == {"b.json"}
    assert {p.name for p in (tmp_path / look.LOOK_DIR / "frames").iterdir()} == {"b.jpg"}


# ---- the seat's half, as the real subprocess ----------------------------------------------------

def _cortex(body, frames, gaze, stop):
    while not stop.is_set():
        look.respond(frames, [1], gaze, body_dir=str(body))
        time.sleep(0.05)


def _client(body, out):
    return subprocess.Popen([sys.executable, "-m", "sage.embodiment.look", str(out)], env=_client_env(body),
                            cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


@pytest.mark.parametrize("gaze,code", [("open", 0), ("closed", 4)])
def test_the_client_gets_the_frame_or_the_cortexs_reason(tmp_path, gaze, code):
    body, out = tmp_path / "body", tmp_path / "home" / "scratch" / "camera" / "f.jpg"
    body.mkdir()
    stop = threading.Event()
    t = threading.Thread(target=_cortex, args=(body, [FRAME], gaze, stop), daemon=True)
    t.start()
    try:
        p = _client(body, out)
        stdout, stderr = p.communicate(timeout=20)
    finally:
        stop.set(); t.join()
    assert p.returncode == code, stderr
    if code == 0:
        assert json.loads(stdout)["eye"] == "right"
        assert out.read_bytes()[:3] == b"\xff\xd8\xff"
        assert not list(out.parent.glob("*.tmp-*"))            # published by rename, nothing half-written
    else:
        assert "eyes are closed" in stderr and not out.exists()
    assert not list((body / look.LOOK_DIR / "results").iterdir())   # the client took its result away


def test_no_cortex_is_said_and_leaves_no_request_behind(tmp_path):
    rc = look.request(str(tmp_path / "f.jpg"), body_dir=str(tmp_path), wait_s=0.3)
    assert rc == 3 and not list((tmp_path / look.LOOK_DIR / "requests").iterdir())


# ---- concurrency (GPT's hold on #425) ----------------------------------------------------------

def test_two_concurrent_clients_each_get_their_own_frame(tmp_path):
    body = tmp_path / "body"
    body.mkdir()
    stop = threading.Event()
    t = threading.Thread(target=_cortex, args=(body, [FRAME], "open", stop), daemon=True)
    t.start()
    try:
        outs = [tmp_path / f"o{i}.jpg" for i in range(2)]
        ps = [_client(body, o) for o in outs]
        codes = [p.wait(timeout=20) for p in ps]
    finally:
        stop.set(); t.join()
    assert codes == [0, 0] and all(o.read_bytes()[:3] == b"\xff\xd8\xff" for o in outs)


def test_a_timeout_withdraws_only_its_own_request(tmp_path):
    other = _ask(tmp_path, rid="b")                          # B is waiting; no cortex yet
    assert look.request(str(tmp_path / "a.jpg"), body_dir=str(tmp_path), wait_s=0.3) == 3
    assert other.exists()                                    # A's timeout left B's request alone
    (r,) = look.respond([FRAME], [1], "open", body_dir=str(tmp_path))
    assert r["id"] == "b" and r["ok"]


def test_racing_responders_answer_each_request_exactly_once(tmp_path):
    n = 24
    for i in range(n):
        _ask(tmp_path, rid=f"q{i:02d}")
    answered, lock = [], threading.Lock()

    def worker():
        for _ in range(20):
            got = look.respond([FRAME], [1], "open", body_dir=str(tmp_path))
            with lock:
                answered.extend(r["id"] for r in got)
    ts = [threading.Thread(target=worker) for _ in range(3)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert sorted(answered) == [f"q{i:02d}" for i in range(n)]          # all, none twice
    assert not list((tmp_path / look.LOOK_DIR / "requests").iterdir())


# ---- the verb: composition, dispatch, availability ----------------------------------------------

def test_a_cortex_seat_composes_the_look_command_without_a_worktree(tmp_path):
    home = str(tmp_path)
    cmd = camera_command({"out_path": "scratch/camera/f.jpg"}, {"memory_root": home, "camera_source": "cortex"})
    assert cmd == f"python3 -m sage.embodiment.look {home}/scratch/camera/f.jpg"
    with pytest.raises(ValueError, match="escapes your home|plain path"):
        camera_command({"out_path": "../x.jpg"}, {"memory_root": home, "camera_source": "cortex"})
    with pytest.raises(ValueError, match="not enabled on this seat"):          # undeclared: the hold stands
        camera_command({"out_path": "scratch/camera/f.jpg"}, {"memory_root": home})


def test_the_dispatcher_runs_it_and_says_it_was_your_eye(tmp_path, monkeypatch):
    monkeypatch.setattr(HestiaF1aDispatcher, "_call",
                        lambda self, n, a: {"actionId": "act"} if n == "hestia_begin_action" else {}, raising=False)
    d = HestiaF1aDispatcher.__new__(HestiaF1aDispatcher)
    d.worktree, d.memory_root, d.camera_source = None, str(tmp_path), "cortex"
    import sage.gateway.hestia_dispatch as hd
    seen = {}

    def ok_run(cmd, **kw):
        seen["cmd"] = cmd
        Path(cmd[-1]).write_bytes(b"\xff\xd8\xffJPEG\xff\xd9")
        return types.SimpleNamespace(returncode=0, stdout=b"{}", stderr=b"")
    monkeypatch.setattr(hd.subprocess, "run", ok_run)
    env = d._do_camera(BeingIntent("camera", {"out_path": "scratch/camera/f.jpg"}))
    assert env.ok and env.result["device"] == "cortex" and "YOUR OPEN EYE" in env.result["note"]
    assert seen["cmd"][:3] == ["python3", "-m", "sage.embodiment.look"]

    monkeypatch.setattr(hd.subprocess, "run", lambda cmd, **kw: types.SimpleNamespace(
        returncode=4, stdout=b"", stderr=b"no frame: your eyes are closed (gaze closed); open them to look"))
    env = d._do_camera(BeingIntent("camera", {"out_path": "scratch/camera/g.jpg"}))
    assert not env.ok and "eyes are closed" in env.result["stderr"] and "gave no frame" in env.result["note"]
    assert "busy" not in env.result["note"]                     # never the ffmpeg taxonomy


def test_availability_follows_the_running_cortex_on_a_cortex_seat():
    live = {"inventory": {"verbs": ["gaze"], "cortex_live": True}}
    dead = {"inventory": {"verbs": [], "cortex_live": False}}
    cfg = {"camera_source": "cortex"}
    assert "camera" not in toolset.unavailable(live, None, cfg)
    assert "not running" in toolset.unavailable(dead, None, cfg)["camera"]
    assert "worktree" in toolset.unavailable(live, None, {})["camera"]          # undeclared: unchanged
