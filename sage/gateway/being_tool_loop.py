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
import re
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
    duplicates: List[dict] = field(default_factory=list)   # identical calls answered without re-executing: {step, effector}
    generates: List[dict] = field(default_factory=list)    # per generate, from Ollama's reply: {done_reason, prompt_eval_count, eval_count, retried}
    compacted: List[dict] = field(default_factory=list)    # per step where old tool results were elided: {step, elisions, chars}

    @property
    def acted(self) -> bool:
        return any(env.ok for _, env in self.trace)

    @property
    def refused(self) -> List[Tuple[BeingIntent, ResultEnvelope]]:
        return [(i, e) for i, e in self.trace if e.refused]


def run_tool_turn(client: BeingGateClient, generate: GenerateFn,
                  messages: List[Dict[str, Any]], max_steps: int = 3) -> ToolTurnResult:
    """Run one being turn that may reach for tools, gated end to end.

    Loop invariant: the being never sees a fabricated result — each tool message is a
    real ResultEnvelope (executed, refused, or honestly `pending` until F1a exists).
    """
    convo = list(messages)
    trace: List[Tuple[BeingIntent, ResultEnvelope]] = []
    done_ok: set = set()
    duplicates: List[dict] = []

    for step in range(max_steps):
        out = generate(convo)
        content = out.get("content") or ""
        intents = out.get("intents") or []

        if not intents:                                    # a spoken turn — the being is done
            res = ToolTurnResult(reply=content, trace=trace, steps=step)
            res.duplicates = duplicates
            return res

        convo.append({"role": "assistant", "content": content, "intents": intents})
        for intent in intents:
            # A call identical to one this turn already executed is not a second act: the model
            # re-emits its last calls after reading their results (beat 149, 2026-09-08: the
            # journal and todo each written twice, same bytes, one step apart). Answered
            # without executing, and named in the record as an intervention.
            key = (intent.effector, json.dumps(dict(intent.args or {}), sort_keys=True, default=str))
            if key in done_ok:
                env = ResultEnvelope(ok=True, result="(already done this beat: identical call, not repeated)",
                                     note="duplicate")
                duplicates.append({"step": step, "effector": intent.effector})
                trace.append((intent, env))
                convo.append({"role": "tool", "effector": intent.effector, "content": env.to_tool_message()})
                continue
            env = client.dispatch(intent)                  # gate + F1a dispatch + consume
            if env.ok:
                done_ok.add(key)
            trace.append((intent, env))
            convo.append({"role": "tool", "effector": intent.effector,
                          "content": env.to_tool_message()})

    # Cap reached with tools still pending: force one final spoken close — we take its
    # words even if it wants more tools, so the being always ends its turn in language.
    out = generate(convo)
    res = ToolTurnResult(reply=out.get("content") or "", trace=trace,
                         steps=max_steps, capped=True)
    res.duplicates = duplicates
    return res


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

def compact_convo(msgs: List[Dict[str, Any]], llm, reserve: int = _ANSWER_RESERVE,
                  measured=None) -> tuple:
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
    size = lambda ms: sum(len(m.get("content") or "") for m in ms)
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
        out[i]["content"] = (kept_head +
                             f"\n[… {elided_n} characters elided from the middle to leave room "
                             f"for your answer. The head above names what this was. If you need "
                             f"part of it, read a NARROW range rather than the file again — a "
                             f"full re-read costs more room than this elision freed. If you need "
                             f"what you concluded from it, that is in your scratch …]\n"
                             + kept_tail)
        elided.append({"index": i, "chars": elided_n, "kept": COMPACT_KEEP_CHARS})
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
            out[i]["content"] = (body[:h] +
                                 f"\n[… {elided_n} characters elided from the middle of your NEWEST "
                                 f"result to leave room for your answer; read it again in a smaller "
                                 f"range if you need the middle …]\n" + body[-(keep - h):])
            elided.append({"index": i, "chars": elided_n, "kept": keep, "newest": True})
    return out, elided


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
    """Turn thinking off for one retry, and put it back.

    A RETRY AFTER A THINK-ONLY GENERATE MUST NOT BE ANOTHER THINK-ONLY GENERATE. Measured
    2026-09-14 on legion-being: a first attempt hit the wall at prompt_eval 24,194 of a
    24,576 window with done_reason=length, everything in `thinking` and content empty. The
    retry, given more room, then spent its ENTIRE 8,000-token budget in `thinking` as well
    and again said nothing. Two generates, roughly 8,400 tokens, no tool call, and the beat
    carried on as if the being had chosen silence.

    More room was the wrong lever, because room was not what ran out — the model never
    started answering. A nudge in the prompt is text the model may ignore, and did. `think`
    is a flag it cannot ignore in the same way. It can still re-open a block on its own
    (measured 5/10 turns, 2026-09-03), so this improves the odds rather than guaranteeing an
    answer; leaving thinking ON for the retry guarantees nothing at all, which is exactly
    what the measurement above shows.

    Restores the previous value, including when the attribute was absent, so a retry cannot
    leave every later turn of the beat silently un-thinking."""
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


