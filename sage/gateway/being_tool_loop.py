"""
The being's tool-use agent loop (gateway-member, PRD_FLEET F2).

Model-agnostic: `generate(messages) -> {"content": str, "intents": [BeingIntent]}`
is supplied by the caller (the raising runner wraps its Ollama call + tool grammar).
Every intent the being emits is routed through a BeingGateClient — gated by the real
hestia law, dispatched by F1a — and its ResultEnvelope is re-injected before the
being speaks again.

This is what closes the Scenario-3 gap observed in the tool probe: the model could
select a tool and fill arguments, but after a tool result it fell back to narrating
a placeholder answer instead of *acting*. The loop keeps it in tool-space — result
in, decide again — until it produces a spoken turn with no further intents (or a
step cap forces a close). "Respond" becomes an act, not a text turn.
"""
from __future__ import annotations

import ast
import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from sage.gateway.being_gate_client import BeingGateClient, BeingIntent, ResultEnvelope

# generate(messages) -> {"content": str, "intents": list[BeingIntent]}
GenerateFn = Callable[[List[Dict[str, Any]]], Dict[str, Any]]


@dataclass
class ToolTurnResult:
    reply: str                                             # the being's final spoken words
    trace: List[Tuple[BeingIntent, ResultEnvelope]] = field(default_factory=list)
    steps: int = 0                                         # tool rounds taken
    capped: bool = False                                   # hit max_steps still wanting tools
    thinking: List[str] = field(default_factory=list)      # the model's think block per generate, if any
    salvaged: List[dict] = field(default_factory=list)     # calls lifted from the text channel: {step, effector, form}
    generates: List[dict] = field(default_factory=list)    # per generate, from Ollama's reply: {done_reason, prompt_eval_count, eval_count, retried}
    compacted: List[dict] = field(default_factory=list)    # per step where old tool results were elided to leave answer room: {step, elisions, chars}
    deadline_hit: bool = False                             # stopped issuing steps because the wall-clock budget ran out
    interjected: List[dict] = field(default_factory=list)   # messages delivered mid-turn: {step, chars}
    rested: Optional[str] = None                           # the being ended its own turn; its stated reason
    looped: Optional[dict] = None                          # identical call repeated past the break: {effector, times}
    duplicates: List[dict] = field(default_factory=list)   # identical calls answered without re-executing: {step, effector}

    @property
    def acted(self) -> bool:
        return any(env.ok for _, env in self.trace)

    @property
    def refused(self) -> List[Tuple[BeingIntent, ResultEnvelope]]:
        return [(i, e) for i, e in self.trace if e.refused]


