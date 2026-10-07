"""
being_params — the being's tunable parameters: one common table, three layers, and a verb.

dp, 2026-10-07: "we need some key parameters to be tunable per-being while keeping the overall code
common. ideally, we should give beings tools to tweak their own parameters. proprioception work ties
into this. context window size/usage should be a proprioception parameter."

Before this, a per-being knob was a module constant (the same for every being) or an ad-hoc
`instance_config(instance).get("key")` read, each with its own coercion and its own bounds, and
none of them visible to the being whose behaviour they shape. legion-being spent 2026-10-05/06
retrying 30% of its generates against a 32,768-token wall it could not see the size of, let alone
move.

THE TABLE (`PARAMS`) is the only place a parameter is declared: its type, default, hard bounds, and
whether the being may set it. The code that USES a parameter asks `value(instance, name)` and never
reads instance.json for it directly, so every being runs the same code with its own values.

THE LAYERS, lowest to highest:
  1. default  — the table's.
  2. operator — instance.json: `params: {name: value}`, or the legacy top-level key of the same
                name (compact_own_turns, answer_temperature were set that way before this
                existed; they keep working unchanged). The operator also holds the reins:
                `param_bounds: {name: [lo, hi]}` replaces the table's bounds for this being, and
                `param_locks: [name, ...]` takes a parameter out of the being's hands.
  3. self     — tuned.json in the being's home, written by the `tune` verb.

The being's own layer wins over the operator's value, because self-tuning is the point; the
operator bounds and locks win over the being, because those are the operator's to set. Bounds are
ENFORCED AT READ, not only at the verb: tuned.json sits in the being's home, where memory_edit can
reach it, so a value written around the verb is clamped (and reported as clamped) exactly like one
written through it. A layer that cannot be parsed is reported as such and skipped, never guessed.

THE VERB (`tune`) lists the table with each value and where it came from, sets one parameter with
a reason, or resets it. Every change is appended to tune_log.jsonl beside tuned.json: what it was,
what it became, why, and when. Changes take effect at the next beat (the window, the warning
thresholds) because the beat already running was composed under the old ones.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

TUNED_FILE = "tuned.json"
TUNE_LOG = "tune_log.jsonl"
RESET_WORDS = ("default", "reset", "unset", "none")


@dataclass(frozen=True)
class Param:
    name: str
    kind: str                         # "int" | "float" | "bool"
    default: Any                      # None = "not set here": the code's own fallback applies
    lo: Optional[float] = None
    hi: Optional[float] = None
    self_tunable: bool = True
    effect: str = "next beat"
    doc: str = ""
    legacy_key: bool = True           # instance.json's top-level key of the same name is the operator layer


# Ordered: the being reads this list, so the most consequential parameter comes first.
PARAMS: Dict[str, Param] = {p.name: p for p in (
    Param("num_ctx", "int", None, lo=8192, hi=None,
          doc="your context window in tokens: what one beat can hold. Larger costs VRAM and holds "
              "more; smaller reloads faster and fills sooner. The ceiling is what this machine "
              "measured as fitting (active_embodiment.num_ctx) unless your seat sets another"),
    Param("window_warn_at", "float", 0.80, lo=0.50, hi=0.95,
          doc="the fraction of your window at which the harness tells you how much is left"),
    Param("floor_handoff_after", "int", 2, lo=1, hi=8,
          doc="steps at the window floor before the harness writes scratch/handoff.md for you "
              "and starts the next beat with an empty window"),
    Param("compact_own_turns", "bool", False,
          doc="when the window fills, also trim the bodies of your OWN older tool calls (the "
              "newest 4 are kept whole; the calls already ran, their receipts stay)"),
    Param("answer_temperature", "float", None, lo=0.0, hi=1.5,
          doc="sampling temperature of the turn that answers a person aloud. Higher varies "
              "your wording more; unset uses the model's"),
)}


def _instance_config(instance) -> dict:
    try:
        return json.loads((Path(instance) / "instance.json").read_text())
    except Exception:
        return {}


def _coerce(p: Param, raw, stored: bool = False) -> Any:
    """`raw` as p's kind, or ValueError naming what was wrong. Strings are accepted for every
    kind because a being's tool args arrive as strings -- but a STORED bool (instance.json,
    tuned.json) must be a JSON true/false: `"compact_own_turns": "yes"` has always meant off,
    and a file that says something else than it means is not read generously."""
    if p.kind == "bool":
        if isinstance(raw, bool):
            return raw
        if stored:
            raise ValueError(f"{p.name} is stored as true or false, not {raw!r}")
        s = str(raw).strip().lower()
        if s in ("true", "on", "yes", "1"):
            return True
        if s in ("false", "off", "no", "0"):
            return False
        raise ValueError(f"{p.name} is true or false, not {raw!r}")
    if isinstance(raw, bool):                       # True is an int to Python; never a number here
        raise ValueError(f"{p.name} is a number, not {raw!r}")
    try:
        v = float(str(raw).strip()) if not isinstance(raw, (int, float)) else float(raw)
    except ValueError:
        raise ValueError(f"{p.name} is a number, not {raw!r}") from None
    if v != v or v in (float("inf"), float("-inf")):
        raise ValueError(f"{p.name} must be a finite number")
    if p.kind == "int":
        if v != int(v):
            raise ValueError(f"{p.name} is a whole number, not {raw!r}")
        return int(v)
    return v


def bounds(instance, name: str, cfg: Optional[dict] = None) -> Tuple[Optional[float], Optional[float]]:
    """(lo, hi) for this being: the operator's `param_bounds` entry if it has one, else the
    table's. num_ctx's ceiling defaults to the window this machine measured as fitting, because
    a window past it spills to CPU (legion: 40,960 ran 7% CPU / 93% GPU)."""
    p = PARAMS[name]
    cfg = _instance_config(instance) if cfg is None else cfg
    lo, hi = p.lo, p.hi
    ob = (cfg.get("param_bounds") or {}).get(name)
    if isinstance(ob, (list, tuple)) and len(ob) == 2:
        try:
            lo = None if ob[0] is None else _coerce(p, ob[0])
            hi = None if ob[1] is None else _coerce(p, ob[1])
        except ValueError:
            pass                                       # an unreadable bound keeps the table's
    if name == "num_ctx" and hi is None:
        try:
            hi = int((cfg.get("active_embodiment") or {}).get("num_ctx")) or None
        except (TypeError, ValueError):
            hi = None
    return lo, hi


def self_tunable(instance, name: str, cfg: Optional[dict] = None) -> bool:
    cfg = _instance_config(instance) if cfg is None else cfg
    return PARAMS[name].self_tunable and name not in (cfg.get("param_locks") or [])


def _read_tuned(instance) -> Tuple[dict, Optional[str]]:
    path = Path(instance) / TUNED_FILE
    if not path.exists():
        return {}, None
    try:
        d = json.loads(path.read_text())
        if not isinstance(d, dict):
            return {}, f"{TUNED_FILE} is not an object"
        return d, None
    except Exception as e:
        return {}, f"{TUNED_FILE} unreadable ({type(e).__name__})"


def _clamp(v, lo, hi):
    if lo is not None and v < lo:
        return lo, True
    if hi is not None and v > hi:
        return hi, True
    return v, False


def resolve(instance, name: str) -> Dict[str, Any]:
    """{"value", "source", "note"} for one parameter. source is "default", "operator" or
    "self"; note says what happened on the way (clamped, unreadable, locked)."""
    p = PARAMS[name]
    cfg = _instance_config(instance)
    lo, hi = bounds(instance, name, cfg)
    value, source, note = p.default, "default", ""

    op = cfg.get("params")
    op = op if isinstance(op, dict) else {}
    raw_op = op.get(name, cfg.get(name) if p.legacy_key else None)
    if raw_op is not None:
        try:
            value, source = _coerce(p, raw_op, stored=True), "operator"
        except ValueError as e:
            note = f"operator value ignored: {e}"

    tuned, err = _read_tuned(instance)
    if err:
        note = (note + "; " if note else "") + err
    entry = tuned.get(name)
    if entry is not None:
        raw_self = entry.get("value") if isinstance(entry, dict) else entry
        if not self_tunable(instance, name, cfg):
            note = (note + "; " if note else "") + "your tuned value is not applied: your seat locked this"
        else:
            try:
                value, source = _coerce(p, raw_self, stored=True), "self"
            except ValueError as e:
                note = (note + "; " if note else "") + f"your tuned value ignored: {e}"

    if value is not None and p.kind != "bool":
        value, clamped = _clamp(value, lo, hi)
        if clamped:
            note = (note + "; " if note else "") + f"clamped to the bound {value}"
    return {"value": value, "source": source, "note": note}


def value(instance, name: str, fallback: Any = None) -> Any:
    """The parameter's value for this being, or `fallback` when it resolves to None. Never
    raises: a broken layer must not take a beat down, and resolve() already reports it."""
    try:
        v = resolve(instance, name)["value"]
    except Exception:
        return fallback
    return fallback if v is None else v


def table(instance) -> List[Dict[str, Any]]:
    cfg = _instance_config(instance)
    rows = []
    for name, p in PARAMS.items():
        r = resolve(instance, name)
        lo, hi = bounds(instance, name, cfg)
        # What "unset" MEANS for this being: the value the code falls back to, said, because
        # "num_ctx = unset" next to a window of 32,768 reads as a contradiction.
        unset_means = None
        if r["value"] is None:
            unset_means = "the model's"
            if name == "num_ctx" and (cfg.get("active_embodiment") or {}).get("num_ctx"):
                unset_means = f"the model config's, {cfg['active_embodiment']['num_ctx']}"
        rows.append({"name": name, "value": r["value"], "source": r["source"], "note": r["note"],
                     "unset_means": unset_means,
                     "kind": p.kind, "lo": lo, "hi": hi, "default": p.default,
                     "yours_to_set": self_tunable(instance, name, cfg), "effect": p.effect,
                     "doc": p.doc})
    return rows


def _fmt(v) -> str:
    if v is None:
        return "unset"
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def shown(row: Dict[str, Any]) -> str:
    """A row's value as the being should read it: an unset value says what it falls back to."""
    if row["value"] is None and row.get("unset_means"):
        return f"unset ({row['unset_means']})"
    return _fmt(row["value"])


