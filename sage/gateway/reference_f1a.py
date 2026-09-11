"""
Reference F1a dispatcher — an interim, SAGE-side stand-in for the hestia dispatch
substrate (PRD_FLEET F1a, PR #579), so the being's OWN safe acts complete end to end
before the real substrate exists.

It executes only the being's local, low-risk effectors:
  * witness       — record a witnessed note (returns a witness_id)
  * memory_read   — read one of the being's own notes (within its instance dir)
  * memory_write  — append to one of the being's own notes (within its instance dir)

It deliberately does NOT execute consequential NETWORK acts (peer_ask, channel_egress):
those cross the society boundary and belong to the real hestia F1a, which witnesses and
routes them. Asking this reference to run one returns a clear "awaits F1a" envelope.

Invariants:
  * Only ever invoked on an intent the gate already ALLOWED (BeingGateClient.dispatch).
  * memory_* is confined to `memory_root` PLUS the roots the gate's verdict names as
    granted (`GatewayVerdict.granted`) — defense in depth that follows the law instead of
    overriding it; a path outside both is an error, never a silent write elsewhere.
  * Every executed act is witnessed (id returned), so nothing the being does is unrecorded.
This is a stand-in, clearly labelled; the real F1a (hestia-side) replaces it wholesale.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from sage.gateway.being_gate_client import BeingIntent, GatewayVerdict, ResultEnvelope


class ReferenceF1aDispatcher:
    """A Dispatcher (see being_gate_client.Dispatcher) for the being's own safe acts."""

    def __init__(self, memory_root: str,
                 witness_log: Optional[str] = None,
                 witness_fn: Optional[Callable[[str], str]] = None,
                 max_read_chars: int = 4000):
        self.memory_root = Path(memory_root).resolve()
        self.witness_log = Path(witness_log) if witness_log else self.memory_root / "witness_log.jsonl"
        self._witness_fn = witness_fn  # optional real hestia witness: (event) -> witness_id
        self.max_read_chars = max_read_chars

    # -- the Dispatcher contract ---------------------------------------------
    def __call__(self, intent: BeingIntent, verdict: GatewayVerdict) -> ResultEnvelope:
        # confinement = the home + whatever the law just consulted as granted for THIS verdict,
        # WITH REACH: each entry is (root, recursive). A bare string (an older gate client)
        # is read as EXACT — the default hestia #1002 chose — never widened by guessing.
        roots = []
        for g in (getattr(verdict, "granted", ()) or ()):
            if isinstance(g, (tuple, list)) and len(g) == 2:
                roots.append((Path(str(g[0])).resolve(), bool(g[1])))
            else:
                roots.append((Path(str(g)).resolve(), False))
        self._extra_roots = tuple(roots)
        handler = getattr(self, f"_do_{intent.effector}", None)
        if handler is None:
            # a consequential network act the reference won't run — real F1a's job
            return ResultEnvelope(ok=False, pending=True,
                                  note=f"'{intent.effector}' awaits hestia F1a (reference runs only witness/memory)")
        try:
            return handler(intent)
        except Exception as e:
            return ResultEnvelope(ok=False, error=f"{type(e).__name__}: {e}")

    # -- witnessing ----------------------------------------------------------
    def _witness(self, event: str) -> str:
        if self._witness_fn is not None:
            try:
                return self._witness_fn(event)
            except Exception:
                pass  # fall back to local witnessing rather than dropping the record
        ts = datetime.now().isoformat()
        wid = hashlib.sha256(f"{ts}|{event}".encode()).hexdigest()[:12]
        self.witness_log.parent.mkdir(parents=True, exist_ok=True)
        with open(self.witness_log, "a") as f:
            f.write(json.dumps({"id": wid, "ts": ts, "event": event}) + "\n")
        return wid

    # -- path confinement (defense in depth over the gate) -------------------
    def _safe_path(self, raw: str, writing: bool = False) -> Path:
        """Resolve a being's memory path. Relative paths are rooted at memory_root, never
        at the process cwd.

        READS follow the law: memory_root plus whatever roots the verdict named as granted.

        WRITES DO NOT, AND THIS IS A SECURITY BOUNDARY, NOT TIDINESS (2026-09-07).
        `check` executes pytest inside the being's worktree, and pytest imports `conftest.py`
        from the rootdir it is given. The moment a being can WRITE into a tree that `check`
        EXECUTES, the bounded effector registry stops bounding the computation: a gated write
        plus a gated execute compose into ungated arbitrary code, running as this seat's user,
        with the vault passphrase and every key on this box in reach. Measured live: with a
        standing grant on the worktree, `memory_write` to `<worktree>/conftest.py` was ALLOWED.
        Nothing had to go wrong for that to be true; two correct grants were enough.

        So writes stay inside the being's own home whatever the grants say. That is a stopgap
        with a known shape: the durable answer is that being-authored code runs under a
        principal that is not the seat (GPT review of PRD #54, point 3 — a hard prerequisite
        for M1 write capability). Until that exists, the invariant is: THE TREE `check`
        EXECUTES IS NOT A TREE THE BEING CAN WRITE.
        """
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = self.memory_root / p
        p = p.resolve()
        # (root, recursive) pairs. The home is always a subtree — it is the being's own.
        roots = [(self.memory_root, True)]
        if not writing:
            roots += list(getattr(self, "_extra_roots", ()) or ())
        def _covered(path: Path, root: Path, recursive: bool) -> bool:
            # exact: the root itself; recursive: the root and everything under it.
            # Separator-aware by construction (Path.parents): /a never fronts for /ab.
            return path == root or (recursive and root in path.parents)

        if not any(_covered(p, r, rec) for r, rec in roots):
            if writing and any(_covered(p, r, rec)
                               for r, rec in (getattr(self, "_extra_roots", ()) or ())):
                raise ValueError(
                    f"writes stay inside your own home ({self.memory_root}); {p} is readable "
                    "to you but not writable, because a tree you can write is a tree `check` "
                    "would then execute. Ask for the affordance rather than the path")
            raise ValueError(f"path escapes the being's memory root and its grants: {p}")
        return p

    # -- effectors -----------------------------------------------------------
    def _do_witness(self, intent: BeingIntent) -> ResultEnvelope:
        event = str(intent.args.get("event", "")).strip()
        if not event:
            return ResultEnvelope(ok=False, error="witness needs an 'event'")
        return ResultEnvelope(ok=True, result="witnessed", witness_id=self._witness(event))

    def _do_memory_read(self, intent: BeingIntent) -> ResultEnvelope:
        if not str(intent.args.get("path", "")).strip():
            return ResultEnvelope(ok=False, error="memory_read needs a 'path' (relative paths are inside your home)")
        p = self._safe_path(intent.args["path"])
        if not p.exists():
            return ResultEnvelope(ok=True, result="", witness_id=self._witness(f"memory_read {p.name} (empty)"))
        content = p.read_text(errors="replace")[: self.max_read_chars]
        return ResultEnvelope(ok=True, result=content, witness_id=self._witness(f"memory_read {p.name}"))

    def _do_memory_write(self, intent: BeingIntent) -> ResultEnvelope:
        if not str(intent.args.get("path", "")).strip():
            return ResultEnvelope(ok=False, error="memory_write needs a 'path' (relative paths are inside your home)")
        p = self._safe_path(intent.args["path"], writing=True)
        content = str(intent.args.get("content", ""))
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a") as f:
            f.write(content + ("\n" if not content.endswith("\n") else ""))
        return ResultEnvelope(ok=True, result=f"wrote {len(content)} chars to {p.name}",
                              witness_id=self._witness(f"memory_write {p.name}"))
