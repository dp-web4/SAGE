"""WINDOW PROFILE: the harness sized from the model's window, not pressed onto it.

Step 1 of the SAGE-at-home PRD (dev-SAGE `PRD_SAGE_AT_HOME_2026-11-26.md` §8, §8a). Opt-in per instance,
`instance.json` `"window_profile": true`. Absent, nothing here runs and the beat is byte-identical.

WHY. Measured on cbp-being (qwen3.8-distill 4B, num_ctx 20480), 42 beats after `tool_descriptions` went lean
(2026-11-27 01:18Z..05:30Z): tool schemas 19,394 chars, state ~24,400, posture 5,045, framing ~5,077, against a
window budget of ~45,300. Every beat of 11-19..26 ran at the sparsest conversation rung with recall cut. A
parent's laptop is smaller: at an 8k window with a 1,500-token reserve the budget is ~20,000 chars, and the
fixed parts alone (schemas + posture + framing, ~29,500) are half again more than all of it.

WHAT IT DOES, given the window budget (`window_budget_chars`, the one producer both fitters use):
1. TOOLS. Every verb stays callable (dp 2026-09-29: every being is offered the whole toolset). Native tool
   calling only accepts verbs that are OFFERED (being_tool_loop.salvage_tool_calls; the gate refuses the
   rest), and a spec costs ~300 chars even cut to its name (measured: all 40 verbs by name = 13,202 chars),
   so a directory of per-verb specs cannot fit a 4k share. Instead the verbs the being uses most keep their
   specs, and the rest sit behind ONE spec, `verb`: a closed list of their names (an enum) with one line
   each, and `args` as an object. `parse_tool_calls` resolves `verb name=X args={...}` to X before the gate,
   so the call is gated, dispatched and recorded as X. `describe X` still returns X's full text, and a verb
   called (through `verb` or natively) or described counts as used: from the next beat it competes for a
   spec by use. A page fault for tools (paged-context PRD P1): listed, reachable, never pushed.
2. STATE. Sections whose kind is listable (settled conclusions, the todo, the journal tail, skills, the
   notes/ and scratch/ listings, two measurements) get a share of the state budget. Over its share, a section
   keeps its heading, as many whole lines as fit, and one line saying how many are not shown and the read
   that shows them. Nothing else in the state is cut by the profile: the body, what the being is entrusted
   with, who it says it is, its conversations (SG4's directory handles those, SAGE #836), letters from dp and
   the seat, its services and account. The todo's run-box duplicate is folded into the todo lines it repeats.
3. NOT IN THIS STEP. Posture and framing text (the being's standing context) are left alone and reported as
   the remaining gap; the inbox is reported, not listed (SG4's inbox half is its own slice).

Per instance (RESEARCH_GENERALIZATION_RULE): measured on one being; the shares below are a starting point
from that measurement, not a law.
"""
import json
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

MODE_KEY = "window_profile"

# Shares of the window budget (chars). Posture and framing are not managed in this step.
SHARES = {"tool_schemas": 0.20, "state": 0.40}

# Listable state sections, by heading prefix (after "## "): share of the STATE budget, which end to keep,
# and the read that shows what was not shown (None: a measurement made fresh each beat, not stored).
SECTIONS = (
    ("What you have settled", 0.18, "head", "memory_read path settled.json"),
    ("todo.md", 0.12, "head", "memory_read path todo.md"),
    ("journal.md (tail)", 0.06, "tail", "journal"),
    ("Skills (", 0.05, "head", "skill with no arguments"),
    ("notes/", 0.04, "head", "memory_read path notes"),
    ("scratch/", 0.04, "head", "memory_read path scratch"),
    ("Your run box, measured", 0.04, "head", None),
    ("Your files and runs, measured", 0.04, "head", None),
)
CENSUS_TODO = "Your open todo items, beside your run box"

ROUTER = "verb"
ROUTER_LINE_CHARS = 60


def mode(cfg: Optional[dict]) -> bool:
    """instance.json `window_profile`: true (or "on") opts in; anything else leaves the beat as it was."""
    v = (cfg or {}).get(MODE_KEY)
    return v is True or str(v).strip().lower() in ("on", "true")


def share_chars(budget: int, part: str) -> int:
    return int(max(0, budget) * SHARES[part])


# ---------------------------------------------------------------- tools

