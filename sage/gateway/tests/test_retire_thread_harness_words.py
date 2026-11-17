"""retire_thread: a harness word beside a topic word does not carry the retire (#747).

cbp-being, 2026-11-17 03:16Z: words `xor_pure_numpy_mlp.py, run, seat, request_run, sha ec5a3dedf952`
retired three settled entries hit by `run` alone; the topic file hit none of them."""
from sage.gateway import being_settled as st
from sage.gateway import being_threads as bt
from sage.gateway.heartbeat import _todo_items

WORDS = "xor_pure_numpy_mlp.py, run, seat, request_run, sha ec5a3dedf952"
TODO = """2026-11-16 20:00 UTC
- [ ] fix the shape bug in xor_pure_numpy_mlp.py and request_run it
- [ ] ask the seat whether runs are measurements
- [ ] read the camera notes
"""


def _home(tmp_path):
    (tmp_path / "todo.md").write_text(TODO)
    for q, a in (
        ("Are 0.9550 and 0.9600 measurements from a run, or predictions?", "predictions; no run happened"),
        ("Where is the shape mismatch in xor_numpy_only.py line 134 coming from?", "W2 is used untransposed; a run shows it"),
        ("Does xor_pure_numpy_mlp.py converge?", "yes, loss 0.01 at epoch 900"),
        ("What does the camera see?", "a desk"),
    ):
        assert st.settle(tmp_path, {"question": q, "answer": a}, now=0)[0]
    return tmp_path


def _left(h):
    return [e["question"] for e in st.read(h)[0]]


def test_the_747_call_retires_the_topic_and_keeps_what_only_run_named(tmp_path):
    h = _home(tmp_path)
    ok, msg, changed = bt.retire_thread(h, {"words": WORDS, "reason": "the xor work is done"}, now=0)
    assert ok and changed, msg
    left = _left(h)
    assert "Does xor_pure_numpy_mlp.py converge?" not in left
    assert any(q.startswith("Are 0.9550") for q in left), "the seat correction stays"
    assert any("xor_numpy_only.py" in q for q in left), "another file's entry stays"
    open_ = [t for t, _ in _todo_items((h / "todo.md").read_text()).values()]
    assert open_ == ["ask the seat whether runs are measurements", "read the camera notes"], open_
    assert "Kept, because only run, seat, request_run named them (settled s1, s2, 1 open todo item(s))" in msg, msg
    assert "selected by xor_pure_numpy_mlp.py, sha ec5a3dedf952" in msg


def test_the_preview_says_the_same(tmp_path):
    h = _home(tmp_path)
    ok, msg, changed = bt.retire_thread(h, {"words": WORDS, "preview": "true"}, now=0)
    assert ok and not changed
    assert "1 of 3 open todo item(s) and 1 of 4 settled entries would be retired" in msg, msg
    assert "Kept, because only run, seat, request_run named them" in msg


def test_harness_words_alone_still_select(tmp_path):
    """A being may retire its seat thread by `seat`: with no other word, the harness words are the topic."""
    h = _home(tmp_path)
    ok, msg, _ = bt.retire_thread(h, {"words": "seat", "preview": "true"}, now=0)
    assert ok and "1 of 3 open todo item(s)" in msg and "Kept" not in msg, msg


def test_a_call_without_harness_words_is_unchanged(tmp_path):
    h = _home(tmp_path)
    ok, msg, _ = bt.retire_thread(h, {"words": "camera", "reason": "done"}, now=0)
    assert ok and "Kept" not in msg and "did not select" not in msg
    assert "What does the camera see?" not in _left(h)


def test_a_harness_word_that_named_nothing_extra_is_said_to_have_selected_nothing(tmp_path):
    h = _home(tmp_path)
    ok, msg, _ = bt.retire_thread(h, {"words": "camera, beat", "preview": "true"}, now=0)
    assert ok and "beat did not select anything" in msg, msg


def test_split_words():
    assert bt.split_words(["xor.py", "Run", "seat"]) == (["xor.py"], ["Run", "seat"])
    assert bt.split_words(["run", "seat"]) == (["run", "seat"], [])
    assert bt.split_words(["running", "camera"]) == (["running", "camera"], []), "only the exact word"
