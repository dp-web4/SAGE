"""
Tests for the raising runner's num_ctx floor.

Ollama's per-request num_ctx default is 4096 whatever the model declares, and it
applies that window SILENTLY: an over-long prompt is truncated to fit and the
request still returns HTTP 200. Measured on Legion 2026-09-06 with qwen3.5:0.8b,
one ~6000-token prompt, num_predict=6000, think off:

    options                 prompt_eval   eval   done_reason
    (no num_ctx)            4095          1      length
    num_ctx=8192            5519          194    stop

One token of output, reported as success. `governed_turn.build_client` has sent a
resolved num_ctx since 2026-09-05; `ollama_raising_session.load_model` did not,
which is the raising-side half of the same defect — and the shape the sprout
raising log recorded from S632 on (mid-sentence truncation, bracketed
placeholders, empty completions). num_predict cannot exceed what the window has
left, so raising the think budget alone could never fix it.

8192 is a FLOOR the model config may raise per size, never lower: qwen38-heretic
:q3km declares its Modelfile's 16384 and must keep it.

Run:
    cd ~/ai-workspace/SAGE
    python3 -m sage.raising.tests.test_num_ctx_floor
"""

import importlib.util
import re
import sys
from pathlib import Path

_RAISING = Path(__file__).resolve().parent.parent
_SAGE = _RAISING.parent
_REPO = _SAGE.parent

# Load model_capabilities by path: sage/irp/__init__ pulls in numpy, which the
# raising hosts do not all carry, and this module needs none of it.
_spec = importlib.util.spec_from_file_location(
    "_model_capabilities", _SAGE / "irp" / "adapters" / "model_capabilities.py")
_mc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mc)
load_capabilities = _mc.load_capabilities

_RUNNER = _RAISING / "scripts" / "ollama_raising_session.py"


def _result(label: str, ok: bool, detail: str = "") -> bool:
    mark = "PASS" if ok else "FAIL"
    line = f"  [{mark}] {label}"
    if detail:
        line += f" — {detail}"
    print(line)
    return ok


# ─── the floor resolves ───

def test_floor_holds_when_config_declares_nothing():
    # sprout's 2b declares num_predict_think but no num_ctx, so it takes the floor.
    got = load_capabilities("qwen3.8-distill:2b").resolve_num_ctx("qwen3.8-distill:2b", 8192)
    return _result("qwen3.8-distill:2b takes the 8192 floor", got == 8192, f"num_ctx={got}")


def test_config_may_raise_the_floor():
    got = load_capabilities("qwen38-heretic:q3km").resolve_num_ctx("qwen38-heretic:q3km", 8192)
    return _result("q3km raises the floor to its Modelfile 16384", got == 16384, f"num_ctx={got}")


def test_config_may_never_lower_the_floor():
    # A declared window SMALLER than the caller's floor must not win: lowering it is
    # the defect this whole file is about, arriving from the other direction.
    caps = load_capabilities("qwen38-heretic:q3km")
    got = caps.resolve_num_ctx("qwen38-heretic:q3km", 32768)
    return _result("a 32768 floor is not lowered to 16384", got == 32768, f"num_ctx={got}")


def test_unknown_model_still_gets_the_floor():
    got = load_capabilities("no-such-model:1b").resolve_num_ctx("no-such-model:1b", 8192)
    return _result("unknown model falls back to the floor", got == 8192, f"num_ctx={got}")


def test_the_window_is_never_smaller_than_the_think_budget_is_useful_in():
    # Not a tautology: it is the invariant the measurement above violated. A size that
    # declares a think budget must have a window big enough for a real prompt plus a
    # meaningful part of it, or num_predict is decorative.
    bad = []
    for name in ("qwen3.8-distill:2b", "qwen38-heretic:q3km"):
        caps = load_capabilities(name)
        ctx = caps.resolve_num_ctx(name, 8192)
        think_budget = caps.resolve_num_predict(name, True, 200)
        if think_budget and think_budget > 0 and ctx <= think_budget:
            bad.append(f"{name}: num_ctx={ctx} <= num_predict_think={think_budget}")
    return _result("declared window exceeds declared think budget", not bad, "; ".join(bad))


# ─── the runner actually sends it ───

def test_runner_passes_a_resolved_num_ctx_to_ollama():
    # Source-level guard, deliberately: load_model() cannot be imported on a host
    # without numpy, and the regression being guarded is precisely that this key
    # goes missing from the OllamaIRP config again.
    src = _RUNNER.read_text()
    m = re.search(r"self\.llm = OllamaIRP\(\{(.*?)\}\)", src, re.S)
    if not m:
        return _result("runner passes num_ctx to OllamaIRP", False, "OllamaIRP({...}) block not found")
    block = m.group(1)
    has_key = "'num_ctx'" in block or '"num_ctx"' in block
    resolves = "resolve_num_ctx" in src
    return _result("runner passes a resolved num_ctx to OllamaIRP",
                   has_key and resolves,
                   f"num_ctx in config={has_key}, resolve_num_ctx called={resolves}")


def test_runner_does_not_hardcode_a_window_below_the_floor():
    src = _RUNNER.read_text()
    bad = [n for n in re.findall(r"num_ctx\s*=\s*(\d+)", src) if int(n) < 8192]
    return _result("runner declares no window below the 8192 floor", not bad, ",".join(bad))


if __name__ == "__main__":
    print("num_ctx floor — raising runner\n")
    tests = [
        test_floor_holds_when_config_declares_nothing,
        test_config_may_raise_the_floor,
        test_config_may_never_lower_the_floor,
        test_unknown_model_still_gets_the_floor,
        test_the_window_is_never_smaller_than_the_think_budget_is_useful_in,
        test_runner_passes_a_resolved_num_ctx_to_ollama,
        test_runner_does_not_hardcode_a_window_below_the_floor,
    ]
    results = [t() for t in tests]
    print()
    passed = sum(results)
    print(f"{passed}/{len(results)} passed")
    sys.exit(0 if passed == len(results) else 1)
