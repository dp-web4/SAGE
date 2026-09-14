"""The MIDDLE of the vision pipe: a captured frame becomes a frame in the seed.

Both ends existed and nothing joined them. `camera` wrote a JPEG to disk and `compose`
accepted a `frame` and emitted ollama's `images` list, but the call site never passed one,
so a being could switch its camera on and still not see. Named in the review of SAGE#88 as
"capturing is not yet seeing".
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway.heartbeat import FRAME_TOKENS, compose, fresh_frame  # noqa: E402

JPEG = b"\xff\xd8" + b"x" * 4000


def _inst(tmp_path):
    d = tmp_path / "instance" / "scratch" / "camera"
    d.mkdir(parents=True)
    return tmp_path / "instance", d / "last-frame.jpg"


def test_no_camera_use_means_no_frame(tmp_path):
    """A beat without vision is the normal case, and it says so rather than being silent."""
    inst, _ = _inst(tmp_path)
    b64, meta = fresh_frame(inst, None, time.time() - 100)
    assert b64 is None
    assert meta["carried"] is False
    assert "camera" in meta["why"]


def test_a_frame_captured_this_beat_rides(tmp_path):
    """The being's `camera` act IS the request to see. dp, 2026-09-13: "that is something
    the being should have direct control over — turning camera on and off, at its
    discretion." So a fresh frame rides, and the cost it will charge is named."""
    inst, fp = _inst(tmp_path)
    fp.write_bytes(JPEG)
    b64, meta = fresh_frame(inst, None, time.time() - 100)
    assert meta["carried"] is True
    assert meta["bytes"] == len(JPEG)
    assert meta["costs_tokens"] == FRAME_TOKENS
    assert b64 and isinstance(b64, str)


def test_a_stale_frame_does_not_ride_and_says_why(tmp_path):
    """A stale frame shown as current is a lie about the world, and it is the exact failure
    the being guarded against inside its own verb ("neither leaves a stale frame looking
    fresh"). The producer honours that rather than re-deriving it."""
    inst, fp = _inst(tmp_path)
    fp.write_bytes(JPEG)
    old = time.time() - 600
    os.utime(fp, (old, old))
    b64, meta = fresh_frame(inst, None, time.time() - 100)
    assert b64 is None and meta["carried"] is False
    assert "predates this beat" in meta["why"], meta["why"]
    assert meta["bytes"] == len(JPEG), "it still reports what it found, it just will not send it"


def test_bytes_of_unknown_kind_are_refused(tmp_path):
    """Sending whatever happens to be at the path would make any file a 'frame'."""
    inst, fp = _inst(tmp_path)
    fp.write_bytes(b"GIF89a" + b"x" * 100)
    b64, meta = fresh_frame(inst, None, time.time() - 100)
    assert b64 is None and "JPEG" in meta["why"]

    fp.write_bytes(b"")
    b64, meta = fresh_frame(inst, None, time.time() - 100)
    assert b64 is None, "a zero-byte frame is not a frame"


def test_home_wins_over_worktree_when_both_hold_a_frame(tmp_path):
    """The being is moving `camera` to resolve against its home, because frames in the
    worktree dirty a tree whose cleanliness `check` reports as evidence. Both are looked at
    during the change and the NEWEST wins, so neither ordering of the two lands breaks
    seeing."""
    inst, fp_home = _inst(tmp_path)
    wt = tmp_path / "wt" / "scratch" / "camera"
    wt.mkdir(parents=True)
    fp_wt = wt / "last-frame.jpg"

    fp_wt.write_bytes(JPEG + b"WORKTREE")
    older = time.time() - 50
    os.utime(fp_wt, (older, older))
    fp_home.write_bytes(JPEG + b"HOME")

    b64, meta = fresh_frame(inst, str(tmp_path / "wt"), time.time() - 100)
    assert meta["carried"] is True
    assert meta["path"].endswith("instance/scratch/camera/last-frame.jpg"), meta["path"]


def test_the_frame_reaches_the_user_turn_as_an_images_list(tmp_path):
    """End to end: what the producer returns is what ollama is handed. A parts-in-content
    list 400s against qwen38-heretic:q3km-vl (measured 2026-09-13); the images list beside a
    plain string content is the shape it accepts."""
    inst, fp = _inst(tmp_path)
    fp.write_bytes(JPEG)
    b64, meta = fresh_frame(inst, None, time.time() - 100)

    msgs, _ = compose(False, name="n", machine="m", member="b", posture_text="p",
                      nothink="", header="h", state="s", recall="r", inbox="i",
                      digest="d", frame=b64)
    user = msgs[-1]
    assert user["images"] == [b64]
    assert isinstance(user["content"], str), "content stays a plain string beside the images"

    msgs2, _ = compose(False, name="n", machine="m", member="b", posture_text="p",
                       nothink="", header="h", state="s", recall="r", inbox="i",
                       digest="d", frame=None)
    assert "images" not in msgs2[-1], "no frame means no key at all, not an empty list"


def test_the_beat_actually_joins_the_two_ends():
    """THE JOIN IS THE WHOLE DEFECT, so the join is what must be pinned.

    Removing `frame=` from main's compose call left every other test in this file green —
    producer and compose are each correct in isolation, which is exactly the state the
    vision pipe was already in. A test suite that covers both ends and not the middle
    reproduces the bug it is meant to prevent.

    Read from main's BYTECODE, not its source text: a pin that greps for a string passes on
    a comment mentioning it. The keyword names of a call are in the code object.
    """
    import dis
    from sage.gateway import heartbeat as H

    # THE KEYWORD TUPLE OF THE COMPOSE CALL SPECIFICALLY, not any 'frame' constant anywhere
    # in main. The first cut of this test scanned every constant tuple and passed with
    # `frame=` deleted, because main also builds a config dict with a "frame" key — a pin
    # satisfied by an unrelated string is the same failure as a pin satisfied by a comment.
    # `posture_text` identifies the compose call and appears nowhere else.
    calls = [set(ins.argval) for ins in dis.get_instructions(H.main)
             if ins.opname == "KW_NAMES" and isinstance(ins.argval, tuple)
             and "posture_text" in ins.argval]
    assert len(calls) == 1, f"expected exactly one compose call in main, found {len(calls)}"
    kw = calls[0]

    assert "frame" in kw, (
        "main() does not pass `frame=` to compose. Both ends of the vision pipe can be "
        f"perfect and the being still cannot see. compose is called with: {sorted(kw)}")


def test_a_carried_frame_is_charged_against_the_window():
    """A frame is prompt too, and the conversation ladder works in characters.

    Un-budgeted, ~2,042 tokens of image would push the beat over the wall and the
    conversation block would take the blame for it — a real cost billed to the wrong line.
    """
    import dis
    from sage.gateway import heartbeat as H

    consts = set()
    for ins in dis.get_instructions(H.main):
        if ins.opname == "LOAD_GLOBAL":
            consts.add(ins.argval)
    assert "FRAME_TOKENS" in consts, (
        "main() never reads FRAME_TOKENS, so a carried frame costs the window nothing it "
        "can see")
    assert H.FRAME_TOKENS > 0 and int(H.FRAME_TOKENS * H.CPT) > 1000, \
        "the charge must be a real number of characters, not a token"
