"""Brief verb descriptions, opt-in per instance, with `describe` for the full text (dp, 2026-10-03: "yes").

Measured on legion-being: the seed compaction cannot touch grew 15.7k -> 17.1k tokens in a week, much
of it verb schemas, leaving ~1.3k tokens of the 18.4k compaction target for a beat's work; long beats
retried ~50% of generates at the window. Brief mode keeps each available verb's FIRST SENTENCE and
every parameter; the rest is one `describe` away.
"""
import inspect
import json

from sage.gateway import toolset
from sage.gateway.being_gate_client import _TOOL_SCHEMAS, BeingIntent, ResultEnvelope
from sage.gateway.being_tool_loop import run_tool_turn


def test_off_by_default_and_only_brief_turns_it_on():
    assert toolset.tool_descriptions_mode({}) == "full"
    assert toolset.tool_descriptions_mode(None) == "full"
    assert toolset.tool_descriptions_mode({"tool_descriptions": "brief"}) == "brief"
    assert toolset.tool_descriptions_mode({"tool_descriptions": "short"}) == "full"
    assert toolset.specs() == toolset.specs(brief=False), "the default rendering is unchanged"


def test_brief_keeps_every_verb_parameter_and_enum_and_is_smaller():
    full = {t["function"]["name"]: t["function"] for t in toolset.specs()}
    brief = {t["function"]["name"]: t["function"] for t in toolset.specs(brief=True)}
    assert set(full) == set(brief), "every verb is still offered"
    for name in full:
        assert brief[name]["parameters"] == full[name]["parameters"], name
        assert len(brief[name]["description"]) <= max(len(full[name]["description"]),
                                                       toolset.BRIEF_DESC_CHARS + 60), name
    assert len(json.dumps(list(brief.values()))) < 0.8 * len(json.dumps(list(full.values())))


def test_a_cut_description_says_where_the_rest_is_and_a_short_one_stays_whole():
    long_name = max(_TOOL_SCHEMAS, key=lambda n: len(_TOOL_SCHEMAS[n][0]))
    b = toolset.brief_description(long_name, _TOOL_SCHEMAS[long_name][0])
    assert b.endswith(f"(Full text: describe {long_name}.)") and len(b) < len(_TOOL_SCHEMAS[long_name][0])
    assert toolset.brief_description("x", "One sentence only.") == "One sentence only."


def test_an_unavailable_verb_keeps_its_reason_in_brief_mode():
    u = {"gaze": "this machine's body has no movable eyes (measured)"}
    g = {t["function"]["name"]: t["function"] for t in toolset.specs(u, brief=True)}["gaze"]
    assert "CANNOT WORK" in g["description"] and "no movable eyes" in g["description"]


def test_describe_returns_the_full_text_and_is_never_dispatched():
    calls = []

    class C:
        def gate(self, intent):
            calls.append(intent.effector)
            from types import SimpleNamespace
            return SimpleNamespace(decision="allow", rule="", reason="ok", command=None)

        def dispatch(self, intent, v):
            calls.append(("dispatch", intent.effector))
            return ResultEnvelope(ok=True, result="r", witness_id="w")
    seq = iter([{"content": "", "intents": [BeingIntent("describe", {"verb": "memory_edit"})]},
                {"content": "done", "intents": []}])
    r = run_tool_turn(C(), lambda convo: next(seq), [{"role": "user", "content": "beat"}], max_steps=4)
    body = r.trace[0][1].result
    assert body.startswith("memory_edit: " + _TOOL_SCHEMAS["memory_edit"][0][:40])
    assert all(f"  {k}" in body for k in _TOOL_SCHEMAS["memory_edit"][1])
    assert calls == [], "describe touches nothing: no gate, no dispatch"
    assert "no verb called" in toolset.full_text("nonsense")


def test_the_heartbeat_offers_and_measures_the_same_specs():
    from sage.gateway import heartbeat as hb
    src = inspect.getsource(hb.main)
    assert '_toolset.specs(_unavail, _enums, brief=_tool_desc_mode == "brief")' in src
    assert '_schema_chars_for(_explore_tools, _unavail, _enums, brief=_tool_desc_mode == "brief")' in src
    assert '"tool_descriptions": _tool_desc_mode' in src, "the beat record says which mode ran"


def test_brief_text_says_which_verbs_touch_the_worktree_and_which_keep_nothing():
    """legion-being, 2026-10-05 (dp chat seq 148): "I confused which tools touch the worktree vs
    my home (the run sandbox changes a copy and keeps nothing; patch_apply is the worktree
    tool) -- a one-line reminder in the tool descriptions would save a beat." It spent most of a
    beat patching a sandbox copy. The brief line is all it sees, so the fact lives there."""
    from sage.gateway import toolset
    brief = {s["function"]["name"]: s["function"]["description"].split(" (Full text")[0]
             for s in toolset.specs(brief=True)}
    assert "COPIES" in brief["run"] and "nothing it changes is kept" in brief["run"]
    assert "worktree" in brief["patch_apply"]
    for verb in ("memory_edit", "memory_write"):
        assert "home" in brief[verb] and "worktree" in brief[verb] and "absolute path" in brief[verb]
    for verb in ("run", "patch_apply", "memory_edit", "memory_write"):
        assert len(brief[verb]) <= toolset.BRIEF_DESC_CHARS