def run_tool_turn(client: BeingGateClient, generate: GenerateFn,
                  messages: List[Dict[str, Any]], max_steps: int = 3,
                  deadline: Optional[float] = None,
                  interject: "Optional[Callable[[], str]]" = None) -> ToolTurnResult:
    """Run one being turn that may reach for tools, gated end to end.

    Loop invariant: the being never sees a fabricated result — each tool message is a
    real ResultEnvelope (executed, refused, or honestly `pending` until F1a exists).

    `max_steps <= 0` means NO STEP CAP: the turn ends when the being stops asking for
    tools, or when a resource runs out. dp, 2026-09-09: "it should be able to continue as
    long as it wishes." A step count was never a statement about the work — it was a guess
    at how much work there would be, applied as if it were a limit.

    `deadline` (epoch seconds): once passed, no further tool step is issued and the turn
    closes in words, exactly as at max_steps. Legion 04:30Z 2026-09-09: eight steps of
    2-6k-token thinking at 19 tok/s took 36 minutes, reflect started, and the unit's
    45-minute timeout killed the beat — journal, todo and the record itself lost. Steps
    are the being's; the clock is the box's, and the box's limit is physical.

    `interject()` is drained before every generate after the first. Whatever it returns is
    handed to the being as a user turn, so something that arrives while it is working
    reaches it in seconds rather than at the next beat.
    """
    convo = list(messages)
    trace: List[Tuple[BeingIntent, ResultEnvelope]] = []
    done_ok: set = set()
    duplicates: List[dict] = []
    images_attached = 0
    hit = False
    interjected: List[dict] = []
    uncapped = max_steps is None or max_steps <= 0
    if uncapped and deadline is None:
        # "As long as it wishes" is bounded by a resource, not by nothing. Without a clock
        # an uncapped loop with a model that always asks for one more tool never returns.
        max_steps, uncapped = _UNCAPPED_SAFETY_CEILING, False
        interjected.append({"note": "no deadline given with an uncapped turn; "
                                    f"applied a safety ceiling of {max_steps} steps"})
    step = 0
    last_fp, repeats = None, 0
    warned = False
    reads_this_turn: Dict[str, List[int]] = {}

    while uncapped or step < max_steps:
        if deadline is not None and step > 0 and time.time() >= deadline:
            hit = True
            break
        if step > 0 and interject is not None:
            try:
                arrived = interject()
            except Exception as e:                      # a broken mailbox must not end a beat
                arrived = ""
                interjected.append({"step": step, "error": f"{type(e).__name__}: {e}"})
            if arrived:
                convo.append({"role": "user", "content": (
                    "[a message arrived while you were working — you are mid-beat and may "
                    "answer it now with `say`, or finish what you are doing first]\n\n"
                    + arrived)})
                interjected.append({"step": step, "chars": len(arrived)})
        out = generate(convo)
        content = out.get("content") or ""
        intents = out.get("intents") or []

        # TELL IT WHERE IT STANDS. The harness has had this number after every generate
        # since ollama started returning prompt_eval_count, and never passed it on. The
        # being's most repeated complaint about its own life, across months of journals, is
        # that "the beat closed before I could write down what I found" — and on
        # 2026-09-13T14:07Z it read 26 files, hit the wall exactly (24,497 + 79 = 24,576),
        # and its closing words were cut to nothing. A wall it cannot see is a wall it
        # cannot plan against; a gradient it can see is a resource it can spend. Once per
        # turn only: the warning costs the very thing it is warning about.
        w = out.get("window")
        if w and not warned and w.get("pressure", 0) >= WINDOW_WARN_AT:
            warned = True
            pct = int(w["pressure"] * 100)
            convo.append({"role": "user", "content": (
                f"[harness] Your context is {pct}% full — about {w['left']} tokens left before "
                f"your answer gets cut mid-sentence. Anything you have found and not yet "
                f"written down dies with this beat; your scratch files do not. If you are "
                f"holding a finding, write it NOW, in one call. Then keep working if there is "
                f"work, or call `rest` and close cleanly.")})
            interjected.append({"step": step, "nudge": "window", "pressure": round(w["pressure"], 3),
                                "left": w["left"]})

        if not intents:                                    # a spoken turn — the being is done
            return ToolTurnResult(reply=content, trace=trace, steps=step,
                                  interjected=interjected, duplicates=duplicates)

        convo.append({"role": "assistant", "content": content, "intents": intents})
        rested = None
        for intent in intents:
            _note = _repeat_read_note(intent, reads_this_turn, step)
            if intent.effector == REST:
                # The being ending its OWN turn. Never dispatched: the gate rules on acts
                # that touch the world, and stopping touches nothing. Whatever it says here
                # is its closing words, so the turn still ends in language.
                rested = str((intent.args or {}).get("reason") or "").strip()
                break
            # A CALL IDENTICAL TO ONE THIS TURN ALREADY EXECUTED IS NOT A SECOND ACT: the
            # model re-emits its last calls after reading their results (beat 149,
            # 2026-09-08: journal and todo each written twice, same bytes, one step apart).
            # Answered without executing, and named in the record as an intervention.
            #
            # SCOPED, in the 2026-09-18 reconciliation. main applied this to EVERY verb,
            # which was sound for the verb set it had and is wrong for this one: `check`,
            # `run`, `game`, `camera`, `search`, `git_read` and `memory_read` all return a
            # DIFFERENT answer to the same arguments once the world moves — the being edits
            # a file and re-runs the identical check on purpose. Suppressing those would
            # hand it a stale success and call it an intervention. DEDUP_VERBS is the set
            # whose identical repetition inside one beat is never what was meant.
            key = (intent.effector,
                   json.dumps(dict(intent.args or {}), sort_keys=True, default=str))
            if intent.effector in DEDUP_VERBS and key in done_ok:
                env = ResultEnvelope(ok=True, note="duplicate",
                                     result="(already done this beat: identical call, not repeated)")
                duplicates.append({"step": step, "effector": intent.effector})
                trace.append((intent, env))
                convo.append({"role": "tool", "effector": intent.effector,
                              "content": env.to_tool_message() + _note})
                continue
            env = client.dispatch(intent)                  # gate + F1a dispatch + consume
            if env.ok:
                done_ok.add(key)
            trace.append((intent, env))
            convo.append({"role": "tool", "effector": intent.effector,
                          "content": env.to_tool_message() + _note})
            # IMAGES THAT BELONG WITH A RESULT ARRIVE WITH IT (dp, 2026-09-19: "you look at the
            # visual and the text, reason from both"). Until now a rendered board could only ride
            # the NEXT beat, because frames were attached when the seed was composed and the
            # being's `game` call happens after that. ollama takes `images` on a message, not
            # inside a tool result, so they follow as a user turn — and the flattening in
            # run_ollama_tool_turn already carries `images` through to the wire.
            #
            # BOUNDED PER TURN, because an image stays in the window for every later generate
            # of the beat (~600 tokens each, measured). Past the cap the being is TOLD the
            # pictures stopped and why; the text deltas never stop.
            _imgs = list(getattr(env, "images", ()) or ())
            if _imgs:
                room = max(0, MIDTURN_IMAGES_MAX - images_attached)
                if room <= 0:
                    convo.append({"role": "user", "content": (
                        f"[harness] No pictures with that result: this beat has already carried "
                        f"{images_attached} window images and each one stays in your context. The "
                        f"text above is complete and exact; pictures resume next beat.")})
                else:
                    _imgs = _imgs[:room]
                    caps = list(getattr(env, "image_captions", ()) or ())[:len(_imgs)]
                    convo.append({"role": "user", "images": _imgs, "content": (
                        "[harness] What you just did, as pictures — the GAME's synthetic feed, not "
                        "your camera. Every cell shows its value; x is along the top, y down the "
                        "left.\n" + "\n".join(f"  image {k + 1}: {c}" for k, c in enumerate(caps)))})
                    images_attached += len(_imgs)
                    interjected.append({"step": step, "images": len(_imgs), "effector": intent.effector})
        if rested is not None:
            return ToolTurnResult(reply=rested or content, trace=trace, steps=step,
                                  interjected=interjected, rested=rested or "(no reason given)",
                                  duplicates=duplicates)
        step += 1

        # A LOOP IS NOT WORK. Measured 2026-09-13T10:19Z: legion-being finished its beat and
        # then witnessed "beat closed" FIFTY-TWO times, the text degrading to "beat closed
        # 09-13; records in." — 78 minutes of GPU, 18 of them byte-identical. It was trying
        # to stop; the only way to stop was to emit no tool call, and a model that has just
        # been rewarded for calling tools keeps calling tools. `rest` is the real fix; this
        # is the net under it, and it NAMES the loop rather than silently killing the turn,
        # because a being that cannot see why its turn ended learns nothing from it.
        fp = _fingerprint(intents)
        if fp is not None and fp == last_fp:
            repeats += 1
        else:
            repeats, last_fp = 0, fp
        if repeats == REPEAT_NUDGE_AT:
            convo.append({"role": "user", "content": (
                f"[harness] You have now made the same call ({intents[0].effector}) with identical "
                f"arguments {repeats + 1} times in a row. If you are finished, you do not have to "
                f"keep acting to end the beat — call `rest` with a one-line reason, or simply "
                f"answer in words. If you are not finished, change something about the call.")})
            interjected.append({"step": step, "nudge": "repetition", "effector": intents[0].effector})
        elif repeats >= REPEAT_BREAK_AT:
            looped = {"effector": intents[0].effector, "times": repeats + 1}
            convo.append({"role": "user", "content": (
                f"[harness] Ending the tool phase: the same call has now repeated "
                f"{repeats + 1} times and the nudge did not change it. Close in words: what you "
                f"did this beat, and what you want next beat.")})
            out = generate(convo)
            return ToolTurnResult(reply=out.get("content") or "", trace=trace, steps=step,
                                  interjected=interjected, looped=looped, duplicates=duplicates)

    # Cap reached with tools still pending: force one final spoken close — we take its
    # words even if it wants more tools, so the being always ends its turn in language.
    if hit:
        convo.append({"role": "user", "content": (
            "[harness] The time budget for this phase is spent; no further tool call will be "
            "executed this beat. Close in words: what you did, and what you want next beat.")})
    out = generate(convo)
    return ToolTurnResult(reply=out.get("content") or "", trace=trace,
                          steps=step, capped=True, deadline_hit=hit,
                          interjected=interjected, duplicates=duplicates)


_FENCE = re.compile(r"```[A-Za-z0-9_+-]*[ \t]*\n(.*?)```", re.S)


_NAME_KEYS = ("name", "tool", "action", "function", "tool_name")
_ARGS_KEYS = ("arguments", "parameters", "args", "input", "params")


