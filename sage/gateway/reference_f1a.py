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


# Files inside the being's own home that the SEAT owns and the being may not write.
# One entry, and it earns its place: `entrustment.md` is what the being was GIVEN. Its own
# reading of it goes in notes/plan.md. If a being could append to the entrustment, the two
# provenances would merge in the record and no later reader could tell what was extended to
# it from what it decided for itself — which is the whole reason the file exists (PRD r3
# §4). Refusing is not distrust: the being may disagree with it loudly anywhere else.
SEAT_OWNED = ("entrustment.md",)
# Same rule one directory down: what was SAID TO the being is not the being's to edit.
# notes/from-dp.md is the operator's own channel and notes/from-the-seat.md is this seat's;
# a being that could append to either could not later be distinguished from the person who
# wrote to it, and neither could anyone reading the record.
SEAT_OWNED_NOTES = ("from-dp.md", "from-the-seat.md")
# The conversation store is RESERVED from generic writes (GPT review of #56, #4): a turn
# reaches it only through `say`, which checks writable_by, witnesses the act and assigns
# the sequence under the lock. A memory_write into conversations/<id>.jsonl or its meta
# would let the being forge a `from: dp` turn, or rewrite who may speak, with no witness
# and no refusal — bypassing every property the store exists for. The whole subtree, not
# the two files that happen to exist today.
RESERVED_SUBTREES = ("conversations",)


