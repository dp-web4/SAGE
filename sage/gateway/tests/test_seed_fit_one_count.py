"""The seed is fitted on the same count the tool loop's step-1 preflight uses (SAGE #582).

hub-being 2026-10-27/28 (11 h), pub-being 2026-10-27..30 (125 beats), mcnugget-being 2026-11-17 15:40Z:
the heartbeat's part-wise fitter accepted a seed that the loop's whole-list preflight then refused, every
beat, with `interventions: []`. The heartbeat now measures the composed seed with the loop's own function
and trims only when the loop would refuse it. Hermetic: fake renderers and a fake LLM, no model, no gate.
"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import being_tool_loop as btl  # noqa: E402
from sage.gateway.being_tool_loop import (run_ollama_tool_turn, uncounted_chars, preflight_tokens,  # noqa: E402
                                          preflight_refuses, WINDOW_SEND_MARGIN)
from sage.gateway.heartbeat import (fit_seed_to_preflight, CONV_LADDER, FIT_FLOORS,  # noqa: E402
                                    SEED_REFIT_HEADROOM)

CTX = 16384
LINE = CTX - WINDOW_SEND_MARGIN
CPT = 2.9


class _Render:
    """A seed as one user turn: fixed text + conversations (shrinking down the ladder) + recall,
    and the digest only when it rides the seed (posture-first). Counts its renders."""
    def __init__(self, fixed, conv_chars, digest_in_seed=True):
        self.fixed, self.conv, self.digest_in_seed, self.n = fixed, conv_chars, digest_in_seed, 0

    def __call__(self, rung, digest, recall):
        self.n += 1
        conv = self.conv[CONV_LADDER.index(rung)]
        body = "f" * self.fixed + "c" * conv + (recall or "") + ((digest or "") if self.digest_in_seed else "")
        return [{"role": "system", "content": "s"}, {"role": "user", "content": body}], None


def _measure(rendered):
    return (btl._convo_chars(rendered[0])) / CPT


def _fit(render, digest, recall, rung_index=0):
    return fit_seed_to_preflight(render, _measure, num_ctx=CTX, rung_index=rung_index,
                                 digest=digest, recall=recall, cpt=CPT)


CONV = [12000, 9000, 6000, 3000, 1500]


def test_a_seed_the_preflight_accepts_is_left_exactly_as_it_was():
    render = _Render(fixed=20000, conv_chars=CONV)
    rendered, rung, digest, recall, iv = _fit(render, "d" * 5000, "r" * 3000)
    assert iv is None and rung == CONV_LADDER[0]
    assert digest == "d" * 5000 and recall == "r" * 3000
    assert render.n == 1, "measured once, nothing re-rendered"


def test_a_seed_over_the_line_is_trimmed_digest_first_until_the_preflight_would_send_it():
    # 30,000 + 12,000 + 3,000 + 5,000 = 50,000 chars = 17,241 tokens at 2.9: over 16,128
    render = _Render(fixed=30000, conv_chars=CONV)
    assert preflight_refuses(_measure(render(CONV_LADDER[0], "d" * 5000, "r" * 3000)), CTX)
    rendered, rung, digest, recall, iv = _fit(render, "d" * 5000, "r" * 3000)
    est = _measure(rendered)
    assert not preflight_refuses(est, CTX), est
    assert est <= LINE - SEED_REFIT_HEADROOM
    assert len(digest) < 5000 and "trimmed to fit" in digest
    assert iv["kind"] == "context_fit" and iv["block"] == "seed" and iv["cause"] == "step1_preflight"
    assert iv["estimated_before"] > LINE >= iv["estimated_after"]
    assert iv["still_refused"] is False and "digest" in iv["suppressed"]


def test_a_block_that_is_not_in_the_seed_is_not_cut_for_it():
    """Act-first: the digest rides the posture turn. Cutting it frees nothing in the seed, so it stays."""
    render = _Render(fixed=33000, conv_chars=CONV, digest_in_seed=False)
    rendered, rung, digest, recall, iv = _fit(render, "d" * 5000, "r" * 6000)
    assert digest == "d" * 5000, "the posture turn's digest must not pay for the seed"
    assert len(recall) < 6000
    assert "digest" not in iv["suppressed"] and "recall" in iv["suppressed"]


def test_the_conversation_ladder_is_stepped_after_the_blocks_reach_their_floors():
    render = _Render(fixed=36000, conv_chars=CONV)
    rendered, rung, digest, recall, iv = _fit(render, "d" * 2000, "r" * 1000)
    assert rung != CONV_LADDER[0]
    assert len(digest) <= FIT_FLOORS["digest"] + 60 and len(recall) <= FIT_FLOORS["recall"] + 60
    assert "conversations stepped down" in iv["suppressed"]
    assert not preflight_refuses(_measure(rendered), CTX)


def test_a_seed_still_over_at_the_last_rung_is_sent_and_says_it_will_be_refused():
    render = _Render(fixed=60000, conv_chars=CONV)
    rendered, rung, digest, recall, iv = _fit(render, "d" * 2000, "r" * 1000)
    assert rung == CONV_LADDER[-1]
    assert iv["still_refused"] is True and "STILL over" in iv["reason"]


def test_no_window_means_no_fit():
    render = _Render(fixed=90000, conv_chars=CONV)
    for ctx in (None, 0, "x"):
        r, rung, d, rc, iv = fit_seed_to_preflight(render, _measure, num_ctx=ctx, rung_index=0,
                                                   digest="d", recall="r", cpt=CPT)
        assert iv is None and d == "d"


# --- one count: the heartbeat's measure IS the loop's preflight -------------------------------------

class _LLM:
    num_ctx = CTX

    def __init__(self):
        self.sent = []

    def get_chat_response(self, messages, tools=None, **kw):
        self.sent.append(messages)
        return {"content": "done", "tool_calls": [], "raw": {"prompt_eval_count": 9000, "eval_count": 5}}


class _Client:
    def dispatch(self, intent):
        raise AssertionError("nothing should be dispatched")


TOOLS = [{"type": "function", "function": {"name": f"verb{i}", "description": "d" * 600,
                                           "parameters": {"type": "object", "properties": {}}}}
         for i in range(30)]


def _seed(chars):
    return [{"role": "system", "content": "s" * 2000}, {"role": "user", "content": "u" * chars}]


def test_the_loop_refuses_exactly_the_seeds_the_heartbeat_measures_as_refused():
    """The step-1 decision and the heartbeat's measurement are one function of the same inputs, so they
    cannot disagree about any seed: probe both sides of the line."""
    llm = _LLM()
    unc = uncounted_chars(TOOLS, "native")
    line_chars = int(LINE * btl.preflight_cpt(llm)) - unc - 2000
    for chars in (line_chars - 50, line_chars + 50):
        seed = _seed(chars)
        predicted = preflight_refuses(preflight_tokens(seed, unc, llm), CTX)
        llm.sent.clear()
        r = run_ollama_tool_turn(_Client(), llm, seed, max_steps=1, tools=TOOLS)
        refused = bool(r.window_full and r.window_full["cause"] == "preflight")
        assert refused == predicted, (chars, predicted, r.window_full)
        assert refused == (not llm.sent)
        if refused:
            assert r.window_full["estimated_prompt"] == int(preflight_tokens(seed, unc, llm))


def test_the_json_act_form_counts_no_schemas_on_either_side():
    assert uncounted_chars(TOOLS, "json") == btl._TEMPLATE_CHARS
    assert uncounted_chars(TOOLS, "native") > uncounted_chars(TOOLS, "json")


def test_a_declared_ratio_moves_both_sides_together():
    llm = SimpleNamespace(num_ctx=CTX, _adapter=SimpleNamespace(
        capabilities=SimpleNamespace(preflight_chars_per_token=3.6)))
    seed = _seed(50000)
    assert preflight_tokens(seed, 0, llm) == btl._convo_chars(seed) / 3.6