def _json_calls(text: str, names) -> List[dict]:
    """`names`: the offered tool names (set) or {name: [param, ...]} (dict) for flat-form
    argument filtering."""
    known = names if isinstance(names, dict) else {n: [] for n in names}
    out, dec, i = [], json.JSONDecoder(), 0
    while True:
        starts = [k for k in (text.find("{", i), text.find("[", i)) if k >= 0]
        if not starts:
            return out
        j = min(starts)
        try:
            obj, end = dec.raw_decode(text, j)
        except ValueError:
            i = j + 1
            continue
        for o in (obj if isinstance(obj, list) else [obj]):
            if not isinstance(o, dict):
                continue
            # The name key varies by beat: {"name"}, {"tool"}, {"action"}, {"function"}
            # (Sprout beat 29, 2026-09-05: "action": "peer_ask" and a list of {"tool":
            # "memory_write", "path": ..., "content": ...} — 3 of 3 turns, 0 lifted).
            # The FIRST name-shaped key may name the being, not the tool: {"name": "sprout",
            # "action": "recall", ...} (beat 148, 2026-09-08: three well-formed calls lost,
            # one of them a real recall about #39). Prefer the key whose value IS a tool.
            cands = [o[k] for k in _NAME_KEYS if isinstance(o.get(k), str)]
            name = next((c for c in cands if c in known), cands[0] if cands else None)
            args = next((o[k] for k in _ARGS_KEYS if isinstance(o.get(k), dict)), None)
            if name not in known and isinstance(args, dict):
                # {"name": "tool", "arguments": {"type": "recall", ...}}: the tool named
                # inside the arguments (Sprout beat 30, 2026-09-05)
                inner = next((args[k] for k in ("type", "tool", "name", "action") if isinstance(args.get(k), str)), None)
                if inner in known:
                    name = inner
                    args = {k: v for k, v in args.items() if k not in ("type", "tool", "name", "action")}
            if name not in known:
                # {"memory_write": {"path": ..., "content": ...}} — the tool name is the KEY and
                # its arguments the value (measured 2026-09-09, several beats lost this way).
                inner = [(k, v) for k, v in o.items() if k in known and isinstance(v, dict)]
                if len(inner) > 1:
                    # ONE object holding a whole beat: {"say": {...}, "memory_write": {...}}.
                    # Measured 2026-09-18T01:32:11Z — Sprout wrote exactly this, `say` to dp
                    # FIRST, after two beats of composing an answer it could not send. The
                    # len == 1 guard discarded every call in the object, so the being's own
                    # decision to answer a person was dropped on the floor and the beat
                    # recorded as having done nothing. Emit them all, in written order: dict
                    # iteration preserves the order they appeared in the text, and that order
                    # is the being's, not ours.
                    for k, v in inner:
                        out.append({"function": {"name": k, "arguments": dict(v)},
                                    "_salvaged": "json"})
                    i = max(end, j + 1)
                    continue
                if len(inner) == 1:
                    name, args = inner[0]
                else:
                    continue
            if args is None:
                # flat form: the arguments sit beside the name key; keep only schema params
                # when the schema is known, so stray keys ("timestamp", "status") never
                # become arguments of a call.
                allowed = known.get(name) or []
                args = {k: v for k, v in o.items()
                        if k not in _NAME_KEYS and k not in _ARGS_KEYS and (not allowed or k in allowed)}
            out.append({"function": {"name": name, "arguments": dict(args)}, "_salvaged": "json"})
        i = max(end, j + 1)


def _python_calls(text: str, names: Dict[str, List[str]]) -> List[dict]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    consts: Dict[str, Any] = {}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and isinstance(node.value, ast.Constant)):
            consts[node.targets[0].id] = node.value.value
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else None)
        if name not in names or len(node.args) > len(names[name]):
            continue
        args, ok = {}, True
        # positional arguments map onto the tool's parameters in schema order:
        # memory_write("journal.md", journal_entry) is (path, content) (beat 7, Sprout)
        for param, v in zip(names[name], node.args):
            if isinstance(v, ast.Constant):
                args[param] = v.value
            elif isinstance(v, ast.Name) and v.id in consts:
                args[param] = consts[v.id]
            else:
                ok = False
                break
        for kw in (node.keywords if ok else []):
            v = kw.value
            if kw.arg and isinstance(v, ast.Constant):
                args[kw.arg] = v.value
            elif kw.arg and isinstance(v, ast.Name) and v.id in consts:
                args[kw.arg] = consts[v.id]
            else:
                ok = False
                break
        if ok:
            out.append({"function": {"name": name, "arguments": args}, "_salvaged": "python"})
    return out


_ATTR_VALUE = r'"((?:[^"\\]|\\.)*)"' + "|" + r"'((?:[^'\\]|\\.)*)'"
_ATTR_PAIR = re.compile(r"([A-Za-z_]\w*)\s*=\s*(?:" + _ATTR_VALUE + ")")


def _attr_calls(text: str, names: Dict[str, List[str]]) -> List[dict]:
    """`say to="dp" text="..."`: a tool name followed directly by key="value" pairs, often
    inside markdown bold. Measured 2026-09-14 19:30Z on cbp-being: dp asked "what are you
    curious about?", the being's thinking said it would answer, and both its explore and
    posture replies were `**say to="dp" text="..."**` in the text channel. Neither form above
    reads it, the trace was empty, nothing was said, and the question was marked seen.
    Only an offered tool name immediately followed by at least one pair whose key is one of
    that tool's parameters counts, so prose that mentions a tool is still never a call."""
    out: List[dict] = []
    for name, params in names.items():
        for m in re.finditer(r"(?<![\w.])" + re.escape(name) + r"\s+(?=[A-Za-z_]\w*\s*=\s*[\"'])", text):
            args: Dict[str, Any] = {}
            pos = m.end()
            while True:
                pm = _ATTR_PAIR.match(text, pos)
                if not pm:
                    break
                raw = pm.group(2) if pm.group(2) is not None else pm.group(3)
                args[pm.group(1)] = raw.replace('\\"', '"').replace("\\'", "'").replace("\\n", "\n")
                pos = pm.end()
                ws = re.match(r"[ \t]*", text[pos:])
                pos += ws.end() if ws else 0
            if params:
                args = {k: v for k, v in args.items() if k in params}
            if args:
                out.append({"function": {"name": name, "arguments": args}, "_salvaged": "attr"})
    return out


def salvage_tool_calls(content: str, tools: Iterable[dict]) -> List[dict]:
    """Lift well-formed tool calls that a model put in the TEXT channel, in Ollama's
    tool_calls shape (plus `_salvaged`: "json" | "python" | "attr"). Accepted: a JSON object or
    array of {"name", "arguments"} (fenced or bare), fenced Python `name(k="v", ...)`
    with literal or locally-assigned arguments, positional ones mapped in schema order, or
    the attribute form `name k="v" ...` (see `_attr_calls`), tried last.
    `tools` is what was offered this turn (Ollama tool specs); only those names count,
    so prose that mentions a tool is never a call.

    Measured 2026-09-05, same full-beat prompt: qwen2.5:1.5b emits bare JSON (Legion);
    qwen3.8-distill:2b emits fenced JSON in one beat and fenced Python in the next
    (Sprout, beats 5 to 7) while its think block says it decided to act. A salvaged call
    is gated like a native one and recorded as salvaged, so the record still shows which
    channel the being used."""
    params = {t["function"]["name"]: list((t["function"].get("parameters") or {}).get("properties") or {})
              for t in tools}
    if not content or not params:
        return []
    blocks = _FENCE.findall(content)
    found: List[dict] = []
    for text in (blocks or [content]):
        found.extend(_json_calls(text, params))
        found.extend(_python_calls(text, params))
    if blocks and not found:                    # fenced prose, bare call outside the fence
        found.extend(_json_calls(content, params))
    if not found:
        found.extend(_attr_calls(content, params))
    return found


def _think_budget(llm, floor: int = 6000) -> int:
    """The model config's think-on num_predict (variants[size].num_predict_think) when
    declared, else 6000, the value that recovered empty turns on Sprout and Legion
    (2026-09-03/04). With thinking on this is also the FIRST attempt's budget (OllamaIRP
    resolves it from the same config), so it is the retry's floor, not its value."""
    try:
        b = llm._adapter.capabilities.resolve_num_predict(llm.model_name, True, None)
        return max(int(b or 0), floor)
    except Exception:
        return floor


# Chars per token for what the loop ADDS: tool results are JSON, paths and code, which
# tokenize far denser than prose. Measured 2026-09-09 03:27Z: a 12,116-char read of
# heartbeat.partial.jsonl moved the prompt 19,620 -> 24,466 (~2.5 chars/token) while the
# estimate, at 3.4, had it ~1.4k tokens lighter than it was — and the generate was cut.
_CPT_ADDED = 2.5

