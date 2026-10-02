"""sprout-being's 2B gets a 16384 window, and nothing else sharing its profile changes (SAGE #284).

Its prompt crossed the 8192 floor on 2026-09-29 07:10Z; ollama 0.30.8 answers an over-window
request with HTTP 400, so explore failed on every beat (33/47 on 09-29, 17/17 on 09-30 to 08:47Z).
Measured on the Orin Nano: 16384 is 2.4 GB, 100% GPU, ~22 tok/s, same as 8192. GPT's hold: the
quant-suffix keys (q8_0/q6_k/q4_k_m) are matched for every alias of the profile, including the
4B hf.co tags, so only the '2b' key carries it."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway.governed_turn import resolve_num_ctx  # noqa: E402


def test_the_2b_gets_16384():
    assert resolve_num_ctx("qwen3.8-distill:2b", 8192) == 16384


def test_the_4b_hf_quant_tags_are_not_raised():
    for tag in ("Q8_0", "Q6_K", "Q4_K_M"):
        assert resolve_num_ctx(f"hf.co/empero-ai/Qwen3.8-4B-Distill-GGUF:{tag}", 8192) == 8192, tag


def test_the_others_on_this_profile_are_unchanged():
    # Legion carrier: the heretic runs at 24576 here (raised from its Modelfile 16384, measured on the
    # 4090); main keeps 16384. Either way #284 must not change it, which is what this pins.
    assert resolve_num_ctx("qwen38-heretic:q3km", 8192) == 24576
    assert resolve_num_ctx("qwen3.8-distill:4b", 8192) == 16384       # its own, on main
    assert resolve_num_ctx("hf.co/empero-ai/Qwen3.8-2B-Distill-GGUF:Q8_0", 8192) == 8192   # unmeasured tag
