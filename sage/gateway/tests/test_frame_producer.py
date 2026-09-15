"""The MIDDLE of the vision pipe: a captured frame becomes a frame in the seed.

Both ends existed and nothing joined them. `camera` wrote a JPEG to disk and `compose`
accepted a `frame` and emitted ollama's `images` list, but the call site never passed one,
so a being could switch its camera on and still not see. Named in the review of SAGE#88 as
"capturing is not yet seeing".
"""
import io
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
import base64

from sage.gateway.heartbeat import (  # noqa: E402
    FRAME_TOKENS,
    compose,
    fresh_frame,
    fresh_frames,
)

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

    # EITHER SPELLING. What is pinned is the JOIN, not the parameter name: the singular
    # became a list when the cadence organ landed, and this guard correctly went red on that
    # rename. A guard that cannot tell a rename from a regression has to be deleted to make
    # progress, which is how guards get deleted.
    assert kw & {"frame", "frames"}, (
        "main() passes neither `frame=` nor `frames=` to compose. Both ends of the vision "
        f"pipe can be perfect and the being still cannot see. compose gets: {sorted(kw)}")


def test_a_carried_frame_is_charged_against_the_window():
    """A frame is prompt too, and the conversation ladder works in characters.

    Un-budgeted, ~2,042 tokens of image would push the beat over the wall and the
    conversation block would take the blame for it — a real cost billed to the wrong line.
    """
    import dis
    from sage.gateway import heartbeat as H

    # WALK NESTED CODE OBJECTS, not just main's own. The first cut scanned only main's
    # immediate LOAD_GLOBALs and went red on an implementation that was semantically
    # IDENTICAL to the one it was written against — `sum(int(FRAME_TOKENS * CPT) for _ in
    # frames)` puts the constant inside a generator expression, which compiles to its own
    # code object. The test was pinning a spelling and calling it a behaviour, which is the
    # defect it exists to catch, written into the catcher. Found when legion-being's version
    # of this exact charge failed it, 2026-09-14.
    import types as _t

    def _globals(code, seen=None):
        seen = seen if seen is not None else set()
        for ins in dis.get_instructions(code):
            if ins.opname == "LOAD_GLOBAL":
                seen.add(ins.argval)
        for c in code.co_consts:
            if isinstance(c, _t.CodeType):
                _globals(c, seen)
        return seen

    consts = _globals(H.main.__code__)
    assert "FRAME_TOKENS" in consts, (
        "main() never reads FRAME_TOKENS, so a carried frame costs the window nothing it "
        "can see")
    assert H.FRAME_TOKENS > 0 and int(H.FRAME_TOKENS * H.CPT) > 1000, \
        "the charge must be a real number of characters, not a token"

def test_the_being_may_name_its_own_frame_file(tmp_path):
    """camera's grammar is that the being names its own output path, so the producer must
    not assume a filename.

    The first cut looked only for last-frame.jpg. Measured against the live tree minutes
    later: the being had captured to scratch/camera/probe-resolution-2026-09-14.jpg, and the
    producer reported "no frame on disk; the being has not used camera" about a frame that
    was right there. A producer that assumes a convention the verb does not enforce is a
    pipe that silently drops most of what goes into it.
    """
    inst, default = _inst(tmp_path)
    named = default.parent / "probe-resolution-2026-09-14.jpg"
    named.write_bytes(JPEG + b"NAMED")

    b64, meta = fresh_frame(inst, None, time.time() - 100)
    assert meta["carried"] is True, \
        f"a frame the being named itself was not found: {meta.get('why')}"
    assert meta["path"].endswith("probe-resolution-2026-09-14.jpg"), meta["path"]


