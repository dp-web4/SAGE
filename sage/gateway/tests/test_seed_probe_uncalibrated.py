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
from sage.gateway import heartbeat as hb  # noqa: E402
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
        self.calls.append((url, payload, timeout))
        if self.refuse:
            code, body = self.refuse if isinstance(self.refuse, tuple) else (
                self.refuse, b'{"error":"the input length exceeds the context length"}')
            raise urllib.error.HTTPError(url, code, "refused", {}, io.BytesIO(body))
        if self.raw is not None:
            return self.raw
        chars = btl._convo_chars(payload["messages"]) + uncounted_chars(payload.get("tools"), "tools")
        return {"prompt_eval_count": int(chars / self.cpt), "eval_count": 1, "done_reason": "length"}


def _llm(**kw):
    llm = SimpleNamespace(ollama_host="http://ollama:11434", model_name="newmodel:4b", think=False,
                          num_ctx=CTX, preflight_cpt_measured=None, timeout_seconds=120)
    for k, v in kw.items():
        setattr(llm, k, v)

    def chat_payload(messages, tools=None, fmt=None):     # the adapter's shape (OllamaIRP.chat_payload)
        p = {"model": llm.model_name, "messages": messages, "stream": False, "keep_alive": "5m",
             "think": llm.think, "options": {"num_predict": 6000, "temperature": 0.8, "num_ctx": llm.num_ctx}}
        if tools:
            p["tools"] = tools
        return p
    llm.chat_payload = chat_payload
    return llm


def _seed(chars):
    return [{"role": "system", "content": "s" * 2000}, {"role": "user", "content": "u" * chars}]


# --- the probe ---------------------------------------------------------------------------------------

def test_the_probe_counts_the_whole_seed_once_with_truncation_and_shift_off():
    post = _Post(cpt=3.7)
    seed = _seed(40000)
    p = probe_seed_count(_llm(), seed, TOOLS, num_ctx=CTX, prior=2.9, post=post)
    assert p["result"] == "counted"
    assert len(post.calls) == 1
    url, payload, timeout = post.calls[0]
    assert url == "http://ollama:11434/api/chat"
    assert payload["truncate"] is False and payload["shift"] is False
    # the adapter's own options, with only num_predict changed
    assert payload["options"] == {"num_predict": 1, "temperature": 0.8, "num_ctx": CTX}
    assert payload["model"] == "newmodel:4b" and payload["keep_alive"] == "5m"
    assert timeout == min(hb.SEED_PROBE_TIMEOUT_S, 120)
    assert payload["tools"] == TOOLS and payload["messages"] == seed and payload["think"] is False
    # in the preflight's own units, so the ratio divides the same chars the loop will count
    assert p["prompt_chars"] == btl._convo_chars(seed) + UNC
    assert p["value"] == round(p["ratio"] * MEASURED_CPT_MARGIN, 3)


def test_a_seed_the_server_will_not_hold_is_a_refusal_not_a_ratio():
    p = probe_seed_count(_llm(), _seed(90000), TOOLS, num_ctx=CTX, prior=2.9, post=_Post(refuse=400))
    assert p["result"] == "refused_by_server" and "value" not in p and p["http_status"] == 400
    assert "exceeds the context length" in p["error"]


def test_only_the_context_length_400_is_a_refusal_every_other_status_is_an_http_error():
    # NOVA on #777: a 401/404/429/5xx, or a 400 for another reason, says nothing about the seed's size
    cases = [(400, b'{"error":"invalid tool schema"}'), (401, b'unauthorized'),
             (404, b'{"error":"model not found"}'), (429, b'{"error":"server busy"}'),
             (500, b'{"error":"llama runner process has terminated"}'), (503, b'')]
    for code, body in cases:
        p = probe_seed_count(_llm(), _seed(100), TOOLS, num_ctx=CTX, prior=2.9, post=_Post(refuse=(code, body)))
        assert p["result"] == "http_error" and p["http_status"] == code and "value" not in p, (code, p)
    # the body is read bounded
    p = probe_seed_count(_llm(), _seed(100), TOOLS, num_ctx=CTX, post=_Post(refuse=(400, b"x" * 50000)))
    assert p["result"] == "http_error" and len(p["error"]) <= 200


