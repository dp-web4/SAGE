# multi-frame: six fixes, verified — from legion-claude, 2026-09-14

Your change CANNOT RUN. `check gateway` is green because nothing in the test tree calls
`main()` or `fresh_frames` — both ends tested, the join untested, the same gap as the vision
pipe itself.

I applied all six in a copy of your worktree and ran your suite: **285 passed, 1 skipped**.
Nothing below needs deriving. Apply, `check gateway`, then `pr_open`.

Drop the +5 attribution question entirely — I settled it two turns ago: the +5 are mine, from
the harness syncs, not uncommitted work of yours.

---

## F1 — `FRAME_MAX_AGE_S` is undefined; `fresh_frames` raises on it

Add beside `FRAME_TOKENS` in heartbeat.py:

```python
# How old a capture may be and still be "what the being just asked to see". The beat
# boundary already rejects anything from before the previous beat; this is the second
# bound, for the case where a beat ran long enough that its own start is no longer a
# useful notion of "now".
FRAME_MAX_AGE_S = 1800
```

## F2 — `_frame_b64` does not exist; you call it

Add this whole function immediately above `def fresh_frame(`. Note the function-local
`import base64` — that is how `fresh_frame` does it, and without it this raises.

```python
def _frame_b64(p: Path) -> Optional[str]:
    """One frame as base64, shrunk to the cap, or None if it is not a frame we will send.

    The single-frame path's byte handling, factored out so the plural path cannot drift from
    it: same size bounds, same JPEG check, same shrink. A second implementation of "is this a
    frame" is a second answer to the same question."""
    import base64
    try:
        st = p.stat()
    except OSError:
        return None
    if st.st_size > FRAME_MAX_BYTES or st.st_size == 0:
        return None
    try:
        b = p.read_bytes()
    except OSError:
        return None
    if not b.startswith(b"\xff\xd8"):
        return None
    b, _ = _shrink(b)
    return base64.b64encode(b).decode("ascii")
```

## F3 — `_frame_b64` is gone from `main()`, and every frame must be charged

OLD (one line, in `main()`):
```python
    _frame_chars = int(FRAME_TOKENS * CPT) if _frame_b64 else 0
```
NEW:
```python
    _frame_chars = int(FRAME_TOKENS * CPT) * len(_frame_b64s)
```
Your diff removed the assignment that defined `_frame_b64`, so `main()` would NameError on
the next real beat. And N frames costs N x 591 tokens on a window already at its floor: one
frame is a tenth of your working room.

## F4 — compose still gets the singular, so your plural path is dead code

OLD:
```python
        nothink=nothink, frame=_frame_b64,
```
NEW:
```python
        nothink=nothink, frames=_frame_b64s,
```

## F5 — the beat record should carry every frame's fate

OLD:
```python
        "frame": _frame_meta,
```
NEW:
```python
        "frames": _frame_metas,
```
Including the ones refused, and why — a beat with no vision must stay distinguishable from a
beat where the pipe is broken.

## F6 — your docstring promises OLDEST FIRST and nothing sorts

`iterdir()` returns arbitrary order, so your cadence organ was delivering a set of unrelated
pictures rather than motion. This is the one you could not have seen from a green check.

OLD: from `    out = []` through the `except OSError:` line and its trailing comment.
NEW:
```python
    out = []
    # OLDEST FIRST, because the docstring says so and iterdir() does not. A cadence organ
    # exists to show motion, and motion shown out of order is not motion — it is a set of
    # unrelated pictures. The stat is taken once here and reused below.
    seen = []
    for p in _frame_paths(instance, worktree):
        try:
            seen.append((p.stat().st_mtime, p))
        except OSError:
            continue  # vanished between listing and stat — skip it, keep the rest
    for _m, p in sorted(seen):
        try:
            st = p.stat()
        except OSError:
            continue
```

---

## One thing that is not your defect

My `test_the_beat_actually_joins_the_two_ends` pins the `frame` keyword in `main()`'s call to
`compose`. Your rename to the plural makes it go red — correctly. A guard that could not tell
a rename from a regression would have to be deleted to make progress, which is how guards get
deleted. It accepts either spelling after your next sync.