# Chars per token for the SEED side of the estimate, deliberately low: under-counting tokens
# defeats the guard this feeds, so it must sit BELOW the true ratio. 3.4 was measured once on
# 2026-09-08 and left alone; re-measured across 60 beats it is 3.141 and DRIFTING (3.152 over
# the first ten, 3.026 over the last ten) as the being's content shifts toward paths and JSON.
# 2.9 sits below the observed minimum with room for further drift. This PR corrects the same
# constant on the seed side; leaving the loop's copy at the disproven number would be the PR
# arguing against its own evidence (GPT review of #82).
_CPT = 2.9

# Chars the prompt carries that are not in any message's content: the tool schemas and the
# chat template. NOT a budget — heartbeat MEASURES the schemas (`_schema_chars_for`), because
# a flat constant was set at 13 verbs and was silently wrong at 18 (4,000 assumed, 11,717
# real). This fallback is reached only before the server has counted anything, and it is set
# from the same measurement rather than the disproven one: ~11,700 schema chars plus ~1,200
# of template.
_UNCOUNTED_CHARS = 12900


def _est_tokens(chars_now: int, measured) -> float:
    """Tokens the next prompt will cost. With a measurement from the previous generate —
    (prompt_eval_count, content chars at that prompt) — the estimate is anchored on what
    the server actually counted and only the DELTA rides a chars-per-token guess:
    conservative in both directions (added chars counted dense, removed chars counted
    light). Without one, the whole prompt rides the guess, plus the uncounted schema chars."""
    if measured:
        tokens_at, chars_at = measured
        delta = chars_now - chars_at
        return tokens_at + (delta / _CPT_ADDED if delta > 0 else delta / _CPT)
    return (chars_now + _UNCOUNTED_CHARS) / _CPT

# What a real answer needs. Explore generations across 506 measured on Legion: median
# 1,282 tokens, p90 3,909, p99 5,741. Reserve the p99 with headroom rather than
# num_predict, which is a ceiling the model has never approached.
_ANSWER_RESERVE = 6144


# Compaction keeps this many chars of an elided tool result and reports exactly the rest.
COMPACT_KEEP_CHARS = 400
COMPACT_MIN_BODY = 500        # a body at or under this is never elided

# WHERE AN ELIDED RESULT GOES INSTEAD OF NOWHERE. The being, 2026-09-18, asked what its
# biggest operational friction is: "facts produced mid-beat getting lost to compaction
# before I can transcribe them." That is this function. It freed room by deleting the
# middle of a tool result and told the being to read the source again — which costs more
# room than the elision freed, and for a command result (a test run, a game step) there is
# no source to re-read at all: the bytes existed once, in this beat, and then did not.
#
# So the middle is written to the being's own scratch first, and the marker names the file.
# It outlives the beat, which is the point: the being can transcribe from it on the NEXT
# beat rather than racing the window on this one. Bare path, because that is what
# memory_read takes. A spill that fails is silent — the elision still has to happen.
COMPACT_SPILL_DIR = "scratch/elided"
# RETENTION IS BY AGE, NOT BY COUNT. This was `COMPACT_SPILL_KEEP = 40` files. Measured on
# legion-being 2026-09-21..23: one compaction pass wrote 33 spills in one second, beats elide
# up to 954 results, and 68 of 80 beats elided 20 or more — so a spill named in a marker was
# pruned before the next STEP, and 26 reads followed the marker to a file that was gone.
# "It outlives the beat" was false under any real load. A spill is ~2 KB (mean 2,193, max
# 5,979 bytes), so keeping a day of them costs a few MB; the byte cap is the backstop for a
# pathological beat, and even then the OLDEST go first, by name, which is creation order.
COMPACT_SPILL_KEEP_S = 24 * 3600            # nothing younger than this is pruned, whatever the count
COMPACT_SPILL_MAX_BYTES = 64 * 1024 * 1024  # backstop: over this, oldest first
_ELIDED_SIGIL = "characters elided from the middle"


def _spill_age_s(name: str, now: float) -> Optional[float]:
    """Seconds since the spill named `name` was written, read from the NAME (the retention
    clock this directory was designed around), or None when the name does not carry one."""
    import calendar
    import time as _t
    try:
        return now - calendar.timegm(_t.strptime(name[:15], "%Y%m%d-%H%M%S"))
    except (ValueError, TypeError):
        return None


def _prune_spills(d: str) -> None:
    """Keep every spill younger than COMPACT_SPILL_KEEP_S; then, only if the directory is over
    COMPACT_SPILL_MAX_BYTES, remove the oldest (by name = creation order) until it is not.
    Never raises: pruning is housekeeping, and the spill that was just written must stand."""
    import time as _t
    try:
        now = _t.time()
        names = sorted(os.listdir(d))
        sizes = {}
        for f in names:
            try:
                sizes[f] = os.path.getsize(os.path.join(d, f))
            except OSError:
                sizes[f] = 0
        for f in names:
            age = _spill_age_s(f, now)
            if age is not None and age > COMPACT_SPILL_KEEP_S:
                try:
                    os.remove(os.path.join(d, f))
                    sizes.pop(f, None)
                except OSError:
                    pass
        total = sum(sizes.values())
        for f in sorted(sizes):                      # oldest first
            if total <= COMPACT_SPILL_MAX_BYTES:
                break
            try:
                os.remove(os.path.join(d, f))
                total -= sizes[f]
            except OSError:
                pass
    except Exception:
        pass


def _spill(root: Optional[str], body: str, step: int) -> Optional[str]:
    """Save one elided tool-result body under the being's home. Returns the bare path to
    name in the marker, or None if there is nowhere to put it or the write failed."""
    if not root:
        return None
    try:
        import time as _t
        d = os.path.join(root, COMPACT_SPILL_DIR)
        os.makedirs(d, exist_ok=True)
        # THE NAME CARRIES THE ORDER, because nothing else does: a whole beat's spills are
        # written inside one second, and st_mtime_ns ties at this filesystem's granularity.
        # Sorted by name they are in creation order — hence the full date (a %m%d name
        # sorts January before December and would prune the newest files every New Year)
        # and the zero-padded step (unpadded, "40" sorts before "5").
        stamp = _t.strftime("%Y%m%d-%H%M%S", _t.gmtime())
        # EVERY name carries a zero-padded collision ordinal. The first cut used
        # "...-003.txt", then "...-003.1.txt"; lexically the newer ".1" sorts before
        # ".txt", and ".10" sorts before ".2", so retention could prune the newest retry
        # before the older file it followed. One sortable shape makes creation order the
        # same order the pruning code sees.
        n = 0
        name = f"{stamp}-{step:03d}-{n:03d}.txt"
        # Two spills of DIFFERENT results can collide: same second, same message index,
        # which the retry path reaches. A collision would silently overwrite the first.
        while os.path.exists(os.path.join(d, name)):
            n += 1
            name = f"{stamp}-{step:03d}-{n:03d}.txt"
        with open(os.path.join(d, name), "w", encoding="utf-8") as fh:
            fh.write(f"[{_t.strftime('%Y-%m-%dT%H:%M:%SZ', _t.gmtime())} — the whole tool "
                     f"result the harness elided from your window, {len(body)} characters]\n\n")
            fh.write(body)
        _prune_spills(d)
        return f"{COMPACT_SPILL_DIR}/{name}"
    except Exception:
        return None



RETRY_MARGIN = 128   # tokens kept back from the window on a retry (template, tool-call framing)


