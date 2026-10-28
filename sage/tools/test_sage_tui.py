"""sage-tui's pure rendering (no terminal, no daemon)."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from sage.tools import sage_tui as t  # noqa: E402


def test_header_shows_state_atp_beat_and_salience():
    lines = t.header_lines({"model": "m", "build": "b"},
                           {"metabolic_state": "wake", "metabolic_age_secs": 3, "metabolic_source": "heartbeat:explore",
                            "atp_percentage": 50.0, "beats": {"completed": 7, "current": {"beat_id": "heartbeat-abc", "phase": "explore", "age_secs": 9}},
                            "salience": {"surprise": 1.0, "novelty": 0.5, "total": 0.55}}, 200)
    assert "state wake" in lines[1] and "50.0%" in lines[1] and "█" * 10 in lines[1]
    assert "phase explore" in lines[2] and "beats completed 7" in lines[2]
    assert "surp" in lines[3] and "total 0.55" in lines[3]


def test_turns_wrap_and_show_the_trial_label_beside_the_words():
    lines = t.turn_lines({"turns": [{"ts": "2026-10-08T18:00:01Z", "from": "sprout-being", "trial": "answer-first",
                                     "text": "word " * 40}]}, 60)
    assert lines[0] == "18:00:01 sprout-being [TEST answer-first]:"
    assert all(len(l) <= 60 for l in lines) and len(lines) > 2


def test_input_is_offered_only_where_dp_may_write():
    assert t.writable({"writable_by": ["dp", "sprout-being"]})
    assert not t.writable({"writable_by": ["sprout-claude", "sprout-being"]})


def test_a_dead_daemon_is_an_error_value_not_a_crash():
    t.BASE = "http://127.0.0.1:9"
    d, e = t.fetch("/health", timeout=0.5)
    assert d == {} and e


# ---- issue #399 (GPT on #398): identity, not position ----
DP = {"id": "dp", "writable_by": ["dp", "sprout-being"]}
ROOM = {"id": "room", "writable_by": ["sprout-being"]}
SEAT = {"id": "sprout-claude", "writable_by": ["sprout-claude", "sprout-being"]}


class _Daemon:
    """A fake daemon: what each conversation's meta is, and where says landed."""
    def __init__(self, metas):
        self.metas, self.said = {m["id"]: m for m in metas}, []

    def __call__(self, path, body=None):
        cid = path.split("/")[2].split("?")[0]
        if body is not None:
            self.said.append((cid, body["message"]))
            return {"delivery": "recorded"}, None
        if cid not in self.metas:
            return {"error": "no such conversation"}, "HTTP 404"
        return {"meta": self.metas[cid]}, None


def test_a_reorder_while_composing_does_not_retarget_the_message():
    st = t.TuiState()
    st.update([DP, ROOM, SEAT])
    assert st.sel_id == "dp" and st.begin(DP)
    st.draft = "for dp only"
    st.update([ROOM, SEAT, DP])                     # room got a turn: the list reorders under the draft
    assert st.sel_id == "dp" and st.target == "dp", "selection and destination follow the ID, not the index"
    daemon = _Daemon([DP, ROOM, SEAT])
    assert st.send(daemon) and daemon.said == [("dp", "for dp only")]


def test_navigation_is_frozen_while_composing_and_selection_survives_refresh():
    st = t.TuiState()
    st.update([DP, ROOM])
    st.move([DP, ROOM], +1)
    assert st.sel_id == "room"
    st.update([ROOM, DP])
    assert st.sel_id == "room", "a refresh keeps the selected ID"
    st.move([ROOM, DP], +1); st.begin(DP)
    st.move([ROOM, DP], +1)
    assert st.target == "dp" and st.sel_id == "dp", "arrow keys do not move the pinned target"


def test_a_gone_or_readonly_target_is_refused_visibly_and_the_draft_is_kept():
    st = t.TuiState()
    st.update([DP]); st.begin(DP); st.draft = "hello"
    gone = _Daemon([ROOM])
    assert not st.send(gone) and gone.said == [] and st.draft == "hello" and "NOT sent" in st.flash
    readonly = _Daemon([{"id": "dp", "writable_by": ["sprout-being"]}])
    assert not st.send(readonly) and readonly.said == [] and st.typing


def test_compose_only_on_the_writable_conversation_on_screen():
    st = t.TuiState()
    st.update([ROOM, DP])
    assert not st.begin(ROOM), "read-only for dp"
    assert not st.begin(DP), "not the selected conversation"
    st.move([ROOM, DP], +1)
    assert st.begin(DP)


# ---- scrolling the conversation text (dp 2026-10-08: the wheel switched conversations instead) ----
def test_scroll_windows_and_clamps():
    st = t.TuiState()
    lines = [f"l{i}" for i in range(100)]
    assert st.window(lines, 10) == lines[90:], "at rest it follows the newest lines"
    st.scroll_by(+25, len(lines), 10)
    assert st.window(lines, 10) == lines[65:75]
    st.scroll_by(+1000, len(lines), 10)
    assert st.scroll == 90 and st.window(lines, 10) == lines[0:10], "stops at the top of the history"
    st.scroll_by(-1000, len(lines), 10)
    assert st.scroll == 0, "stops at the newest"


