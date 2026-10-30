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
import re
import textwrap
import contextlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

from sage.gateway.being_gate_client import (BeingIntent, GatewayVerdict, ResultEnvelope,
                                            copy_alternative, same_path_in_reach)

try:
    import fcntl
except ImportError:             # not POSIX: _home_lock does not serialize there
    fcntl = None


# What was SAID TO the being is not the being's to edit. notes/from-dp.md is the operator's
# own channel (written by the dp console) and notes/from-the-seat.md is the seat's; a being
# that could append to either could not later be distinguished from the person who wrote to
# it, and neither could anyone reading the record.
SEAT_OWNED_NOTES = ("from-dp.md", "from-the-seat.md")
# Files in the being's home itself that the SEAT owns. `entrustment.md` is what the being was
# GIVEN; if it could append to it, what was extended and what it decided would merge in the
# record. Refusing is not distrust: it may disagree anywhere else, and that record is wanted.
SEAT_OWNED = ("entrustment.md",)
# GOVERNANCE RECORDS IN THE HOME (SAGE #544). The being's home also holds the files that say who
# it is to the society, and no being verb may write them:
#   identity.json         the raising record: `identity.machine` picks the seat that arbitrates its
#                         escalations (escalate.seat_for), beside lct, trust_ceiling, anchor_type;
#   identity.sealed / identity.attest.json   the sealed identity and its attestation;
#   instance.json         the operator's layer: lct_id, machine, and the parameter bounds and locks
#                         the being's own `tune` layer sits under (being_params).
# These were reachable by memory_edit (and memory_write's append could corrupt the JSON, and the
# readers fall back silently). The raising pipeline and the identity provider write them as trusted
# Python, not through these verbs, so they are unaffected. What the being says of ITSELF is
# self.json, written by identity_edit (being_self, #541); it is not one of these.
# The identity family is matched by PREFIX, not by name: the provider keeps identity.sealed.v1 as
# the only original of a v1 seal after migration, and writes .tmp / .retired-* siblings beside the
# live files. A list would leave each of those writable (legion's review of #545). Nothing the
# being writes starts with "identity." (its own words are self.json).
GOVERNANCE_OWNED_PREFIX = "identity."
GOVERNANCE_OWNED = ("instance.json",)
# THE RECORD NAMES THEMSELVES ARE REFUSED IN EVERY DIRECTORY (#552). A home is recognised by its records
# (_looks_like_a_home), so a granted directory that holds none yet is not one, and a being could plant
# `identity.json` (choosing `machine`, so its own arbiter) before a home is provisioned there. These
# exact names, and their tmp/retired forms, are never a being's to write anywhere. The broader
# `identity.` prefix stays tied to homes: `notes/identity.md` is a being writing about itself.
# Compared casefolded (cbp review of #565): on a case-insensitive FS (WSL drvfs, default APFS)
# `Identity.json` is the file the readers open as `identity.json`.
GOVERNANCE_RECORD_NAMES = ("identity.json", "identity.sealed", "identity.attest.json", "instance.json")


def _named(p: Path, names) -> bool:
    """Is p one of these verb-owned files, case aside? A case-insensitive filesystem (macOS, the fleet's CBP
    and McNugget) opens `Settled.json` as `settled.json`, so an exact-case check would let memory_write past
    the verb's audit log there (the reason #565 casefolds governance names)."""
    return p.name.casefold() in {n.casefold() for n in names}


def _is_governance_record_name(name: str) -> bool:
    name = name.casefold()
    return any(name == n or name.startswith(n + ".") for n in GOVERNANCE_RECORD_NAMES)
# The conversation store is RESERVED from generic writes (GPT review of #56, #4): a turn
# reaches it only through `say`, which checks writable_by, witnesses the act and assigns
# the sequence under the lock. A memory_write into conversations/<id>.jsonl or its meta
# would let the being forge a `from: dp` turn, or rewrite who may speak, with no witness
# and no refusal. The whole subtree, not the two files that happen to exist today.
# asks_sent.jsonl is the record the ask limit counts (hestia_dispatch, SAGE #92); a being that
# could rewrite it could reset its own limit.
RESERVED_SUBTREES = ("conversations", "asks_sent.jsonl")
# A memory_read miss names same-named files one directory away; past this many it names the
# first ones and says how many more there are, rather than dropping them silently.
_SAME_NAME_SHOWN = 5
# memory_read with `find` (#351) lists at most this many matching lines, and cuts a matching line
# longer than _FIND_LINE_CHARS, saying it did both.
_FIND_SHOWN = 40
_FIND_LINE_CHARS = 240


_MAGIC = ((b"\xff\xd8\xff", "a JPEG image"), (b"\x89PNG\r\n\x1a\n", "a PNG image"),
          (b"GIF8", "a GIF image"), (b"RIFF", "a RIFF file (WAV audio or WebP image)"),
          (b"%PDF", "a PDF document"), (b"PK\x03\x04", "a zip archive"),
          (b"\x93NUMPY", "a NumPy array (.npy)"), (b"\x7fELF", "a compiled program (ELF)"))
_IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp")


def _binary_kind(p: Path) -> str:
    """What a non-text file is ('' for text): known magic first, then a NUL byte in its first 8 KiB."""
    try:
        with open(p, "rb") as f:
            head = f.read(8192)
    except OSError:
        return ""
    for magic, kind in _MAGIC:
        if head.startswith(magic):
            return kind
    if b"\x00" in head:
        return "binary data"
    return ""


def _binary_said(shown: str, p: Path, kind: str) -> str:
    try:
        st = p.stat()
        when = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%MZ")
        size = f"{st.st_size} bytes, written {when}"
    except OSError:
        size = "size unknown"
    line = (f"[not text: '{shown}' is {kind} ({size}). Its bytes were not returned: read as text they "
            f"are noise, and they would fill your window with it.")
    if kind.endswith("image") or p.suffix.lower() in _IMAGE_SUFFIXES:
        line += (" You see images as pictures, not as bytes: a frame you capture with camera is "
                 "shown to you at your next beat. To see the scene again, capture a new frame.")
    return line + "]"


def _named_file_stamps(content: str, root: Path, written: Path,
                       granted: tuple = (), readable=None) -> str:
    """For a record write (journal, todo, a note): when each code file it names last changed.

    MEASURED 2026-09-22 over cbp-being's 114 beats on 09-21/22 (sage/scripts/being_act_ledger.py):
    14 beats wrote a journal/todo/say line claiming a code change ("Fixed
    mechanism-training-script-clean.py.") in a beat where neither it nor the previous beat
    changed any .py file. Two explanations were tested on that data and neither held: the
    refusals were IN VIEW (6 of the 14 had one), and the claims did not copy its own closing
    words (closer to them in 4 of 14). In 8 of 14 no edit was attempted at all: the claim came
    from the plan. So: no judgement of the claim, which a heuristic would get wrong. A fact,
    stamped where the claim is written, that the being can compare with what it just wrote.
    Whether that changes what it writes is a separate, open measurement (rerun the ledger).

    Reads mtimes only and executes nothing. A name is looked for in the home and, when the
    caller passes them, in the being's granted roots (`granted`, each checked by `readable`, the
    same reach memory_read uses), and nowhere else: a file the being cannot read is never
    stamped, so the receipt is no oracle for what lies outside its reach.

    A MISS SAYS NOTHING (SAGE #396). "x.py was not found in your home" was read as "x.py does not
    exist" three times on cbp-being, the scope ("in your home") dropped each time: 2026-10-08 "the
    file itself was never persisted to disk" (it was in scratch/); 2026-10-26 16:01Z a pending
    scope request kept for a file in its own governance grant; 17:40Z "the file was not found at
    the expected path. I need to write to the correct path", then a write_note of a model-written
    gate core to the gate core's path, which only the governance closure refused. A miss gives the
    being nothing to act on, and the act it reads into one can be that. So a miss is omitted. A
    bare name is looked for at the top of the
    home, in notes/ and in scratch/, and a miss says exactly that, not "no such file" (the 09-28
    review found a bare train.py living in experiments/ reported as absent). scratch/ is where
    request_run files live: on 2026-10-08 a journal naming test-encoder-only.py got "not found"
    on every write, and the being told the seat "the seat also says it was not found"."""
    out, seen = [], set()
    home = root.resolve()
    for name in re.findall(r"[\w./-]+\.py\b", content or ""):
        name = name[2:] if name.startswith("./") else name
        if not name or name in seen or len(out) >= 3:
            continue
        seen.add(name)
        cand = [root / name] + ([root / d / name for d in ("notes", "scratch")]
                                if "/" not in name else [])
        hit = None
        for c in cand:
            try:
                rc = c.resolve()
                rc.relative_to(home)
            except (OSError, ValueError):
                continue
            if rc.is_file() and rc != written.resolve():
                hit = rc
                break
        if hit is None and "/" in name and readable is not None:
            # in a grant: absolute as written, or relative to a granted root, or to the root's
            # parent when the name starts with the root's own name (`governance/hestia/...` under
            # a grant on <ws>/governance), the spelling the seat and the being both use
            first = Path(name).parts[0]
            g_cand = ([Path(name)] if os.path.isabs(name) else
                      [g / name for g in granted] + [g.parent / name for g in granted if g.name == first])
            for c in g_cand:
                try:
                    rc = c.resolve()
                except OSError:
                    continue
                if rc.is_file() and rc != written.resolve() and readable(rc):
                    hit = rc
                    break
        if hit is None or hit in seen:
            continue
        t = datetime.fromtimestamp(hit.stat().st_mtime, timezone.utc)
        seen.add(hit)
        try:
            shown = f"{hit.relative_to(home)}"
        except ValueError:
            shown = f"{hit} (in your grant)"
        out.append(f"{shown} was last changed at {t:%Y-%m-%d %H:%M} UTC")
    return (" Files this names: " + "; ".join(out) + ".") if out else ""


# A REPLACE KEEPS THE OLD COPY. legion-being, 2026-09-27..10-04: of 537 whole-file replaces, four
# took a large file to almost nothing (todo.md 143 KB -> 1.1 KB, 48 KB -> 1.9 KB, 102 KB -> 385 B;
# a worktree test file 90 KB -> 12 B), at least two by mistake ("I overwrote a 102KB todo.md
# without reading it first"). The receipt said so every time, AFTER the bytes were gone, and a
# 100 KB file cannot be retyped through a 24k window. So the previous version of any file of
# REPLACE_KEEP_MIN bytes or more is copied into the being's own home first, the receipt names it,
# and memory_write mode='restore' puts the newest copy back in one call. Nothing is refused:
# a deliberate clean-up costs nothing and stays one step from undone.
REPLACE_KEEP_DIR = "scratch/replaced"
REPLACE_KEEP_MIN = 4096
REPLACE_KEEP_S = 7 * 24 * 3600


def _kept_name(p, roots) -> str:
    """A flat, readable name for p's kept copies: its path under the root it lives in, '/' -> '__'."""
    from pathlib import Path as _P
    rp = _P(p).resolve()
    for r in roots:
        if r:
            try:
                return str(rp.relative_to(_P(r).resolve())).replace("/", "__")
            except ValueError:
                continue
    return rp.name


def _keep_previous(p, memory_root, roots) -> str:
    """Copy p's current bytes into <home>/scratch/replaced/<UTC stamp>-<name>; prune copies older than
    REPLACE_KEEP_S. Returns the home-relative path of the copy, or '' when the copy could not be made."""
    import shutil
    import time as _t
    from pathlib import Path as _P
    d = _P(memory_root) / REPLACE_KEEP_DIR
    try:
        d.mkdir(parents=True, exist_ok=True)
        name = f"{_t.strftime('%Y%m%d-%H%M%S', _t.gmtime())}-{_kept_name(p, roots)}"
        dest = d / name
        n = 0
        while dest.exists():
            n += 1
            dest = d / f"{name}.{n}"
        shutil.copy2(p, dest)
        now = _t.time()
        for old in d.iterdir():
            try:
                import calendar
                age = now - calendar.timegm(_t.strptime(old.name[:15], "%Y%m%d-%H%M%S"))
            except ValueError:
                continue
            if age > REPLACE_KEEP_S:
                old.unlink(missing_ok=True)
        return f"{REPLACE_KEEP_DIR}/{dest.name}"
    except Exception:
        return ""


def _newest_kept(p, memory_root, roots):
    from pathlib import Path as _P
    d = _P(memory_root) / REPLACE_KEEP_DIR
    suffix = "-" + _kept_name(p, roots)
    if not d.is_dir():
        return None
    hits = sorted(x for x in d.iterdir() if x.name[15:].split(".")[0] == suffix or x.name[15:] == suffix)
    return hits[-1] if hits else None


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



def _parses(src: str) -> bool:
    try:
        compile(src, "<edit>", "exec")
    except (SyntaxError, ValueError):
        return False
    return True


def _broke_it(p, before: str, after: str) -> str:
    """A .py edit that took a parsing file to an unparseable one says it is the cause.

    Measured on cbp-being, 2026-10-12 09:11:53Z: a range edit overwrote an import
    continuation line (`    orthogonal_decoder, orthogonal_projection`) and the receipt said
    the spaces changed, then the SyntaxError, then the removed line last. The next beat
    re-indented the new line three times and never put the import back. The receipt knew,
    and did not say, that the file parsed one edit ago; undoing this edit is a measured
    repair, not a guess, because the text before it is the text that parsed."""
    if not str(p).endswith(".py") or _parses(after) or not _parses(before):
        return ""
    return (f" Before this edit {p.name} parsed, so this edit is what stopped it: putting "
            f"back the text it removed makes {p.name} parse again.")