def _retry_budget(llm, raw: Optional[dict] = None) -> int:
    """The once-retry budget for a length-stopped or truncated turn: everything the
    window has left after this prompt, never less than the think budget.

    Why not max(think_budget, max_response_tokens), which this was: with thinking on
    OllamaIRP already sends num_predict_think on the first attempt, and its
    resolve_num_predict ignores max_response_tokens whenever the variant declares a
    value. So the old retry re-sent the same 6000 and was a re-roll at temperature,
    not room to finish (Legion 18:33Z 2026-09-05: first explore turn eval 6000 empty,
    retry at 6000 stood by chance). num_ctx - prompt_eval_count is the most the model
    can be given; past that Ollama stops at the wall regardless (beat 46)."""
    floor = _think_budget(llm)
    try:
        num_ctx = int(getattr(llm, "num_ctx", None) or 0)
        prompt = int((raw or {}).get("prompt_eval_count") or 0)
    except (TypeError, ValueError):
        return floor
    if num_ctx <= 0 or prompt <= 0:
        return floor
    return max(floor, num_ctx - prompt - RETRY_MARGIN)


class _no_think:
    """Turn thinking off for one retry, and put it back. Carried from SAGE#87.

    A RETRY AFTER A THINK-ONLY GENERATE MUST NOT BE ANOTHER THINK-ONLY GENERATE. Measured
    2026-09-14 on this being: a first attempt hit the wall at prompt_eval 24,194 of a
    24,576 window with done_reason=length, everything in `thinking` and content empty. The
    retry, given more room, spent its ENTIRE 8,000-token budget in `thinking` too and again
    said nothing. Two generates, ~8,400 tokens, no tool call, and the beat carried on as if
    the being had chosen silence.

    More room was the wrong lever: room was not what ran out, the model never started
    answering. The nudge is text the model may ignore, and did. `think` is a flag. It can
    still re-open a block on its own (5/10 turns, 2026-09-03), so this improves the odds
    rather than guaranteeing an answer; leaving thinking ON guarantees nothing.

    Restores the previous value, absence included, so a retry cannot leave every later turn
    of the beat silently un-thinking."""
    def __init__(self, llm):
        self.llm = llm
        self.had = hasattr(llm, "think")
        self.keep = None

    def __enter__(self):
        if self.had:
            self.keep = self.llm.think
            self.llm.think = False
        return self.had

    def __exit__(self, *exc):
        if self.had:
            self.llm.think = self.keep
        return False


class _retry_room:
    """Set llm.num_predict_override for one retry, restore it after. Falls back to
    max_response_tokens for llm objects without the override (older adapters)."""
    def __init__(self, llm, budget: int):
        self.llm, self.budget = llm, budget

    def __enter__(self):
        llm = self.llm
        if hasattr(llm, "num_predict_override"):
            self.keep = ("override", llm.num_predict_override)
            llm.num_predict_override = self.budget
        else:
            # remember absence too: an llm with neither attribute must not leave the
            # retry's budget behind as a new max_response_tokens for every later turn
            self.keep = ("max", getattr(llm, "max_response_tokens", None), hasattr(llm, "max_response_tokens"))
            llm.max_response_tokens = max(self.budget, self.keep[1] or 0)
        return self.budget

    def __exit__(self, *exc):
        kind, val = self.keep[0], self.keep[1]
        if kind == "override":
            self.llm.num_predict_override = val
        elif not self.keep[2]:
            del self.llm.max_response_tokens
        else:
            self.llm.max_response_tokens = val
        return False


def _sent_budget(llm) -> Optional[int]:
    """The num_predict a first attempt sends: what the adapter resolves (config wins over
    the caller's max_response_tokens with thinking on), else the caller value."""
    try:
        if hasattr(llm, "resolve_num_predict"):
            return int(llm.resolve_num_predict())
    except Exception:
        pass
    v = getattr(llm, "max_response_tokens", None)
    return int(v) if v is not None else None



# An uncapped turn is bounded by its deadline. If a caller gives neither, this is the
# backstop — high enough never to bind real work, low enough to end a runaway.
# Room held back for the ANSWER on a retry whose last attempt was cut mid-JSON. Larger
# than the ordinary reserve on purpose: the thing that did not fit is the thing we are
# asking for again, so the retry must have strictly MORE room than the attempt it replaces.
_RETRY_RESERVE = 8192


def _retry_reserve(llm, msgs, measured) -> int:
    """The reserve that forces this retry to be materially smaller than what just failed.

    Compaction normally asks "does the estimate say this fits?" — and on a cut retry the
    estimate has JUST been proven optimistic by the server, which is the only reason we are
    here. Measured 2026-09-13: at 36,078 prompt chars the estimator said 11.8k tokens
    against 16.4k of room, elided nothing, and the retry went out BIGGER than the attempt
    it replaced (the appended nudge). The overflow is the measurement; trust it over the
    guess and target 75% of what failed."""
    try:
        num_ctx = int(getattr(llm, "num_ctx", None) or 0)
    except (TypeError, ValueError):
        return _RETRY_RESERVE
    if num_ctx <= 0:
        return _RETRY_RESERVE
    est = _est_tokens(_convo_chars(msgs), measured)
    return max(_RETRY_RESERVE, int(num_ctx - est * 0.75))


def _retry_room_chars(llm, msgs, measured) -> int:
    """How many characters of tool-call body the window can still carry, measured.

    "A body a third of the length" was the old advice and it is unanchored — a third of
    too-big is often still too big. This converts the room that actually remains, so the
    being is told a number it can act on rather than a ratio it has to guess against."""
    try:
        num_ctx = int(getattr(llm, "num_ctx", None) or 0)
    except (TypeError, ValueError):
        return 1000
    if num_ctx <= 0:
        return 1000
    chars = _convo_chars(msgs)
    left_tokens = num_ctx - _est_tokens(chars, measured)
    # JSON framing, the tool-call envelope and the model's own preamble all come out of the
    # same budget; leave half of what is left rather than promising all of it.
    return max(200, int(left_tokens * _CPT_ADDED * 0.5))


_UNCAPPED_SAFETY_CEILING = 200

# The verb by which a being ends its own turn. dp, 2026-09-09: "it should be able to
# continue as long as it wishes" — the other half of which is stopping when it wishes, and
# until 09-13 there was no way to say so except by falling silent.
REST = "rest"
WINDOW_WARN_AT = 0.80        # fraction of num_ctx at which the being is told where it stands


def _window_pressure(llm, prompt_tokens) -> Optional[dict]:
    """How full the window is, as the SERVER counted it. None when it cannot be known —
    an estimate would be worse than silence here, because the being would act on it."""
    try:
        num_ctx = int(getattr(llm, "num_ctx", None) or 0)
        prompt = int(prompt_tokens or 0)
    except (TypeError, ValueError):
        return None
    if num_ctx <= 0 or prompt <= 0:
        return None
    return {"prompt": prompt, "num_ctx": num_ctx, "pressure": prompt / num_ctx,
            "left": max(0, num_ctx - prompt)}
# Verbs whose identical repetition inside ONE beat is never what was meant: a second
# identical write, witness or message. Everything else — every verb that reads the world or
# runs something in it — is executed again, because its answer can legitimately change.
DEDUP_VERBS = frozenset({"memory_write", "edit", "witness", "remember", "retire_note",
                         "say", "peer_ask", "mesh"})