def render_table(instance, with_docs: bool = True) -> str:
    lines = []
    for r in table(instance):
        rng = "" if r["kind"] == "bool" else f" [{_fmt(r['lo'])}..{_fmt(r['hi'])}]"
        who = "yours to set" if r["yours_to_set"] else "set by your seat"
        line = f"- {r['name']} = {shown(r)} ({r['source']}; {who}{rng})"
        if r["note"]:
            line += f" — {r['note']}"
        if with_docs:
            line += f"\n    {r['doc']}"
        lines.append(line)
    return "\n".join(lines)


def tune(instance, name: Optional[str] = None, raw: Any = None, why: str = "",
         now: Optional[float] = None) -> Tuple[bool, str]:
    """The `tune` verb's body. No name: the table. A name and a value: set it (or reset it with
    "default"). Returns (ok, text the being reads). Refuses, never clamps, at write time: the
    being asked for a specific value and is owed a no with the bounds, not a different yes."""
    if not name:
        return True, ("Your parameters (value, where it came from, whether it is yours to set, "
                      "bounds). Set one with tune(name, value, why); 'default' resets it.\n"
                      + render_table(instance))
    name = str(name).strip()
    if name not in PARAMS:
        return False, f"no parameter {name!r}. Yours: {', '.join(PARAMS)}"
    p = PARAMS[name]
    cfg = _instance_config(instance)
    if not self_tunable(instance, name, cfg):
        return False, (f"{name} is set by your seat, not by you. If it should be yours, say why "
                       f"to your seat; the lock is theirs to lift.")
    why = str(why or "").strip()
    if not why:
        return False, "say why (the 'why' argument): the change is recorded with its reason"
    if raw is None or str(raw).strip() == "":
        return False, f"give a value for {name}, or 'default' to reset it"
    before = resolve(instance, name)
    tuned, err = _read_tuned(instance)
    if err:
        return False, f"cannot change it: {err}. Fix or remove {TUNED_FILE} first"
    if str(raw).strip().lower() in RESET_WORDS:
        tuned.pop(name, None)
        new = None
    else:
        try:
            new = _coerce(p, raw)
        except ValueError as e:
            return False, str(e)
        lo, hi = bounds(instance, name, cfg)
        if p.kind != "bool":
            if lo is not None and new < lo or hi is not None and new > hi:
                return False, f"{name} must be within [{_fmt(lo)}..{_fmt(hi)}] for you; {_fmt(new)} is not"
        tuned[name] = {"value": new, "at": _iso(now), "why": why[:500]}
    path = Path(instance) / TUNED_FILE
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(tuned, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)
    after = resolve(instance, name)
    try:
        with open(Path(instance) / TUNE_LOG, "a") as f:
            f.write(json.dumps({"at": _iso(now), "name": name, "from": before["value"],
                                "from_source": before["source"], "to": after["value"],
                                "to_source": after["source"], "why": why[:500]}) + "\n")
    except Exception:
        pass                                            # the change happened; the log is the extra
    return True, (f"{name}: {_fmt(before['value'])} ({before['source']}) -> {_fmt(after['value'])} "
                  f"({after['source']}). Takes effect: {p.effect}."
                  + (f" Note: {after['note']}" if after["note"] else ""))


