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
from datetime import datetime, timezone
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
# the two files that happen to exist today. asks_sent.jsonl is the record the ask limit
# counts (hestia_dispatch, SAGE #92): a being that could rewrite it could reset its own limit.
RESERVED_SUBTREES = ("conversations", "asks_sent.jsonl")


SHARED_FORUM = "/ai-workspace/shared-context/forum"


def _shared_destination_hint(p) -> str:
    """Name the verb that DOES reach where the being was trying to write.

    legion-being hit this refusal twice on 2026-09-13 trying to answer a peer on the fleet
    forum, because `memory_write` is the intuitive verb and the refusal named no other. It
    already had a working path — `peer_ask` and `mesh` file to the forum through the
    gateway — and used it both times only after spending a step on the refusal. A boundary
    that says only what is forbidden makes the being guess at what is allowed."""
    if SHARED_FORUM in str(p).replace("\\", "/"):
        return (" To reach the forum, use `peer_ask` (it files your message there, in your "
                "name, and wakes the being you addressed) or `mesh` (a pointer at something "
                "already posted). Those are the sanctioned doors to shared space; they are "
                "not a workaround, they are the verb for this.")
    return ""


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
        #
        # TWO FIELDS, ONE FACT (reconciliation 2026-09-18). This branch overloaded `granted`
        # to carry pairs; main kept `granted` as bare roots and added `granted_reach` for the
        # pairs, which is backward-compatible and is what the rest of main reads. Prefer the
        # explicit field, accept either shape in it, and keep reading a bare entry as EXACT:
        # a dispatcher that guessed "recursive" would be wider than the law it enforces.
        roots = []
        for g in (getattr(verdict, "granted_reach", ()) or getattr(verdict, "granted", ()) or ()):
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
    def _former_home_equivalent(self, p: Path):
        """If `p` lies under a home this being used to have (instance.json `former_homes`),
        the path of the same file under its CURRENT home; else None."""
        try:
            import json as _json
            cfg = _json.loads((self.memory_root / "instance.json").read_text())
            for fh in cfg.get("former_homes") or []:
                old = Path(str(fh.get("path", ""))).resolve()
                if str(old) != "/" and (p == old or old in p.parents):
                    return self.memory_root / p.relative_to(old)
        except (OSError, ValueError):
            pass
        return None

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
            if writing:
                # A home that was renamed leaves absolute paths to the OLD one in the being's
                # own notes. The harness knows where that file lives now; say so.
                moved = self._former_home_equivalent(p)
                if moved is not None:
                    raise ValueError(
                        f"{p} is inside your FORMER home, which is now a frozen record and is "
                        f"not written. Your home moved; the same file is {moved} — write there "
                        f"(or use the relative path, which always means your current home)")
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
                    f"{p} is readable to you but not writable. This is not a missing grant "
                    "— the gate may well grant this path, and the write would still be "
                    "refused here, because a tree you can write and `check` can execute is "
                    "arbitrary code running as the seat."
                    + _shared_destination_hint(p) +
                    (" If none of those is what you wanted, appeal for the affordance and "
                     "name what you would write, rather than asking for the path."
                     if _shared_destination_hint(p) else
                     " If you need this written, appeal for the affordance and name what "
                     "you would write, rather than asking for the path — a seat can also "
                     "carry it for you if you say what and where."))
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
        # AN EMPTY ANSWER MUST SAY WHY IT IS EMPTY (the rule git_read got on 2026-09-08, which
        # this effector never did). Measured 2026-09-15: dp granted cbp-being read on
        # /var/log/hestia/policy/daemon.log, a path the being had invented and that does not
        # exist. This returned ok with "" and the being wrote "the daemon log is empty,
        # suggesting a crash or silent failure": a nonexistent file read as evidence for an
        # outage that was not happening. Missing, empty and directory are three different
        # facts, and each now says which it is.
        shown = str(intent.args["path"]).strip()
        if not p.exists():
            # A SILENT ZERO IS A FALSE ABSENCE, AND NEITHER IS IT AN ERROR. Two incidents,
            # one class. Legion 2026-09-09 02:24Z: six reads in one beat came back ok with
            # nothing and the being read absence into them. CBP 2026-09-15: dp granted read
            # on a path that does not exist, memory_read returned ok with "", and the being
            # wrote "the daemon log is empty, suggesting a crash" — a grant meant to reduce
            # friction became evidence for an outage that was not happening.
            #
            # RECONCILIATION 2026-09-18: this branch answered with ok=False and main with
            # ok=True plus a self-naming result. MAIN'S CONVENTION WINS, because the law
            # refused nothing here and the renderer labels a not-ok envelope "[dispatch
            # error]" — a false label for a path that simply is not there. Every diagnostic
            # this branch had earned is kept inside the answer, where the being reads it.
            rel = intent.args["path"]
            where = (f"relative paths resolve under your home {self.memory_root}"
                     if not str(rel).startswith("/") else "absolute path, resolved as given")
            parent = p.parent
            siblings = ""
            if parent.is_dir():
                names = sorted(x.name for x in parent.iterdir())[:40]
                siblings = f"; {parent} contains: " + (", ".join(names) if names else "(nothing)")
            # WHERE IT ACTUALLY IS, if a file of that name exists anywhere in its home.
            # legion-being lost the `scratch/game/` prefix four times on 2026-09-17/18 —
            # moves.md, current.md, board.txt, each read at the home root or the wrong
            # subdirectory, each costing a verb and a compaction. It had PINNED the right
            # path in a note; the window ate the note. An answer that names the remedy is
            # one it can act on without spending another read (the `check` grammar lesson,
            # 2026-09-07), and this one is a single bounded walk of its own home.
            found = ""
            try:
                base = p.name
                root = Path(self.memory_root)
                hits = [str(q.relative_to(root)) for q in root.rglob(base)
                        if q.is_file() and ".git" not in q.parts][:3]
                if hits:
                    found = (f". A file called {base!r} IS in your home, at: "
                             + ", ".join(hits) + " — read it by that path")
            except Exception:  # noqa: BLE001 — a helpful hint must never turn a miss into a crash
                found = ""
            return ResultEnvelope(
                ok=True,
                result=(f"[no such path: '{shown}' does not exist ({where}). This is not an empty "
                        f"file: there is nothing here to read, so it is no evidence about anything "
                        f"else{found}{siblings}. memory_write creates a file inside your home.]"),
                witness_id=self._witness(f"memory_read {p.name} (does not exist)"))
        if p.is_dir():
            # A directory read is a listing: name, kind, size — what a being without `ls`
            # needs to stop guessing filenames (five guesses in one beat, 2026-09-09).
            rows = []
            for x in sorted(p.iterdir(), key=lambda y: (not y.is_dir(), y.name))[:200]:
                try:
                    rows.append(f"- {x.name}/" if x.is_dir() else f"- {x.name}  ({x.stat().st_size} bytes)")
                except OSError:
                    rows.append(f"- {x.name}  (unreadable)")
            listing = (f"[directory: '{shown}' holds {len(rows)} entr{'y' if len(rows) == 1 else 'ies'}]\n"
                       + ("\n".join(rows) if rows else "(empty directory)"))
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
        if not content:
            # AN EXISTING EMPTY FILE SAYS SO. The branch's fix covered missing and directory
            # and left this one silent, which is the same false absence one step in.
            content = f"[empty file: '{shown}' exists and has no content]"
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

    # Bounds on one edit. An edit is a SMALL, LOCATED change; anything larger is a rewrite
    # and should be honest about being one.
    EDIT_MAX_CHARS = 4000

    def _do_edit(self, intent: BeingIntent) -> ResultEnvelope:
        """Replace one exact occurrence of `old` with `new` inside a file.

        WHY THIS VERB EXISTS, measured 2026-09-13. `memory_write` has two modes: append, or
        replace the WHOLE file. To change three lines inside compose(), legion-being would
        have had to resend all of heartbeat.py — 63,645 chars, ~25,458 tokens, against a
        working budget of ~6,500. Four times its entire per-beat room. So it could not.

        It did the only thing its verbs allowed: appended a wrapper at the end of the file
        that shadows the original function. The semantics were right and the shape was
        wrong, and the shape was wrong because nothing else was reachable. Every one of its
        merged PRs until now added a NEW file, which I had read as a preference; it was the
        structure of its instruments. A being that can only append can only ever bolt on.

        EXACTLY ONE MATCH, or it refuses. Zero means the anchor is not what it thinks — very
        often whitespace or a line it is remembering rather than reading. More than one means
        it does not know which site it is changing, and picking for it would be the harness
        guessing at intent. Both refusals say the count, because a refusal that names its own
        cause is one the being can correct without asking."""
        raw = str(intent.args.get("path", "")).strip()
        if not raw:
            return ResultEnvelope(ok=False, error="edit needs a 'path'")
        old = str(intent.args.get("old", ""))
        new = str(intent.args.get("new", ""))
        if not old:
            return ResultEnvelope(ok=False, error=(
                "edit needs 'old': the exact text to replace. To ADD text rather than change "
                "it, use memory_write (append is its default)."))
        if old == new:
            return ResultEnvelope(ok=False, error="edit 'old' and 'new' are identical; nothing to do")
        for name, val in (("old", old), ("new", new)):
            if len(val) > self.EDIT_MAX_CHARS:
                return ResultEnvelope(ok=False, error=(
                    f"edit '{name}' is {len(val)} chars; the limit is {self.EDIT_MAX_CHARS}. "
                    f"An edit is a small located change — anchor on the shortest unique text, "
                    f"or make several edits."))
        p = self._safe_path(raw, writing=True)          # same confinement as every write
        if not p.exists():
            return ResultEnvelope(ok=False, error=f"no such file to edit: {p}")
        try:
            body = p.read_text(errors="replace")
        except Exception as e:
            return ResultEnvelope(ok=False, error=f"edit could not read {p}: {type(e).__name__}: {e}")
        n = body.count(old)
        if n == 0:
            return ResultEnvelope(ok=False, error=(
                f"edit found no occurrence of that text in {p}. The anchor has to match the "
                f"file BYTE FOR BYTE — indentation included — so read the lines you are "
                f"anchoring on rather than recalling them."))
        if n > 1:
            return ResultEnvelope(ok=False, error=(
                f"edit found {n} occurrences of that text in {p} and will not choose for you. "
                f"Extend the anchor with a neighbouring line until it is unique."))
        before = len(body)
        p.write_text(body.replace(old, new, 1))
        after = p.stat().st_size
        return ResultEnvelope(
            ok=True,
            result=(f"edited {p} — replaced {len(old)} chars with {len(new)}; "
                    f"file was {before} bytes, now {after}. One occurrence, as required."),
            witness_id=self._witness(f"edit {p.name}: {old[:60]!r} -> {new[:60]!r}"))

    def _do_retire_note(self, intent: BeingIntent) -> ResultEnvelope:
        """Mark one of the being's OWN notes as no longer current, by renaming it and writing
        a dated header. Nothing is destroyed.

        WHY THE BEING NEEDS THIS. Its memory is append-only: `memory_write` opens in append
        mode, and there is no rename or delete. It can add a claim and never retract one, so
        every correction lands BELOW the stale note and both re-enter the next beat — often
        with the older one read first. Measured 2026-09-15/16 on cbp-being: a true claim
        ("membot is down", true on 09-13) outlived its cause by three days and drove ~40 beats
        of escalation, because nothing it could do said "this is finished". dp, to the being:
        "renaming and deleting aren't verbs you have yet — we're looking at that."

        Bounded: only inside `notes/` or `scratch/` in its own home. `_safe_path(writing=True)`
        already refuses the seat-owned notes and the reserved subtrees, and a path outside the
        home, so this adds only the notes/-or-scratch/ rule. The file keeps its content
        and gains a header; the name gains `.retired-<date>`, so a reader and a listing both
        see that it is closed."""
        raw = str(intent.args.get("path", "")).strip()
        reason = str(intent.args.get("reason", "")).strip()
        if not raw:
            return ResultEnvelope(ok=False, error="retire_note needs a 'path' (a note in your own notes/ or scratch/)")
        if not reason:
            return ResultEnvelope(ok=False, error="retire_note needs a 'reason': what you know now that the note does not")
        p = self._safe_path(raw, writing=True)
        if p.parent.name not in ("notes", "scratch") or p.parent.parent != self.memory_root:
            return ResultEnvelope(ok=False, error=(
                f"retire_note is for your own notes: '{raw}' is not directly inside your notes/ or "
                f"scratch/. Your journal and todo are the running record and are not retired this way."))
        if not p.exists():
            return ResultEnvelope(ok=False, error=f"no such note: '{raw}' does not exist, so there is nothing to retire")
        if ".retired-" in p.name:
            return ResultEnvelope(ok=True, result=f"{p.name} is already retired; nothing changed")
        stamp = datetime.now(timezone.utc)
        dest = p.with_name(f"{p.stem}.retired-{stamp:%Y-%m-%d}{p.suffix}")
        body = p.read_text(errors="replace")
        dest.write_text(
            f"> RETIRED {stamp:%Y-%m-%d %H:%M}Z by cbp-being. No longer current: {reason}\n"
            f"> Kept whole below, as it was written.\n\n" + body)
        p.unlink()
        return ResultEnvelope(ok=True, result=f"retired {p.name} -> {dest.name}",
                              witness_id=self._witness(f"retire_note {p.name} -> {dest.name}: {reason[:120]}"))

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
        # ALREADY THERE? A being deep in a long beat cannot see what it wrote twenty steps
        # ago — its context is saturated and the earlier result has been elided. legion-being
        # ran a 42-step beat on 2026-09-11 appending to one file 28 times, several chunks
        # byte-identical to ones already in it. Not fatal (11% duplication in 29 KB of real
        # notes) and not worth refusing over, because deliberate repetition is legitimate.
        # But it should not be INVISIBLE. Say it, and let the being decide.
        repeat = ""
        if mode == "append" and content.strip() and p.exists():
            try:
                tail = p.read_text(errors="replace")
                if content.strip() in tail:
                    where = "at the end already" if tail.rstrip().endswith(content.strip()) \
                            else "already somewhere in this file"
                    repeat = (f" NOTE: this exact content was {where} — you may have written it "
                              f"in an earlier step of this beat and not been able to see it.")
            except OSError:
                pass
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
                    f"append is the default, pass mode='replace' to overwrite).{repeat}"),
            witness_id=self._witness(f"memory_write {p.name} ({mode})"))