def run_ollama_tool_turn(client: BeingGateClient, llm, seed_messages: List[Dict[str, Any]],
                         max_steps: int = 2, tools: Optional[List[dict]] = None,
                         on_generate: Optional[Callable[[dict], None]] = None) -> ToolTurnResult:
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
    # (prompt_eval_count, chars at that prompt) from the last generate the server counted.
    # Compaction is anchored on this, so only the DELTA rides a chars-per-token estimate.
    measured = None

    def generate(convo: List[Dict[str, Any]]) -> Dict[str, Any]:
        nonlocal measured
        # Flatten the loop's convo (carries extra keys) to chat messages. An assistant
        # turn that emitted intents MUST keep them as tool_calls: Qwen's chat template
        # raises on a tool message that follows an assistant message without tool_calls,
        # and Ollama surfaces that as HTTP 500 (measured: every post-tool turn 500'd).
        msgs = []
        for m in convo:
            out = {"role": m.get("role", "user"), "content": m.get("content", "")}
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
        msgs, _elided = compact_convo(msgs, llm, measured=measured)
        if _elided:
            compacted.append({"step": len(thoughts), "elisions": len(_elided),
                              "chars": sum(e["chars"] for e in _elided)})
        retried = 0
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
            # DID IT RUN OUT OF ROOM, OR NEVER START ANSWERING? Those want opposite
            # remedies and the old code gave both the same one. A generate that produced a
            # think block and no content did not need more room — it needed to stop
            # deliberating, and handing it a bigger budget bought a longer silence.
            thought_only = (bool(str(msg.get("thinking") or "").strip())
                            and not str(msg.get("content") or "").strip())
            if raw.get("done_reason") == "length" and (hasattr(llm, "max_response_tokens")
                                                       or hasattr(llm, "num_predict_override")):
                if thought_only:
                    # NOT the same prompt again: the retry has to change something the model
                    # can see. Measured 2026-09-08, five beats running, an identical prompt
                    # produced an identical cut-off deliberation — a deterministic loop,
                    # twice a beat. This says what happened and asks for one act.
                    msgs.append({"role": "user", "content": (
                        f"[harness] Your previous attempt spent its whole budget deliberating "
                        f"({raw.get('eval_count')} tokens) and the window cut it before any "
                        f"tool call. The window will not grow. Act now: one tool call. The "
                        f"deliberation belongs in journal.md, after the act.")})
                from contextlib import ExitStack
                with ExitStack() as _stack:
                    budget = _stack.enter_context(_retry_room(llm, _retry_budget(llm, raw)))
                    unthought = bool(thought_only and _stack.enter_context(_no_think(llm)))
                    print(f"[tool-loop] retrying once with num_predict={budget}"
                          f"{' , thinking OFF and a nudge' if unthought else ''} "
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
            # re-measure from the list AS SENT: any nudge appended above is inside this count
            measured = (int(raw["prompt_eval_count"]),
                        sum(len(m.get("content") or "") for m in msgs))
        entry = {"done_reason": raw.get("done_reason"), "prompt_eval_count": raw.get("prompt_eval_count"),
                 "eval_count": raw.get("eval_count"), "retried": retried, "num_predict": sent}
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
        return {"content": content, "intents": parse_tool_calls(calls)}

    result = run_tool_turn(client, generate, seed_messages, max_steps=max_steps)
    result.thinking = thoughts
    result.salvaged = salvaged
    result.generates = generates
    # The compaction log belongs to the function that OWNS it. run_tool_turn does not
    # define `compacted` — attaching it there is a NameError no test would catch, which is
    # exactly what my first attempt did. Copied here so the intervention is observable in
    # the beat record (GPT review of #82: a list nobody returns is not an instrument).
    result.compacted = list(compacted)

    return result
