"""While a turn waits for the being, the console polls fast and says what the beat is doing (SAGE #788).

dp, 2026-11-18, after a demo: a model that answers quickly and shows it is working feels more capable.
The console looked for the being's reply every 20 s (a 10 s reply could take 30 s to appear) and said
only "1 awaiting the being". These tests lift the functions out of dashboard.html and run them under
node, so what is pinned is behaviour, not a string:

  * pollDelay: 2 s while a turn waits, 20 s otherwise;
  * waitingLine: says "writing its answer" ONLY when the heartbeat reported its answer phase, otherwise
    names the phase it is in, or that no beat is running; nothing when nothing waits;
  * waitingState (dp, 2026-11-19: no cancelling an in-flight call; let it complete, then switch
    attention, and show 'busy' rather than 'thinking' meanwhile): 'thinking' only in the answer phase,
    'busy' while any other phase runs, 'waiting' when no beat runs;
  * loadConversations(poll=true) rebuilds the log only when the conversation grew, so a 2 s poll
    neither flickers nor resets the scroll; a non-poll load still always rebuilds.

Run: python3 sage/gateway/tests/test_console_waiting_for_the_being.py   (or pytest)
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

HTML = (Path(__file__).resolve().parents[3] / "sage-rs/sage-daemon/src/dashboard.html").read_text()

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def _function(name: str) -> str:
    for head in (f"async function {name}(", f"function {name}("):
        if head in HTML:
            start = HTML.index(head)
            break
    else:
        raise AssertionError(f"{name} is not in dashboard.html")
    depth, i = 0, HTML.index("{", start)
    while True:
        c = HTML[i]
        depth += c == "{"
        depth -= c == "}"
        i += 1
        if depth == 0:
            return HTML[start:i]


def _const(name: str) -> str:
    start = HTML.index(f"const {name} =")
    return HTML[start:HTML.index(";", start) + 1]


def _node(prog: str, arg) -> dict:
    out = subprocess.run(["node", "-e", prog, json.dumps(arg)], text=True, capture_output=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


PURE = "\n".join([_const("POLL_IDLE_MS"), _const("POLL_WAITING_MS"), _function("fmtAge"),
                  _function("pollDelay"), _function("waitingState"), _function("waitingLine")])


def _line(beats, awaiting, being="mcnugget-being"):
    prog = PURE + """
const A = JSON.parse(process.argv[1]);
process.stdout.write(JSON.stringify({line: waitingLine(A.being, A.beats, A.awaiting),
                                     state: waitingState(A.beats, A.awaiting),
                                     delay: pollDelay(A.awaiting)}));
"""
    return _node(prog, {"beats": beats, "awaiting": awaiting, "being": being})


def test_polls_fast_only_while_a_turn_waits():
    assert _line(None, 0)["delay"] == 20000
    assert _line(None, 1)["delay"] == 2000
    assert _line(None, 3)["delay"] == 2000


def test_nothing_waiting_says_nothing():
    assert _line({"current": {"phase": "answer", "age_secs": 5}}, 0)["line"] is None


def test_writing_its_answer_only_in_the_answer_phase():
    got = _line({"current": {"phase": "answer", "age_secs": 30}}, 1)["line"]
    assert "writing its answer now" in got and got.startswith("thinking \u00b7 1 turn waiting")
    for phase in ("explore", "posture", "reflect", "account", "start"):
        got = _line({"current": {"phase": phase, "age_secs": 294}}, 1)["line"]
        assert "writing" not in got, phase
        assert phase in got and "runs to completion before it answers" in got, got


def test_no_beat_running_is_said_plainly():
    got = _line({"current": None, "since_last_beat_end_secs": 125}, 2)["line"]
    assert got.startswith("waiting \u00b7 2 turns waiting") and "no beat is running" in got
    assert "waiting for a beat to start" in _line({}, 1)["line"]
    assert "mcnugget-being" in _line({"current": {"phase": "explore", "age_secs": 1}}, 1)["line"]
    assert "the being" in _line({"current": {"phase": "explore", "age_secs": 1}}, 1, being=None)["line"]


def test_busy_while_a_step_runs_thinking_only_when_answering():
    """dp, 2026-11-19: the in-flight call completes; meanwhile the console says busy, not thinking."""
    for phase in ("explore", "posture", "reflect", "account", "start"):
        got = _line({"current": {"phase": phase, "age_secs": 121}}, 1)
        assert got["state"] == "busy", phase
        assert got["line"].startswith("busy \u00b7 ") and "thinking" not in got["line"], got
    got = _line({"current": {"phase": "answer", "age_secs": 4}}, 1)
    assert got["state"] == "thinking" and got["line"].startswith("thinking \u00b7 ")
    assert _line({"current": None, "since_last_beat_end_secs": 9}, 1)["state"] == "waiting"
    assert _line({"current": {"phase": "explore", "age_secs": 9}}, 0)["state"] is None


def _poll(listing: list, shown: int, poll: bool) -> dict:
    prog = """
let convs = [], convId = 'dp', convRefused = false;
let shownCount = null;
const loaded = []; let rendered = 0;
const classes = new Set();
const convNote = { textContent: '', classList: { add: c => classes.add(c), remove: c => classes.delete(c) },
                   appendChild() {} };
const convSelect = { innerHTML: '', value: null, appendChild() {} };
const document = { createElement() { return {}; } };
const location = { port: '8760', hostname: 'mcnugget' };
const escapeHtml = s => String(s);
const convWritable = c => (c.writable_by || []).includes('dp');
async function loadConversation(id) { loaded.push(id); }
function renderConvState() { rendered += 1; }
const BASE = '';
const A = JSON.parse(process.argv[1]);
shownCount = A.shown;
async function fetch() { return { ok: true, status: 200, json: async () => ({conversations: A.listing}) }; }
""" + _function("loadConversations") + """
loadConversations(A.poll).then(() => process.stdout.write(JSON.stringify({loaded, rendered})));
"""
    return _node(prog, {"listing": listing, "shown": shown, "poll": poll})


DP = {"id": "dp", "title": "dp", "writable_by": ["dp"], "awaiting_being": 1, "count": 40}


def test_a_poll_rebuilds_the_log_only_when_the_conversation_grew():
    same = _poll([DP], shown=40, poll=True)
    assert same == {"loaded": [], "rendered": 1}
    grew = _poll([dict(DP, count=41, awaiting_being=0)], shown=40, poll=True)
    assert grew["loaded"] == ["dp"]


def test_a_non_poll_load_always_rebuilds():
    assert _poll([DP], shown=40, poll=False)["loaded"] == ["dp"]


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