def test_new_turns_do_not_yank_a_reader_to_the_bottom_but_a_follower_follows():
    st = t.TuiState()
    lines = [f"l{i}" for i in range(50)]
    st.scroll_by(+10, len(lines), 10)
    shown = st.window(lines, 10)
    st.grew(5); more = lines + [f"n{i}" for i in range(5)]
    assert st.window(more, 10) == shown, "the same text stays on screen"
    st2 = t.TuiState()
    st2.grew(5)
    assert st2.scroll == 0 and st2.window(more, 10) == more[-10:], "at the bottom, new turns are followed"


def test_switching_conversation_returns_to_the_newest():
    st = t.TuiState()
    st.update([DP, ROOM]); st.scroll_by(+20, 100, 10)
    st.move([DP, ROOM], +1)
    assert st.sel_id == "room" and st.scroll == 0


# ---- the machine body, memory first (dp 2026-10-18) ----
GIB = 1024 ** 3
BODY = {"line": "GPU 11% · 61°C | CPU 52% · 62°C · RAM 2.8/7.4 GiB (one pool, GPU included) (+3.5 GiB swap)"
                " | disk 22% (679 GiB free) | memory: unified",
        "memory": {"pool": "unified", "total_bytes": {"value": 8 * GIB}, "used_bytes": {"value": 6 * GIB},
                   "available_bytes": {"value": 2 * GIB}, "swap_total_bytes": {"value": 10 * GIB},
                   "swap_used_bytes": {"value": 3.5 * GIB}},
        "served_age_s": 4.0}


def test_memory_comes_first_as_a_bar_of_the_one_pool():
    lines = t.body_lines(BODY, {"model": "qwen3.8-distill:4b", "loaded_models": ["qwen3.8-distill:4b"]}, 200)
    assert lines[0].startswith("RAM  ") and "█" * 15 in lines[0]
    assert "6.0/8.0 GiB" in lines[0] and "75%" in lines[0] and "one pool, GPU incl." in lines[0]
    assert "avail 2.0" in lines[0] and "swap 3.5/10.0" in lines[0]


def test_the_rest_is_the_samplers_line_without_its_ram_part():
    lines = t.body_lines(BODY, {"model": "qwen3.8-distill:4b", "loaded_models": ["qwen3.8-distill:4b"]}, 200)
    assert "GPU 11% · 61°C" in lines[1] and "disk 22% (679 GiB free)" in lines[1]
    assert "CPU 52% · 62°C" in lines[1], "RAM shares the CPU segment; only RAM is dropped"
    assert "RAM" not in lines[1] and "memory: unified" not in lines[1]
    assert "model loaded" in lines[1] and "sampled 4s ago" in lines[1]


def test_an_unloaded_model_says_so_and_an_old_daemon_says_nothing():
    assert "model not loaded" in t.body_lines(BODY, {"model": "m:4b", "loaded_models": []}, 200)[1]
    assert "model" not in t.body_lines(BODY, {"model": "m:4b"}, 200)[1]   # pre-#433 /health has no field


def test_a_same_family_different_tag_is_not_the_loaded_model():
    """NOVA on #469: matching the text before ':' reported qwen:2b as qwen:4b loaded."""
    h = {"model": "qwen3.8-distill:4b", "loaded_models": ["qwen3.8-distill:2b"]}
    assert "model not loaded" in t.body_lines(BODY, h, 200)[1]
    assert "model not loaded" in t.body_lines(BODY, dict(h, model_loaded=False), 200)[1]


def test_the_daemons_own_answer_wins():
    h = {"model": "m:4b", "loaded_models": ["m:4b"], "model_loaded": False}
    assert "model not loaded" in t.body_lines(BODY, h, 200)[1]
    h = {"model": "m:4b", "loaded_models": ["m:4b"], "model_loaded": True}
    assert "model loaded" in t.body_lines(BODY, h, 200)[1]


def test_only_a_bare_name_means_latest():
    assert t._same_model("m:latest", "m") and t._same_model("m", "m:latest")
    assert not t._same_model("m:2b", "m:4b") and not t._same_model("m:2b", "m")
    assert not t._same_model("", "m")


def test_an_unsensed_body_is_said_not_drawn_as_zero():
    assert t.body_lines({}, {}, 200) == ["body: not sensed (the daemon did not answer /body)"]
    assert t.body_lines({"unavailable": "sampler starting"}, {}, 200) == ["body: not sensed (sampler starting)"]
    no_mem = dict(BODY, memory={})
    assert t.body_lines(no_mem, {}, 200)[0] == "RAM  not sensed"


def test_body_lines_fit_the_width():
    assert all(len(l) <= 50 for l in t.body_lines(BODY, {"model": "m", "loaded_models": []}, 50))