def call_counts(instance, beats: int = 100) -> Counter:
    """How many of the being's last `beats` working beats called each verb (a refused call still counts:
    it reached for it), plus verbs it asked `describe` about. Same reading as toolset.recently_called."""
    from sage.gateway import beat_health as bh
    counts, working = Counter(), 0
    for rec in bh.iter_beats_newest_first(instance):
        seen = set()
        for _, phase in bh._phases(rec):
            for t in phase.get("trace") or ():
                if not isinstance(t, dict) or not t.get("effector"):
                    continue
                seen.add(str(t["effector"]))
                if t["effector"] == "describe" and isinstance(t.get("args"), dict):
                    seen.add(str(t["args"].get("verb") or "").strip())
        if seen:
            working += 1
            counts.update(seen - {""})
        if working >= beats:
            break
    return counts


def _one_line(desc: str, cap: int = ROUTER_LINE_CHARS) -> str:
    d = re.sub(r"\s*\((?:Full text|describe)[^)]*\)\s*", " ", str(desc or "")).strip()
    d = re.sub(r"\s*\(describe \w+[^)]*\)\s*$", "", d)
    m = re.match(r"(.+?[.!?])(\s|$)", d, re.S)
    first = (m.group(1) if m else d).strip()
    return first if len(first) <= cap else first[:cap - 1].rstrip() + "…"


def router_spec(tail: List[dict], with_lines: bool = True) -> dict:
    names = [s["function"]["name"] for s in tail]
    listing = ""
    if with_lines:
        listing = " " + "; ".join(f"{s['function']['name']}: {_one_line(s['function'].get('description', ''))}"
                                  for s in tail)
    return {"type": "function", "function": {
        "name": ROUTER,
        "description": ("Calls one of these verbs by its name, with its arguments as an object; "
                        "describe <name> gives that verb's parameters." + listing),
        "parameters": {"type": "object",
                       "properties": {"name": {"type": "string", "enum": names},
                                      "args": {"type": "object"}},
                       "required": ["name"]}}}


def fit_tools(specs: List[dict], budget: int, counts: Counter,
              always: frozenset = frozenset({"describe", "stay_awake", "rest"})) -> Tuple[List[dict], dict]:
    """(specs to offer, record). Unchanged when the specs fit their budget. Otherwise the verbs in `always`
    keep their specs, then the most-used verbs, in order, while the whole (kept specs + the `verb` spec over
    the rest) stays within `budget`; the rest are listed in `verb`. If even that is over, `verb` drops its
    one-line descriptions (names only) before any used verb loses its spec."""
    size = lambda xs: len(json.dumps(xs))
    before = size(specs)
    rec = {"budget": budget, "before": before}
    if before <= budget:
        return specs, dict(rec, after=before, routed=[], fits=True)
    by_name = {s["function"]["name"]: s for s in specs}
    order = [s["function"]["name"] for s in specs]
    kept = [n for n in order if n in always]
    rank = sorted((n for n in order if n not in always), key=lambda n: (-counts.get(n, 0), order.index(n)))

    def build(keep, lines=True):
        tail = [by_name[n] for n in order if n not in keep]
        out = [by_name[n] for n in order if n in keep]
        return out + ([router_spec(tail, lines)] if tail else [])

    lines = True
    if size(build(set(kept), True)) > budget:
        lines = False
    for n in rank:
        if counts.get(n, 0) <= 0:
            break                                   # an unused verb never takes a spec from the listing
        if size(build(set(kept) | {n}, lines)) <= budget:
            kept.append(n)
        else:
            break                                   # by use, in order: a less-used verb never jumps a more-used one
    out = build(set(kept), lines)
    routed = [n for n in order if n not in kept]
    return out, dict(rec, after=size(out), kept=[n for n in order if n in kept], routed=routed,
                     router_lines=lines, fits=size(out) <= budget)


def resolve_router(name: str, args: dict) -> Tuple[str, dict]:
    """`verb name=X args={...}` -> (X, {...}). Anything else is returned unchanged. A string `args` is parsed
    as JSON; a malformed one becomes {"_raw": ...} so the gate refuses it with the verb's own reason."""
    if name != ROUTER or not isinstance(args, dict) or not str(args.get("name") or "").strip():
        return name, args
    inner = args.get("args")
    if inner is None:
        inner = {}
    if isinstance(inner, str):
        try:
            inner = json.loads(inner) if inner.strip() else {}
        except Exception:
            inner = {"_raw": inner}
    return str(args["name"]).strip(), inner if isinstance(inner, dict) else {"_raw": inner}


# ---------------------------------------------------------------- state

def _split(state: str) -> List[str]:
    """The state as chunks, each starting at a '## ' heading (the first chunk is whatever precedes one).
    ''.join(chunks) == state."""
    idx = [m.start() for m in re.finditer(r"(?m)^## ", state)]
    if not idx:
        return [state]
    out = [state[:idx[0]]] if idx[0] > 0 else []
    for a, b in zip(idx, idx[1:] + [len(state)]):
        out.append(state[a:b])
    return out