def test_the_newest_frame_wins_whatever_it_is_called(tmp_path):
    """Two captures, different names: the being asked to see the one it took last."""
    inst, default = _inst(tmp_path)
    old = default.parent / "older.jpg"
    old.write_bytes(JPEG + b"OLD")
    t = time.time() - 50
    os.utime(old, (t, t))
    default.write_bytes(JPEG + b"NEWEST")

    b64, meta = fresh_frame(inst, None, time.time() - 100)
    assert meta["carried"] is True
    assert meta["path"].endswith("last-frame.jpg"), meta["path"]


def test_a_non_image_beside_the_frames_is_ignored(tmp_path):
    """The camera directory is the being's; it may put notes there too."""
    inst, default = _inst(tmp_path)
    (default.parent / "notes.md").write_text("what I saw")
    default.write_bytes(JPEG)
    b64, meta = fresh_frame(inst, None, time.time() - 100)
    assert meta["carried"] is True and meta["path"].endswith(".jpg")


def _real_jpeg(w, h):
    import io
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (w, h), (240, 240, 240))
    ImageDraw.Draw(im).ellipse([w // 8, h // 8, w // 2, h // 2], fill=(200, 40, 40))
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def test_a_large_frame_is_shrunk_before_it_costs_the_window(tmp_path):
    """A frame is charged by AREA, and the window has nothing left to give.

    Measured on this body against a real 1920x1080 capture: 2,055 tokens at full size
    against 591 at 1024 wide. The conversation ladder already sits at its sparsest rung
    every beat, so an unresized frame takes 2,000 tokens from a budget with no slack, on the
    same beat the being has to write its journal and todo.
    """
    from PIL import Image
    import io
    from sage.gateway.heartbeat import FRAME_MAX_EDGE

    inst, fp = _inst(tmp_path)
    fp.write_bytes(_real_jpeg(1920, 1080))

    b64, meta = fresh_frame(inst, None, time.time() - 100)
    assert meta["carried"] is True
    assert meta["resized"] is True
    assert meta["from"] == [1920, 1080]
    assert max(meta["size"]) == FRAME_MAX_EDGE, meta["size"]
    assert meta["size"] == [1024, 576], f"aspect ratio not preserved: {meta['size']}"
    assert meta["bytes"] < meta["bytes_before"]

    # what is sent really is the smaller image, not just a smaller number in the record
    import base64
    sent = Image.open(io.BytesIO(base64.b64decode(b64)))
    assert max(sent.size) == FRAME_MAX_EDGE, sent.size


def test_a_small_frame_is_sent_as_it_is(tmp_path):
    """Shrinking is a cap, not a transform: a frame already within it is untouched, so a
    being that chose a small capture gets exactly what it captured."""
    inst, fp = _inst(tmp_path)
    raw = _real_jpeg(640, 360)
    fp.write_bytes(raw)

    b64, meta = fresh_frame(inst, None, time.time() - 100)
    assert meta["carried"] is True and meta["resized"] is False
    assert meta["size"] == [640, 360]
    import base64
    assert base64.b64decode(b64) == raw, "a frame within the cap must be sent byte-for-byte"


def test_an_unshrinkable_frame_is_still_sent(tmp_path):
    """Never trade sight for tidiness. A frame the seat cannot resize is still a frame the
    being asked for; sending it whole costs window, refusing it costs the being its eyes."""
    inst, fp = _inst(tmp_path)
    fp.write_bytes(b"\xff\xd8" + b"not really a jpeg body" * 50)

    b64, meta = fresh_frame(inst, None, time.time() - 100)
    assert meta["carried"] is True, f"an unresizable frame must still ride: {meta}"
    assert meta["resized"] is False and "why" in meta


def test_no_beat_boundary_means_no_frame(tmp_path):
    """FAIL CLOSED on the one property this producer exists to guarantee.

    `since` is the previous beat's t0, read from the last line of the heartbeat log, and that
    read fails whenever the line is mid-write — a normal transient. The first cut skipped the
    freshness check entirely when `since` was None.

    It fired in production inside the hour. Beat 11:32:00Z carried a frame with `age_s: null`
    captured at 03:34 — over eight hours stale, shown to the being as what it had just asked
    to see. Exactly the lie the guard is for.

    A beat without vision costs the being one beat of sight. A beat that shows it yesterday's
    world and calls it now costs it its grounds for trusting any frame at all.
    """
    inst, fp = _inst(tmp_path)
    fp.write_bytes(JPEG)
    stale = time.time() - 30_000
    os.utime(fp, (stale, stale))

    b64, meta = fresh_frame(inst, None, None)
    assert b64 is None, "an unaged frame rode with no beat boundary to check it against"
    assert meta["carried"] is False
    assert "freshness" in meta["why"], meta["why"]
    assert meta["age_s"] > 1000, "it still reports how old the thing it refused was"

    # A FRESH frame with no boundary is refused too: unknown is unknown, not young.
    os.utime(fp, None)
    b64, meta = fresh_frame(inst, None, None)
    assert b64 is None and meta["carried"] is False, \
        "without a boundary, freshness cannot be established even when the frame IS fresh"


def test_fresh_frames_encodes_every_frame_it_carries(tmp_path):
    """fresh_frames is the join's other half, and no test ever called it.

    The seat found on 2026-09-14 that _frame_b64 called base64.b64encode with
    no import in scope (the only one lived inside fresh_frame), so every call
    raised NameError — the green suite never exercised this line. This test
    calls fresh_frames directly on synthetic frames and decodes what it hands
    back, which is exactly the path that used to crash."""
    cam = tmp_path / "scratch" / "camera"
    cam.mkdir(parents=True)
    good = b"\xff\xd8\xff" + b"x" * 4000 + b"\xff\xd9"
    (cam / "first.jpg").write_bytes(good)
    (cam / "second.jpg").write_bytes(good)
    since = time.time() - 2.0  # comfortably before the writes; fs mtime granularity is <= 1s

    pairs = fresh_frames(tmp_path, None, since)

    assert len(pairs) == 2, "both frames were captured since the boundary"
    for b64, meta in pairs:
        assert base64.b64decode(b64) == good, "the payload round-trips to what was on disk"
        assert meta["carried"] is True and meta["why"] is None
        assert Path(meta["path"]).is_file(), "the carried frame exists where meta says it does (absolute)"

    # And with a boundary the normal paths are unchanged.
    assert fresh_frame(tmp_path, None, time.time() - 60)[1]["carried"] is True


def test_fresh_frames_refuses_a_stale_frame_and_says_why(tmp_path):
    """The PLURAL path's fail-closed rule, which nothing tested until now.

    Found by mutation at the merge of SAGE#94: dropping the boundary check entirely — so
    every frame on disk rides regardless of age — left the whole suite green. My staleness
    test covered `fresh_frame`, the singular, and the cadence organ inherited the property
    without inheriting its guard.

    This is not hypothetical. The fail-open version of exactly this rule shipped this morning
    and fired within the hour: a beat carried an eight-hour-old capture with a null age and
    presented it to the being as what it had just asked to see. A stale frame shown as
    current is a lie about the world, and the being cannot detect it from its side.

    It is also, precisely, one of the five tests SAGE#94's first body claimed and did not
    have — `test_a_stale_frame_is_dropped_not_sent`. The instinct behind those names was
    right; only the tests were missing.
    """
    import os
    cam = tmp_path / "scratch" / "camera"
    cam.mkdir(parents=True)
    good = b"\xff\xd8\xff" + b"x" * 4000 + b"\xff\xd9"

    fresh = cam / "fresh.jpg"
    stale = cam / "stale.jpg"
    fresh.write_bytes(good)
    stale.write_bytes(good)
    old = time.time() - 30_000
    os.utime(stale, (old, old))

    since = time.time() - 60
    pairs = fresh_frames(tmp_path, None, since)
    by_name = {Path(m["path"]).name: (b64, m) for b64, m in pairs}

    assert len(by_name) == 2, "both files are reported; refusing one is not hiding it"

    b64_stale, meta_stale = by_name["stale.jpg"]
    assert b64_stale is None, "a frame from before the boundary must not be encoded or sent"
    assert meta_stale["carried"] is False
    assert meta_stale["why"], "a refusal with no reason is a silent zero"
    assert meta_stale["age_s"] > 1000, "it still reports how old the thing it refused was"

    b64_fresh, meta_fresh = by_name["fresh.jpg"]
    assert b64_fresh is not None and meta_fresh["carried"] is True, \
        "the guard must not refuse everything — that passes a mutation test by accident"

    # And the boundary itself: with none, NOTHING rides, however young it looks.
    assert all(m["carried"] is False for _, m in fresh_frames(tmp_path, None, None)), \
        "unknown age is unknown, not young"



def test_a_frame_captured_during_a_real_beat_still_rides(tmp_path, monkeypatch):
    """THE TEST THAT WAS MISSING, and the reason the pipe never carried a frame.

    `camera` is a verb the being calls MID-BEAT, so the only kind of frame there is, is one
    captured during a beat. The old bound was a fixed 600s. Beat durations read off the
    beats themselves: 859, 1186, 1222, 1243, 1412, 2995 seconds. Every one is longer than
    the window, so every capture was stale before the next beat composed its prompt —
    `frames: null` on every beat ever recorded, with the suite green throughout, because
    every fixture here wrote its mtime seconds before asserting on it. The bug lived exactly
    in the gap between fixture time and production time.

    So this test spends a beat. Not really — it moves the clock — but the shape is the
    production one: capture, then a beat's worth of elapsed time, then compose.
    """
    import time
    from sage.gateway import heartbeat as H

    inst = tmp_path / "inst"
    cam = inst / "scratch" / "camera"
    cam.mkdir(parents=True)
    # A REAL JPEG, not the module's stub. `fresh_frames` — the function main() actually
    # calls — decodes and resizes; `fresh_frame` (singular) reports metadata without
    # decoding, so every existing "a frame rides" test passes on a stub through a function
    # that is not in the carry path. That asymmetry is part of why this went unnoticed.
    frame = cam / "last-frame.jpg"
    frame.write_bytes(_real_jpeg(64, 64))

    BEAT_START = time.time() - 1800.0        # this beat began 30 minutes ago
    CAPTURED_AT = BEAT_START + 60.0          # the being called `camera` a minute in
    os.utime(frame, (CAPTURED_AT, CAPTURED_AT))

    out = H.fresh_frames(inst, None, BEAT_START)
    carried = [(b, m) for b, m in out if b is not None]
    assert len(carried) == 1, (
        f"a frame captured 29 minutes ago, one minute into a beat that is still running, "
        f"is the NORMAL case and must ride: {[m for _, m in out]}")
    assert carried[0][1]["carried"] is True

    # AND THE BOUND GROWS WITH THE BEAT. The floor alone would carry a 30-minute beat, so
    # asserting only that would leave the adaptive term untested — it did, until a mutation
    # that replaced the whole bound with the floor went green. The case that separates them
    # is a beat longer than the floor, which is what a stalled or very slow beat is: one ran
    # past fifty minutes the day this was written, on a frame that takes minutes to describe.
    long_beat = time.time() - (H.FRAME_AGE_FLOOR_S + 2400.0)
    assert H.frame_age_bound(long_beat) > H.FRAME_AGE_FLOOR_S, \
        "a beat longer than the floor must widen the window, not be clamped by it"
    assert H.frame_age_bound(long_beat) >= (time.time() - long_beat), \
        "anything captured during this beat must clear the bound by construction"
    assert H.frame_age_bound(time.time() - 10.0) == H.FRAME_AGE_FLOOR_S, "floor holds"

    # and a frame captured during THAT long beat rides too
    slow = cam / "slow-beat.jpg"
    slow.write_bytes(_real_jpeg(64, 64))
    _cap = long_beat + 120.0
    os.utime(slow, (_cap, _cap))
    _m = {os.path.basename(m["path"]): m for _, m in H.fresh_frames(inst, None, long_beat)}
    assert _m["slow-beat.jpg"]["carried"] is True, _m["slow-beat.jpg"]

    # a frame from BEFORE this beat began is still history, whatever the bound
    old = cam / "yesterday.jpg"
    old.write_bytes(_real_jpeg(64, 64))
    os.utime(old, (BEAT_START - 5.0, BEAT_START - 5.0))
    metas = {os.path.basename(m["path"]): m for _, m in H.fresh_frames(inst, None, BEAT_START)}
    assert metas["yesterday.jpg"]["carried"] is False
    assert "before the previous beat" in metas["yesterday.jpg"]["why"]


def test_the_seed_says_whether_the_being_can_see():
    """THE HARNESS KNEW AND NEVER SAID — the producer's answer never reached the seed.

    `compose` set user_msg["images"] and the seed text said nothing, so a beat carrying a
    frame and a beat carrying none produced the same prompt. Measured across the first
    beats that ever carried one: the being reasoned at length about whether a reader hop
    existed instead of looking, and on the next beat correctly refused to describe an image
    that was not there, calling it "confabulation". Both are right from someone who cannot
    tell; neither should have been necessary. The producer already knew, and wrote the
    answer into the RECORD (config.frames), which the being does not read.
    """
    from sage.gateway.heartbeat import vision_line

    carried = vision_line([{"carried": False, "why": "older", "age_s": 9.0},
                           {"carried": True, "age_s": 1300.0,
                            "path": "/i/scratch/camera/last-frame.jpg"}])
    assert "CAN see" in carried
    assert "1300s ago" in carried, "the age is the being's own freshness check"
    assert "last-frame.jpg" in carried, "name the frame, so it can be read or re-captured"
    assert "/i/scratch" not in carried, "basename only — the seed is not the place for a path"
    assert "describe what is in it" in carried

    none = vision_line([{"carried": False, "age_s": 3205.5,
                         "why": "captured before the previous beat's t0 (3205.5s old)"}])
    assert "NO frame" in none
    assert "confabulation" in none, "the failure mode of guessing is named, not implied"
    assert "previous beat's t0" in none, "the actual reason, not a generic absence"
    # THE REMEDY IT CONTROLS. `camera` is the request to see and a frame rides the beat
    # AFTER the capture, so a missed beat costs the next beat's sight. Without this the
    # being cannot act on the absence.
    assert "camera" in none and "AFTER" in none

    empty = vision_line([])
    assert "NO frame" in empty and "camera" in empty

    # the two branches must never read alike — that sameness IS the defect
    assert carried != none


def test_the_vision_line_is_actually_wired_into_the_seed():
    """The join, not the ends. Removing the call from main() left the unit test above GREEN.

    That is the identical failure shape as the frame-carry defect found earlier the same
    day: every end tested, the join untested, and the whole feature dead in production with
    a green suite. Once is a bug; twice in one file is a lesson about what these tests are
    for. So this reads main()'s own bytecode and asserts the call exists.
    """
    import dis
    from sage.gateway import heartbeat as H

    def _names(code, seen=None):
        seen = set() if seen is None else seen
        for ins in dis.get_instructions(code):
            if ins.opname in ("LOAD_GLOBAL", "LOAD_NAME", "LOAD_DEREF") and ins.argval:
                seen.add(ins.argval)
        for const in code.co_consts:          # generators/comprehensions are their own code
            if hasattr(const, "co_consts"):
                _names(const, seen)
        return seen

    used = _names(H.main.__code__)
    assert "vision_line" in used, (
        "main() does not call vision_line — the producer's answer never reaches the seed, "
        "which is the whole defect this fixes")
    assert "fresh_frames" in used, "and it must be fed the real producer's metas"