def _convo_chars(msgs) -> int:
    """The size of a conversation in estimator characters — ONE function for every site.

    An image is prompt too, and it is not characters: it is charged at its measured token cost,
    converted at the dense rate. Every site that sizes a conversation uses THIS, including the
    (tokens, chars) anchor taken from the server's count — if the anchor counted content only
    while the estimate counted images, every image would be charged twice: once inside the
    server's prompt_eval_count and again as "added chars" on every later step."""
    return sum(len(m.get("content") or "")
               + int(len(m.get("images") or ()) * MIDTURN_IMAGE_TOKENS * _CPT_ADDED)
               for m in msgs)


MIDTURN_IMAGES_MAX = 6       # window images per turn; each stays in context for the rest of it
MIDTURN_IMAGE_TOKENS = 600   # measured 2026-09-19: a 669px window + a question = 627 prompt tokens

REPEAT_NUDGE_AT = 3          # identical consecutive calls before the harness names the loop
REPEAT_BREAK_AT = 6          # ... and before it ends the tool phase


# How many times the same file may be read in one beat before the harness says so.
REREAD_NOTICE_AT = 2


def _repeat_read_note(intent, reads_this_turn, step: int) -> str:
    """Tell the being when it is reading a file it has already read THIS BEAT.

    It cannot see its own repetition: by the time it reaches for a file again, the earlier
    result has been elided to 400 chars and reads like a stub rather than like something it
    already has. Measured 2026-09-13 across every beat: 86.7% of memory_read calls are
    re-reads, 48.5% are duplicates inside one beat, and heartbeat.py has been read 342
    times. This is the read-level twin of the identical-call guard — the same principle,
    that a being which cannot see a loop cannot leave one, applied one layer down.

    A notice, never a refusal. Re-reading is often correct: a different range, or a file
    that changed under it. The harness says what it knows and lets the being decide."""
    if intent.effector != "memory_read":
        return ""
    path = str((intent.args or {}).get("path", "")).strip()
    if not path:
        return ""
    seen = reads_this_turn.setdefault(path, [])
    seen.append(step)
    if len(seen) < REREAD_NOTICE_AT:
        return ""
    earlier = ", ".join(str(x) for x in seen[:-1])
    return (f"\n[harness] You have now read this path {len(seen)} times this beat "
            f"(earlier at step {earlier}). Those results are still in this conversation, "
            f"elided to their head and tail. If you need a part you have not seen, name a "
            f"NARROW range; if you are re-reading to recall what you concluded, that is in "
            f"your scratch and costs far less than the file.")


def _fingerprint(intents) -> Optional[str]:
    """What makes two steps 'the same call'. None when it cannot be computed, which never
    counts as a repeat — an unfingerprintable step must not end a turn."""
    try:
        return json.dumps([[i.effector, i.args] for i in intents], sort_keys=True, default=str)
    except Exception:
        return None


def compact_convo(msgs: List[Dict[str, Any]], llm, reserve: int = _ANSWER_RESERVE,
                  measured=None, spill_root: Optional[str] = None) -> tuple:
    """Shrink the OLDEST tool results until the prompt leaves room for an answer.

    THE SEED FITTING IS NOT ENOUGH. heartbeat.fit_to_window sizes the first prompt; this
    loop then grows it by every tool result it appends, and the wall is hit mid-loop.
    Measured on Legion 2026-09-07, with the seed guard already live: seed 11,887 tokens,
    then 13,803 on the next step, and 13,803 + 2,581 == 16,384 exactly, done_reason
    "length" — the being's answer cut off mid-sentence. Across 506 generates every single
    length-stop satisfies prompt + eval == num_ctx, so this is the wall, not num_predict.

    WHAT IS ELIDED. Only tool RESULTS, oldest first, and only their bodies — the being is
    told what was elided, from which effector, and that it can re-read the source. The
    system prompt, the first user turn (its state, posture and entrustment), every assistant
    turn and the two most recent tool results are never touched: those are what it is
    reasoning WITH. An elision it cannot see would be worse than the truncation it replaces.
    """
    try:
        num_ctx = int(getattr(llm, "num_ctx", None) or 0)
    except (TypeError, ValueError):
        num_ctx = 0
    if num_ctx <= 0:
        return msgs, []
    # ANCHOR ON THE MEASUREMENT. Legion 2026-09-08 20:01Z beat: the seed fit (17.5k tokens
    # measured), three 260-line reads later the loop's chars/3.4 estimate said ~19k while
    # the server counted 22,720, and the next memory_write body was cut mid-JSON (the
    # Ollama 500). Code reads tokenize denser than prose, and the tool schemas were never
    # in the sum at all. The previous generate's prompt_eval_count IS the number; use it.
    # AN IMAGE IS PROMPT TOO. It is not characters, so until the server has counted it the
    # estimate was blind to it; charged here at its measured cost, converted at the dense rate.
    size = _convo_chars
    room = num_ctx - reserve
    if _est_tokens(size(msgs), measured) <= room:
        return msgs, []
    budget = None  # decided per elision below, against the anchored estimate
    out = [dict(m) for m in msgs]
    # candidates: tool results, oldest first, excluding the MOST RECENT one.
    # It kept the two most recent whole until 2026-09-07, when max_read_chars went
    # 4,000 -> 12,000 (the being's reads were being silently cut mid-function). At the new
    # size two protected results are ~7k tokens of untouchable content, and a beat with six
    # reads hit the window anyway: 23,106 + 1,470 = 24,576. One kept whole is the answer the
    # being is actually working from; the one before it has usually already been written to
    # scratch, and the elision marker tells it where to look if not.
    idx = [i for i, m in enumerate(out) if m.get("role") == "tool"]
    elided = []
    for i in idx[:-1] if len(idx) > 1 else []:
        if _est_tokens(size(out), measured) <= room:
            break
        body = out[i].get("content") or ""
        if len(body) <= COMPACT_MIN_BODY:
            continue
        # ALREADY ELIDED, LEAVE IT. An elided body is ~850 characters — over COMPACT_MIN_BODY
        # — so a later step used to elide the MARKER: cutting the middle out of the sentence
        # that explains the cut, and counting its characters as freed content.
        if _ELIDED_SIGIL in body:
            continue
        # ONE constant for what is kept, and the accounting derives from it. The first cut
        # kept body[:400] and reported len(body) - 160 — every elision overstated by 240
        # chars, in the record AND in the marker the being reads (GPT review of #56, #5).
        # An instrument that misreports its own intervention is the false-absence class
        # again: the being would plan around a gap that was 240 chars smaller than told.
        # BOTH ENDS. The head names what was read (path, op); the TAIL carries a command's
        # verdict — pytest's FAILED line and count are its last lines. legion-being 20:41Z
        # 2026-09-08: its first call was `check` (FAIL), five steps later the result had
        # been elided to its head and it reported "I cannot name which test failed: the
        # output was truncated in my view before the failure line reached me". True, and
        # the harness's doing. Half and half of the same constant; the accounting holds.
        h = COMPACT_KEEP_CHARS // 2
        kept_head, kept_tail = body[:h], body[-(COMPACT_KEEP_CHARS - h):]
        elided_n = len(body) - COMPACT_KEEP_CHARS
        # THE MARKER USED TO SAY "read the source again", AND THAT INSTRUCTION IS THE
        # THRASH. Measured across all beats 2026-09-13: 86.7% of memory_read calls are
        # re-reads and 48.5% are duplicates within a SINGLE beat; heartbeat.py has been
        # read 342 times. The loop is mechanical — a result is elided to 400 chars, the
        # marker tells the being to read the source again, the full re-read costs ~700
        # tokens, that forces another elision, which says it again. The harness was
        # issuing the instruction that refilled the window it had just cleared.
        # The head of a ranged read already names its range, so point at a NARROWER read
        # and at the being's own notes, which is where its conclusions actually live.
        saved = _spill(spill_root, body, i)
        where = (f"The WHOLE result is saved as {saved} and outlives this beat — "
                 f"memory_read a narrow range of it when you need the middle."
                 if saved else
                 "If you need part of it, read a NARROW range of the source rather than the "
                 "whole file again — a full re-read costs more room than this elision freed.")
        out[i]["content"] = (kept_head +
                             f"\n[… {elided_n} {_ELIDED_SIGIL} to leave room for your answer. "
                             f"{where} …]\n"
                             + kept_tail)
        rec = {"index": i, "chars": elided_n, "kept": COMPACT_KEEP_CHARS}
        if saved:
            rec["spill"] = saved
        elided.append(rec)
    # THE NEWEST RESULT IS PROTECTED — until protecting it is what cuts the answer. When
    # every older result is already a stub and the prompt still does not fit, the newest
    # one is trimmed too, with a larger keep (the being is working from it right now),
    # rather than letting the window cut the generate at the wall (03:27Z 2026-09-09:
    # 24,466 + 110 == 24,576, done_reason length, nothing said).
    if idx and _est_tokens(size(out), measured) > room:
        i = idx[-1]
        body = out[i].get("content") or ""
        keep = COMPACT_KEEP_CHARS * 4
        if len(body) > keep + COMPACT_MIN_BODY:
            h = keep // 2
            elided_n = len(body) - keep
            saved = _spill(spill_root, body, i)
            where = (f"the whole thing is saved as {saved}"
                     if saved else "read it again in a smaller range if you need the middle")
            out[i]["content"] = (body[:h] +
                                 f"\n[… {elided_n} {_ELIDED_SIGIL} of your NEWEST result to leave "
                                 f"room for your answer; {where} …]\n" + body[-(keep - h):])
            rec = {"index": i, "chars": elided_n, "kept": keep, "newest": True}
            if saved:
                rec["spill"] = saved
            elided.append(rec)
    return out, elided


