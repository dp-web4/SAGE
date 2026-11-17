"""A being still refused at its prior ratio asks the server once, and so can calibrate (McNugget on #774).

measured_preflight_cpt learns only from a step-1 generate that was sent. A seed over the line at the declared
or default ratio (pub's 11-17 trial: an unconfigured model at 2.9, 16,450 estimated against 16,384) was
trimmed or refused at that ratio, so no sample was ever taken. Now, uncalibrated and cut, the heartbeat
counts the untrimmed seed on the server (num_predict 1, truncation and shift off) and fits at that seed's
own ratio. Hermetic: a fake POST and a fake LLM, no model, no gate.
"""
import io
import json
import os
import sys
import urllib.error
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import being_tool_loop as btl  # noqa: E402
from sage.gateway.being_tool_loop import (run_ollama_tool_turn, uncounted_chars, preflight_tokens,  # noqa: E402
                                          preflight_cpt, WINDOW_SEND_MARGIN)
from sage.gateway.heartbeat import (probe_seed_count, fit_seed_calibrating, fit_seed_to_preflight,  # noqa: E402
                                    measured_preflight_cpt, CONV_LADDER, MEASURED_CPT_MARGIN)

CTX = 16384
LINE = CTX - WINDOW_SEND_MARGIN
TOOLS = [{"type": "function", "function": {"name": f"verb{i}", "description": "d" * 300,
                                           "parameters": {"type": "object", "properties": {}}}}
         for i in range(20)]
UNC = uncounted_chars(TOOLS, "tools")


class _Post:
    """The server: counts a prompt at `cpt` chars per token, or refuses it, and remembers what it was sent."""
    def __init__(self, cpt=3.7, refuse=None, raw=None):
        self.cpt, self.refuse, self.raw, self.calls = cpt, refuse, raw, []

    def __call__(self, url, payload, timeout):
        self.calls.append((url, payload))
        if self.refuse:
            raise urllib.error.HTTPError(url, self.refuse, "too long", {},
                                         io.BytesIO(b'{"error":"the input length exceeds the context length"}'))
        if self.raw is not None:
            return self.raw
        chars = btl._convo_chars(payload["messages"]) + uncounted_chars(payload.get("tools"), "tools")
        return {"prompt_eval_count": int(chars / self.cpt), "eval_count": 1, "done_reason": "length"}


def _llm(**kw):
    return SimpleNamespace(ollama_host="http://ollama:11434", model_name="newmodel:4b", think=False,
                           num_ctx=CTX, preflight_cpt_measured=None, **kw)


def _seed(chars):
    return [{"role": "system", "content": "s" * 2000}, {"role": "user", "content": "u" * chars}]


# --- the probe ---------------------------------------------------------------------------------------

def test_the_probe_counts_the_whole_seed_once_with_truncation_and_shift_off():
    post = _Post(cpt=3.7)
    seed = _seed(40000)
    p = probe_seed_count(_llm(), seed, TOOLS, num_ctx=CTX, prior=2.9, post=post)
    assert p["result"] == "counted"
    assert len(post.calls) == 1
    url, payload = post.calls[0]
    assert url == "http://ollama:11434/api/chat"
    assert payload["truncate"] is False and payload["shift"] is False
    assert payload["options"] == {"num_predict": 1, "num_ctx": CTX}
    assert payload["tools"] == TOOLS and payload["messages"] == seed and payload["think"] is False
    # in the preflight's own units, so the ratio divides the same chars the loop will count
    assert p["prompt_chars"] == btl._convo_chars(seed) + UNC
    assert p["value"] == round(p["ratio"] * MEASURED_CPT_MARGIN, 3)


def test_a_seed_the_server_will_not_hold_is_a_refusal_not_a_ratio():
    p = probe_seed_count(_llm(), _seed(90000), TOOLS, num_ctx=CTX, prior=2.9, post=_Post(refuse=400))
    assert p["result"] == "refused_by_server" and "value" not in p
    assert "exceeds the context length" in p["error"]


