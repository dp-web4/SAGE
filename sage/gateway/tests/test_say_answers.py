"""A say records which turns it answers, and only those close (NOVA's hold on #675).

The live-time window (dead_s_of) keeps an old question open longer, so a later turn about something
else must not be what closes it. `say` writes `answers` on every turn: the seqs the being named, or []
when it named none. conversations.unanswered closes exactly what a turn names."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sage.gateway import conversations as conv  # noqa: E402
from sage.gateway.being_gate_client import BeingIntent  # noqa: E402
from sage.gateway.hestia_dispatch import _answer_seqs  # noqa: E402
from sage.gateway.tests.test_hestia_dispatch import _ALLOW, _disp  # noqa: E402

ME = "sprout-being"


def _home():
    d, root = _disp()
    home = Path(root)
    conv.create(home, "dp", title="dp", participants=["dp", ME], writable_by=["dp", ME])
    return d, home


def test_a_say_that_names_nothing_records_an_empty_answers_and_closes_nothing():
    d, home = _home()
    conv.append(home, "dp", speaker="dp", text="what did the click change?", enforce_write=False)
    r = d(BeingIntent("say", {"to": "dp", "text": "Status: still reading the source today."}), _ALLOW)
    assert r.ok, r.error
    assert conv.recent(home, "dp", limit=1)[-1]["answers"] == []
    assert r.result["answers"] == []
    assert [t["seq"] for t in conv.unanswered(home, "dp", ME)] == [1], "the question is still open"
    w = r.result["still_waiting"]
    assert w.startswith("1 in 'dp' is still waiting on you") and "named no turn it answers" in w, w


def test_a_say_that_names_its_turn_closes_it():
    d, home = _home()
    conv.append(home, "dp", speaker="dp", text="what did the click change?", enforce_write=False)
    r = d(BeingIntent("say", {"to": "dp", "text": "It set the latch on the first click.", "answers": "1"}),
          _ALLOW)
    assert r.ok, r.error
    assert conv.recent(home, "dp", limit=1)[-1]["answers"] == [1]
    assert conv.unanswered(home, "dp", ME) == [] and "still_waiting" not in r.result


def test_a_seq_that_is_not_someone_elses_turn_is_refused_and_nothing_is_sent():
    d, home = _home()
    conv.append(home, "dp", speaker="dp", text="what did the click change?", enforce_write=False)
    mine = d(BeingIntent("say", {"to": "dp", "text": "A first note of my own, about the board."}), _ALLOW)
    for bad in ("9", str(mine.result["seq"]), "soon"):
        r = d(BeingIntent("say", {"to": "dp", "text": "This answers it, I think.", "answers": bad}), _ALLOW)
        assert not r.ok and "nothing was sent" in r.error and "waiting on you there now: 1 (dp)" in r.error, \
            (bad, r.error)
    assert len(conv.recent(home, "dp")) == 2, "no refused turn reached the log"


def test_answer_seqs_reads_the_forms_a_being_writes():
    assert _answer_seqs(None) == ([], []) and _answer_seqs("") == ([], []) and _answer_seqs([]) == ([], [])
    assert _answer_seqs(12) == ([12], [])
    assert _answer_seqs([12, "14", 12]) == ([12, 14], [])
    assert _answer_seqs("12, 14") == ([12, 14], [])
    assert _answer_seqs("seq 12 and 14") == ([12, 14], [])
    assert _answer_seqs("#7") == ([7], [])
    assert _answer_seqs("0, x") == ([], ["0", "x"])
    assert _answer_seqs([True]) == ([], ["True"])