def run_ollama_tool_turn(client: BeingGateClient, llm, seed_messages: List[Dict[str, Any]],
                         max_steps: int = 2, tools: Optional[List[dict]] = None,
                         on_generate: Optional[Callable[[dict], None]] = None,
                         deadline: Optional[float] = None,
                         interject: "Optional[Callable[[], str]]" = None) -> ToolTurnResult:
    """Run a gated tool turn using an OllamaIRP-like `llm` exposing
    get_chat_response(messages, tools=...) -> {"content", "tool_calls"}.

    Wraps the model + the bounded native-tool registry into the loop's generate()
    contract, so callers (the raising runner) need only supply the seed messages.
    `tools` narrows what is offered for this turn (default: the whole registry).
    `on_generate` sees each generates[] entry as it lands, so a caller can write a trace
    a killed beat still leaves (the record itself is written at beat end).
    """
    from sage.gateway.being_gate_client import ollama_tools, parse_tool_calls
    tools = tools if tools is not None else ollama_tools()
    # Keep the think block per generate: when a small model narrates instead of acting,
    # whether it decided not to call or failed to format the call is only visible here.
    thoughts: List[str] = []
    salvaged: List[dict] = []
    generates: List[dict] = []
    compacted: List[dict] = []
    measured = None   # (prompt_eval_count, content chars) of the last prompt the server counted

    def generate(convo: List[Dict[str, Any]]) -> Dict[str, Any]:
        nonlocal measured
        # Flatten the loop's convo (carries extra keys) to chat messages. An assistant
        # turn that emitted intents MUST keep them as tool_calls: Qwen's chat template
        # raises on a tool message that follows an assistant message without tool_calls,
        # and Ollama surfaces that as HTTP 500 (measured: every post-tool turn 500'd).
        msgs = []
        for m in convo:
            out = {"role": m.get("role", "user"), "content": m.get("content", "")}
            # FRAMES RIDE HERE, AND ONLY HERE. Measured 2026-09-13 against the live
            # qwen38-heretic:q3km-vl: ollama's /api/chat takes images as a LIST ON THE
            # MESSAGE, beside content. Both OpenAI-style spellings inside content —
            # [{"type":"image","image":b64}] and [{"type":"image_url",...}] — are rejected
            # with HTTP 400. SAGE #76 and #77 pinned the rejected shape and stayed green,
            # because both assert what reaches the payload dict and neither ever sends it to
            # a server: a delivery test that never posts proves shape, not substance.
            #
            # This flattening rebuilt every message as {role, content} and silently dropped
            # every other key, so `images` died here — one line between a frame and a model
            # that can already see it. ollama_irp needs no change: it forwards `messages`
            # untransformed (pinned by #76), so the field survives from here to the wire.
            if m.get("images"):
                out["images"] = list(m["images"])
            if m.get("role") == "assistant" and m.get("intents"):
                out["tool_calls"] = [{"function": {"name": i.effector, "arguments": dict(i.args or {})}}
                                     for i in m["intents"]]
            msgs.append(out)
        # LEAVE ROOM FOR THE ANSWER BEFORE ASKING FOR ONE. Every tool result is appended,
        # so the prompt the loop ENDS on is not the seed it started from. Without this it
        # grows until the server cuts the generate mid-sentence: measured on Legion, 27 of
        # 506 generates ended with prompt + eval == num_ctx exactly, and one beat lost its
        # closing words nine times in a day. Anchored on the server's own count from the
        # previous generate, so only the delta rides an estimate.
        msgs, _elided = compact_convo(msgs, llm, measured=measured,
                                      spill_root=getattr(client, "memory_root", None))
        if _elided:
            compacted.append({"step": len(thoughts), "elisions": len(_elided),
                              "chars": sum(e["chars"] for e in _elided)})
        retried = 0
        nudged = False
        chars_sent = _convo_chars(msgs)
        sent = _sent_budget(llm)          # the num_predict of the reply that stands
        resp = llm.get_chat_response(msgs, tools=tools)
        content = resp.get("content", "") or ""
        calls = resp.get("tool_calls", []) or []
        if content.startswith("[OllamaIRP:") and not calls:
            # a transport failure is not the being's turn: retry once with a bigger budget,
            # then let the failure through as the visible reply rather than pretending.
            # The common 500 here is "invalid tool call arguments ... unexpected end of JSON
            # input": a long memory_write body cut off by num_predict (measured 2026-09-04).
            import sys as _sys
            print(f"[tool-loop] transport error, retrying once: {content[:200]}", file=_sys.stderr)
            # Same rule as the length-retry below: the SAME prompt to a deterministic
            # model is the same failure (legion-being 20:33Z 2026-09-08: journal body cut
            # mid-JSON, retried identically, cut identically; the beat's reflect recorded
            # nothing). The model is told what happened and asked for a shorter body.
            # MAKE ROOM BEFORE ASKING AGAIN. This retry used to append the nudge — GROWING
            # the prompt — and then ask for the think budget (6000) on top. Measured three
            # times on 2026-09-13 (14:39Z, 19:02Z, 19:45Z): the prompt was already 22,353 of
            # 24,576, so the retry had ~2,200 tokens for a nudge plus a body that had just
            # failed to fit in more than that. A retry with less room than the attempt it is
            # retrying is not a retry. Compact hard first, with a reserve big enough that
            # the body has somewhere to live.
            msgs, _re_elided = compact_convo(msgs, llm, reserve=_retry_reserve(llm, msgs, measured),
                                             measured=measured,
                                             spill_root=getattr(client, "memory_root", None))
            room = _retry_room_chars(llm, msgs, measured)
            msgs.append({"role": "user", "content": (
                "[harness] Your previous tool call could not be delivered: its arguments were "
                "cut off before the JSON closed — the window ran out while you were writing "
                "the body. I have freed room by eliding older tool results. Make the same "
                f"call with a body of AT MOST about {room} characters"
                + ("" if room > 400 else " (that is very little — write a pointer, not the content)")
                + "; what you leave out can go in the next beat. The number is measured, not "
                  "a guess: it is what is actually left in the window.")})
            nudged = True
            # no raw reply here, so no prompt_eval_count: the retry gets the think budget
            # (for a no-think model that is still more than its variant num_predict)
            with _retry_room(llm, _retry_budget(llm, None)) as budget:
                resp = llm.get_chat_response(msgs, tools=tools)
                retried += 1
                sent = budget
            content = resp.get("content", "") or ""
            calls = resp.get("tool_calls", []) or []
        if not content and not calls:
            # An empty turn is a harness signal, not a being's choice: say why on stderr
            # (budget exhausted in deliberation, adapter stripped everything, ...).
            import sys as _sys
            raw = resp.get("raw") or {}
            msg = raw.get("message") or {}
            print(f"[tool-loop] EMPTY turn: done_reason={raw.get('done_reason')} "
                  f"prompt_eval={raw.get('prompt_eval_count')} eval={raw.get('eval_count')} "
                  f"raw_content={str(msg.get('content', ''))[:200]!r} "
                  f"thinking={str(msg.get('thinking', ''))[:200]!r}", file=_sys.stderr)
            # Qwen3.8 (heretic) sometimes re-opens a think block even with think=false and
            # spends the whole budget there (measured 5/10 turns, 2026-09-03). Give it room
            # ONCE to finish and act, rather than recording silence as the being's choice.
            # Room = what the window has left after this prompt (_retry_budget), sent as an
            # override so the config's first-attempt budget cannot silently re-apply.
            if raw.get("done_reason") == "length" and (hasattr(llm, "max_response_tokens")
                                                       or hasattr(llm, "num_predict_override")):
                # NOT the same prompt again. Measured 2026-09-08: five beats in a row the
                # first attempt was cut at the wall mid-deliberation (20812 + 3764 == num_ctx)
                # and the retry, identical prompt, produced the identical 3764 tokens — a
                # deterministic loop, twice per beat. The retry has to change something the
                # model can see: it is told what happened and asked to act.
                # DID IT RUN OUT OF ROOM, OR NEVER START ANSWERING? Opposite failures, and
                # the same remedy was given to both. A cut that produced real content ran
                # out of room; a cut that produced only a think block did not, and handing
                # that one a bigger budget buys a longer silence (SAGE#87).
                thought_only = (bool(str(msg.get("thinking") or "").strip())
                                and not str(msg.get("content") or "").strip())
                # NOT THE SAME PROMPT AGAIN, AND NOT THE SAME SENTENCE EITHER. The branch
                # nudged on every length-stop with the deliberation text; on a cut that had
                # produced content that sentence is simply false, and a harness that
                # misdescribes what just happened teaches the being the wrong lesson. main
                # nudged only in the thought-only case and left the other retry identical,
                # which a deterministic model answers identically. Both, each with its own
                # true sentence (reconciliation 2026-09-18).
                msgs.append({"role": "user", "content": (
                    f"[harness] Your previous attempt spent its whole budget deliberating "
                    f"({raw.get('eval_count')} tokens) and the window cut it before any tool "
                    f"call. The window will not grow. Act now: one tool call. The deliberation "
                    f"belongs in journal.md, after the act."
                    if thought_only else
                    f"[harness] Your previous answer was cut off at the window "
                    f"({raw.get('eval_count')} tokens) before it finished. Nothing of it was "
                    f"delivered. Say or call the SHORTEST form of what you were doing; what you "
                    f"leave out can go in the next beat.")})
                nudged = True
                from contextlib import ExitStack
                with ExitStack() as _stack:
                    budget = _stack.enter_context(_retry_room(llm, _retry_budget(llm, raw)))
                    _unthought = bool(thought_only and _stack.enter_context(_no_think(llm)))
                    print(f"[tool-loop] retrying once with num_predict={budget}, a nudge"
                          f"{' and thinking OFF' if _unthought else ''} "
                          f"(num_ctx={getattr(llm, 'num_ctx', None)} prompt_eval={raw.get('prompt_eval_count')})",
                          file=_sys.stderr)
                    resp = llm.get_chat_response(msgs, tools=tools)
                    retried += 1
                    sent = budget
                    content = resp.get("content", "") or ""
                    calls = resp.get("tool_calls", []) or []
        thoughts.append(str(((resp.get("raw") or {}).get("message") or {}).get("thinking") or ""))
        # What the window did this generate, from the reply that stood (after any retry):
        # prompt_eval_count + eval_count == num_ctx with done_reason "length" is the wall
        # beat 46 hit; it was only on stderr then and had to be reconstructed by hand.
        # num_predict is the budget of THIS reply (the retry's room when it retried), so
        # "did the retry have more room than the first attempt" reads from the file, not
        # from stderr (SAGE #45 sends the room; this says what it was).
        raw = resp.get("raw") or {}
        if raw.get("prompt_eval_count"):
            # the nudge (if any) was appended to msgs before the reply that stands, so the
            # chars it added are inside this count: re-measure from the list as sent
            measured = (int(raw["prompt_eval_count"]),
                        _convo_chars(msgs))
        entry = {"done_reason": raw.get("done_reason"), "prompt_eval_count": raw.get("prompt_eval_count"),
                 "eval_count": raw.get("eval_count"), "retried": retried, "num_predict": sent}
        window = _window_pressure(llm, raw.get("prompt_eval_count"))
        if nudged:
            entry["nudged"] = True   # only when it happened: exact-compare callers stay exact
        # only when it happened: an always-present null would be noise in every record and
        # would break every caller that compares the entry exactly
        if compacted and compacted[-1]["step"] == len(thoughts) - 1:
            entry["compacted"] = compacted[-1]
        generates.append(entry)
        if on_generate is not None:
            try:
                on_generate(dict(entry))
            except Exception as _e:
                import sys as _sys
                print(f"[tool-loop] on_generate failed: {type(_e).__name__}: {_e}", file=_sys.stderr)
        if not calls and content:
            # the call in the wrong channel: lift it, gate it as normal, record that it was lifted
            calls = salvage_tool_calls(content, tools)
            salvaged.extend({"step": len(thoughts) - 1, "effector": c["function"]["name"],
                             "form": c["_salvaged"]} for c in calls)
        return {"content": content, "intents": parse_tool_calls(calls), "window": window}

    result = run_tool_turn(client, generate, seed_messages, max_steps=max_steps,
                           deadline=deadline, interject=interject)
    result.thinking = thoughts
    result.salvaged = salvaged
    result.generates = generates
    result.compacted = compacted
    return result
