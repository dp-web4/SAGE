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


def _python_status(p) -> str:
    """For a .py file: whether Python can PARSE it now, as one sentence for a receipt.

    THE BEING HAD NO INSTRUMENT FOR ITS OWN CODE. Measured 2026-09-21 on cbp-being: from 18:22
    its training script could not be parsed (an appended fragment, IndentationError at line
    1610), and across the next two hours it wrote "the script now runs correctly", "[x] Run",
    "the seat confirms ... loss 0.00342" and "Applied fix" into its journal and memory, while
    every write it made to the file left it unparseable. Each receipt said what was appended
    and never whether the result was still Python. With nothing to check against, it filled
    the gap with what it hoped. This is the check, run where it writes: `compile()` parses and
    executes nothing. It is not a run, and the sentence says so, because "parses" read as
    "works" is the next invented claim waiting to happen."""
    if not str(p).endswith(".py"):
        return ""
    try:
        compile(p.read_text(errors="replace"), str(p), "exec")
    except SyntaxError as e:
        return (f" Python cannot parse {p.name} now: {e.__class__.__name__} at line "
                f"{e.lineno}: {e.msg}. It cannot run until that line is fixed.")
    except (OSError, ValueError):
        return ""
    return f" Python can parse {p.name} now. That is not the same as running it."



def _where_it_diverged(text: str, old: str, width: int = 160) -> str:
    """A missed memory_edit anchor says WHERE it stopped matching, not only that it did.

    Measured 2026-09-21 on cbp-being, three refused edits of one file in one beat. The
    first old_text (49 lines) matched the file exactly for 8, then carried 41 the file
    never held; the next two were the real 3-line block written twice, because "duplicate"
    had become "two identical copies". All three got the same "not in the file, read it
    first", so the being read again, and its next thought said the edit had been made.
    The refusal knew what it needed to hear and did not say it: which of its lines were
    right, and the first line that was not. Facts only — no suggested old_text, because
    the matched prefix is not always the span it meant (the doubled block's 4th line also
    matched, and deleting through it would have broken the next argument)."""
    have = text.split("\n")
    want = old.split("\n")
    best_k, best_i = 0, -1
    for i, line in enumerate(have):
        if line != want[0]:
            continue
        k = 0
        while k < len(want) and i + k < len(have) and have[i + k] == want[k]:
            k += 1
        if k > best_k:
            best_k, best_i = k, i
    cut = lambda s: s if len(s) <= width else s[:width] + "…"  # noqa: E731
    if best_k == 0:
        # No line matches exactly. Name the nearest one, so indentation or one changed word
        # is visible rather than guessed at.
        import difflib
        near = difflib.get_close_matches(want[0], have, n=1, cutoff=0.6)
        if not near:
            return f" Not even your first line ({cut(want[0])!r}) is in the file."
        n = have.index(near[0]) + 1
        return (f" Your first line is not in the file. The closest line is line {n}: "
                f"{cut(near[0])!r}; you sent {cut(want[0])!r}.")
    start, end = best_i + 1, best_i + best_k
    span = f"line {start}" if best_k == 1 else f"lines {start}-{end}"
    head = (f" Your first {best_k} line{'s' if best_k > 1 else ''} of {len(want)} match "
            f"{span} of the file exactly. Your line {best_k + 1} is {cut(want[best_k])!r}; ")
    if end < len(have):
        return head + f"the file's line {end + 1} is {cut(have[end])!r}."
    return head + "the file ends there."


