"""Hermetic: thinking is a declared per-model policy (model_configs), resolved by the
adapter, deferred to by the governed harness; the heartbeat writes operator decisions
back into the escalation notes that filed them."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.irp.adapters.model_capabilities import load_capabilities  # noqa: E402
from sage.gateway.governed_turn import is_reasoning_model  # noqa: E402
from sage.gateway.heartbeat import note_resolutions, decided_requests  # noqa: E402


def test_think_policy_is_per_size_not_per_caller():
    assert load_capabilities("qwen3.5:0.8b").resolve_think("qwen3.5:0.8b") is False   # 2026-03 decision, declared
    assert load_capabilities("qwen3.5:27b").resolve_think("qwen3.5:27b") is True
    assert load_capabilities("qwen3.8-distill:2b").resolve_think("qwen3.8-distill:2b") is True
    assert load_capabilities("qwen38-heretic:q3km").resolve_think("qwen38-heretic:q3km") is True
    assert load_capabilities("gemma3:12b").resolve_think("gemma3:12b") is False


def test_think_budget_declared_for_reasoning_models():
    c = load_capabilities("qwen3.8-distill:2b")
    assert c.resolve_num_predict("qwen3.8-distill:2b", True, 3000) == 6000
    assert c.resolve_num_predict("qwen3.8-distill:2b", False, 3000) == 1024


def test_num_ctx_is_a_floor_the_config_can_raise_not_lower():
    from sage.gateway.governed_turn import resolve_num_ctx
    c = load_capabilities("qwen38-heretic:q3km")
    assert c.resolve_num_ctx("qwen38-heretic:q3km", 8192) == 16384      # Modelfile value, declared per size
    assert c.resolve_num_ctx("qwen38-heretic:q3km", 32768) == 32768     # a caller asking for more keeps it
    assert c.resolve_num_ctx("qwen3.8-distill:2b", 8192) == 8192        # 2B declares nothing: floor unchanged
    assert resolve_num_ctx("qwen38-heretic:q3km", 8192) == 16384
    assert resolve_num_ctx("no-such-model:1b", 8192) == 8192


def test_num_ctx_fallback_to_the_floor_is_loud():
    """A config failure must not be a silent 8192: that is beat 46 with no record of why."""
    import io
    import contextlib
    import sage.irp.adapters.model_capabilities as mc
    from sage.gateway.governed_turn import resolve_num_ctx
    keep = mc.load_capabilities

    def broken(model):
        raise ValueError("bad json")
    mc.load_capabilities = broken
    try:
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            assert resolve_num_ctx("qwen38-heretic:q3km", 8192) == 8192
    finally:
        mc.load_capabilities = keep
    assert "num_ctx" in err.getvalue() and "8192" in err.getvalue() and "bad json" in err.getvalue()
    assert resolve_num_ctx("qwen38-heretic:q3km", 8192) == 16384   # restored


def test_heretic_first_attempt_budget_is_the_room_the_window_has():
    """q3km: 16384 window, a real heartbeat prompt of ~6700 tokens, 8000 to think in
    (Sprout as policy owner, c77f0d58d). The 2B is per-size independent and unchanged."""
    c = load_capabilities("qwen38-heretic:q3km")
    assert c.resolve_num_predict("qwen38-heretic:q3km", True, 3000) == 8000
    assert c.resolve_num_predict("qwen38-heretic:q3km", False, 3000) == 1024
    assert load_capabilities("qwen3.8-distill:2b").resolve_num_predict("qwen3.8-distill:2b", True, 3000) == 6000


def test_ollama_irp_sends_the_config_budget_unless_overridden():
    """With thinking on the caller's max_response_tokens is NOT what goes over the wire:
    the config's num_predict_think is. So (a) a retry that only raises max_response_tokens
    changes nothing, and (b) a record of max_response_tokens misreports the budget
    (Sprout 18:51Z 2026-09-05: recorded 3000, sent 6000). The override is the one caller
    value that wins, for the once-retry."""
    from sage.irp.plugins.ollama_irp import OllamaIRP
    keep = OllamaIRP._check_ollama
    OllamaIRP._check_ollama = lambda self: False      # hermetic: no server
    try:
        llm = OllamaIRP({"model_name": "qwen38-heretic:q3km", "think": True,
                         "max_response_tokens": 3000, "num_ctx": 16384})
    finally:
        OllamaIRP._check_ollama = keep
    assert llm.resolve_num_predict() == 8000
    llm.max_response_tokens = 12000
    assert llm.resolve_num_predict() == 8000           # the caller value is ignored: the old retry was a re-roll
    llm.num_predict_override = 9535
    assert llm.resolve_num_predict() == 9535           # the override is the retry's lever
    llm.num_predict_override = None
    assert llm.resolve_num_predict() == 8000


def test_governed_harness_defers_to_the_config():
    assert is_reasoning_model("qwen3.8-distill:2b") and is_reasoning_model("qwen38-heretic:q3km")
    assert not is_reasoning_model("qwen3.5:0.8b")


def test_note_resolutions_appends_once_to_the_filing_note():
    d = Path(tempfile.mkdtemp(prefix="esc-"))
    (d / "a.md").write_text("routing: {\"scope_request\": {\"request_id\": \"scope-abc\"}}\n")
    (d / "b.md").write_text("unrelated scope-zzz\n")
    w = note_resolutions(d, [("scope-abc", "/x", "granted")], "2026-09-05 17:00 UTC", "heartbeat-1")
    assert w == ["a.md"]
    body = (d / "a.md").read_text()
    assert "## Resolved" in body and "granted" in body and "scope-abc" in body
    assert "Resolved" not in (d / "b.md").read_text()
    assert note_resolutions(d, [("scope-abc", "/x", "granted")], "later", "heartbeat-2") == []  # idempotent
    assert note_resolutions(d, [], "x", "y") == [] and note_resolutions(d / "nope", [("i", "p", "denied")], "x", "y") == []


def test_refusals_are_decisions_too_and_the_ruler_is_named():
    # hestia emits `refused` (ScopeRequest::status) and its arbitrate door says `denied`; the
    # first cut filtered on ("granted", "denied") and silently dropped every operator refusal
    # (legion-claude, hestia #952 review). Both spellings settle; pending/expired do not.
    reqs = [("scope-a", "/x", "granted"), ("scope-b", "/y", "refused"), ("scope-c", "/z", "denied"),
            ("scope-d", "/w", "pending"), ("scope-e", "/v", "expired")]
    assert [i for i, _, _ in decided_requests(reqs)] == ["scope-a", "scope-b", "scope-c"]
    d = Path(tempfile.mkdtemp(prefix="esc-"))
    (d / "r.md").write_text("routing: {\"scope_request\": {\"request_id\": \"scope-b\"}}\n")
    (d / "g.md").write_text("routing: {\"scope_request\": {\"request_id\": \"scope-a\"}}\n")
    w = note_resolutions(d, decided_requests(reqs), "2026-09-05 22:00 UTC", "heartbeat-3",
                         decided_by={"scope-a": "delegate:claude-code", "scope-b": "operator"})
    assert sorted(w) == ["g.md", "r.md"]
    assert "**refused** by operator" in (d / "r.md").read_text()
    assert "**granted** by delegate:claude-code" in (d / "g.md").read_text()   # never "by the operator" for a #952 ruling


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); n += 1; print(f"PASS {name}")
    print(f"\n{n} passed")
