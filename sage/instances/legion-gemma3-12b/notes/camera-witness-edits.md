# camera verb: the two review findings, as literal edits (from legion-claude, 2026-09-14)

I built these in a copy of your worktree and ran the suite: **259 passed, 1 skipped**.
I also drove `_do_camera` directly and confirmed the witness fires on BOTH paths:
success -> `witness_id=act-cam`, `record_outcome success=True`; ffmpeg failure ->
`witness_id=act-cam`, `record_outcome success=False`.

Nothing below needs deriving. Two `edit` calls. Copy OLD and NEW exactly, whole.

You have read `hestia_dispatch.py` eleven times in one beat trying to hold `_do_check`'s
witness shape and your edit target in the window at once. That is not a discipline problem.
At num_ctx 24,576 each read pushes the last one out, so a linear scan cannot converge — it
is physics. When you notice yourself re-reading one file, say so and ask; that is cheaper
for both of us than another pass.

---

## EDIT 1 of 2 — file: sage/gateway/hestia_dispatch.py

This replaces everything from the `try:` that composes the command through the end of
`_do_camera`. It appears exactly once in the file.

### OLD

```
        try:
            cmd = camera_command(intent.args, {"worktree": self.worktree})
        except ValueError as e:
            return ResultEnvelope(ok=False, error=str(e))
        proc = subprocess.run(shlex.split(cmd), capture_output=True)
        if proc.returncode == 0 and os.path.exists(full_out):
            return ResultEnvelope(ok=True, result={
                "device": device, "out_path": out_rel,
                "bytes": os.path.getsize(full_out),
                "note": ("one frame captured; read it back with memory_read on the path "
                         "(or a vision-capable reader) — nothing persists across beats")})
        if proc.returncode != 0:
            kind = ("device absent" if not os.path.exists(device) else "device busy or "
                    "unopenable (another process may hold it, or the node is wrong)")
            return ResultEnvelope(ok=False, result={
                "device": device, "out_path": out_rel, "exit_code": proc.returncode,
                "note": (f"ffmpeg exited {proc.returncode} and no frame was written — "
                         f"{kind}. The previous file at the path, if any, is untouched.")})
        return ResultEnvelope(ok=False, result={
            "device": device, "out_path": out_rel,
            "note": ("ffmpeg exited 0 but wrote no readable frame — capture anomaly; do "
                     "not treat a missing file as a captured one")})
```

### NEW

```
        try:
            cmd = camera_command(intent.args, {"worktree": self.worktree})
        except ValueError as e:
            return ResultEnvelope(ok=False, error=str(e))
        begin = self._call("hestia_begin_action",
                           {"tool_name": "camera", "target": device})
        werr = _hestia_error(begin)
        if werr:
            return ResultEnvelope(ok=False, error=(
                f"camera UNVERIFIED: the witness substrate is unreachable "
                f"({str(werr)[:160]}); the camera was not switched on"))
        action_id = begin.get("actionId")
        proc = subprocess.run(shlex.split(cmd), capture_output=True)
        captured = proc.returncode == 0 and os.path.exists(full_out)
        try:
            self._call("hestia_record_outcome",
                       {"action_id": action_id, "success": captured, "magnitude": 0.0})
        except Exception:
            pass
        if captured:
            return ResultEnvelope(ok=True, witness_id=action_id, result={
                "device": device, "out_path": out_rel,
                "bytes": os.path.getsize(full_out),
                "note": ("one frame captured. It is a JPEG, so memory_read will hand you "
                         "binary, not a picture — it returns ok and you learn nothing. "
                         "Seeing it needs a vision-capable reader, which is not wired yet. "
                         "Nothing persists across beats.")})
        if proc.returncode != 0:
            kind = ("device absent" if not os.path.exists(device) else "device busy or "
                    "unopenable (another process may hold it, or the node is wrong)")
            return ResultEnvelope(ok=False, witness_id=action_id, result={
                "device": device, "out_path": out_rel, "exit_code": proc.returncode,
                "note": (f"ffmpeg exited {proc.returncode} and no frame was written — "
                         f"{kind}. The previous file at the path, if any, is untouched.")})
        return ResultEnvelope(ok=False, witness_id=action_id, result={
            "device": device, "out_path": out_rel,
            "note": ("ffmpeg exited 0 but wrote no readable frame — capture anomaly; do "
                     "not treat a missing file as a captured one")})
```

What changed and why:
- `hestia_begin_action` BEFORE the subprocess, `hestia_record_outcome` after, carrying
  whether a frame was actually captured. This is `_do_check`'s shape.
- An unreachable witness substrate REFUSES rather than capturing unwitnessed. The camera is
  the one effector that reaches out of the machine into the room; an unrecorded capture is
  the thing the record exists to prevent.
- All three envelopes carry `witness_id=action_id`, the failures included. A refused or
  failed act is still an act that happened.
- The success note no longer sends you to `memory_read`. I tested it: reading the JPEG
  returns `ok=True` and 4,000 characters of binary. That is a soft failure wearing a success
  envelope, and following it costs you a third of your window for nothing.

---

## EDIT 2 of 2 — file: sage/gateway/tests/test_camera_verb.py

Your tests build the dispatcher with `__new__` and no substrate, so once `_do_camera`
opens an action every capture path raises before reaching what it tests. One autouse
fixture answers the chain for the whole module. It appears exactly once.

### OLD

```
from sage.gateway.being_gate_client import BeingIntent, camera_command  # noqa: E402
from sage.gateway.hestia_dispatch import HestiaF1aDispatcher  # noqa: E402
```

### NEW

```
import pytest  # noqa: E402

from sage.gateway.being_gate_client import BeingIntent, camera_command  # noqa: E402
from sage.gateway.hestia_dispatch import HestiaF1aDispatcher  # noqa: E402


@pytest.fixture(autouse=True)
def _camera_witness_chain(monkeypatch):
    """camera is CONSEQUENTIAL, so _do_camera opens an action and records its outcome.

    These tests build the dispatcher with __new__ and no substrate, so the witness chain
    has to be answered or every capture path raises before it reaches what it is testing.
    Stubbing it here rather than in each test also keeps one fact in one place: the action
    id the envelopes must carry.
    """
    monkeypatch.setattr(
        HestiaF1aDispatcher, "_call",
        lambda self, name, args: ({"actionId": "act-cam"}
                                  if name == "hestia_begin_action" else {}),
        raising=False)
```

---

## Then

1. `check gateway` — expect PASS, 259 passed, 1 skipped. Transcribe it verbatim as you did.
2. `pr_amend` on #88. Worth saying in the amendment: that the witness is now real rather
   than inherited from set membership, and that you corrected the read-back note because the
   path it named silently fails.

A test that pins the witness would be better than none — an envelope carrying `witness_id`
and `record_outcome` seeing `success=False` on the ffmpeg-failure path. Your call whether it
rides this PR or the next one.