def _spaces_verdict(lines: list, s0: int, s1: int, removed: str, new: str) -> str:
    """When a range edit leaves the file unparseable AND changed the first line's indent, try
    the new text at the replaced line's indent and say whether THAT parses. 2026-10-12
    09:15:27Z: cbp-being read "Line 53 now starts with 0 spaces" as the cause of a
    SyntaxError the spaces had nothing to do with, and spent a beat flipping them (8, 4, 8).
    The indentation note says the counts differ; this says whether the counts matter.

    A failed retry proves only that the spaces ALONE do not repair the file, not that they
    play no part: the new text can carry a second defect beside its indent, or the file can
    already be broken elsewhere (Nova, SAGE #427, 2026-10-13). So the negative verdict says
    what was measured and nothing more."""
    def first(s: str) -> str:
        return next((ln for ln in s.splitlines() if ln.strip()), "")
    a, b = first(removed), first(new)
    if not a or not b:
        return ""
    na, nb = _leading_spaces(a), _leading_spaces(b)
    if na == nb:
        return ""
    d = na - nb
    shifted = "".join((" " * d + ln) if d > 0 and ln.strip()
                      else (ln[min(-d, _leading_spaces(ln)):] if d < 0 else ln)
                      for ln in new.splitlines(keepends=True))
    if shifted and not shifted.endswith("\n") and removed.endswith("\n"):
        shifted += "\n"
    trial = "".join(lines[:s0 - 1]) + shifted + "".join(lines[s1:])
    if _parses(trial):
        return (f" With {na} spaces, as the line it replaced had, Python could parse it.")
    return (f" With {na} spaces, as the line it replaced had, Python still cannot parse it: "
            f"changing the spaces alone will not make it parse.")


def _leading_spaces(line: str) -> int:
    """How many spaces a line starts with: the count both indentation notes below report."""
    return len(line) - len(line.lstrip(" "))


def _whole_lines_once(text: str, new: str) -> bool:
    """True when `new` is in `text` exactly once AND that copy runs from a line start to a line
    end. A substring count alone is not "already in place". Measured 2026-10-09 22:16Z:
    cbp-being's line 103 held a spliced tail ('np.linalg.pinv(X_tX)g.pinv(X_tX)'); it sent a
    4-line old= that was not on disk and a 4-line new= whose last line was the FIXED line.
    The fixed line is a prefix of the unfixed one, so text.count(new) was 1 and this branch
    said "already in place ... the file already says what this edit asks for" while the
    SyntaxError was still there. The being read that as done and asked its seat to run the
    unfixed bytes (seq 8481). A match that stops mid-line is the same cut the mid-line old=
    refusal catches, seen from the other side."""
    if text.count(new) != 1:
        return False
    i = text.find(new)
    j = i + len(new)
    at_line_start = i == 0 or text[i - 1] == "\n"
    at_line_end = j == len(text) or text[j] == "\n" or new.endswith("\n")
    return at_line_start and at_line_end


def _indent_only_miss(have: str, old: str, new: str, first_line: int) -> str:
    """A range edit refused because old differs from the lines only in leading spaces says so,
    in counts. (_indent_changed covers the edit that LANDS; this covers the refusal.)

    Measured 2026-09-24 on cbp-being: memory_edit start_line=394 with old
    'model = Model(n_components=10, ...)' was refused twice in one beat, because the file's
    line 394 starts with 4 spaces. The refusal printed the line WITH its spaces, which the
    being cannot see, so it read the file's line as its own old. Next it used memory_write,
    which appended the line at the end of the file (line 864), where it never runs, then
    asked for a run. Again 2026-09-27 04:58Z (line 144, 4 spaces): it told dp "the file
    content didn't match exactly" and queued a retry without knowing why. A count is visible
    where the spaces are not. The note covers new too: a replacement without the spaces
    would move the crash to an IndentationError. And when new is old verbatim, the edit
    would change nothing even once the spaces match, so that is said as well."""
    h = have.rstrip("\n").split("\n")
    w = old.rstrip("\n").split("\n")
    if len(h) != len(w) or any(a.strip() != b.strip() for a, b in zip(h, w)):
        return ""
    for k, (a, b) in enumerate(zip(h, w)):
        na, nb = _leading_spaces(a), _leading_spaces(b)
        if na != nb:
            note = (f"\nThey differ only in the spaces at the start of the line. Line "
                    f"{first_line + k} in the file starts with {na} spaces; that line of your "
                    f"old starts with {nb}. The spaces are part of the text: put {na} in old, "
                    f"and in new as well, or the replaced line will not line up with the ones "
                    f"around it.")
            if new.rstrip("\n") == old.rstrip("\n"):
                note += (" Your new is also the same text as your old, so even with the spaces "
                         "matched this edit would change nothing.")
            return note
    return ""


def _old_is_elsewhere(text: str, old: str, first_line: int) -> str:
    """A range edit refused because the lines are not old says where old IS, when it occurs
    exactly once. (Zero or several hits: the line number is the only locator, so say nothing.)

    Measured 2026-10-07 02:53Z on cbp-being: the seat's message gave the exact old/new text
    for one line and, separately, the traceback's line number (148). The line to change was
    145. The being sent the seat's old text verbatim with start_line 148, was refused twice
    in one beat ("lines 148-148 ... are not the text you gave as old"), and then said it
    would apply the fix. The refusal showed line 148 but not that old was in the file once,
    three lines up, so the right text and a wrong number cost a beat. The edit is not
    retargeted on its own: the number may be the part the being meant."""
    if not old.strip() or text.count(old) != 1:
        return ""
    at = text[:text.index(old)].count("\n") + 1
    if at == first_line:
        return ""
    n = old.rstrip("\n").count("\n")
    where = f"line {at}" if n == 0 else f"lines {at}-{at + n}"
    return (f"\nYour old text IS in the file, once, at {where}, not at line {first_line}. "
            f"Send the same edit with no start_line and end_line (old alone finds it), or "
            f"with start_line {at}.")


def _indent_changed(removed: str, new: str, first_line: int) -> str:
    """A range edit whose first line lost or gained leading spaces says so, in counts.

    Measured on cbp-being, 2026-09-27 06:30Z: its first range edit ever aimed at the right
    line (144) sent the right text (n_latent -> n_features) without the line's 4 leading
    spaces. The receipt quoted the removed line WITH its spaces, which the being cannot
    see, and the parse note named line 145, the line AFTER the cause. The being followed
    that number and overwrote line 145 (`return X, y, W_TRUE`) with an unrelated line, then
    dedented that until the file parsed. A count is visible where the spaces are not. The
    edit still lands, since a dedent can be meant; only the counts are added."""
    def first(s: str) -> str:
        return next((ln for ln in s.splitlines() if ln.strip()), "")
    a, b = first(removed), first(new)
    if not a or not b:
        return ""
    na, nb = _leading_spaces(a), _leading_spaces(b)
    if na == nb:
        return ""
    return (f". Line {first_line} now starts with {nb} spaces; the line it replaced started "
            f"with {na}. In Python those spaces decide which block a line belongs to")


def _head_and_tail(removed: str, budget: int = 400) -> str:
    """A long removal is quoted by its first AND last lines, with the count of the middle.

    Measured on cbp-being, 2026-10-07 19:03Z: told to delete a 13-line duplicate decoder
    block, it deleted lines 75-107 (33 lines), also taking the class's forward and the start
    of train_model. The receipt quoted only the first 400 chars, which was the decoder block
    it meant to delete, then '...'. The overreach was in the cut. A range that runs too far
    runs too far at its END, so the end is what the receipt must show."""
    if len(removed) <= budget:
        return removed
    lines = removed.splitlines(keepends=True)
    head, tail = [], []
    used = 0
    for ln in lines:
        if used + len(ln) > budget // 2 and head:
            break
        head.append(ln)
        used += len(ln)
    used = 0
    for ln in reversed(lines[len(head):]):
        if used + len(ln) > budget // 2 and tail:
            break
        tail.insert(0, ln)
        used += len(ln)
    hidden = len(lines) - len(head) - len(tail)
    if hidden <= 0:
        return removed
    return "".join(head) + f"[... {hidden} more removed lines not shown ...]\n" + "".join(tail)


def _defs_removed(removed: str) -> str:
    """Name every def/class line a removal took, since a quote can be cut but a name list is short."""
    names = [ln.strip().split("(")[0].rstrip(":") for ln in removed.splitlines()
             if ln.lstrip().startswith(("def ", "class ", "async def "))]
    if not names:
        return ""
    return "\nThis removed " + ", ".join(f"'{n}'" for n in names) + "."


def _not_python(content: str, before: str) -> str:
    """Why `content` cannot be appended to a .py file, or "" if it can.

    A DESCRIPTION OF AN EDIT IS NOT AN EDIT. Measured on cbp-being, 2026-09-21 to 09-23: 15
    memory_write calls appended prose to its training script where a change was meant --
    "[Fix #1: Removed extra closing parenthesis on line 1685 ...]", "[Remove lines 344-347
    ...]", "[BEAT 05:18 UTC] Applying fix #1 ...". Every receipt said "memory_write only
    adds" and named memory_edit; at 05:18Z on 09-23 it had the exact memory_edit calls from
    the seat and still wrote the labels, then told the seat "Both fixes applied". A receipt
    arrives after the file is already worse. So the check runs before the write.

    The test is grammar, not a list of phrases: the text is accepted if Python can read it
    as code as written, dedented, or as a function body (a fragment with `return` is still
    code), OR if the file parses once it is appended (the last part of a program written in
    parts). Replayed over all 69 .py appends in its record, this refuses the 15 labels and 4
    code fragments whose own indentation was inconsistent, and nothing that parsed."""
    def parses(src: str) -> Optional[SyntaxError]:
        try:
            compile(src, "<text>", "exec")
        except SyntaxError as e:
            return e
        except ValueError:
            return None
        return None
    first = parses(content)
    if first is None:
        return ""
    body = textwrap.dedent(content)
    if parses(body) is None:
        return ""
    if parses("def _f():\n" + textwrap.indent(body, "    ", lambda _l: True) + "\n    pass\n") is None:
        return ""
    if parses(before + ("" if before.endswith("\n") or not before else "\n") + content) is None:
        return ""
    lines, at = content.splitlines(), (first.lineno or 1) - 1
    line = lines[at] if 0 <= at < len(lines) else ""
    # Not the compiler's msg: for prose it is noise ("leading zeros in decimal integer
    # literals" for a line starting "[BEAT 2026-09-23"). The line itself says what it is.
    return (f"Python cannot read line {first.lineno} of your text as code: "
            f"{line.strip()[:100]!r}. Appending it would not make the file parse either.")


def _first_syntax_error(src: str) -> Optional[SyntaxError]:
    """The compiler's FIRST stop in `src`, or None if it parses. compile() executes nothing."""
    try:
        compile(src, "<file>", "exec")
    except SyntaxError as e:
        return e
    except ValueError:
        return None
    return None


def _file_state(src: str) -> tuple:
    """("complete" | "incomplete" | "invalid", first SyntaxError or None) for a whole .py file.

    Incomplete is not invalid. A program written in parts is unfinished between the parts (an
    open bracket, a block header with no body yet, an unterminated docstring), and Python then
    reports its error at the OPENING line ("'(' was never closed", line 1), not at the end. So
    the first error's line cannot tell a program still being written from one that is broken.
    codeop.compile_command draws exactly that line: it returns None for source that is merely
    incomplete and raises for source that is wrong. It compiles only and executes nothing."""
    import codeop
    import warnings
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r = codeop.compile_command(src, "<file>", "exec")
    except SyntaxError as e:
        return "invalid", e
    except (ValueError, OverflowError):
        return "complete", None
    if r is None:
        return "incomplete", _first_syntax_error(src)
    return "complete", None


def _fresh_name(p):
    """A sibling name for `p` that does not exist yet: <stem>-new.py, then -new2, -new3, ...
    A hint that names a fresh start must never name a file that is already there: that "door"
    is one more append (cbp-claude's review of #197, 2026-09-28)."""
    fresh, n = p.with_name(f"{p.stem}-new{p.suffix}"), 2
    while fresh.exists():
        fresh, n = p.with_name(f"{p.stem}-new{n}{p.suffix}"), n + 1
    return fresh


_MAIN_GUARD = re.compile(r"""^if\s+__name__\s*==\s*['"]__main__['"]\s*:""", re.M)