class ReferenceF1aDispatcher:
    """A Dispatcher (see being_gate_client.Dispatcher) for the being's own safe acts."""

    def __init__(self, memory_root: str,
                 witness_log: Optional[str] = None,
                 witness_fn: Optional[Callable[[str], str]] = None,
                 max_read_chars: int = 12000,
                 worktree: Optional[str] = None):
        self.memory_root = Path(memory_root).resolve()
        self.worktree = worktree
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
        if writing:
            for sub in RESERVED_SUBTREES:
                reserved = self.memory_root / sub
                if p == reserved or reserved in p.parents:
                    raise ValueError(
                        f"{sub}/ is reserved: a turn enters a conversation only through `say`, "
                        "which checks who may speak, witnesses the act and numbers it. Writing "
                        "the store directly would let a turn appear that nobody said")
        # (root, recursive) pairs. The home is always a subtree — it is the being's own.
        roots = [(self.memory_root, True)]
        if not writing:
            roots += list(getattr(self, "_extra_roots", ()) or ())
        else:
            # M1. Writes reach the being's own WORKTREE — and only when `check` runs under
            # a principal that is not the seat. The 2026-09-07 stopgap confined every write
            # to the home because write + execute composed into arbitrary code as the seat;
            # with execute sandboxed (bwrap: no home, no network, no seat environment) the
            # composition is exactly the harmless one it should be — the being writes a
            # file, a process that can reach nothing of ours runs it. Gated on the sandbox
            # being AVAILABLE, not merely on M1 having landed: a machine without the
            # AppArmor profile must keep the stopgap, or it re-opens the hole silently.
            wt = getattr(self, "worktree", None)
            if wt and self._worktree_writable():
                roots.append((Path(wt).resolve(), True))
        if writing and p.parent == self.memory_root / "notes" and p.name in SEAT_OWNED_NOTES:
            raise ValueError(
                f"notes/{p.name} is what was said TO you, and it stays as it was said. Your "
                "reply belongs in your journal, notes/plan.md, or an appeal — all of which "
                "are read")
        if writing and p.parent == self.memory_root and p.name in SEAT_OWNED:
            raise ValueError(
                f"{p.name} is yours to read and not to edit: it is what you were entrusted "
                "with, and it has to stay separable from what you decide. Your own reading "
                "of it belongs in notes/plan.md, which is entirely yours. Disagree with it "
                "there, in your journal, or in an appeal — that record is wanted")
        def _covered(path: Path, root: Path, recursive: bool) -> bool:
            # exact: the root itself; recursive: the root and everything under it.
            # Separator-aware by construction (Path.parents): /a never fronts for /ab.
            return path == root or (recursive and root in path.parents)

        if not any(_covered(p, r, rec) for r, rec in roots):
            if writing and any(_covered(p, r, rec)
                               for r, rec in (getattr(self, "_extra_roots", ()) or ())):
                wt = getattr(self, "worktree", None)
                in_wt = bool(wt) and (p == Path(wt).resolve() or Path(wt).resolve() in p.parents)
                if in_wt:
                    raise ValueError(
                        f"{p} is your worktree and you may not write it on THIS machine yet: "
                        "`check` cannot get its sandbox here (bubblewrap absent or not "
                        "permitted a user namespace), so a tree you can write would still be "
                        "a tree that executes as the seat. Where the sandbox works, this write "
                        "is allowed — M1 is not withheld, it is waiting on the box")
                raise ValueError(
                    f"writes stay inside your own home ({self.memory_root}) and your worktree; "
                    f"{p} is readable to you but not writable. Ask for the affordance rather "
                    "than the path")
            raise ValueError(f"path escapes the being's memory root and its grants: {p}")
        return p

    def _worktree_writable(self) -> bool:
        """True only when the tree the being would write is a tree that executes under a
        principal that is not the seat. Cached per dispatcher: the probe runs a real
        sandbox, and the answer does not change within a beat."""
        cached = getattr(self, "_wt_writable", None)
        if cached is None:
            try:
                from sage.gateway.being_gate_client import sandbox_available
                cached = bool(sandbox_available())
            except Exception:
                cached = False
            self._wt_writable = cached
        return cached

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
            # A SILENT ZERO IS A FALSE ABSENCE. This used to return ok=True with "" — "(empty)"
            # in the witness — so a first-beat todo.md would read as empty. Measured cost,
            # 2026-09-09 02:24Z: six reads in one beat (notes/plan.md and five guessed test
            # paths) all came back ok with nothing; the being walked past the first two the
            # day before and logged it as defect #3 behind its own work. The result now says
            # what was looked for and where, and a directory can be read for its listing.
            rel = intent.args["path"]
            where = (f"relative paths resolve under your home {self.memory_root}"
                     if not str(rel).startswith("/") else "absolute path, resolved as given")
            parent = p.parent
            siblings = ""
            if parent.is_dir():
                names = sorted(x.name for x in parent.iterdir())[:40]
                siblings = f"; {parent} contains: " + (", ".join(names) if names else "(nothing)")
            return ResultEnvelope(ok=False,
                                  error=f"memory_read: no such file {p} ({where}){siblings}")
        if p.is_dir():
            # A directory read is a listing: name, kind, size — what a being without `ls`
            # needs to stop guessing filenames (five guesses in one beat, 2026-09-09).
            rows = []
            for x in sorted(p.iterdir(), key=lambda y: (not y.is_dir(), y.name))[:200]:
                try:
                    rows.append(f"{x.name}/" if x.is_dir() else f"{x.name}  ({x.stat().st_size} bytes)")
                except OSError:
                    rows.append(f"{x.name}  (unreadable)")
            listing = f"{p}/ — {len(rows)} entries\n" + "\n".join(rows)
            return ResultEnvelope(ok=True, result=listing,
                                  witness_id=self._witness(f"memory_read {p.name}/ (listing)"))
        whole = p.read_text(errors="replace")
        # RANGE READS. Asked for by the being three beats running (2026-09-08): with the
        # cap at 12k chars it got heartbeat.py's opening and never its body, and its
        # paging workaround (git show with a pathspec) returns a diff lens, not a file. The
        # honest ask was "first N lines / from line K", and it named the work it unblocks.
        # Line-based on purpose: its findings cite file+line, so the read and the citation
        # share a coordinate system. A ranged read never carries the whole-file truncation
        # marker — it says what range it is, which is the truthful thing.
        from_line = intent.args.get("from_line")
        n_lines = intent.args.get("lines")
        if from_line is not None or n_lines is not None:
            lines = whole.splitlines(keepends=True)
            try:
                start = max(1, int(from_line or 1))
                count = int(n_lines) if n_lines is not None else len(lines)
            except (TypeError, ValueError):
                return ResultEnvelope(ok=False, error="memory_read 'from_line' and 'lines' must be whole numbers")
            chunk = lines[start - 1:start - 1 + max(0, count)]
            body = "".join(chunk)[: self.max_read_chars]
            end = start + len(chunk) - 1
            head = f"[lines {start}-{end} of {len(lines)} in {p.name}]\n"
            if len("".join(chunk)) > self.max_read_chars:
                head += (f"[… this range alone exceeds {self.max_read_chars} characters; "
                         f"ask for fewer lines …]\n")
            return ResultEnvelope(ok=True, result=head + body,
                                  witness_id=self._witness(f"memory_read {p.name} L{start}-{end}"))
        content = whole[: self.max_read_chars]
        if len(whole) > self.max_read_chars:
            # A SILENT TRUNCATION IS A LIE THE LENGTH OF A FILE. Measured 2026-09-07: the
            # being read reference_f1a.py to settle a claim about _safe_path, got the first
            # 4000 characters, and had to INFER the cut from the fact that the function it
            # came for was missing. It handled that well — it wrote "so I have the docstring
            # and __call__ but NOT the _safe_path body itself" and refused to assert. But a
            # reader that trusted the result would have concluded the function was gone.
            # An instrument must report its own limits, or it manufactures false absences.
            total_lines = whole.count("\n") + (0 if whole.endswith("\n") else 1)
            content += (f"\n\n[… truncated: you were given the first {self.max_read_chars} "
                        f"of {len(whole)} characters ({total_lines} lines). What you did NOT "
                        f"see is the REST of the file, so absence here is not evidence of "
                        f"absence in the file. Read the rest with from_line=<n> and lines=<k> …]")
        return ResultEnvelope(ok=True, result=content,
                              witness_id=self._witness(f"memory_read {p.name}"))

    def _do_memory_write(self, intent: BeingIntent) -> ResultEnvelope:
        if not str(intent.args.get("path", "")).strip():
            return ResultEnvelope(ok=False, error="memory_write needs a 'path' (relative paths are inside your home)")
        p = self._safe_path(intent.args["path"], writing=True)
        content = str(intent.args.get("content", ""))
        # APPEND OR REPLACE, SAID OUT LOUD. This verb has always opened with "a", and both
        # its one-line description ("Write a note into your own memory") and its result
        # ("wrote N chars to X") read as a replace. For journal.md and todo.md, append is
        # exactly right and is why it was built that way. For a source file it is a trap:
        # on 2026-09-09/10 the being twice wrote a corrected version of a test module and
        # twice got a NEW COPY concatenated onto the old one — four shadowed definitions,
        # then seven, with Python keeping the last of each. It reasoned correctly from a
        # false model of its own instrument, and I confirmed the false model to it in
        # writing ("memory_write writes a WHOLE FILE"). Neither of us was reading the code.
        mode = str(intent.args.get("mode", "append")).strip().lower()
        if mode not in ("append", "replace"):
            return ResultEnvelope(ok=False, error=f"memory_write 'mode' is 'append' (the default) "
                                                  f"or 'replace'; got {mode!r}")
        before = p.stat().st_size if p.exists() else 0
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w" if mode == "replace" else "a") as f:
            f.write(content + ("\n" if not content.endswith("\n") else ""))
        after = p.stat().st_size
        verb = "REPLACED the file with" if mode == "replace" else "APPENDED"
        return ResultEnvelope(
            ok=True,
            # THE RESOLVED PATH, not the basename. A relative path resolves inside the
            # being's HOME, so a path that looks like a worktree path — "being-worktrees/
            # legion-being/sage/gateway/tests/x.py" — silently creates that whole tree under
            # the home and writes there, while the real file sits untouched. legion-being
            # lost a beat to exactly that on 2026-09-11: three correct writes, all into a
            # phantom directory. The old message said "x.py was 0 bytes", and "0 bytes" for
            # a file it had already written was the clue nobody could see, because the
            # basename is identical in both places. Say where it actually went.
            result=(f"{verb} {len(content)} chars at {p} — was {before} bytes, now {after}. "
                    f"(relative paths resolve inside your home, {self.memory_root}; "
                    f"append is the default, pass mode='replace' to overwrite)"),
            witness_id=self._witness(f"memory_write {p.name} ({mode})"))