def test_a_count_too_low_to_be_the_whole_prompt_is_not_believed():
    # e.g. a server that ignored truncate=false and dropped a message: the ratio reads far above the prior
    p = probe_seed_count(_llm(), _seed(40000), TOOLS, num_ctx=CTX, prior=2.9, post=_Post(cpt=5.0))
    assert p["result"] == "implausible" and "value" not in p


def test_a_count_near_the_windows_edge_is_kept_because_truncation_was_off():
    seed = _seed(int((CTX - 100) * 3.4) - UNC - 2000)
    p = probe_seed_count(_llm(), seed, TOOLS, num_ctx=CTX, prior=2.9, post=_Post(cpt=3.4))
    assert p["prompt_eval_count"] >= LINE and p["result"] == "counted" and p["value"]


def test_the_json_form_and_a_missing_server_are_not_probed():
    post = _Post()
    assert probe_seed_count(_llm(), _seed(100), TOOLS, num_ctx=CTX, act_form="json",
                            post=post)["result"] == "skipped_json_form"
    assert probe_seed_count(SimpleNamespace(num_ctx=CTX), _seed(100), TOOLS, num_ctx=CTX,
                            post=post)["result"] == "skipped_no_server"
    assert probe_seed_count(_llm(), _seed(100), TOOLS, num_ctx=0, post=post)["result"] == "skipped_no_server"
    assert post.calls == []


def test_no_count_and_a_transport_error_leave_no_value():
    assert probe_seed_count(_llm(), _seed(100), TOOLS, num_ctx=CTX,
                            post=_Post(raw={"done_reason": "stop"}))["result"] == "no_count"

    def boom(url, payload, timeout):
        raise OSError("connection refused")
    p = probe_seed_count(_llm(), _seed(100), TOOLS, num_ctx=CTX, post=boom)
    assert p["result"] == "error" and "value" not in p


# --- the decision: when to ask, and what the answer changes ------------------------------------------

class _Render:
    """fixed text + conversations (shrinking down the ladder) + recall + digest, as one user turn."""
    def __init__(self, fixed, conv):
        self.fixed, self.conv = fixed, conv

    def __call__(self, rung, digest, recall):
        body = "f" * self.fixed + "c" * self.conv[CONV_LADDER.index(rung)] + (recall or "") + (digest or "")
        return [{"role": "system", "content": "s" * 2000}, {"role": "user", "content": body}], None


CONV = [6000, 4500, 3000, 1500, 800]


def _decide(llm, render, post, cal, digest="D" * 6000, recall="R" * 3000):
    def fit():
        return fit_seed_to_preflight(render, lambda r: preflight_tokens(r[0], UNC, llm), num_ctx=CTX,
                                     rung_index=0, digest=digest, recall=recall, cpt=preflight_cpt(llm))
    return fit_seed_calibrating(
        fit, lambda: probe_seed_count(llm, render(CONV_LADDER[0], digest, recall)[0], TOOLS, num_ctx=CTX,
                                      prior=cal["prior"], post=post),
        llm, cal)


def _pub_trial_render():
    """pub's 11-17 shape: an unconfigured model at the 2.9 default, the seed just over the line
    (~16,450 estimated against 16,384), while the server counts it at ~3.7 chars/token."""
    fixed = int(16450 * 2.9) - UNC - 2000 - CONV[0] - 6000 - 3000
    return _Render(fixed, CONV)