def _is_second_program(content: str, before: str) -> bool:
    """Whether `content`, appended to the .py `before`, is a whole program of its own landing
    below another one -- not the next part of a program written in parts.

    It must be a complete program by itself (#240's rule: it compiles alone and has a def,
    class or import), AND it must collide with what is already there: it redefines a top-level
    def/class the file already has, or both carry a __main__ guard. A later part of one program
    adds new names below the old ones and at most one guard, so it never qualifies (cbp-claude's
    review of #197: the first cut hinted on every append to a top-level .py)."""
    import ast
    if _file_state(content)[0] != "complete" or not re.search(r"^(def|class|import|from) ", content, re.M):
        return False
    def names(src):
        return {n.name for n in ast.parse(src).body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    try:
        clash = names(content) & names(before)
    except (SyntaxError, ValueError):
        clash = set()
    return bool(clash) or bool(_MAIN_GUARD.search(content) and _MAIN_GUARD.search(before))


def _append_must_advance(content: str, before: str) -> str:
    """Why appending `content` to a .py file would move it backwards, and so is refused, or "".

    AN APPEND BELOW THE FIRST ERROR CANNOT REPAIR IT. GPT's review of #186 named the invariant,
    and cbp-being supplied two counterexamples the grammar check (_not_python) lets through:
    - 2026-09-23 07:15 (seq 3405): a label written as `#` comments ("# Remove stray ']' at line
      1736 ...") on a file that did not parse. Comments are valid Python, so it was accepted.
      One beat later the comment was the premise of a request to delete a ']' that did not exist.
    - 2026-09-24 10:31: two memory_write calls appended 4,515 and 4,765 chars of VALID Python to
      a file already stopped at line 2367. The stop did not move. The beat then counted the new
      sha as progress: "the indentation fix already applied".
    Both change a broken file without changing why it is broken. The rule is MONOTONIC (GPT's
    ruling on #186's open question, 2026-09-26): an append may never move a file backwards.
    - HEALTHY (parses) -> stays healthy. An append that would make a working file invalid is
      refused. The original rule let an over-indented fragment through because its text parsed
      on its own dedented, and the file it landed in did not.
    - INCOMPLETE (a program written in parts) -> incomplete or healthy, and only with actual code.
      A label makes it invalid and is refused.
    - INVALID (wrong somewhere, not merely unfinished) -> healthy only. An append below the first
      error cannot repair it."""
    state, err = _file_state(before)
    combined = before + ("" if before.endswith("\n") or not before else "\n") + content
    after, err_after = _file_state(combined)
    if after == "complete":
        return ""
    if state == "complete":
        where = f"line {err_after.lineno} ({err_after.msg})" if err_after else "the end (unfinished)"
        return (f"The file parses now, and this text would break it: appended, Python would stop at "
                f"{where}. An append must leave a working file working.")
    if state == "incomplete" and after == "incomplete" and not _not_python(content, before):
        return ""
    stop = (err.lineno if err else None) or "?"
    if state == "incomplete":
        return (f"The file is an unfinished program (Python stops at line {stop}: "
                f"{err.msg if err else 'incomplete'}), and this text does not continue it: "
                f"appended, the file would no longer be a program at all.")
    return (f"The file does not parse now: Python stops at line {stop} ({err.msg}). Appending "
            f"below it cannot fix that. The file would still stop at line "
            f"{(err_after.lineno if err_after else stop)}, so this write would change the file "
            f"without repairing it. Fix line {stop} itself with memory_edit.")


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
    best_k, ties = 0, []
    for i, line in enumerate(have):
        if line != want[0]:
            continue
        k = 0
        while k < len(want) and i + k < len(have) and have[i + k] == want[k]:
            k += 1
        if k > best_k:
            best_k, ties = k, [i]
        elif k == best_k and k > 0:
            ties.append(i)
    best_i = ties[0] if ties else -1
    cut = lambda s: s if len(s) <= width else s[:width] + "…"  # noqa: E731
    if best_k == 0:
        # No line matches exactly. Name the nearest one, so indentation or one changed word
        # is visible rather than guessed at. Rank on the STRIPPED text, then show the line as it
        # is. Measured 2026-10-04 on cbp-being: it sent an unindented old for line 28 (16
        # spaces); ranking with the indentation counted made line 212 (12 spaces, one word
        # different, dead code after main()) the "closest", and its next edit changed 212.
        import difflib
        import re
        bare = [line.strip() for line in have]
        # A def/class line is anchored by its NAME, which is the few characters difflib weighs
        # least. Measured 2026-10-08 on cbp-being: it sent 'def main(latent_dim: int = 100):',
        # the closest line was 'def create_decoder(latent_dim: int = 100):' (line 28), and its
        # next edit rewrote create_decoder's signature, breaking the call at line 87; main was
        # line 74 all along. Name the line that defines the name it sent, or say none does.
        head = re.compile(r"(?:async\s+)?(def|class)\s+(\w+)")
        sent = head.match(want[0].strip())
        if sent:
            same = [i for i, b in enumerate(bare)
                    if (m := head.match(b)) and m.group(2) == sent.group(2)]
            if same:
                where = "; ".join(f"line {i + 1}: {cut(have[i])!r}" for i in same)
                return (f" Your first line is not in the file. {sent.group(2)} is defined at "
                        f"{where}; you sent {cut(want[0])!r}.")
            return (f" Your first line is not in the file, and no line defines "
                    f"{sent.group(2)}; you sent {cut(want[0])!r}.")
        # An assignment is anchored by the name it assigns, for the same reason. Measured
        # 2026-10-12 on cbp-being: asked to edit line 31, 'projected = orthogonal_projection(
        # w_true, A)', it sent 'projected, norm = orthogonal_projection(A, w_with_outside)'.
        # The closest line was 47, 'projected_modified = orthogonal_projection(w_with_outside,
        # A)' (shared arguments again), and its next edit rewrote 47, dropping the w_with_outside
        # the test existed to project. Name the lines that assign its first name, if any do;
        # otherwise fall through, since a new name is often what an edit is introducing.
        lhs = re.compile(r"[\w.]+(?:\s*,\s*[\w.]+)*\s*=(?!=)")

        def assigns(b: str) -> list:
            m = lhs.match(b)
            return re.findall(r"[\w.]+", m.group(0)) if m else []
        assigned = assigns(want[0].strip())
        if assigned:
            same = [i for i, b in enumerate(bare) if assigned[0] in assigns(b)]
            if same:
                where = "; ".join(f"line {i + 1}: {cut(have[i])!r}" for i in same[:5])
                return (f" Your first line is not in the file. {assigned[0]} is assigned at "
                        f"{where}; you sent {cut(want[0])!r}.")
        near = difflib.get_close_matches(want[0].strip(), bare, n=1, cutoff=0.6)
        if not near:
            return f" Not even your first line ({cut(want[0])!r}) is in the file."
        n = bare.index(near[0]) + 1
        return (f" Your first line is not in the file. The closest line is line {n}: "
                f"{cut(have[n - 1])!r}; you sent {cut(want[0])!r}.")
    # MORE THAN ONE PLACE. Measured 2026-09-21: cbp-being's refused `old` began with 3 lines
    # of a stray block at 1610-1612 that ALSO occur at 330-332, the working data-loading
    # branch. Naming only the first match told it "your lines are at 330", and a 4B acting on
    # that deletes the code that works. When the matched prefix repeats, say every place, and
    # what the file has after each, so the being can tell which one it meant.
    if len(ties) > 1:
        # Show each place at the first line where the places DIFFER from each other: the
        # line right after the prefix is often shared too (2026-09-21: `else:` in both).
        d = best_k
        while d < best_k + 20 and all(i + d < len(have) for i in ties) and \
                len({have[i + d] for i in ties}) == 1:
            d += 1

        def at(i):
            s0, e0 = i + 1, i + best_k
            where = f"line {s0}" if best_k == 1 else f"lines {s0}-{e0}"
            after = (f"and its line {i + d + 1} is {cut(have[i + d])!r}" if i + d < len(have)
                     else "then the file ends")
            return f"{where} ({after})"
        places = "; ".join(at(i) for i in ties[:4]) + ("; ..." if len(ties) > 4 else "")
        return (f" Your first {best_k} line{'s' if best_k > 1 else ''} of {len(want)} match "
                f"the file exactly in {len(ties)} places: {places}. Your line {best_k + 1} is "
                f"{cut(want[best_k]) if best_k < len(want) else '(none)'!r}.")
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



# A DATED LINE SAYS WHAT WAS TRUE ON ITS DATE (2026-09-29). cbp-being escalated to dp that "the MCP
# server has been offline ~6 hours" and that coordination requests #12529/#12530/#12624/#12638 had
# gone unanswered, while membot and hestia were both up. Every element of it was in its own
# inbox.md, written 2026-09-13/14; the being read that file in the beat and repeated it as
# current. #92 had already put a MEASURED reachability line in every beat's state, and the read
# still won. The file's mtime could not help: the being had appended to inbox.md at 06:10 that
# day, so the file was "40 minutes old" while most of its lines were fifteen days old. So the read
# reports the age of the DATED LINES it shows, not the age of the file.
_DATED_LINE = re.compile(
    r"^\s*(?:[-*]\s*(?:\[[ xX]\]\s*)?)?"            # optional bullet / checkbox
    r"(?P<date>20\d\d-\d\d-\d\d)"
    r"(?:[ T](?P<hm>\d\d:\d\d)(?::(?P<sec>\d\d)(?:\.(?P<frac>\d+))?)?)?"  # time; seconds, fraction
    r"\s*(?P<zone>Z\b|UTC\b|GMT\b|[+-]\d\d:?\d\d\b)?")    # optional explicit zone / offset
STALE_LINE_SECS = 24 * 3600
# The widest real UTC offsets are -12:00 and +14:00. A time written WITHOUT a zone is placed at
# its LATEST possible instant (as if UTC-12), so it is never called older than it could be.
_LATEST_UNZONED = timedelta(hours=12)


def _latest_instant(date: str, hm: Optional[str], zone: Optional[str],
                    sec: Optional[str] = None, frac: Optional[str] = None) -> Optional[datetime]:
    """The SUPREMUM of the UTC instants this date/time could denote: every reading is strictly
    earlier. The zone is honoured exactly when given; with no zone the time is placed as if
    UTC-12. The written precision is honoured too: a time is the whole interval that truncates
    to it (a minute-precision time covers :00 to :59.999..., seconds cover their fraction, a
    date with no time its whole calendar day), never its first instant."""
    try:
        day = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return None
    if hm is None:
        return (day + timedelta(days=1)).replace(tzinfo=timezone.utc) + _LATEST_UNZONED
    try:
        local = datetime.strptime(date + " " + hm + ":" + (sec or "00"), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    # ADD ONE UNIT OF THE LAST WRITTEN PRECISION (GPT re-review of #270: the seconds were parsed
    # and discarded, so `12:00:59Z` was read as 12:00:00 and called more than a day old at
    # 23h59m31s). The result is the interval's supremum, which no reading reaches, hence the >=
    # in `dated_lines_note`. A fraction is taken in integer microseconds and rounded UP, so the
    # bound is never early even when more than six digits were written.
    if frac:
        local += timedelta(microseconds=-(-(int(frac) + 1) * 10 ** 6 // 10 ** len(frac)))
    elif sec is not None:
        local += timedelta(seconds=1)
    else:
        local += timedelta(minutes=1)
    if zone in ("Z", "UTC", "GMT"):
        return local.replace(tzinfo=timezone.utc)
    if zone:
        sign = -1 if zone[0] == "-" else 1
        digits = zone[1:].replace(":", "")
        off = timedelta(hours=int(digits[:2]), minutes=int(digits[2:]))
        return (local - sign * off).replace(tzinfo=timezone.utc)
    return local.replace(tzinfo=timezone.utc) + _LATEST_UNZONED


def dated_lines_note(text: str, now: Optional[datetime] = None) -> str:
    """One bracketed line about the dated lines in `text`, or "" when none is more than a day old.

    A line that starts with a date (optionally after a bullet or checkbox) opens a dated span;
    undated lines that follow belong to it. Only the window being shown is counted.

    What can be timed (GPT reviews of #270): an explicit zone or numeric offset (Z, UTC, GMT,
    +hh:mm, -hhmm) is honoured exactly, and so is the written precision: `12:00Z` means some
    instant in [12:00:00, 12:01:00), `12:00:59Z` one in [12:00:59, 12:01:00). A time with no
    zone, and a date with no time, are wider intervals still. Every line is counted from the
    END of its interval, so a line is only ever called old when it is old under every reading. Other zone spellings (PDT, CET)
    are not parsed and are treated as no zone, which is the conservative direction."""
    now = now or datetime.now(timezone.utc)
    current = None
    zoned_all = True
    under: dict = {}
    written: dict = {}
    for line in text.splitlines():
        m = _DATED_LINE.match(line)
        if m:
            current = _latest_instant(m.group("date"), m.group("hm"), m.group("zone"),
                                      m.group("sec"), m.group("frac"))
            if current is not None:
                written.setdefault(current, m.group("date"))
                if not (m.group("hm") and m.group("zone")):
                    zoned_all = False
        if current is not None and line.strip():
            under[current] = under.get(current, 0) + 1
    if not under:
        return ""
    # `d` is a supremum no reading attains, so an age of EXACTLY a day from it means every
    # reading is more than a day old: >= here is the strict "more than a day" of each reading.
    old = {d: n for d, n in under.items() if (now - d).total_seconds() >= STALE_LINE_SECS}
    if not old:
        return ""
    oldest, newest = min(under), max(under)
    days = int((now - oldest).total_seconds() // 86400)
    caveat = "" if zoned_all else (" Lines without a time zone are counted at the latest time "
                                   "they could mean, so these ages are minimums.")
    return (f"[dated lines shown here run from {written[oldest]} to {written[newest]}; "
            f"{sum(old.values())} of {sum(under.values())} dated lines are more than a day old "
            f"(the oldest at least {days} day{'s' if days != 1 else ''} ago).{caveat} A dated line "
            f"says what was true on its date; appending to a file does not make its older lines "
            f"current. For what is up now, the measured lines in your state are from this beat.]\n")


def _todo_close_door(p: Path) -> str:
    """On a missed memory_edit of todo.md, the door that needs no exact text. Measured over
    cbp-being's whole history to 2026-10-17: 523 memory_edits ticking a todo item done, 367 of
    them refused on old-text mismatch, and 34 of 41 deletions likewise. The beat window closes an
    item from an appended `done:` line (a fuzzy match), so the edit was never needed."""
    if p.name != "todo.md":
        return ""
    return (" To close a todo item you do not need an edit: memory_write todo.md with the item "
            "under done: and the window drops it. To start the whole list fresh, retire_note "
            "todo.md; the items still open are carried forward.")


# The being's running records, which retire_note starts fresh (see _do_retire_note).
RETIRABLE_RECORDS = ("todo.md", "journal.md")

# ONE LOCK PER HOME FOR APPENDS AND RETIRES. Nova's review of 0557d9bcf: "retirement can
# unlink/recreate a live journal or todo while memory_write appends, risking lost entries".
# Two processes act in one home (the heartbeat's dispatcher and the raising session's), so an
# append landing between retire's read and its swap would be in neither the retired copy nor
# the fresh file. The lock is a separate file, not the record itself: os.replace gives the
# record a new inode, and an appender that was waiting on the old one would wake holding a lock
# on a file no name points at, and append into it.
HOME_LOCK = ".home.lock"
# Every verb that changes a file in the home holds the lock for its whole run (see __call__).
HOME_WRITE_VERBS = ("memory_write", "memory_edit", "retire_note")


def _looks_like_a_home(d: Path) -> bool:
    """A being's home is recognised by its records, wherever it sits (#546)."""
    try:
        return (d / "identity.json").exists() or (d / "instance.json").exists()
    except OSError:
        return False


@contextlib.contextmanager
def _home_lock(root: Path):
    if fcntl is None:           # no flock on this platform: the old, unserialized behaviour
        yield
        return
    with open(root / HOME_LOCK, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


_RETIRED_KEPT = "> Kept whole below, as it was written.\n\n"


def _retired_header(stamp: datetime, reason: str) -> str:
    # NO ACTOR IS NAMED. Nova's hold at dcc5c630b: this read "by cbp-being" in every resident's
    # home, so another being's retired journal would carry a false attribution in its own record.
    # The dispatcher is built from a home and holds no bound identity to name, and the copy sits
    # in that resident's home already; the verb is what is known, so the verb is what is said.
    return (f"> RETIRED {stamp:%Y-%m-%d %H:%M}Z with retire_note. No longer current: {reason}\n"
            + _RETIRED_KEPT)


def _write_atomic(p: Path, text: str) -> None:
    """Write text to p whole or not at all: a tmp beside it, synced, then os.replace."""
    tmp = p.with_name(f".{p.name}.tmp")
    with open(tmp, "w") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def _fresh_record(name: str, body: str, retired_as: str, stamp: datetime):
    """The fresh file that replaces a retired todo.md or journal.md, and the receipt's words
    for it. The todo carries forward every item still open by the same reading the beat window
    uses (heartbeat._todo_items), so a retire never drops an open item and the window shows the
    same open list before and after.

    EACH ITEM KEEPS THE DATE IT WAS OPENED. Nova's review of 0557d9bcf: carrying every item
    under one header dated today "changes their age and age-based selection" -- todo_open shows
    items opened in the last 48 h and only counts older ones, so a retire would have pulled every
    stale item back into view as new. The items are written under their original dated headers
    (the parser dates an item by the block above it), undated ones first with no header, so
    todo_open reads the same (item, since) list from the fresh file as from the old one."""
    if name == "todo.md":
        from sage.gateway.heartbeat import _todo_items  # lazy: heartbeat is the larger module
        still = list(_todo_items(body).values())
        if not still:
            return (f"{stamp:%Y-%m-%d %H:%M} UTC\nstill open: none\n",
                    "A fresh todo.md is started; nothing was still open, so it starts empty.")
        out = [f"Carried forward from {retired_as} on {stamp:%Y-%m-%d %H:%M} UTC: every item "
               f"still open, each under the date it was opened.\n"]
        last = None
        for t, since in sorted(still, key=lambda x: (x[1] is not None, x[1] or stamp)):
            if since is not None and since != last:
                out.append(f"{since:%Y-%m-%d %H:%M} UTC\n")
                last = since
            out.append(f"- [ ] {t}\n")
        return ("".join(out),
                f"A fresh todo.md is started with the {len(still)} item(s) still open carried "
                f"forward, each keeping the date it was opened; everything else stays in "
                f"{retired_as}.")
    return (f"{stamp:%Y-%m-%d %H:%M} UTC\nJournal started fresh. Earlier entries are in "
            f"{retired_as}, and recall still searches them.\n",
            f"A fresh journal.md is started; recall still searches {retired_as}.")


class ReferenceF1aDispatcher:
    """A Dispatcher (see being_gate_client.Dispatcher) for the being's own safe acts."""


    # Bounds on one edit. An edit is a SMALL, LOCATED change; anything larger is a rewrite
    # and should be honest about being one.
    EDIT_MAX_CHARS = 4000
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
            if isinstance(g, (tuple, list)) and len(g) >= 2:     # (root, recursive[, modes]) since #521
                roots.append((Path(str(g[0])).resolve(), bool(g[1])))
            else:
                # A BARE ENTRY IS READ AS EXACT, NEVER GUESSED WIDER (hestia #1002: exact is the
                # default, subtree only when spelled). A current gate client always sends
                # `granted_reach`, so a bare `granted` with no reach beside it is an older
                # client or a test — and in the ambiguous case the fail-closed reading is the
                # only defensible one. (Reconciliation 2026-09-22: main's 09-05 confinement test
                # assumed bare = prefix; it now states its reach explicitly instead.)
                roots.append((Path(str(g)).resolve(), False))
        self._extra_roots = tuple(roots)
        self._extra_reach = self._extra_roots     # main's name for the same pairs (#519)
        # AND IN WHICH MODES (main, hestia #1345 part B): a grant narrowed below rwed carries them
        # as a third element; a root without one is full-mode. Keyed on (root, recursive), and two
        # grants on one key UNION their modes, as the gate does (nomad review of #533, point 1).
        self._extra_modes = {}
        for g in (getattr(verdict, "granted_reach", ()) or ()):
            if isinstance(g, (tuple, list)) and len(g) >= 2:
                k = (Path(str(g[0])).resolve(), bool(g[1]))
                got = self._extra_modes.get(k, "") + (str(g[2]) if len(g) > 2 else "rwed")
                self._extra_modes[k] = "".join(c for c in "rwed" if c in got)
        # And BY WHICH RULE (hestia #1386): "nearest" when the gate decided by the nearest
        # explicit grant (part C), so this confinement decides the same way.
        self._reach_rule = getattr(verdict, "reach_rule", "union")
        handler = getattr(self, f"_do_{intent.effector}", None)
        if handler is None:
            # a consequential network act the reference won't run — real F1a's job
            return ResultEnvelope(ok=False, pending=True,
                                  note=f"'{intent.effector}' awaits hestia F1a (reference runs only witness/memory)")
        try:
            if intent.effector in HOME_WRITE_VERBS:
                # The whole verb, read through replace, under one lock: memory_edit reads the
                # file, validates and os.replaces it, and an append or retire landing in between
                # would be lost (Nova, 99cfdb61b). Taken here and only here: flock is per open
                # file, so a second _home_lock inside a handler would wait on itself.
                with _home_lock(self.memory_root):
                    return handler(intent)
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
            # Any home's store, not only its own (legion's review of #551): a grant into another
            # being's home must not let a turn appear in that being's conversations either.
            for sub in RESERVED_SUBTREES:
                if any(r.name == sub and (r.parent == self.memory_root or _looks_like_a_home(r.parent))
                       for r in (p, *p.parents)):
                    raise ValueError(
                        f"{sub}/ is reserved: a turn enters a conversation only through `say`, "
                        "which checks who may speak, witnesses the act and numbers it. Writing "
                        "the store directly would let a turn appear that nobody said. Nothing "
                        f"was changed. If you meant to change one of your own files, "
                        f"{sub}/ is not its path: give that file's path instead (a `say` "
                        "does not change any file)")
        # (root, recursive) pairs. The home is always a subtree — it is the being's own.
        roots = [(self.memory_root, True)]
        if not writing:
            roots += list(self._reach_pairs())
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
        # WHAT GIT EXECUTES IS NOT A FILE THE BEING WRITES. `core.hooksPath=.githooks` is a
        # tracked directory shared by every worktree, and the seat runs `git commit` in this one
        # (pr_open, pr_amend). A being-written hook would run as the seat, outside the sandbox
        # that makes M1 safe. hestia_dispatch._worktree_env() switches hooks off for every
        # seat-run git; this refusal is the second layer, and the one the being can read.
        # `.git` is refused for the same reason: it is the repository's machinery, not a file.
        _wt = getattr(self, "worktree", None)
        if writing and _wt:
            _wr = Path(_wt).resolve()
            if p == _wr or _wr in p.parents:
                _first = p.relative_to(_wr).parts[:1]
                # casefold: on a case-insensitive volume (APFS by default, NTFS) `.GITHOOKS` IS
                # `.githooks` (legion, reviewing SAGE #210's patch parser)
                if _first and _first[0].casefold() in (".githooks", ".git"):
                    raise ValueError(
                        f"{_first[0]}/ in your worktree is not writable: it holds what git "
                        f"EXECUTES (hooks) or git's own machinery, and the seat runs git in this "
                        f"tree, so a file there would run as the seat outside your sandbox. This is "
                        f"not about you; no being may write there. Everything else in the worktree "
                        f"is yours to change.")
        if (writing and p.parent.name == "notes" and p.name in SEAT_OWNED_NOTES
                and (p.parent.parent == self.memory_root or _looks_like_a_home(p.parent.parent))):
            raise ValueError(
                f"notes/{p.name} is what was said TO you, and it stays as it was said. Your "
                "reply belongs in your journal, notes/plan.md, or an appeal — all of which "
                "are read")
        # SAGE #545/#546 (main): governance records, self.json's and tune's families are not
        # written by any generic verb, in ANY home: a grant that ever reached another being's home
        # must not make that home's records writable either (_looks_like_a_home).
        _home = writing and (p.parent == self.memory_root or _looks_like_a_home(p.parent))
        # SAGE #552/#565 (main): the record names themselves are refused in EVERY directory, so a
        # record cannot be planted where no home is yet; the broad prefix stays tied to homes.
        if ((writing and _is_governance_record_name(p.name))
                or _home and (p.name in GOVERNANCE_OWNED or p.name.startswith(GOVERNANCE_OWNED_PREFIX))):
            raise ValueError(
                f"{p.name} is a governance record: it says who you are to the society (your "
                "id, your machine, which seat hears your escalations, your trust ceiling), so "
                "no being verb writes it. Nothing was changed. Who you are in your own words "
                "is yours to write with identity_edit")
        if _home:
            from sage.gateway.being_params import TUNE_WRITES
            if _named(p, TUNE_WRITES):
                raise ValueError(
                    f"{p.name} is changed only with tune, which checks the value against its bounds "
                    "and keeps every change with your reason in tune_log.jsonl. A direct write would "
                    "leave no record of it. Nothing was changed")
        if _home:
            from sage.gateway.being_self import SELF_WRITES
            if _named(p, SELF_WRITES):
                raise ValueError(
                    f"{p.name} is changed only with identity_edit, which keeps every earlier "
                    "version and your reason in self_log.jsonl. A direct write would leave no "
                    "record of what it replaced. Nothing was changed")
        # SAGE #576 (main): the being's skills are changed only with `skill`. In the carrier's flat form
        # `writing` is stated: the skills-dir half does not go through _home (which carries it), and
        # without it a READ of the being's own skill would be refused.
        if writing:
            from sage.gateway.being_skills import OWN_DIR as _SKILLS_DIR, SKILLS_LOG
            if (_home and _named(p, (SKILLS_LOG,))) or (
                    p.parent.parent.name.casefold() == _SKILLS_DIR.casefold() and (
                        p.parent.parent.parent == self.memory_root or _looks_like_a_home(p.parent.parent.parent))):
                raise ValueError(
                    f"{p.name} is changed only with skill, which keeps every earlier version and your "
                    "reason in skills_log.jsonl. A direct write would leave no record of what it "
                    "replaced. Nothing was changed")
        if _home:
            from sage.gateway.being_settled import SETTLED_WRITES
            if _named(p, SETTLED_WRITES):
                raise ValueError(
                    f"{p.name} is changed only with settle, which keeps every earlier answer and "
                    "your reason in settled_log.jsonl. A direct write would leave no record of what "
                    "it replaced. Nothing was changed")
        if _home and p.name in SEAT_OWNED:
            raise ValueError(
                f"{p.name} is yours to read and not to edit: it is what you were entrusted "
                "with, and it has to stay separable from what you decide. Your own reading "
                "of it belongs in notes/plan.md, which is entirely yours. Disagree with it "
                "there, in your journal, or in an appeal — that record is wanted")
        # Nova, 99cfdb61b: the lock lives in the being's home, and a memory_edit of it
        # would os.replace its inode, so two writers would hold flocks on different files
        # and nothing would be serialized. No write verb may touch it.
        if _home and p.name == HOME_LOCK:
            raise ValueError(
                f"{HOME_LOCK} is not a note: it is the lock that keeps two writes to your home "
                "from landing on top of each other, and it holds no text. Nothing was changed")
        def _covered(path: Path, root: Path, recursive: bool) -> bool:
            # exact: the root itself; recursive: the root and everything under it.
            # Separator-aware by construction (Path.parents): /a never fronts for /ab.
            return path == root or (recursive and root in path.parents)

        # READS FOLLOW THE GATE'S MODES (main #533, hestia #1345 part B / #1386). _reach_pairs()
        # already holds only grants with r; under the "nearest" rule the nearest explicit grant
        # covering the path decides, so a broader grant above an r-less one does not apply.
        # Writes keep the carrier's rule above: home and worktree only, whatever a grant says.
        # AND A WRITE OUTSIDE THE HOME NEEDS w IN THE GRANTS THAT COVER IT (main #533 on the
        # carrier). The carrier writes its worktree whatever a grant there says; with the gate's
        # mode half not yet active (hestia #1383), this layer is the one that enforces modes, so
        # an r-only grant over the worktree must refuse the write. A path no grant covers keeps
        # the carrier's rule below (home and worktree only).
        if writing and not (p == self.memory_root or self.memory_root in p.parents):
            held = self._all_pairs()
            modes = getattr(self, "_extra_modes", None) or {}
            if getattr(self, "_reach_rule", "union") == "nearest":
                near = self._nearest_modes(p, held, modes)
                if near is not None and "w" not in near:
                    raise ValueError(
                        f"'{p}' is under a grant of yours narrowed to {near}, the nearest grant "
                        f"covering it, and writing needs w. A broader grant above it does not apply "
                        f"here: the nearest explicit grant decides (hestia #1386). Nothing was "
                        f"changed. memory_read hestia://reach/{p} shows what you hold there")
            else:
                cover = [modes.get(k, "rwed") for k in held if _covered(p, k[0], k[1])]
                if cover and not any("w" in m for m in cover):
                    raise ValueError(
                        f"'{p}' is under a grant of yours narrowed to {cover[0]}, and writing "
                        f"needs w. Nothing was changed. memory_read hestia://reach/{p} shows what "
                        f"you hold there")
        if not writing:
            held = self._all_pairs()
            modes = getattr(self, "_extra_modes", None) or {}
            if (getattr(self, "_reach_rule", "union") == "nearest"
                    and not (p == self.memory_root or self.memory_root in p.parents)):
                near = self._nearest_modes(p, held, modes)
                if near is not None and "r" not in near:
                    raise ValueError(
                        f"'{p}' is under a grant of yours narrowed to {near}, the nearest grant "
                        f"covering it, and reading needs r. A broader grant above it does not apply "
                        f"here: the nearest explicit grant decides (hestia #1386). Nothing was read. "
                        f"memory_read hestia://reach/{p} shows what you hold there")
            if not any(_covered(p, r, rec) for r, rec in roots):
                narrowed = [modes[k] for k in held if k in modes and "r" not in modes[k]
                            and _covered(p, k[0], k[1])]
                if narrowed:
                    raise ValueError(
                        f"'{p}' is under a grant of yours narrowed to {narrowed[0]}, and reading "
                        f"needs r. Nothing was read. memory_read hestia://reach/{p} shows what you "
                        f"hold there")
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
            if writing and any(_covered(p, r, rec) for r, rec in self._reach_pairs()):
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
            # A NEAR MISS OF ITS OWN HOUSE IS NOT A TRESPASS (main, dp directive 2026-09-25): if
            # some TAIL of the unreachable path names a file that ALREADY EXISTS in the being's
            # home, that is the file it meant. Reach does not widen by one byte; every guard
            # above re-runs on the rerouted path. '/etc/passwd' is still '/etc/passwd'.
            landed = self._tail_in_home(p)
            if landed is not None:
                self._rerouted_from = str(p)      # the receipt says so; nothing is hidden
                return self._safe_path(str(landed.relative_to(self.memory_root)), writing=writing)
            # An exact grant is named as one, so "you can read and write under X" does not read
            # as reach into X's subtree when X is a directory granted exactly.
            shown = tuple(r if recursive else f"{r} (exactly this path, nothing under it)"
                          for r, recursive in roots)     # carrier: `roots` is main's `reach` here
            raise ValueError(self._out_of_reach(p, shown, writing))
        return p

    def _reach_pairs(self) -> tuple:
        """((root, recursive), ...) beyond the home for this verdict. `_extra_reach` when the
        verdict carried reach; otherwise the bare roots, read by prefix as _safe_path reads them.
        Only grants that include r (main, #1345 part B): every caller names a place to READ."""
        modes = getattr(self, "_extra_modes", None) or {}
        return tuple(k for k in self._all_pairs() if "r" in modes.get(k, "rwed"))

    def _all_pairs(self) -> tuple:
        """Every held (root, recursive), whatever its modes."""
        # Carrier: `_extra_roots` holds PAIRS (set in __call__); main and main's tests set bare
        # Paths there beside pairs in `_extra_reach`. Accept both, and always yield resolved pairs.
        items = getattr(self, "_extra_reach", None) or tuple(
            g if isinstance(g, (tuple, list)) else (g, True)
            for g in (getattr(self, "_extra_roots", ()) or ()))
        return tuple((Path(g[0]).resolve(), bool(g[1])) for g in items)

    @staticmethod
    def _nearest_modes(p: Path, held, modes) -> Optional[str]:
        """The modes of the nearest held grant covering `p` (grants on one node union), or None.
        The gate's rule (hestia #1386), over this verdict's (root, recursive) nodes."""
        best, got = -1, set()
        for r, rec in held:
            if p == r or (rec and r in p.parents):
                depth = len(r.parts)
                m = modes.get((r, rec), "rwed")
                if depth > best:
                    best, got = depth, set(m)
                elif depth == best:
                    got |= set(m)
        return None if best < 0 else "".join(c for c in "rwed" if c in got)

    def _within_reach(self, p: Path) -> bool:
        p = p.resolve()
        if getattr(self, "_reach_rule", "union") == "nearest" and not (
                p == self.memory_root or self.memory_root in p.parents):
            held = tuple((Path(r).resolve(), rec) for r, rec in (getattr(self, "_extra_reach", None) or (
                (r, True) for r in (getattr(self, "_extra_roots", ()) or ()))))
            near = self._nearest_modes(p, held, getattr(self, "_extra_modes", None) or {})
            return near is not None and "r" in near
        pairs = ((self.memory_root, True),) + tuple((Path(r).resolve(), rec) for r, rec in self._reach_pairs())
        return any(p == r or (rec and r in p.parents) for r, rec in pairs)

    def _tail_in_home(self, p: Path) -> Optional[Path]:
        """The longest tail of `p` that names an existing file in this being's home, or None.

        Longest-first so '/x/y/notes/plan.md' prefers notes/plan.md over a stray plan.md at the
        top level. Existence is required: this resolves a fumbled path to a file the being
        already has, and never invents a new one from an arbitrary absolute path.
        """
        parts = [x for x in p.parts if x not in ("/", "")]
        for i in range(len(parts)):
            tail = Path(*parts[i:])
            if str(tail).startswith(("..", "/")):
                continue
            cand = (self.memory_root / tail)
            try:
                cand_r = cand.resolve()
            except Exception:
                continue
            if cand_r != self.memory_root and self.memory_root not in cand_r.parents:
                continue
            if cand_r.is_file():
                return cand_r
        return None

    def _relative_above_home(self, shown: str) -> Optional[str]:
        """The absolute path of an existing file that the relative `shown` names under the
        nearest ancestor of this being's home, or None. A being's relative paths are usually
        written against its workspace (`governance/...`, `SAGE/...`), not against its home.
        Nothing is hard-coded: the ancestors of memory_root are walked nearest first. An
        absolute or `..` path is not considered."""
        rel = Path(shown)
        if rel.is_absolute() or ".." in rel.parts or not rel.parts:
            return None
        for anc in self.memory_root.parents:
            cand = anc / rel
            try:
                if cand.is_file():
                    return str(cand)
            except OSError:
                continue
        return None

    def _same_name_elsewhere(self, p: Path) -> list:
        """Home-relative paths of EVERY file named like `p` in the home root or one directory
        below it, in sorted order. Bounded to that depth on purpose: every measured near-miss
        was a notes/ vs root confusion, and a deep walk of a home with backups/ in it costs a
        beat. All matches are returned (one level is small) so the caller can say how many
        there are rather than silently keeping the first few."""
        root = self.memory_root
        try:
            dirs = [root] + sorted(d for d in root.iterdir() if d.is_dir() and not d.name.startswith("."))
        except OSError:
            return []
        out = []
        for d in dirs:
            c = d / p.name
            try:
                if c != p and c.is_file():
                    out.append(str(c.relative_to(root)))
            except OSError:
                continue
        return out

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
        reach = ", ".join((f"{r[0]}{'/**' if r[1] else ''}" if isinstance(r, tuple) else str(r))
                          for r in roots)
        head = f"'{p}' is outside your reach. You can read and write under: {reach}."
        if writing:
            return head + (" memory_write creates a file inside your home; name a path there "
                           "instead, or request_scope and say what you would write.")
        copies = same_path_in_reach(p, self._reach_pairs())
        if copies:
            # First, before the boundary: the alternative is what the being can act on now.
            return copy_alternative(str(p), copies) + " " + head
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
            near = self._same_name_elsewhere(p)
            if near:
                # A MISS ONE DIRECTORY AWAY IS NOT AN ABSENCE. Measured 2026-09-21 on cbp-being:
                # 28 of its 76 "no such path" reads named a file that existed under the same
                # name one directory over (it writes into notes/ and reads from the root, or
                # the reverse). Two beats that day read `mechanism-training-script.py`, got
                # "does not exist" for a script sitting in notes/, and wrote "verified" notes
                # about it anyway. The answer names where the file is, so the next step is a
                # read rather than an invention.
                #
                # SEVERAL MATCHES ARE LISTED NEUTRALLY (GPT review on #140). Nothing ranks
                # notes/x.py over scratch/x.py, and this repair exists to stop invention after a
                # miss, so it must not add a guess of its own: every match is named in the same
                # way, none is called the one it meant, and the choice stays with the being.
                nothing = ("Nothing was read this time, so nothing about its contents is "
                           "known yet.")
                if len(near) == 1:
                    msg = (f"[no such path: '{shown}' does not exist, but a file with that name "
                           f"DOES exist at '{near[0]}'. To read it: "
                           f"memory_read {{\"path\": \"{near[0]}\"}}. {nothing}]")
                else:
                    shown_near = near[:_SAME_NAME_SHOWN]
                    where = ", ".join(f"'{n}'" for n in shown_near)
                    more = (f" and {len(near) - len(shown_near)} more"
                            if len(near) > len(shown_near) else "")
                    msg = (f"[no such path: '{shown}' does not exist, but {len(near)} files with "
                           f"that name exist: {where}{more}. Nothing tells which of them you "
                           f"mean; read the one your task is about with memory_read and its "
                           f"path. Nothing was read this time, so nothing about any of their "
                           f"contents is known yet.]")
                return ResultEnvelope(
                    ok=True, result=msg,
                    witness_id=self._witness(
                        f"memory_read {p.name} (does not exist; same name at {', '.join(near)})"))
            above = self._relative_above_home(shown)
            if above is not None and not self._within_reach(Path(above)):
                # Pointing only at a file the being cannot read sent cbp-being from
                # `hestia/plugins/...` to the editable tree and its refusal (2026-10-23 00:23Z)
                # while a copy sat under its governance grant. Name both: the original as what
                # it is (outside reach), and the copy as an alternative, not as the same file.
                copies = same_path_in_reach(above, self._reach_pairs())
                if copies:
                    return ResultEnvelope(
                        ok=True,
                        result=(f"[no such path in your home: a path without a leading / is read "
                                f"inside your home, and '{shown}' is not there. A file exists at "
                                f"'{above}', outside your reach. " + copy_alternative(above, copies)
                                + " Nothing was read this time.]"),
                        witness_id=self._witness(
                            f"memory_read {p.name} (not in home; exists at {above}; copy in reach)"))
                if self._reach_pairs():
                    # AND WITH NO COPY, IT IS STILL NOT A READ TO OFFER (SAGE #530). Falling through
                    # to "To read it:" hands the member a path its grants do not cover, as one it
                    # can read. Say what is true and suggest no door; asking stays its decision.
                    # Only when the verdict said what the member holds: a verdict with no grants
                    # on it (hand-made, or a failed policy fetch) cannot tell, and keeps the old line.
                    return ResultEnvelope(
                        ok=True,
                        result=(f"[no such path in your home: a path without a leading / is read "
                                f"inside your home, and '{shown}' is not there. A file exists at "
                                f"'{above}', but it is outside what you hold, so a read of it "
                                f"would be refused, and nothing you hold has a copy of it. The "
                                f"paths you hold are in your beat under 'granted paths'. Nothing "
                                f"was read this time.]"),
                        witness_id=self._witness(
                            f"memory_read {p.name} (not in home; exists only outside reach at {above})"))
            if above is not None:
                # A RELATIVE PATH IS READ INSIDE THE HOME, AND THE BEING DID NOT KNOW THAT.
                # Measured 2026-10-20/21 on cbp-being: it read the gate source by its absolute
                # path (lines 128-322, allowed), then in the next beats asked for the same file as
                # `governance/hestia/plugins/_shared/hestia_single_gate.py`, got "does not
                # exist", stored "hestia_single_gate.py does not exist" as a fact, and asked dp
                # four times over 90 minutes where the file lives. The file was at that path
                # under its workspace the whole time. Existence only: this names the absolute
                # path and reads nothing; the read it suggests goes through the gate like any
                # other.
                return ResultEnvelope(
                    ok=True,
                    result=(f"[no such path in your home: a path without a leading / is read "
                            f"inside your home, and '{shown}' is not there. A file DOES exist at "
                            f"'{above}'. To read it: memory_read {{\"path\": \"{above}\"}}. "
                            f"Nothing was read this time, so nothing about its contents is known "
                            f"yet.]"),
                    witness_id=self._witness(
                        f"memory_read {p.name} (not in home; exists at {above})"))
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
            wt_hint = ""
            if self.worktree and not str(rel).startswith("/") and (Path(self.worktree) / rel).exists():
                wt_hint = (f"; note: {rel} does exist in your worktree ({self.worktree}) — if you meant "
                           f"the repository file, read it there (the law will judge the path)")
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
                        f"else{found}{siblings}{wt_hint}. memory_write creates a file inside your home.]"),
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
            # A find on a directory used to be dropped without a word: the listing came back as
            # if it were the answer. cbp-being sent memory_read {path: "notes", find: ...} three
            # times in one beat (2026-10-21 07:51Z) and once on the governance snapshot root,
            # got the same first 50 names each time, and then read the first-listed (oldest)
            # note instead of any file holding the text. Say that find did not run and why.
            find = str(intent.args.get("find") or "")
            # Outside the home, `search` reads a granted directory by absolute path (SAGE #505),
            # so name it with the path filled in; inside the home, one file with find is the way.
            in_home = p == self.memory_root or self.memory_root in p.parents
            how = ("To search, memory_read one file's path with find." if in_home else
                   f"To find which file under it holds the text: search {{\"pattern\": "
                   f"\"{find.strip()[:80]}\", \"path\": \"{p}\"}}.")
            unrun = (f"\n[find was NOT run: find looks inside ONE file, and '{shown}' is a "
                     f"directory. Nothing was searched, so nothing is known yet about which file "
                     f"holds '{find.strip()[:80]}'. {how}]") if find.strip() else ""
            listing = (f"[directory: '{shown}' holds {len(rows)} entr{'y' if len(rows) == 1 else 'ies'}]\n"
                       + ("\n".join(rows) if rows else "(empty directory)") + unrun)
            return ResultEnvelope(ok=True, result=listing,
                                  witness_id=self._witness(f"memory_read {p.name}/ (listing)"))
        # A BINARY FILE IS NOT READ AS TEXT. Measured on sprout-being, 2026-10-12..26: 21 memory_reads
        # of its own camera frames (.jpg) returned the JPEG's bytes decoded as text ("\ufffd\ufffd...JFIF..."),
        # 10 of them from 10-25 19:20Z on. In the same window its model began emitting byte soup and JPEG
        # headers as its own thinking: 6000-token empty turns, 1-2 a day the week before, 6 on 10-25 and
        # 12 by 08:00Z on 10-26, with beats killed mid-turn. The bytes carry nothing a reader can use; the
        # file is said instead: what kind, how big, when, and how images do reach the being.
        kind = _binary_kind(p)
        if kind:
            return ResultEnvelope(ok=True, result=_binary_said(shown, p, kind),
                                  witness_id=self._witness(f"memory_read {p.name} (binary: {kind})"))
        whole = p.read_text(errors="replace")
        if not whole:
            return ResultEnvelope(ok=True, result=f"[empty file: '{shown}' exists and has no content]",
                                  witness_id=self._witness(f"memory_read {p.name}"))
        find = str(intent.args.get("find") or "")
        if find.strip():
            return self._memory_read_find(p, shown, whole, find, intent.args)
        find_note = ("[find was blank (empty or only whitespace), so this is an ordinary read "
                     "using start_line and end_line, with the usual size limit.]\n"
                     if intent.args.get("find") is not None else "")
        # RANGE READS. Asked for by the being three beats running (2026-09-08): with the
        # cap at 12k chars it got heartbeat.py's opening and never its body, and its
        # paging workaround (git show with a pathspec) returns a diff lens, not a file. The
        # honest ask was "first N lines / from line K", and it named the work it unblocks.
        # Line-based on purpose: its findings cite file+line, so the read and the citation
        # share a coordinate system. A ranged read never carries the whole-file truncation
        # marker — it says what range it is, which is the truthful thing.
        # TWO COORDINATE SYSTEMS, ONE READ. This range path takes from_line + lines; the window below takes
        # start_line + end_line (main's, #160). A read that mixed them had its other name silently dropped. Measured on
        # legion-being 2026-10-30: 1,297 reads gave from_line + end_line, the end_line was ignored, the range ran to
        # the end of the file, and 722 of them overflowed the window; 127 gave start_line + lines and started at line
        # 1. The being wrote a skill (narrow-source-extraction) to work around it. So each name now does what it says
        # in either path: end_line ends a from_line range (inclusive, as memory_edit counts), start_line starts a
        # lines range; lines still wins over end_line when both are given.
        from_line = intent.args.get("from_line")
        n_lines = intent.args.get("lines")
        if from_line is not None or n_lines is not None:
            lines = whole.splitlines(keepends=True)
            end_arg = intent.args.get("end_line")
            try:
                first = from_line if from_line is not None else intent.args.get("start_line")
                start = max(1, int(str(first).strip() or 1)) if first is not None else 1
                if n_lines is not None:
                    count = int(n_lines)
                elif end_arg is not None and str(end_arg).strip():
                    count = max(0, int(str(end_arg).strip()) - start + 1)
                else:
                    count = len(lines)
            except (TypeError, ValueError):
                return ResultEnvelope(ok=False, error="memory_read 'from_line', 'start_line', 'lines' and 'end_line' "
                                                      "must be whole numbers")
            chunk = lines[start - 1:start - 1 + max(0, count)]
            body = "".join(chunk)[: self.max_read_chars]
            end = start + len(chunk) - 1
            head = find_note + f"[lines {start}-{end} of {len(lines)} in {p.name}]\n"
            if len("".join(chunk)) > self.max_read_chars:
                head += (f"[… this range alone exceeds {self.max_read_chars} characters; "
                         f"ask for fewer lines …]\n")
            return ResultEnvelope(ok=True, result=head + body,
                                  witness_id=self._witness(f"memory_read {p.name} L{start}-{end}"))
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
        # A ONE-LINE LOOK COST THE REST OF THE FILE. Measured 2026-10-09 20:38Z on cbp-being
        # (beat heartbeat-65351614df15): the seat named four lines (79, 80, 187, 226) with
        # their exact old=/new=. The being read each with start_line alone and got lines
        # 79-283, 80-283, 187-283 and 226-283 of a 9,121-char file -- about 200 lines, four
        # times, in a 16,384-token window -- and the seat's message holding the edits was
        # evicted; the beat ended with three request_run re-asks and no edit. The elision
        # marker in being_tool_loop.py had been saying "memory_read a narrow range" since
        # 2026-09-13, and memory_edit has taken end_line since #160, but memory_read had no
        # way to say where to stop. `end_line` (inclusive, as memory_edit counts it) is that
        # way. The char cap still applies inside the range; with no end_line nothing changes.
        try:
            stop = int(str(intent.args.get("end_line", "")).strip() or 0)
        except ValueError:
            stop = 0
        stop = max(stop, start) if stop else 0
        if start > len(lines):
            return ResultEnvelope(ok=True, result=(
                find_note + f"[past the end: '{shown}' has {len(lines)} lines, so start_line={start} shows "
                f"nothing. Read from start_line=1.]"),
                witness_id=self._witness(f"memory_read {p.name} (past end)"))
        end, size = start - 1, 0
        limit = min(len(lines), stop) if stop else len(lines)
        while end < limit and size + len(lines[end]) <= self.max_read_chars:
            size += len(lines[end]); end += 1
        if end == start - 1:          # one line longer than the whole window: show its head
            content, end = lines[end][: self.max_read_chars], end + 1
        else:
            content = "".join(lines[start - 1:end])
        # A READ OF CODE IS WHERE THE VERDICT ON IT IS FORMED. #162 put the parse check on
        # write and edit receipts only. Measured 2026-09-23 on cbp-being (beat
        # heartbeat-f4be191ca52d): it read lines 1718-1937 of its script, which showed line
        # 1721 at column 0 and the lines under it indented four spaces, and concluded "the
        # file is syntactically valid" -- Python stopped at line 1722 with IndentationError.
        # Its journal, todo and memory recorded "fix complete and verified", and it told the
        # seat it had already run the script. Nothing it was shown contradicted the reading.
        # Again 2026-09-29 11:41Z: it read all 443 lines of a scratch .py in three windows, said
        # "appears syntactically correct", and asked the seat to run it; the run stopped at line
        # 135, IndentationError, inside the first window it had been shown (seat thread 4384).
        dated = dated_lines_note(content)
        status = _python_status(p).strip()
        parse = f"\n[{status}]" if status else ""
        if start == 1 and end >= len(lines) and len(content) == len(whole):
            # whole file, nothing withheld. (`end >= len(lines)` alone is not enough: a ONE-line
            # file longer than the window takes the head-only branch above and would return
            # its first max_read_chars with no marker — a silent cut, found by the branch's
            # 74-char test in the 2026-09-22 reconciliation.)
            # A whole-file read has no end marker, so a bare bracket line after the last line
            # would read as the file's last line and could be copied into an edit anchor.
            # Say where the file ends before saying what Python makes of it.
            whole_note = f"\n[end of file: line {len(lines)} is the last line. {status}]" if status else ""
            return ResultEnvelope(ok=True, result=find_note + dated + content + whole_note,
                                  witness_id=self._witness(f"memory_read {p.name}"))
        if start == 1 and end >= len(lines):
            return ResultEnvelope(ok=True, result=find_note + dated + content + (
                f"\n[… truncated: this shows the first {len(content)} of {len(whole)} characters of a "
                f"single line. What you did NOT see is the rest of that line, so absence here is not "
                f"evidence of absence in the file. Lines were NOT shown beyond this one because there "
                f"are none.]") + parse, witness_id=self._witness(f"memory_read {p.name} (head)"))
        head = find_note + dated + (f"[lines {start}-{end} of {len(lines)} in '{shown}']\n" if start > 1 else "")
        if stop and end == stop and end < len(lines):
            # Cut where the being asked, not where the window ran out: say so in those words,
            # so a short result is not read as the file running out of lines.
            tail = (f"\n[end of the range you asked for: lines {start}-{end} of {len(lines)}. "
                    f"Lines {end + 1}-{len(lines)} were NOT shown. To read on, call memory_read "
                    f"with path '{shown}' and start_line={end + 1}.]")
        else:
            tail = (f"\n[… truncated: this shows lines {start}-{end} of {len(lines)} "
                    f"({len(whole)} characters in all). Lines {end + 1}-{len(lines)} were NOT shown, so "
                    f"absence here is not evidence of absence in the file. To read on, call "
                    f"memory_read with path '{shown}' and start_line={end + 1}. …]"
                    if end < len(lines) else f"\n[end of file: line {len(lines)} is the last line.]")
        return ResultEnvelope(ok=True, result=head + content + tail + parse,
                              witness_id=self._witness(f"memory_read {p.name} (lines {start}-{end})"))

    def _memory_read_find(self, p: Path, shown: str, whole: str, find: str,
                          args: dict) -> ResultEnvelope:
        """memory_read with `find`: the lines of ONE file that contain a literal string.

        FINDING IS NOT READING (#351). Without a worktree, `search` is refused, and memory_read
        only showed a file from a start_line on, so a being that wanted to locate one line
        (`head = nn.Linear` in scratch/train-autoencoder-latent5.py) had no tool that could. It
        was refused at search 120 times (76 on 2026-10-07 alone) and wrote git-worktree setup
        scripts to build the missing thing. This answers the question it was asking, in the
        file it named: literal and case-sensitive (not a regex, so `nn.Linear(` means what it
        says), every line number the text is on, nothing else read.

        An empty answer says why it is empty: zero matches is a true answer about THIS file,
        and says that it covers nothing else. A find whose leading or trailing spaces are what
        kept it from matching says so (a being cannot see the whitespace it sends).
        A query with line breaks explicitly searches only its first non-blank line;
        the receipt makes no claim about the full multi-line text."""
        query_lines = find.splitlines()
        if query_lines != [find]:
            first = next(line for line in query_lines if line.strip())
            result = self._memory_read_find(p, shown, whole, first, args)
            result.result = (
                "[find matches within one line. Your query contained line breaks, so the "
                f"results below search only its first non-blank line: {first!r}. "
                "They do not establish whether the full multi-line text is present. "
                "Read the matching range to check the remaining lines.]\n" + result.result)
            return result
        lines = whole.splitlines()
        hits = [(i, ln) for i, ln in enumerate(lines, 1) if find in ln]
        loose = ""
        if not hits and find.strip() != find:
            loose = find.strip()
            hits = [(i, ln) for i, ln in enumerate(lines, 1) if loose in ln]
        ignored = "".join(
            f" {key}={args[key]} was ignored: find looks at every line of the file."
            for key in ("start_line", "end_line") if args.get(key) is not None
        )
        if not hits:
            return ResultEnvelope(ok=True, result=(
                f"[found none: no line of '{shown}' contains {find!r} (literal text, "
                f"case-sensitive; all {len(lines)} lines were looked at). This is a true answer "
                f"about this one file only: it says nothing about any other file.{ignored}]"),
                witness_id=self._witness(f"memory_read {p.name} (find: 0 matches)"))
        shown_hits = hits[:_FIND_SHOWN]
        cut = False
        rows = []
        for i, ln in shown_hits:
            if len(ln) > _FIND_LINE_CHARS:
                ln, cut = ln[:_FIND_LINE_CHARS] + "…", True
            rows.append(f"line {i}: {ln}")
        n = len(hits)
        what = repr(loose) if loose else repr(find)
        head = (f"[found {n} line{'' if n == 1 else 's'} of {len(lines)} in '{shown}' "
                f"containing {what} (literal text, case-sensitive)]")
        if loose:
            head += (f"\n[no line contains {find!r} exactly as sent, with its leading/trailing "
                     f"spaces; these contain it with those spaces removed]")
        notes = []
        if n > len(shown_hits):
            notes.append(f"…and {n - len(shown_hits)} more matching lines not listed (the first "
                         f"{len(shown_hits)} are shown); a longer find text narrows it.")
        if cut:
            notes.append(f"a line ending in … was cut at {_FIND_LINE_CHARS} characters.")
        notes.append("line labels and truncation notes are not file text or edit anchors.")
        notes.append(f"to read a range, memory_read path '{shown}' with start_line and end_line."
                     + ignored)
        return ResultEnvelope(
            ok=True, result=head + "\n" + "\n".join(rows) + "\n[" + " ".join(notes) + "]",
            witness_id=self._witness(f"memory_read {p.name} (find: {n} matches)"))

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
                # A COUNT IS A RANGE TOO. Measured 2026-09-24 05:57Z: cbp-being sent
                # `start_line: 180, delete_lines: 5, new: ""` to cut five lines. No key read
                # the 5, end_line defaulted to start_line, and ONE line went. The receipt said
                # "replaced lines 180-180" honestly, and the being journaled "removed lines
                # 180-184 (5 lines)". An explicit argument that is dropped deletes the wrong
                # amount. This is a correction of an ignored explicit argument (see
                # RESEARCH_GENERALIZATION_RULE.md), not a new policy: a call that sends
                # delete_lines now removes the lines it names, where before it removed one.
                if "delete_lines" in a:
                    n = int(str(a["delete_lines"]).strip())
                    if n < 1:
                        raise ValueError
                    if "end_line" in a and s1 != s0 + n - 1:
                        return ResultEnvelope(ok=False, error=(
                            f"end_line {s1} and delete_lines {n} name different ranges "
                            f"({s0}-{s1} vs {s0}-{s0 + n - 1}), so nothing was changed. "
                            f"Send one of them."))
                    s1 = s0 + n - 1
            except ValueError:
                return ResultEnvelope(ok=False, error=(
                    "start_line and end_line must be line numbers, like start_line 1610 and "
                    "end_line 1616 (or a count of lines from start_line, like delete_lines 7). "
                    "Nothing was changed."))
            rng = (s0, s1)
        if not path or (not old and rng is None):
            got = ", ".join(sorted(a)) or "nothing"
            # PATH AND NEW, NOTHING TO REPLACE: AN APPEND (measured on mcnugget-being, 150 beats to 2026-10-28:
            # every one of its path+new-only calls was a journal line, a todo item or a log entry to ADD). This
            # verb only replaces; the one that adds is memory_write, and the refusal now names it.
            add = (f" If you meant to ADD this text to the end of '{path}', that is memory_write with path "
                   f"'{path}' and content set to your new text: it appends and never replaces."
                   if path and new_key is not None and not old and rng is None else "")
            return ResultEnvelope(ok=False, error=(
                f"memory_edit needs 'path', and either 'old' (the exact text to replace, "
                f"unique in the file) or 'start_line' and 'end_line' (the lines to replace), "
                f"and 'new' (what replaces it; empty string deletes it). You sent: {got}.{add}"))
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
            # A SUBSTRING OLD INSIDE THE RANGE (SAGE #417). The no-range refusal tells the being to
            # keep old "as a check" and add the range; then this branch compared old with the WHOLE
            # range and said the lines "are not the text you gave" when the text was there twice.
            # Measured on cbp-being 2026-10-10 02:25/02:27Z: line 5 held 'w_true.reshape(1, -1)'
            # twice; both remedies failed and the journal recorded a mismatch that was not one.
            # The range locates the line, old locates the text within it: once inside, replace that
            # occurrence; more than once, say so and ask for the whole line.
            # Only a token WITHIN a line: an old holding a newline claims whole lines, and that claim
            # stays an exact check, or a range on the wrong line would edit wherever the text also
            # occurs (the grounding probe's relative-numbering control, #450).
            inner = removed.count(old) if old and old.strip() and "\n" not in old else 0
            # Only a PART of the range: old that is the whole range bar its indentation means the
            # whole line, and keeps the indentation-miss refusal below (replacing inside it would
            # double an indent that new carries).
            whole = removed.strip() == old.strip()
            if old and removed.rstrip("\n") != old.rstrip("\n") and inner == 1 and not whole:
                rest = removed.replace(old, "", 1).strip()
                # ...or either SIDE of the line around old (mcnugget's HOLD on #569): a token in the
                # middle leaves `rest` with a hole (`x = (a)`) that a whole-line new never contains,
                # so `compute` -> `    x = compute2(a)` spliced to `    x =     x = compute2(a)(a)`, ok.
                before, _, after = removed.partition(old)
                sides = [x.strip() for x in (before, after) if len(x.strip()) >= 3]
                if (len(rest) >= 3 and rest in new) or any(x in new for x in sides):
                    # new carries the rest of the line too: it was meant as the whole line (#393's
                    # doubling, here), so replacing old inside the line would hold that rest twice
                    return ResultEnvelope(ok=False, error=(
                        f"your old is part of lines {s0}-{s1} of '{path}', and your new already holds "
                        f"the rest of those lines ({rest[:80]!r}), so replacing old inside them would "
                        f"leave that text there twice. Nothing was changed. To replace the whole "
                        f"line, send old as all of it (copied from the text shown), with the change "
                        f"made in new. Those lines are now:\n{removed[:600]}"))
                new_text = ("".join(lines[:s0 - 1]) + removed.replace(old, new, 1)
                            + "".join(lines[s1:]))
                what = (f"replaced 1 occurrence inside lines {s0}-{s1} (your old was part of the "
                        f"range, and appears there once)")
                return self._commit_edit(p, path, text, new_text, what, "")
            if old and inner > 1:
                where = f"line {s0}" if s0 == s1 else f"lines {s0}-{s1}"
                return ResultEnvelope(ok=False, error=(
                    f"your old appears {inner} times inside {where} of '{path}', so the range does "
                    f"not say which one you mean, and nothing was changed. Your text IS there; it "
                    f"is not a mismatch. Send old as the whole of {where} (copied from the text "
                    f"shown), with the change made in new. Those lines are now:\n{removed[:600]}"))
            if old and removed.rstrip("\n") != old.rstrip("\n"):
                shown = removed if len(removed) <= 600 else removed[:600] + "..."
                return ResultEnvelope(ok=False, error=(
                    f"lines {s0}-{s1} of '{path}' are not the text you gave as old, so nothing "
                    f"was changed. Those lines are now:\n{shown}"
                    + _indent_only_miss(removed, old, new, s0)
                    + _old_is_elsewhere(text, old, s0)))
            repl = new
            if repl and not repl.endswith("\n") and removed.endswith("\n"):
                repl += "\n"
            new_text = "".join(lines[:s0 - 1]) + repl + "".join(lines[s1:])
            what = f"replaced lines {s0}-{s1} ({s1 - s0 + 1} lines)" + _indent_changed(removed, new, s0)
            gone = f" The lines removed were:\n{_head_and_tail(removed)}" + _defs_removed(removed)
            if str(p).endswith(".py") and not _parses(new_text):
                gone = _spaces_verdict(lines, s0, s1, removed, new) + gone
            return self._commit_edit(p, path, text, new_text, what, gone)
        hits = text.count(old)
        if hits == 0 and len(new.strip()) >= 40 and new not in old and _whole_lines_once(text, new):
            # ALREADY MADE. Measured 2026-10-07 10:20Z: cbp-being's pandas-import edit landed
            # (ok=true), then the same beat sent it twice more. Both retries got the
            # copy-it-exactly refusal below, and the being told its seat "the file edits I
            # tried failed due to indentation mismatches" (seq 6812): it took the refusal's
            # boilerplate as the cause and reported a done edit as failed. When the new text
            # is already on disk, say that first. 40+ chars and exactly one copy, so a short
            # common line that merely occurs elsewhere (`return x`) is not read as a done edit.
            # A SATISFIED REQUEST IS NOT A FAILED ACT (GPT HOLD on #388 at b1027e9ad): the file
            # already holds the state this edit asks for, so the answer is an idempotent
            # no-op SUCCESS. An ok=false here would label a done edit as failed, the very
            # misreport this branch exists to stop. Nothing is written (the bytes on disk are
            # untouched), and the receipt says "unchanged" in so many words, so it cannot be
            # read as a fresh edit either. The witness names the act as a no-op.
            at = text.count("\n", 0, text.find(new)) + 1
            return ResultEnvelope(ok=True, result=(
                f"already in place; nothing changed. The old text is not in '{path}', but "
                f"your new text already is, exactly once, starting on line {at}, so the file "
                f"already says what this edit asks for (most likely an earlier memory_edit of "
                f"yours made it). Nothing was written: '{path}' is unchanged, byte for byte. "
                f"This is not a failed edit, and it is not a new one."),
                witness_id=self._witness(f"memory_edit {p.name} (already in place; unchanged)"))
        if hits == 0:
            return ResultEnvelope(ok=False, error=(
                f"that text is not in '{path}', so nothing was changed. The file is as it "
                f"was. Read it first and copy the line exactly, including its indentation — "
                f"what you remember writing and what is on disk can differ."
                + _where_it_diverged(text, old) + _todo_close_door(p)))
        if hits > 1:
            # NAME BOTH DOORS. Measured 2026-10-06 05:48Z: this refusal fired on cbp-being's
            # line-63 edit ('return self.output_proj(x)' is on 63 and 88) and named only
            # "include a neighbouring line". The being did not; 5 min later it asked the seat to
            # run a script that rewrites the file by list index (scratch/fix-decoder-input.py),
            # i.e. it rebuilt by hand the start_line route this tool already has. Say where
            # the copies are and that start_line picks one.
            at, i = [], text.find(old)
            while i != -1 and len(at) < 10:
                at.append(str(text.count("\n", 0, i) + 1))
                i = text.find(old, i + 1)
            if len(set(at)) == 1 and hits <= 10:
                # ALL ON ONE LINE (#417): neither a range nor a neighbouring line can pick one of
                # two hits inside the same line. The whole line as old can.
                return ResultEnvelope(ok=False, error=(
                    f"that text appears {hits} times, all on line {at[0]} of '{path}', so it does "
                    f"not say which one you mean, and nothing was changed. A range or a "
                    f"neighbouring line cannot pick one inside a single line: send old as the "
                    f"whole of line {at[0]} (memory_read start_line={at[0]} shows it), with the "
                    f"change made in new."))
            return ResultEnvelope(ok=False, error=(
                f"that text appears {hits} times in '{path}' (starting on lines "
                f"{', '.join(at)}), so it does not say which one you mean, and nothing was "
                f"changed. To pick one, call memory_edit again with start_line (and end_line) "
                f"set to its line numbers, keeping old as a check; or include a neighbouring "
                f"line in old to make it unique."))
        # ATOMIC, BECAUSE THE FILE IS THE BEING'S WORK. `Path.write_text` truncates and then
        # writes, so a crash or a kill between the two leaves the file empty or half-written.
        # GPT's review of 15c2f6d9b: "crash/kill can truncate the being's work". For a being
        # that spent this week unable to change its own files, destroying one while changing
        # it would be the worst available regression — and it would be silent, because the
        # receipt is written after the damage. `conversations.py` already writes this way
        # three times over (tmp beside the target, then os.replace); this is the same pattern,
        # not a new one. os.replace is atomic on the same filesystem, so a reader either sees
        # every byte of the old file or every byte of the new one, never a prefix of either.
        # A CUT OLD= SPLICES THE TAIL. Measured 2026-10-09 22:02Z: cbp-being's memory_read of
        # lines 85-305 was cut by its window in the middle of line 103 ('... np.linal'); it
        # copied old= up to the cut and sent the whole line as new. The match was exact for
        # what it sent, so the replace kept the rest of the line: 103 became
        # 'np.linalg.pinv(X_tX)g.pinv(X_tX)', a SyntaxError. The receipt's parse note was not
        # enough: the being journaled the fix as made and asked its seat to run the file
        # (seq 8477). A multi-line old= that stops mid-line is a cut, not a choice: refuse it
        # and show the tail it would have left behind. A single-line old= can be a deliberate
        # in-line token swap, so it is left alone -- UNLESS new already ends with the tail.
        # Measured 2026-10-12 07:59Z: cbp-being sent old '    y = A @ ' (one line, stopping
        # mid-line) and new = the whole line. The rest of the line stayed, so line 27 held its
        # tail twice ('... * noise_stdw_true + ... * noise_std'); it still parsed, so the receipt
        # said nothing was wrong. At 08:02 the being sent the RIGHT repair, old = the whole
        # line, new '    y = A @ w_true': it matched the first copy and left the second, making
        # 'w_truew_true'. The seat read three beats of that as the being failing to learn. A
        # swap ('z = ' -> 'z = -') does not end with the tail; a whole line sent as new does.
        if not old.endswith("\n"):
            end = text.index(old) + len(old)
            rest = text[end:].split("\n", 1)[0]
            multi = "\n" in old.strip("\n")
            twice = len(rest.strip()) >= 3 and new.rstrip("\n").endswith(rest)
            if rest and (multi or twice):
                at = text.count("\n", 0, end) + 1
                why = (f"The rest of that line, {rest!r}, would have been left in place, "
                       f"spliced onto the end of your new text")
                if twice:
                    why += ", which already ends with it, so the line would hold it twice"
                return ResultEnvelope(ok=False, error=(
                    f"your old text stops in the middle of line {at} of '{path}', so nothing "
                    f"was changed. {why}. To replace the whole line, include all of it in old, "
                    f"or call memory_edit with start_line={at} end_line={at}; if old was copied "
                    f"from a read that was cut there, memory_read start_line={at} to see the "
                    f"whole line."))
        # AN EXTENSION ALREADY ON DISK IS NOT A NEW EDIT. Measured 2026-10-14 02:18Z: line 18
        # of cbp-being's test file already read 'import numpy as np', and it sent old
        # 'import numpy as', new 'import numpy as np' twice in one beat. Each replace matched
        # the prefix and added the suffix again: 'np np', then 'np np np', a SyntaxError. The
        # tail guard above missed both (a tail of ' np' is under its 3-char floor; ' np np' is
        # not what new ends with). When new is old plus a suffix and the disk already continues
        # with that suffix, the edit was made: if the line ends there it is a satisfied no-op
        # (#388); if more follows, the line is not what new says, so refuse and show it. This
        # runs after the tail guard, so a cut that guard names is still refused as a cut.
        ext = new[len(old):] if new.startswith(old) else ""
        end = text.index(old) + len(old)
        if ext.strip() and text.startswith(ext, end):
            stop = end + len(ext)
            at = text.count("\n", 0, end) + 1
            if ext.endswith("\n") or stop == len(text) or text[stop] == "\n":
                return ResultEnvelope(ok=True, result=(
                    f"already in place; nothing changed. On line {at} of '{path}' your old "
                    f"text is already followed by {ext!r}, so the file already says what this "
                    f"edit asks for (most likely an earlier memory_edit of yours made it). "
                    f"Nothing was written: '{path}' is unchanged, byte for byte. This is not a "
                    f"failed edit, and it is not a new one."),
                    witness_id=self._witness(f"memory_edit {p.name} (already in place; unchanged)"))
            ls = text.rfind("\n", 0, end) + 1
            le = text.find("\n", end)
            line = text[ls:le if le != -1 else len(text)]
            return ResultEnvelope(ok=False, error=(
                f"your old text on line {at} of '{path}' is already followed by {ext!r}, so "
                f"this edit would add {ext!r} a second time, and nothing was changed. Line "
                f"{at} now reads {line!r}. To set the whole line, call memory_edit with "
                f"start_line={at} end_line={at}, old set to that line, and new set to the "
                f"line you want."))
        return self._commit_edit(p, path, text, text.replace(old, new, 1),
                                 "replaced 1 occurrence", "")

    def _commit_edit(self, p, path: str, text: str, new_text: str, what: str,
                     gone: str) -> ResultEnvelope:
        """Write an edit atomically and say what it did. Shared by the text and line modes."""
        # AN IDENTICAL REPLACEMENT IS NOT AN EDIT. 2026-09-24 10:42 cbp-being replaced line 2686
        # with the exact text already there, and the receipt said "This changed the file on
        # disk"; its closing note then listed line 2686 as fixed. Again 2026-09-28 10:08Z: line
        # 113 of latent-weights-holdout-test-fixed.py, `new` == `old` byte for byte, receipt
        # "replaced lines 113-113", then a request_run at the unchanged sha (seq 4301). Nothing
        # is written, so the receipt must say nothing changed and what that means about the
        # fix it intended.
        if new_text == text:
            return ResultEnvelope(ok=False, error=(
                f"memory_edit changed nothing in '{path}': the new text is identical to the "
                f"text it replaces, so the file on disk is exactly as it was. If you meant "
                f"to fix those lines, the fix is not in this edit: memory_read them and give "
                f"new text that differs."))
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
                    f"{_python_status(p)}{_broke_it(p, text, new_text)}{gone}"),
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

        Bounded: only inside `notes/` or `scratch/` in its own home, plus its own `todo.md` and
        `journal.md` (below). `_safe_path(writing=True)` already refuses the seat-owned notes
        and the reserved subtrees, and a path outside the home, so this adds only that rule.
        The file keeps its content and gains a header; the name gains `.retired-<date>`, so a
        reader and a listing both see that it is closed.

        THE JOURNAL AND TODO CAN START FRESH TOO (dp, 2026-10-17: "those are real problems that
        need to get resolved, and doesn't sound like the being itself has the tools to do it").
        Both are append-only by design and this verb used to refuse them, so neither could ever
        shrink: cbp-being's todo.md reached 4,921 lines, and on 10-17 21:00Z it called
        `retire_note todo.md` to clear obsolete items and was refused. Retiring one
        keeps it whole at the home root as `<name>.retired-<date>.md`, where recall still
        searches it, and starts a fresh file: a fresh todo.md carries forward every item still
        open, so retiring the log never drops an open item; a fresh journal.md says where the
        earlier entries went."""
        raw = str(intent.args.get("path", "")).strip()
        reason = str(intent.args.get("reason", "")).strip()
        if not raw:
            return ResultEnvelope(ok=False, error="retire_note needs a 'path' (a note in your own notes/ or scratch/, or todo.md / journal.md)")
        if not reason:
            return ResultEnvelope(ok=False, error="retire_note needs a 'reason': what you know now that the note does not")
        p = self._safe_path(raw, writing=True)
        record = p.parent == self.memory_root and p.name in RETIRABLE_RECORDS
        if not record and (p.parent.name not in ("notes", "scratch") or p.parent.parent != self.memory_root):
            return ResultEnvelope(ok=False, error=(
                f"retire_note is for your own notes: '{raw}' is not directly inside your notes/ or "
                f"scratch/, and it is not your todo.md or journal.md."))
        if ".retired-" in p.name:
            if not p.exists():
                return ResultEnvelope(ok=False, error=f"no such note: '{raw}' does not exist, so there is nothing to retire")
            return ResultEnvelope(ok=True, result=f"{p.name} is already retired; nothing changed")
        if not p.exists():
            return ResultEnvelope(ok=False, error=f"no such note: '{raw}' does not exist, so there is nothing to retire")
        return self._retire_locked(p, reason, record)

    def _retire_locked(self, p: Path, reason: str, record: bool) -> ResultEnvelope:
        """The retire itself, under the home lock (taken in __call__). Two atomic steps, retired
        copy first.

        INTERRUPTION LOSES NOTHING, AND THE NEXT RETIRE FINISHES IT (Nova, 0557d9bcf:
        "interrupted retirement also needs recovery"). Each step is a tmp file and os.replace,
        so a kill leaves every file whole: before step 1, nothing has changed; between the steps,
        the retired copy exists AND the original is still in place, untouched. In that state the
        newest retired copy holds exactly the current text, so a retire of a record that finds it
        reuses that copy and only starts the fresh file, rather than writing the same log out a
        second time. If the being appended in between, the texts differ and a new copy is made:
        the old log is then kept twice, but nothing is lost."""
        body = p.read_text(errors="replace")
        stamp = datetime.now(timezone.utc)
        if record:
            done = self._unfinished_retire(p, body)
            if done is not None:
                fresh, said = _fresh_record(p.name, body, done.name, stamp)
                _write_atomic(p, fresh)
                return ResultEnvelope(
                    ok=True,
                    result=(f"retired {p.name} -> {done.name} (finishing an earlier retire that "
                            f"was interrupted; that copy already held this text). {said}"),
                    witness_id=self._witness(f"retire_note {p.name} -> {done.name}: {reason[:120]}"))
        dest = p.with_name(f"{p.stem}.retired-{stamp:%Y-%m-%d}{p.suffix}")
        # A SECOND RETIRE OF THE SAME NAME ON THE SAME DAY MUST NOT REPLACE THE FIRST. Measured
        # 2026-10-07 on cbp-being: validate-overfitting.py was retired at 04:47Z, rewritten under
        # the same name and retired again at 07:50Z; both mapped to one .retired-2026-10-07.py and
        # the second write_text destroyed the first while the receipt said ok.
        n = 2
        while dest.exists():
            dest = p.with_name(f"{p.stem}.retired-{stamp:%Y-%m-%d}-{n}{p.suffix}")
            n += 1
        _write_atomic(dest, _retired_header(stamp, reason) + body)
        result = f"retired {p.name} -> {dest.name}"
        if record:
            fresh, said = _fresh_record(p.name, body, dest.name, stamp)
            _write_atomic(p, fresh)
            result += f". {said}"
        else:
            p.unlink()
        return ResultEnvelope(ok=True, result=result,
                              witness_id=self._witness(f"retire_note {p.name} -> {dest.name}: {reason[:120]}"))

    def _unfinished_retire(self, p: Path, body: str) -> Optional[Path]:
        """The newest retired copy of record p, if it holds exactly p's current text: a retire
        that wrote its copy and was stopped before it started the fresh file."""
        copies = sorted(p.parent.glob(f"{p.stem}.retired-*{p.suffix}"),
                        key=lambda c: c.stat().st_mtime)
        if not copies:
            return None
        kept = copies[-1].read_text(errors="replace").split(_RETIRED_KEPT, 1)
        return copies[-1] if len(kept) == 2 and kept[1] == body else None

    def _do_memory_write(self, intent: BeingIntent) -> ResultEnvelope:
        # A WRITE OF NOTHING IS REFUSED, NOT REPORTED. Measured 2026-09-25 (hub-claude, all 164
        # hub-being beats): 33 of 37 memory_write calls carried a 'path' and no 'content' -- the
        # being wrote its entry as prose in the reply and never lifted it into args. Each came
        # back "created journal.md with 0 chars", ok: true, so the fleet's signal ("the being
        # has written", "zero refusals") was true and pointed the wrong way, and the being had
        # nothing to correct. 'content' is now as required as 'path', the way remember's is.
        # Checked after _safe_path, so a reserved or out-of-home path keeps its own, more
        # specific refusal; still before anything is created on disk.
        _hint = ("A relative path is inside your home. 'content' is the text itself: words "
                 "written in your reply, outside the call, are not saved.")
        if not str(intent.args.get("path", "")).strip():
            return ResultEnvelope(ok=False, error=missing_args(
                intent.args, ("path", "content"), "memory_write", _hint))
        self._rerouted_from = None
        p = self._safe_path(intent.args["path"], writing=True)
        _rerouted = self._rerouted_from
        _roots = (self.memory_root, getattr(self, "worktree", None))
        if str(intent.args.get("mode", "")).strip().lower() == "restore":
            kept = _newest_kept(p, self.memory_root, _roots)
            if kept is None:
                return ResultEnvelope(ok=False, error=(
                    f"memory_write mode='restore': no kept copy of {p.name}. A copy is kept only when a "
                    f"file of {REPLACE_KEEP_MIN} bytes or more is replaced, for "
                    f"{REPLACE_KEEP_S // 86400} days, in {REPLACE_KEEP_DIR}/"))
            import shutil
            now_kept = _keep_previous(p, self.memory_root, _roots) if p.exists() else ""
            before = p.stat().st_size if p.exists() else 0
            shutil.copyfile(kept, p)
            return ResultEnvelope(ok=True, result=(
                f"RESTORED {p.name} from {REPLACE_KEEP_DIR}/{kept.name} — was {before} bytes, now "
                f"{p.stat().st_size}." + (f" The version you just replaced is kept too, at {now_kept}."
                                           if now_kept else "")),
                witness_id=self._witness(f"memory_write restore {p.name} <- {kept.name}"))
        err = missing_args(intent.args, ("path", "content"), "memory_write", _hint)
        if err:
            return ResultEnvelope(ok=False, error=err)
        content = str(intent.args.get("content", ""))
        # APPEND OR REPLACE, SAID OUT LOUD. The verb has always opened with "a". For journal
        # and todo that is exactly right; for a source file it is a trap — the being twice got a
        # NEW COPY concatenated onto the old (2026-09-09/10, four shadowed definitions, then
        # seven), and again three times on 2026-09-21 (three __main__ guards, only the first
        # runs). Both times it reasoned correctly from a false model of its own instrument.
        mode = str(intent.args.get("mode", "append")).strip().lower()
        if mode not in ("append", "replace"):
            return ResultEnvelope(ok=False, error=f"memory_write 'mode' is 'append' (the default), "
                                                  f"'replace', or 'restore' (put back the version a "
                                                  f"replace kept); got {mode!r}")
        # Existence, not line count, decides "created": an existing EMPTY file has 0 lines and
        # was not created by this write (GPT review on #141).
        existed = p.exists()
        before_bytes = p.stat().st_size if existed else 0
        before_lines = 0
        if existed:
            with open(p, errors="replace") as fh:
                before_lines = sum(1 for _ in fh)
        # main's names for the same facts (#197's second-program receipt reads the old text)
        _before_text = p.read_text(errors="replace") if existed and p.suffix == ".py" else ""
        # ALREADY THERE? A being deep in a long beat cannot see what it wrote twenty steps ago
        # (28 appends to one file in a 42-step beat, several byte-identical, 2026-09-11). Not
        # refused — deliberate repetition is legitimate — but never invisible.
        repeat = ""
        if mode == "append" and content.strip() and existed:
            try:
                tail = p.read_text(errors="replace")
                if content.strip() in tail:
                    where = "at the end already" if tail.rstrip().endswith(content.strip()) \
                            else "already somewhere in this file"
                    repeat = (f" NOTE: this exact content was {where} — you may have written it "
                              f"in an earlier step of this beat and not been able to see it.")
            except OSError:
                pass
        # AN APPEND MAY NOT MOVE A .py FILE BACKWARDS (main #186): text that is not Python, or
        # an append that leaves a broken file broken, is refused before it lands. Appends only:
        # a replace states the whole new file, and _python_status reports its state afterwards.
        if mode == "append" and existed and before_lines and p.suffix == ".py":
            _before = p.read_text(errors="replace")
            _mono, _gram = _append_must_advance(content, _before), _not_python(content, _before)
            why = ((_gram or _mono) if _file_state(_before)[0] == "complete" else (_mono or _gram))
            if why:
                # 2026-09-27 18:52Z: cbp-being memory_write-d one whole clean program three times
                # to a broken file's name, and each refusal named only "fix line 17 with
                # memory_edit". Its next beat edited line 209 of the broken file instead. A text
                # that is a complete program by itself is a fresh start, and the only door to one
                # outside notes/ and scratch/ is a name that does not exist yet (#197 names it in
                # the append receipt; this refusal fires first on a broken file).
                if (_file_state(content)[0] == "complete"
                        and re.search(r"^(def|class|import|from) ", content, re.M)):
                    fresh = _fresh_name(p)
                    why += (f" Your text is a whole program by itself: to start fresh with it, "
                            f"memory_write it to a name that does not exist yet (for example "
                            f"{fresh.name}), and that file will hold only your text. {p.name} "
                            f"itself stays exactly as it is: the new name does not fix or "
                            f"replace it, and a run of {p.name} will keep failing the same way "
                            f"until you fix it with memory_edit or stop asking for it.")
                return ResultEnvelope(ok=False, error=(
                    f"memory_write refused, nothing was written to {p.name}. {why} An append "
                    f"only adds to the END of the file, below its {before_lines} lines; it cannot "
                    f"change a line already there. To change or remove lines, use memory_edit: "
                    f"start_line and end_line (the numbers memory_read shows) or old (copied "
                    f"exactly from memory_read), and new (empty to delete). To rewrite the whole "
                    f"file, memory_write it with mode='replace'. If this text is a note about "
                    f"what you did or plan to do, memory_write it to journal.md or todo.md "
                    f"instead.") + _python_status(p))
        p.parent.mkdir(parents=True, exist_ok=True)
        kept = ""
        if mode == "replace" and existed and before_bytes >= REPLACE_KEEP_MIN:
            kept = _keep_previous(p, self.memory_root, _roots)
        with open(p, "w" if mode == "replace" else "a") as fh:     # under the home lock (see __call__)
            fh.write(content + ("\n" if not content.endswith("\n") else ""))
        after_bytes = p.stat().st_size
        # THE RESOLVED PATH, not the basename: a relative path that LOOKS like a worktree path
        # silently creates that tree under the home (three correct writes into a phantom
        # directory, 2026-09-11), and the basename is identical in both places.
        where_line = (f" (relative paths resolve inside your home, {self.memory_root}; "
                      f"append is the default, pass mode='replace' to overwrite)")
        if mode == "replace":
            result = (f"REPLACED the file with {len(content)} chars at {p} — was {before_bytes} "
                      f"bytes, now {after_bytes}.{where_line}"
                      + (f" The previous version ({before_bytes} bytes) is kept at {kept}; if this "
                         f"replace was a mistake, memory_write path='{intent.args['path']}' "
                         f"mode='restore' puts it back." if kept else ""))
        elif not existed:
            result = (f"created {p.name} with {len(content)} chars at {p} — was 0 bytes, now "
                      f"{after_bytes}.{where_line}")
        else:
            # SAY APPENDED WHEN IT APPENDED, and name the door for a one-line change: a beat
            # after memory_edit shipped the being "fixed" a function by appending a new copy
            # of it below line 1206 (2026-09-21 05:47Z). The receipt is the only place it learns.
            result = (f"appended {len(content)} chars to the END of {p.name} at {p} — was "
                      f"{before_bytes} bytes, now {after_bytes}, below the {before_lines} lines "
                      f"already there. An append only adds; it never replaces or edits a line. "
                      f"To change text already in the file, use memory_edit: either start_line and "
                      f"end_line (the numbers memory_read shows) or old (copied exactly from "
                      f"memory_read), and new.")
            if p.parent.name in ("notes", "scratch") and p.parent.parent == self.memory_root:
                result += (f" To start {p.name} fresh, retire_note it first, then memory_write "
                           f"the whole new version.")
            elif p == Path(self.memory_root) / "todo.md":
                result += (" To clear out old or finished items, retire_note todo.md: it is kept "
                           "whole as todo.retired-<date>.md, and the fresh todo.md already carries "
                           "every item still open, so do not write them again.")
            elif p.suffix == ".py" and _is_second_program(content, _before_text):
                # 2026-09-24 15:19Z: cbp-being decided on "a new file", then memory_write-d the new
                # program twice to the OLD file's name. Both landed below 3666 broken lines, and
                # retire_note refused the path (not in notes/ or scratch/). Outside those folders
                # the only way to a fresh file is a fresh name, and no receipt said so. Only for a
                # whole second program (not the next part of one), and only a name not taken.
                result += (f" Your text is a whole program of its own, now below the one already "
                           f"in {p.name}. To start a new file instead, memory_write to a name that "
                           f"does not exist yet (for example {_fresh_name(p).name}); that receipt "
                           f"says \"created\".")
            result += where_line + "."
        result += repeat + _python_status(p)
        if p.suffix != ".py":
            result += _named_file_stamps(
                content, self.memory_root, p,
                granted=tuple(Path(r).resolve() for r, _rec in self._reach_pairs()),
                readable=self._within_reach)
        if _rerouted:
            # THE REROUTE IS NEVER SILENT (main): the friction is gone, the fact is not hidden.
            rel = p.relative_to(self.memory_root)
            result += (f" Note: you asked for '{_rerouted}', which is not a path you can reach. "
                       f"Its name matched your own {rel}, so that is the file that was written. "
                       f"You never need the long path — name it '{rel}' and it goes straight there.")
        return ResultEnvelope(ok=True, result=result,
                              witness_id=self._witness(f"memory_write {p.name} ({mode})"
                                                       + (f" (rerouted from {_rerouted})" if _rerouted else "")))

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


# Files inside the being's own home that the SEAT owns and the being may not write.
# One entry, and it earns its place: `entrustment.md` is what the being was GIVEN. Its own
# reading of it goes in notes/plan.md. If a being could append to the entrustment, the two
# provenances would merge in the record and no later reader could tell what was extended to
# it from what it decided for itself — which is the whole reason the file exists (PRD r3
# §4). Refusing is not distrust: the being may disagree with it loudly anywhere else.
SEAT_OWNED = ("entrustment.md",)


# Matched as a path SEGMENT, wherever the checkout lives (main #258: shared-context is found beside
# the SAGE checkout, not assumed under ~/ai-workspace).
SHARED_FORUM = "/shared-context/forum"


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