def test_a_timeout_is_a_timeout_not_a_refusal_and_the_budget_is_bounded():
    import socket

    def slow(url, payload, timeout):
        slow.timeout = timeout
        raise socket.timeout("timed out")
    p = probe_seed_count(_llm(), _seed(100), TOOLS, num_ctx=CTX, post=slow)
    assert p["result"] == "timeout" and "value" not in p
    assert slow.timeout == p["timeout_s"] <= hb.SEED_PROBE_TIMEOUT_S
    # never more than the adapter's own request timeout
    probe_seed_count(_llm(timeout_seconds=30), _seed(100), TOOLS, num_ctx=CTX, post=slow)
    assert slow.timeout == 30

    def wrapped(url, payload, timeout):         # urllib wraps a connect timeout in URLError
        raise urllib.error.URLError(socket.timeout("timed out"))
    assert probe_seed_count(_llm(), _seed(100), TOOLS, num_ctx=CTX, post=wrapped)["result"] == "timeout"


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
    assert probe_seed_count(_llm(_ollama_available=False), _seed(100), TOOLS, num_ctx=CTX,
                            post=post)["result"] == "skipped_no_server"
    # no adapter to build step 1's request from: don't guess at it
    assert probe_seed_count(SimpleNamespace(ollama_host="h", model_name="m", num_ctx=CTX), _seed(100), TOOLS,
                            num_ctx=CTX, post=post)["result"] == "skipped_no_adapter"
    # the adapter sends another window than the preflight counts against: a count there answers nothing
    llm = _llm()
    llm.num_ctx = 8192
    assert probe_seed_count(llm, _seed(100), TOOLS, num_ctx=CTX, post=post)["result"] == "skipped_ctx_mismatch"
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


def test_a_timed_out_probe_leaves_the_prior_fit_and_never_reads_as_a_refusal():
    import socket
    llm = _llm()
    cal = {"source": "declared_or_default", "prior": 2.9}

    def slow(url, payload, timeout):
        raise socket.timeout("timed out")
    res = _decide(llm, _pub_trial_render(), slow, cal)
    assert res[4] is not None and cal["probe"]["result"] == "timeout"
    assert cal["source"] == "declared_or_default" and llm.preflight_cpt_measured is None


def test_a_refit_that_raises_puts_the_prior_ratio_back():
    # NOVA on #777: the record must name the ratio the loop will use
    llm = _llm()
    cal = {"source": "declared_or_default", "prior": 2.9, "used": 2.9}
    render = _pub_trial_render()
    calls = []

    def fit():
        calls.append(llm.preflight_cpt_measured)
        if llm.preflight_cpt_measured:
            raise RuntimeError("refit broke")
        return fit_seed_to_preflight(render, lambda r: preflight_tokens(r[0], UNC, llm), num_ctx=CTX,
                                     rung_index=0, digest="D" * 6000, recall="R" * 3000, cpt=preflight_cpt(llm))

    def probe():
        return probe_seed_count(llm, render(CONV_LADDER[0], "D" * 6000, "R" * 3000)[0], TOOLS,
                                num_ctx=CTX, prior=2.9, post=_Post(cpt=3.7))
    res = fit_seed_calibrating(fit, probe, llm, cal)
    assert len(calls) == 2 and res[4] is not None
    assert llm.preflight_cpt_measured is None and cal["source"] == "declared_or_default" and cal["used"] == 2.9
    assert "refit broke" in cal["probe"]["refit_error"]


def test_with_its_own_few_counts_a_refused_being_uses_them_and_is_not_probed():
    # #776 first: 1-4 own counts and still refused -> the provisional ratio, no server call
    llm, post = _llm(), _Post(cpt=3.7)
    render = _Render(int(17400 * 2.9) - UNC - 2000 - CONV[-1], CONV)    # refused even at the sparsest rung
    cal = {"source": "declared_or_default", "prior": 2.9, "value": None,
           "provisional": round(3.68 * MEASURED_CPT_MARGIN, 3)}
    res = _decide(llm, render, post, cal)
    assert post.calls == [] and "probe" not in cal
    assert cal["source"] == "measured_provisional" and llm.preflight_cpt_measured == cal["provisional"]
    assert cal["refused_at_prior"]["estimated_after"] > LINE
    assert res[4] is None or not res[4].get("still_refused")


def test_the_probe_request_is_the_adapters_own_request(monkeypatch):
    """Parity with OllamaIRP.get_chat_response: the same body, but num_predict 1 and truncation/shift off."""
    from sage.irp.plugins import ollama_irp
    monkeypatch.setattr(ollama_irp.OllamaIRP, "_check_ollama", lambda self: True)
    irp = ollama_irp.OllamaIRP({"model_name": "qwen3.8-distill:4b", "num_ctx": CTX, "think": False,
                                "ollama_host": "http://ollama:11434"})
    sent = {}

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        sent["body"] = json.loads(req.data)
        return _Resp(json.dumps({"message": {"content": "x"}, "prompt_eval_count": 10}).encode())
    monkeypatch.setattr(ollama_irp.urllib.request, "urlopen", fake_urlopen)
    seed = _seed(1000)
    irp.get_chat_response(seed, tools=TOOLS)
    step1 = sent["body"]
    post = _Post(cpt=3.7)
    probe_seed_count(irp, seed, TOOLS, num_ctx=CTX, prior=2.9, post=post)
    probe = post.calls[0][1]
    same = lambda d: {k: v for k, v in d.items() if k not in ("truncate", "shift", "options")}
    assert same(probe) == same(step1)
    assert probe["options"] == dict(step1["options"], num_predict=1)
    assert probe["truncate"] is False and probe["shift"] is False