def _kind(chunk: str):
    head = chunk[3:].split("\n", 1)[0] if chunk.startswith("## ") else ""
    for prefix, share, keep, handle in SECTIONS:
        if head.startswith(prefix):
            return prefix, share, keep, handle
    return None


def _journal_handle(instance, kept_lines: int, hidden: int) -> str:
    try:
        n = len((Path(instance) / "journal.md").read_text(errors="replace").splitlines())
    except OSError:
        n = 0
    end = n - kept_lines
    start = end - hidden + 1
    if n <= 0 or end < 1:
        return "memory_read path journal.md"
    return f"memory_read path journal.md start_line {max(1, start)} end_line {end}"


def _cut(chunk: str, share: int, keep: str, handle: Optional[str], instance) -> Tuple[str, dict]:
    body_end = chunk.rstrip("\n")
    trailer = chunk[len(body_end):]
    lines = body_end.split("\n")
    head, body = lines[0], lines[1:]

    def note(hidden, kept):
        if handle == "journal":
            h = _journal_handle(instance, kept, hidden)
        else:
            h = handle
        what = f"{hidden} more line{'s' if hidden != 1 else ''} not shown here"
        return f"_({what}: {h})_" if h else f"_({what}; measured fresh each beat, not stored)_"

    seq = body if keep == "head" else list(reversed(body))
    chosen, used = [], len(head) + 1
    for ln in seq:
        if used + len(ln) + 1 + len(note(len(body) - len(chosen) - 1, len(chosen) + 1)) + 1 > share:
            break
        chosen.append(ln)
        used += len(ln) + 1
    if keep != "head":
        chosen = list(reversed(chosen))
    hidden = len(body) - len(chosen)
    if hidden <= 0:
        return chunk, {}
    text = "\n".join([head] + chosen + [note(hidden, len(chosen))]) + trailer
    return text, {"section": head[3:83], "before": len(chunk), "after": len(text), "share": share,
                  "lines_shown": len(chosen), "lines_hidden": hidden,
                  "handle": (None if handle is None else ("journal.md lines" if handle == "journal" else handle))}


def _fold_census(chunks: List[str]) -> Tuple[List[str], int]:
    """The run-box todo block quotes open todo items the todo section already shows. Each quoted item that
    the todo shows gets the measurement beside it there, and leaves the run-box block; whatever the todo
    doesn't show stays in that block."""
    ti = next((i for i, c in enumerate(chunks) if c.startswith("## todo.md")), None)
    ci = next((i for i, c in enumerate(chunks) if c.startswith("## " + CENSUS_TODO)), None)
    if ti is None or ci is None:
        return chunks, 0
    todo = chunks[ti].split("\n")
    census_end = chunks[ci].rstrip("\n")
    trailer = chunks[ci][len(census_end):]
    cl = census_end.split("\n")
    keep, folded = [cl[0]], 0
    for ln in cl[1:]:
        m = re.match(r'- "(.*?)": (measured, .*)$', ln)
        hit = None
        if m:
            q = m.group(1)
            hit = next((j for j, t in enumerate(todo) if t.startswith("- [ ] ") and t[6:].startswith(q)), None)
        if hit is None:
            keep.append(ln)
            continue
        todo[hit] = todo[hit] + f" (run box {m.group(2)})"
        folded += 1
    out = list(chunks)
    out[ti] = "\n".join(todo)
    if len(keep) == 1 or all(k.startswith("- … and") for k in keep[1:]):
        out[ci] = ""
    else:
        out[ci] = "\n".join(keep) + trailer
    return out, folded


def fit_state(state: str, budget: int, instance) -> Tuple[str, dict]:
    """(state text, record). `budget` is the state's share of the window, in chars."""
    chunks = _split(state)
    chunks, folded = _fold_census(chunks)
    listed = []
    for i, c in enumerate(chunks):
        k = _kind(c)
        if not k:
            continue
        prefix, share, keep, handle = k
        cap = int(budget * share)
        if len(c) <= cap:
            continue
        chunks[i], r = _cut(c, cap, keep, handle, instance)
        if r:
            listed.append(r)
    text = "".join(chunks)
    exempt = sum(len(c) for c in chunks if not _kind(c))
    return text, {"budget": budget, "before": len(state), "after": len(text), "todo_folded": folded,
                  "listed": listed, "not_managed_chars": exempt,
                  "over_budget_by": max(0, len(text) - budget)}