def _iso(now: Optional[float]) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() if now is None else now))


# -- the window, as a sense ------------------------------------------------------------------
# Shaped like proprioception.py's readings (#379): every value is {"value", "source"} or
# {"gap": why}, so it can sit in that snapshot as "window" when #379 lands, and until then
# renders on its own. Read from the beat records, i.e. what the SERVER counted, never estimated.

WINDOW_LOOKBACK = 10


def _ok(v, source: str) -> Dict:
    return {"value": v, "source": source}


def _gap(why: str) -> Dict:
    return {"gap": why}


def _recent_beats(instance, n: int) -> List[dict]:
    path = Path(instance) / "heartbeats.jsonl"
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 4_000_000))
            tail = f.read().decode("utf-8", errors="replace").splitlines()
    except Exception:
        return []
    out = []
    for line in reversed(tail):
        try:
            r = json.loads(line)
        except Exception:
            continue
        if isinstance(r, dict) and (r.get("explore") or {}).get("generates"):
            out.append(r)
            if len(out) >= n:
                break
    return out


def _causes(gens) -> Dict[str, int]:
    """Retried generates by what the first attempt hit (being_tool_loop.retry_cause_of).
    A record from before 2026-10-07 has no cause: counted as "unrecorded", never guessed."""
    out: Dict[str, int] = {}
    for g in gens:
        if g.get("retried"):
            k = g.get("retry_cause") or "unrecorded"
            out[k] = out.get(k, 0) + 1
    return out