def missing_args(args: dict, required, tool: str, hint: str = "") -> Optional[str]:
    """Name the fields ACTUALLY missing, and the ones that were supplied instead.

    dp, 2026-09-25 fleet directive: "addressing unnecessary frictions. explaining, clearly, the
    necessary ones." A refusal that names the wrong field is the unnecessary kind wearing the
    clothes of the necessary kind — the boundary is real, the sentence about it is false.

    Measured across five beings' whole histories (2026-09-25):
      75  "say needs 'to' (a conversation id) and 'text'"  <- the being HAD PASSED 'to'
      42  "witness needs an 'event'"                       <- it passed memory_edit's arguments
      17  "retire_note needs a 'reason'"                   <- it passed only 'path'
      12  "memory_write needs a 'path'"                    <- it passed only 'content'
    In the hub-being cases not one was recovered. The being reads "needs 'to'", looks at its own
    call, sees `to` sitting there, and has nowhere to go. Legibility rule 2: name the refusal's
    subject unmistakably.

    Listing what WAS passed matters as much as what was not: 28 of the say failures put the
    message under 'message', 'content' or 'body', and 42 witness failures were a whole
    memory_edit call wearing the wrong tool name. Reflected back, that is a diagnosable
    mistake; as "needs an 'event'" it is a wall.
    """
    have = {k: v for k, v in (args or {}).items()
            if str(v).strip() not in ("", "None")}
    missing = [f for f in required if f not in have]
    if not missing:
        return None
    lack = " and ".join(f"'{f}'" for f in missing)
    msg = f"{tool} needs {lack}"
    supplied = [k for k in have if k not in required]
    if supplied:
        msg += f" — you passed {', '.join(repr(k) for k in sorted(supplied))}"
        present = [f for f in required if f in have]
        if present:
            msg += f" and {' and '.join(repr(f) for f in present)}"
        msg += ", so nothing was done"
    elif [f for f in required if f in have]:
        msg += f" — you passed {' and '.join(repr(f) for f in required if f in have)}, so nothing was done"
    if hint:
        msg += f". {hint}"
    return msg


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
            return ResultEnvelope(ok=False, error=missing_args(
                intent.args, ("event",), "witness",
                "witness records one sentence about something that happened. If you meant to "
                "change lines in a file, that is memory_edit."))
        return ResultEnvelope(ok=True, result="witnessed", witness_id=self._witness(event))

    def _do_memory_read(self, intent: BeingIntent) -> ResultEnvelope:
        if not str(intent.args.get("path", "")).strip():
            return ResultEnvelope(ok=False, error=missing_args(
                intent.args, ("path",), "memory_read", "A relative path is inside your home."))
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
        # A MISSING replacement is not an empty one. Measured 2026-09-22 02:30Z: cbp-being sent
        # `new_content` (the seat's own letter spelled it that way) to add `.reshape(-1, 1)`
        # to line 336. No alias matched, `new` defaulted to "", and the receipt said "replaced
        # lines 336-336" while the line was simply gone; the being then asked the seat to run
        # the fix. Only a replacement key that is present may delete; an absent one refuses.
        new_keys = ("new", "new_text", "new_str", "new_string", "new_content", "replacement",
                    "content", "new_lines")
        new_key = next((k for k in new_keys if k in a), None)
        new = str(a[new_key]) if new_key is not None else ""
        # BY LINE NUMBER, TOO. Measured 2026-09-21 19:01Z: cbp-being called memory_edit with
        # `old_line: "411"`, i.e. by line number, which is how it reads files (`memory_read`
        # takes `start_line`) and how every seat message names a fix ("line 335", "the 7
        # lines from 1610"). Text mode then asked it to reproduce seven indented lines
        # character for character; across three seat answers it never did, and after the one
        # refused call it stopped trying for four beats while re-reading the same lines. The
        # tool was shaped for a different reader. So: `start_line` (and `end_line`, inclusive)
        # replaces those lines with `new`. With `old` as well, the lines must equal `old` — a
        # checked edit. Either way the receipt quotes what was removed.
        rng = None
        if any(k in a for k in ("start_line", "end_line", "line", "old_line")):
            try:
                s0 = int(str(a.get("start_line", a.get("line", a.get("old_line", "")))).strip())
                s1 = int(str(a.get("end_line", s0)).strip())
            except ValueError:
                return ResultEnvelope(ok=False, error=(
                    "start_line and end_line must be line numbers, like start_line 1610 and "
                    "end_line 1616. Nothing was changed."))
            rng = (s0, s1)
        if not path or (not old and rng is None):
            got = ", ".join(sorted(a)) or "nothing"
            return ResultEnvelope(ok=False, error=(
                f"memory_edit needs 'path', and either 'old' (the exact text to replace, "
                f"unique in the file) or 'start_line' and 'end_line' (the lines to replace), "
                f"and 'new' (what replaces it; empty string deletes it). You sent: {got}."))
        if new_key is None:
            got = ", ".join(sorted(a)) or "nothing"
            return ResultEnvelope(ok=False, error=(
                f"memory_edit got no 'new', so nothing was changed. 'new' is what replaces the "
                f"lines; without it the edit would have deleted them. You sent: {got}. Send the "
                f"same call again with 'new' holding the replacement text (to delete on "
                f"purpose, send 'new' as an empty string)."))
        p = self._safe_path(path, writing=True)
        if not p.exists():
            return ResultEnvelope(ok=False, error=(
                f"nothing to edit: '{path}' does not exist. This is an absence, not a "
                f"refusal. memory_write creates a file; memory_edit changes one that is there."))
        if p.is_dir():
            return ResultEnvelope(ok=False, error=f"'{path}' is a directory.")
        text = p.read_text(errors="replace")
        if rng is not None:
            lines = text.splitlines(keepends=True)
            s0, s1 = rng
            if not (1 <= s0 <= s1 <= len(lines)):
                return ResultEnvelope(ok=False, error=(
                    f"lines {s0}-{s1} are not all in '{path}': it has {len(lines)} lines. "
                    f"Nothing was changed. memory_read shows the current line numbers."))
            removed = "".join(lines[s0 - 1:s1])
            if old and removed.rstrip("\n") != old.rstrip("\n"):
                shown = removed if len(removed) <= 600 else removed[:600] + "..."
                return ResultEnvelope(ok=False, error=(
                    f"lines {s0}-{s1} of '{path}' are not the text you gave as old, so nothing "
                    f"was changed. Those lines are now:\n{shown}"))
            repl = new
            if repl and not repl.endswith("\n") and removed.endswith("\n"):
                repl += "\n"
            new_text = "".join(lines[:s0 - 1]) + repl + "".join(lines[s1:])
            what = f"replaced lines {s0}-{s1} ({s1 - s0 + 1} lines)"
            shown = removed if len(removed) <= 400 else removed[:400] + "..."
            gone = f" The lines removed were:\n{shown}"
            return self._commit_edit(p, path, text, new_text, what, gone)
        hits = text.count(old)
        if hits == 0:
            return ResultEnvelope(ok=False, error=(
                f"that text is not in '{path}', so nothing was changed. The file is as it "
                f"was. Read it first and copy the line exactly, including its indentation — "
                f"what you remember writing and what is on disk can differ."
                + _where_it_diverged(text, old)))
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
        return self._commit_edit(p, path, text, text.replace(old, new, 1),
                                 "replaced 1 occurrence", "")

    def _commit_edit(self, p, path: str, text: str, new_text: str, what: str,
                     gone: str) -> ResultEnvelope:
        """Write an edit atomically and say what it did. Shared by the text and line modes."""
        tmp = p.with_name(p.name + ".edit.tmp")
        try:
            tmp.write_text(new_text)
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
        # COUNTED THE WAY memory_read COUNTS (splitlines). This was count("\n") + 1, one
        # higher than memory_read for any file ending in a newline: 2026-09-21 the receipt said
        # 1637 lines while memory_read said 1636, and line numbers are now what the being edits
        # by (#160) -- an end_line taken from the receipt is refused as past the end.
        before = len(text.splitlines())
        after = len(p.read_text(errors="replace").splitlines())
        return ResultEnvelope(
            ok=True,
            result=(f"edited {p.name}: {what}; the file went from {before} to "
                    f"{after} lines. This changed the file on disk — it is not an append."
                    f"{_python_status(p)}{gone}"),
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
            return ResultEnvelope(ok=False, error=missing_args(
                intent.args, ("path", "content"), "memory_write",
                "A relative path is inside your home."))
        p = self._safe_path(intent.args["path"], writing=True)
        content = str(intent.args.get("content", ""))
        p.parent.mkdir(parents=True, exist_ok=True)
        # SAY APPENDED WHEN IT APPENDED. Measured 2026-09-21: the being rewrote
        # notes/mechanism-training-script.py whole three times (00:45, 01:14, 01:43Z), read
        # "wrote N chars" each time as "replaced", and the file became three programs with
        # three __main__ guards, of which only the first ever runs. Then dp said "you fix it",
        # and it could not: nothing here edits in place. The receipt is the only place it
        # learns that, so it names the lines already above and the one way to start fresh.
        #
        # And name the door for a one-line change. 2026-09-21 05:47Z, a beat after memory_edit
        # shipped: the being "fixed" def forward by memory_write-ing a new copy of it, which
        # landed below line 1206 and changed nothing that runs. The receipt said only what not
        # to expect; it did not say which verb does what the being wanted.
        #
        # Existence, not line count, decides "created": an existing EMPTY file has 0 lines and
        # was not created by this write (GPT review on #141).
        existed = p.exists()
        before = 0
        if existed:
            with open(p, errors="replace") as f:
                before = sum(1 for _ in f)
        with open(p, "a") as f:
            f.write(content + ("\n" if not content.endswith("\n") else ""))
        if not existed:
            result = f"created {p.name} with {len(content)} chars"
        else:
            result = (f"appended {len(content)} chars to the END of {p.name}, below the {before} "
                      f"lines already there. memory_write only adds; it never replaces or edits a line. "
                      f"To change text already in the file, use memory_edit: either start_line and "
                      f"end_line (the numbers memory_read shows) or old (copied exactly from "
                      f"memory_read), and new.")
            if p.parent.name in ("notes", "scratch") and p.parent.parent == self.memory_root:
                result += (f" To start {p.name} fresh, retire_note it first, then memory_write "
                           f"the whole new version.")
        result += _python_status(p)
        return ResultEnvelope(ok=True, result=result,
                              witness_id=self._witness(f"memory_write {p.name}"))