def test_pub_trials_shape_an_unconfigured_model_over_the_line_now_runs_with_its_seed_whole():
    llm, post = _llm(), _Post(cpt=3.7)
    render = _pub_trial_render()
    cal = {"source": "declared_or_default", "prior": preflight_cpt(llm), "used": preflight_cpt(llm)}
    whole = render(CONV_LADDER[0], "D" * 6000, "R" * 3000)
    assert preflight_tokens(whole[0], UNC, llm) > LINE            # refused at the prior, as on 11-17
    (seed, _), rung, d, r, iv = _decide(llm, render, post, cal)
    assert len(post.calls) == 1
    assert cal["source"] == "probe" and cal["probe"]["result"] == "counted"
    assert cal["probe"]["fit_at_prior"]["estimated_before"] > LINE
    # fitted at the seed's own ratio: nothing cut, and the loop's own preflight now sends it
    assert iv is None and seed == whole[0] and rung == CONV_LADDER[0]
    assert d == "D" * 6000 and r == "R" * 3000
    assert llm.preflight_cpt_measured == cal["probe"]["value"]
    sent = []
    llm.get_chat_response = lambda messages, tools=None, **kw: (sent.append(messages) or {
        "content": "done", "tool_calls": [],
        "raw": {"prompt_eval_count": int((btl._convo_chars(messages) + UNC) / 3.7), "eval_count": 5}})
    res = run_ollama_tool_turn(SimpleNamespace(dispatch=None), llm, seed, max_steps=1, tools=TOOLS)
    assert sent and not res.window_full
    assert res.generates[0]["prompt_chars"] == btl._convo_chars(seed) + UNC   # a sample, so it calibrates


def test_a_calibrated_being_and_a_seed_that_fits_are_never_probed():
    post = _Post()
    llm = _llm()
    small = _Render(1000, CONV)
    cal = {"source": "declared_or_default", "prior": 2.9}
    _, _, _, _, iv = _decide(llm, small, post, cal)
    assert iv is None and post.calls == [] and "probe" not in cal
    big = _pub_trial_render()
    cal = {"source": "measured", "prior": 2.9}
    _decide(llm, big, post, cal)
    assert post.calls == [] and "probe" not in cal


def test_a_failed_probe_leaves_the_fit_at_the_prior_and_says_so():
    llm = _llm()
    render = _pub_trial_render()
    cal = {"source": "declared_or_default", "prior": 2.9}
    res = _decide(llm, render, _Post(refuse=400), cal)
    assert res[4] is not None and res[4]["block"] == "seed"         # the prior fit stands
    assert cal["source"] == "declared_or_default" and llm.preflight_cpt_measured is None
    assert cal["probe"]["result"] == "refused_by_server"


def test_a_probe_that_raises_never_costs_the_beat():
    llm = _llm()
    cal = {"source": "declared_or_default", "prior": 2.9}

    def fit():
        return fit_seed_to_preflight(_pub_trial_render(), lambda r: preflight_tokens(r[0], UNC, llm),
                                     num_ctx=CTX, rung_index=0, digest="D" * 6000, recall="R" * 3000,
                                     cpt=preflight_cpt(llm))

    def probe():
        raise RuntimeError("no")
    res = fit_seed_calibrating(fit, probe, llm, cal)
    assert res[4] is not None and cal["probe"]["result"] == "error"


def test_after_five_sent_beats_the_measured_ratio_takes_over_and_probing_stops(tmp_path):
    llm = _llm()
    seed = _pub_trial_render()(CONV_LADDER[0], "D" * 6000, "R" * 3000)[0]
    chars = btl._convo_chars(seed) + UNC
    with open(tmp_path / "heartbeats.jsonl", "w") as f:
        for _ in range(5):
            f.write(json.dumps({"model": "newmodel:4b", "num_ctx": CTX, "explore": {"generates": [
                {"prompt_chars": chars, "prompt_eval_count": int(chars / 3.7)}]}}) + "\n")
    cal = measured_preflight_cpt(tmp_path, "newmodel:4b", prior=2.9)
    assert cal["value"] and cal["samples"] == 5
    llm.preflight_cpt_measured = cal["value"]
    cal.update(source="measured", prior=2.9)
    post = _Post()
    (s, _), _, _, _, iv = _decide(llm, _pub_trial_render(), post, cal)
    assert iv is None and post.calls == [] and s == seed