def sense_window(instance, lookback: int = WINDOW_LOOKBACK) -> Dict:
    beats = _recent_beats(instance, lookback)
    src = "heartbeats.jsonl explore.generates (ollama prompt_eval_count)"
    if not beats:
        return {"num_ctx": _gap("no beat with measured generates yet"), "last": _gap("no beat yet")}
    last = beats[0]
    ctx = last.get("num_ctx") or (last.get("config") or {}).get("num_ctx_resolved")
    gens = last["explore"]["generates"]
    prompts = [g.get("prompt_eval_count") or 0 for g in gens]
    seed = prompts[0] if prompts and prompts[0] else None
    peak = max(prompts) if prompts else None
    ex = last.get("explore") or {}
    out = {
        "num_ctx": _ok(ctx, "beat record num_ctx") if ctx else _gap("not recorded"),
        "last": {
            "at": last.get("ts"),
            "seed_tokens": _ok(seed, src) if seed else _gap("first generate not counted"),
            "peak_tokens": _ok(peak, src) if peak else _gap("no counted generate"),
            "generates": len(gens),
            "retried": sum(1 for g in gens if g.get("retried")),
            "retry_causes": _causes(gens),
            "floor_reached": bool(ex.get("handoff")) or any(
                (i or {}).get("nudge") == "floor" for i in (ex.get("interjected") or [])),
            "handed_off": bool(ex.get("handoff")),
            "compacted": ex.get("compacted"),
        },
    }
    if ctx:
        peaks = [max([g.get("prompt_eval_count") or 0 for g in b["explore"]["generates"]] or [0])
                 for b in beats]
        retried = sum(sum(1 for g in b["explore"]["generates"] if g.get("retried")) for b in beats)
        total = sum(len(b["explore"]["generates"]) for b in beats)
        causes: Dict[str, int] = {}
        for b in beats:
            for k, v in _causes(b["explore"]["generates"]).items():
                causes[k] = causes.get(k, 0) + v
        out["recent"] = {"beats": len(beats),
                         "peak_over_90pct": sum(1 for x in peaks if x >= 0.9 * ctx),
                         "retried": retried, "generates": total, "retry_causes": causes}
    return out


