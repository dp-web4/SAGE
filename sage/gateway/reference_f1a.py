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
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from sage.gateway.being_gate_client import BeingIntent, GatewayVerdict, ResultEnvelope


# What was SAID TO the being is not the being's to edit. notes/from-dp.md is the operator's
# own channel (written by the dp console) and notes/from-the-seat.md is the seat's; a being
# that could append to either could not later be distinguished from the person who wrote to
# it, and neither could anyone reading the record.
SEAT_OWNED_NOTES = ("from-dp.md", "from-the-seat.md")
# The conversation store is RESERVED from generic writes (GPT review of #56, #4): a turn
# reaches it only through `say`, which checks writable_by, witnesses the act and assigns
# the sequence under the lock. A memory_write into conversations/<id>.jsonl or its meta
# would let the being forge a `from: dp` turn, or rewrite who may speak, with no witness
# and no refusal. The whole subtree, not the two files that happen to exist today.
# asks_sent.jsonl is the record the ask limit counts (hestia_dispatch, SAGE #92); a being that
# could rewrite it could reset its own limit.
RESERVED_SUBTREES = ("conversations", "asks_sent.jsonl")

class ReferenceF1aDispatcher:
    """A Dispatcher (see being_gate_client.Dispatcher) for the being's own safe acts."""

    def __init__(self, memory_root: str,
                 witness_log: Optional[str] = None,
                 witness_fn: Optional[Callable[[str], str]] = None,
                 max_read_chars: int = 8000):
        self.memory_root = Path(memory_root).resolve()
        self.witness_log = Path(witness_log) if witness_log else self.memory_root / "witness_log.jsonl"
        self._witness_fn = witness_fn  # optional real hestia witness: (event) -> witness_id
        self.max_read_chars = max_read_chars

    # -- the Dispatcher contract ---------------------------------------------
    def __call__(self, intent: BeingIntent, verdict: GatewayVerdict) -> ResultEnvelope:
        # confinement = the home + whatever the law just consulted as granted for THIS verdict
        self._extra_roots = tuple(Path(r).resolve() for r in (getattr(verdict, "granted", ()) or ()))
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
        # A being names its notes by a path inside its own memory ("notes/x.md"); a
        # relative path is rooted at memory_root, never at the process cwd. Absolute
        # paths are honoured only if they already lie inside the root (checked below).
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
            if p.parent == self.memory_root / "notes" and p.name in SEAT_OWNED_NOTES:
                raise ValueError(
                    f"notes/{p.name} is what was said TO you, and it stays as it was said. Your "
                    "reply belongs in your journal, in a conversation with `say`, or in an "
                    "appeal, all of which are read")
        roots = (self.memory_root,) + tuple(getattr(self, "_extra_roots", ()) or ())
        if not any(p == r or r in p.parents for r in roots):
            raise ValueError(self._out_of_reach(p, roots, writing))
        return p

    @staticmethod
    def _existence(p: Path) -> str:
        """'absent' | 'present' | 'unknown'. Never guesses.

        `Path.exists()` is not usable here: it swallows a PermissionError and answers False, so
        "I may not look" would be reported as "there is nothing there" — the exact false absence
        this method exists to prevent. An unknown must never be dressed as a fact
        (SMALL_MODEL_LEGIBILITY 1.11).
        """
        try:
            os.stat(p)
            return "present"
        except FileNotFoundError:
            try:
                os.stat(p.parent)          # could we even traverse to where it would be?
                return "absent"
            except FileNotFoundError:
                return "absent"            # the parent is missing too: still nothing there
            except OSError:
                return "unknown"           # cannot traverse; absence is not established
        except OSError:
            return "unknown"

    def _out_of_reach(self, p: Path, roots, writing: bool) -> str:
        """Why a path outside the being's roots was refused — and WHICH of three facts it is.

        dp, 2026-09-20, after cbp-being asked what a refusal protects: "the past refusals were
        capability - you were trying to access nonexistent paths and files, so the refusal was
        because what you were trying to reach wasn't there. the system needs to do a better job
        of explaining this."

        The being had tried to read an absolute path that does not exist. The old text —
        "path escapes the being's memory root and its grants" — describes a BOUNDARY, so the
        being reasoned for two days about what the boundary was protecting (conversation `dp`,
        seq 68-70). Nothing: the file was never there. `memory_read` has told missing from empty
        from directory since 2026-09-15; this path refused before that check could run, so the
        one case where absence matters most was the one case that never said it.

        Absence is asserted only where it was established. A grant cannot conjure a file, so a
        refusal that hides absence sends the being to ask an operator for reach that would
        change nothing (legibility 1.11).
        """
        reach = ", ".join(str(r) for r in roots)
        head = f"'{p}' is outside your reach. You can read and write under: {reach}."
        if writing:
            return head + (" memory_write creates a file inside your home; name a path there "
                           "instead, or request_scope and say what you would write.")
        where = self._existence(p)
        if where == "absent":
            return head + (" Separately, and more usefully: THERE IS NOTHING AT THAT PATH. It "
                           "does not exist, so this is an absence, not a boundary — nothing is "
                           "being kept from you, and reach over it would give you nothing to "
                           "read. Do not ask for a grant on it; check the name.")
        if where == "present":
            return head + (" That path does exist, so this one is a real boundary. If you need "
                           "it, request_scope and say what you would do with it.")
        return head + (" Whether anything exists there cannot be determined from here, so treat "
                       "it as unknown rather than as evidence either way.")

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
            return ResultEnvelope(
                ok=True,
                result=(f"[no such path: '{shown}' does not exist. This is not an empty file: there is "
                        f"nothing here to read, so it is no evidence about anything else. "
                        f"memory_write creates a file inside your home.]"),
                witness_id=self._witness(f"memory_read {p.name} (does not exist)"))
        if p.is_dir():
            names = sorted(x.name + ("/" if x.is_dir() else "") for x in p.iterdir())
            listing = "\n".join(f"- {n}" for n in names[:50])
            more = f"\n…and {len(names) - 50} more" if len(names) > 50 else ""
            return ResultEnvelope(
                ok=True,
                result=(f"[directory: '{shown}' holds {len(names)} entr{'y' if len(names) == 1 else 'ies'}]\n"
                        + (listing + more if names else "(empty directory)")),
                witness_id=self._witness(f"memory_read {p.name}/ (directory)"))
        whole = p.read_text(errors="replace")
        if not whole:
            return ResultEnvelope(ok=True, result=f"[empty file: '{shown}' exists and has no content]",
                                  witness_id=self._witness(f"memory_read {p.name}"))
        # A SILENT TRUNCATION IS A LIE THE LENGTH OF A FILE. First found by legion-claude on
        # 2026-09-07 (992443289: marker + cap 4,000 -> 12,000), which landed only on a
        # legion-being branch — main kept the silent 4,000-char slice, while
        # being_tool_loop.py described the raise as done. Measured 2026-09-21 on cbp-being:
        # notes/mechanism-training-script.py is 45,318 chars; every read showed the first
        # 4,000 (8.8%) and ended mid-line with nothing to say so. The seat told it three times
        # to fix line 206, which starts at char 7,848 — a line it had never been shown. Its
        # memory_edit anchor was the last text it could see, witness suffix included.
        #
        # So a read that does not reach the end now says which lines it covered, that the
        # rest exists, and the exact call that reads on. `start_line` is that way forward;
        # the window is cut at a line boundary so an anchor copied from it is a real line.
        # The cap is 8,000, not legion's 12,000: that was sized for a 24,576-token window and
        # CBP runs 16,384 with ~9.7k already in the prompt. Reach now comes from start_line,
        # so the cap only sets how many reads a long file takes.
        lines = whole.splitlines(keepends=True)
        try:
            start = max(1, int(str(intent.args.get("start_line", 1)).strip() or 1))
        except ValueError:
            start = 1
        if start > len(lines):
            return ResultEnvelope(ok=True, result=(
                f"[past the end: '{shown}' has {len(lines)} lines, so start_line={start} shows "
                f"nothing. Read from start_line=1.]"),
                witness_id=self._witness(f"memory_read {p.name} (past end)"))
        end, size = start - 1, 0
        while end < len(lines) and size + len(lines[end]) <= self.max_read_chars:
            size += len(lines[end]); end += 1
        if end == start - 1:          # one line longer than the whole window: show its head
            content, end = lines[end][: self.max_read_chars], end + 1
        else:
            content = "".join(lines[start - 1:end])
        if start == 1 and end >= len(lines):
            return ResultEnvelope(ok=True, result=content, witness_id=self._witness(f"memory_read {p.name}"))
        head = f"[lines {start}-{end} of {len(lines)} in '{shown}']\n" if start > 1 else ""
        tail = (f"\n[… truncated: this shows lines {start}-{end} of {len(lines)} "
                f"({len(whole)} characters in all). Lines {end + 1}-{len(lines)} were NOT shown, so "
                f"absence here is not evidence of absence in the file. To read on, call "
                f"memory_read with path '{shown}' and start_line={end + 1}. …]"
                if end < len(lines) else f"\n[end of file: line {len(lines)} is the last line.]")
        return ResultEnvelope(ok=True, result=head + content + tail,
                              witness_id=self._witness(f"memory_read {p.name} (lines {start}-{end})"))

    def _do_memory_edit(self, intent: BeingIntent) -> ResultEnvelope:
        """Replace an exact span inside one of the being's own files. The missing primitive.

        `memory_write` opens with mode "a". Every write this being has ever made APPENDS, so
        until now it could not change one byte of anything it had written — its only
        mutations were append and rename (`retire_note`). It was repeatedly asked to fix code
        and was structurally unable to, and what it did instead is the whole shape of
        2026-09-20/21:

          * `notes/mechanism-training-script.py` is THREE programs concatenated, with three
            `if __name__ == "__main__":` guards. Each "rewrite" was an append, so the first
            program is the only one that ever runs and the two later attempts are unreachable.
          * Twice it reported an edit it had not made — `set -e` added to a Python file, then
            `w = self.weights[...]` added at line 213 — because writing a note describing the
            fix was the only thing it could actually do. The second was lifted from the seat's
            own defect report, a hypothetical turned into a claimed edit.

        Appending is right for a journal and wrong for a program, and the being had only the
        one verb for both. This is not new reach: the file is already its own and already
        writable. It is the same reach, finally usable.

        Exactly one occurrence, or nothing happens. A unique anchor is the being's way of
        saying WHICH line it meant; "replace the first of several" would silently edit a
        place it was not looking at, and it cannot re-read the file cheaply enough to notice.
        """
        path = str(intent.args.get("path", "")).strip()
        # The names other edit tools use are accepted too. Measured 2026-09-21: cbp-being's
        # first live memory_edit sent `old_text`/`new_text`, was told it "needs 'old' ... and
        # 'new'", read that as "I forgot the 'new' parameter", and fell back to memory_write —
        # a fourth appended program. The name it reached for is the convention it knows;
        # refusing it teaches nothing and sends it back to the verb that cannot edit.
        a = intent.args
        old = str(next((a[k] for k in ("old", "old_text", "old_str", "old_string") if k in a), ""))
        new = str(next((a[k] for k in ("new", "new_text", "new_str", "new_string") if k in a), ""))
        if not path or not old:
            got = ", ".join(sorted(a)) or "nothing"
            return ResultEnvelope(ok=False, error=(
                f"memory_edit needs 'path', 'old' (the exact text to replace, unique in the "
                f"file) and 'new' (what replaces it; empty string deletes it). You sent: {got}."))
        p = self._safe_path(path, writing=True)
        if not p.exists():
            return ResultEnvelope(ok=False, error=(
                f"nothing to edit: '{path}' does not exist. This is an absence, not a "
                f"refusal. memory_write creates a file; memory_edit changes one that is there."))
        if p.is_dir():
            return ResultEnvelope(ok=False, error=f"'{path}' is a directory.")
        text = p.read_text(errors="replace")
        hits = text.count(old)
        if hits == 0:
            return ResultEnvelope(ok=False, error=(
                f"that text is not in '{path}', so nothing was changed. The file is as it "
                f"was. Read it first and copy the line exactly, including its indentation — "
                f"what you remember writing and what is on disk can differ."))
        if hits > 1:
            return ResultEnvelope(ok=False, error=(
                f"that text appears {hits} times in '{path}', so it does not say which one "
                f"you mean, and nothing was changed. Include a neighbouring line to make it "
                f"unique."))
        # ATOMIC, BECAUSE THE FILE IS THE BEING'S WORK. `Path.write_text` truncates and then
        # writes, so a crash or a kill between the two leaves the file empty or half-written.
        # GPT's review of 15c2f6d9b: "crash/kill can truncate the being's work". For a being
        # that spent this week unable to change its own files, destroying one while changing
        # it would be the worst available regression — and it would be silent, because the
        # receipt is written after the damage. `conversations.py` already writes this way
        # three times over (tmp beside the target, then os.replace); this is the same pattern,
        # not a new one. os.replace is atomic on the same filesystem, so a reader either sees
        # every byte of the old file or every byte of the new one, never a prefix of either.
        tmp = p.with_name(p.name + ".edit.tmp")
        try:
            tmp.write_text(text.replace(old, new, 1))
            os.replace(tmp, p)
        except OSError as e:
            # The original is untouched — os.replace either happened or did not.
            try:
                tmp.unlink()
            except OSError:
                pass
            return ResultEnvelope(ok=False, error=(
                f"the edit could not be written ({e}); '{path}' is unchanged. Nothing was "
                f"lost — the file is exactly as it was before you asked."))
        before = text.count("\n") + 1
        after = p.read_text(errors="replace").count("\n") + 1
        return ResultEnvelope(
            ok=True,
            result=(f"edited {p.name}: replaced 1 occurrence; the file went from {before} to "
                    f"{after} lines. This changed the file on disk — it is not an append."),
            witness_id=self._witness(f"memory_edit {p.name} ({before}->{after} lines)"))

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
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a") as f:
            f.write(content + ("\n" if not content.endswith("\n") else ""))
        return ResultEnvelope(ok=True, result=f"wrote {len(content)} chars to {p.name}",
                              witness_id=self._witness(f"memory_write {p.name}"))