_CAUSE_WORDS = {"window": "the window wall", "output_budget": "the output budget for one reply",
                "stopped_thinking": "thinking that stopped with no reply",
                "cut_call": "a tool call cut mid-arguments", "length": "a length cut (window size unknown)", "unrecorded": "cause not recorded"}


def _render_causes(causes: Dict[str, int]) -> str:
    if not causes:
        return ""
    order = ["window", "output_budget", "length", "stopped_thinking", "cut_call", "unrecorded"]
    parts = [f"{causes[k]} {_CAUSE_WORDS.get(k, k)}" for k in order if causes.get(k)]
    parts += [f"{v} {k}" for k, v in causes.items() if k not in order]
    return " (" + ", ".join(parts) + ")"


def render_window(sense: Dict) -> str:
    ctx = (sense.get("num_ctx") or {}).get("value")
    last = sense.get("last") or {}
    if not ctx or "gap" in last:
        why = (sense.get("num_ctx") or {}).get("gap") or last.get("gap") or "not measured"
        return f"Your window: {why}."
    def pct(d):
        v = (d or {}).get("value")
        return f"{v:,} ({100 * v // ctx}%)" if v else "not counted"
    s = (f"Your window: {ctx:,} tokens. Last beat: you started at {pct(last.get('seed_tokens'))} "
         f"before your first act, peaked at {pct(last.get('peak_tokens'))}; "
         f"{last.get('retried', 0)} of {last.get('generates', 0)} generates retried"
         f"{_render_causes(last.get('retry_causes') or {})}")
    if last.get("handed_off"):
        s += "; it reached the floor and the harness handed off"
    elif last.get("floor_reached"):
        s += "; it reached the floor"
    rec = sense.get("recent")
    if rec and rec["beats"] > 1:
        s += (f". Last {rec['beats']} beats: {rec['peak_over_90pct']} peaked above 90%, "
              f"{rec['retried']} of {rec['generates']} generates retried"
              f"{_render_causes(rec.get('retry_causes') or {})}")
    return s + "."
