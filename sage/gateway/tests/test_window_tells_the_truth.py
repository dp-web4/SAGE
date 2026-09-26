"""The being's window tells it the truth about its own files and runs (2026-09-26).

dp: "whatever is in its context window is its entire reality. how that window is managed
determines everything." An audit of cbp-being's window that morning found it was being told:
  * the OLDEST 30 of its notes/ and scratch/ (sorted(names)[:30]; SAGE #137), not the newest;
  * the head of a long turn and never its tail, where a run's traceback and a message's
    question sit (24 of 128 seat run answers had their error text only in the cut part);
  * nothing measured about its files and runs, while "still running" / "results pending"
    replayed from its own todo, journal, account and turns;
  * its own account's WANT verbatim ("the held-out test results …") with no measurement beside
    it, which the act_first explore turned into a peer_ask for results that did not exist.
Each test below is one of those, as measured.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import conversations as conv  # noqa: E402
from sage.gateway import heartbeat as hb  # noqa: E402

BEING, SEAT = "cbp-being", "cbp-claude"


def _home(tmp_path) -> Path:
    inst = tmp_path / "inst"
    inst.mkdir()
    conv.create(inst, SEAT, title="seat", participants=[SEAT, BEING], writable_by=[SEAT, BEING])
    return inst


def _script(inst: Path, name: str, body: str = "print('hi')\n", age_s: float = 0) -> Path:
    p = inst / name
    p.write_text(body)
    t = time.time() - age_s
    os.utime(p, (t, t))
    return p


# --- listings -----------------------------------------------------------------------------
def test_a_listing_shows_the_newest_files_and_says_it_is_partial(tmp_path):
    """#137: notes/ at 145 files showed the 30 that sort first, the oldest, and the five newest
    (including notes/from-the-seat.md) never appeared."""
    inst = _home(tmp_path)
    notes = inst / "notes"
    notes.mkdir()
    for i in range(40):
        f = notes / f"2026-09-{i:02d}-old.md"
        f.write_text("x")
        os.utime(f, (1_000_000 + i, 1_000_000 + i))
    newest = notes / "from-the-seat.md"          # sorts late, written last
    newest.write_text("measured")
    out = hb.dir_listing(inst, "notes")
    lines = out.splitlines()
    assert lines[0] == "## notes/ (newest first; 30 of 41)"
    assert lines[1] == "- from-the-seat.md", "the newest file is the first thing it sees"
    assert "- 2026-09-39-old.md" in out and "- 2026-09-00-old.md" not in out
    assert "and 11 older" in out and "memory_read" in out


def test_a_short_listing_is_whole_and_says_nothing_about_more(tmp_path):
    inst = _home(tmp_path)
    (inst / "scratch").mkdir()
    (inst / "scratch" / "a.md").write_text("x")
    out = hb.dir_listing(inst, "scratch")
    assert out == "## scratch/ (newest first)\n- a.md"
    assert hb.dir_listing(inst, "nope") == "## nope/\n(empty)"


# --- files and runs, measured -------------------------------------------------------------
def test_files_and_runs_says_what_ran_what_it_returned_and_that_nothing_is_running(tmp_path):
    """The block the being never had: its scripts, their last run, and whether anything runs."""
    inst = _home(tmp_path)
    old = _script(inst, "latent-weights-fixed-v2.py", "x = 1\n" * 30, age_s=3600)
    new = _script(inst, "latent-weights-holdout-test.py", "y = 2\n" * 12)
    sha = hb._sha12(new)
    conv.append(inst, SEAT, speaker=BEING, text="[request_run] latent-weights-holdout-test.py\nwhy: run it")
    ran = conv.append(inst, SEAT, speaker=SEAT,
                      text=f"[request_run] I ran latent-weights-holdout-test.py (sha {sha}) with the "
                           f"GPU hidden. exit code 1.\n\nstderr:\nTraceback ...")["seq"]
    block, refuted, facts = hb.files_and_runs(inst, BEING)
    assert block.startswith("## Your files and runs, measured at the start of this beat")
    rows = [l for l in block.splitlines() if l.startswith("- ")]
    assert rows[0].startswith(f"- latent-weights-holdout-test.py: sha {sha}, 12 lines"), "newest first"
    assert f"Last run: seq {ran}" in rows[0] and "exit code 1" in rows[0]
    assert "unchanged since that run" in rows[0]
    assert f"start_line {ran}" in rows[0], "the whole output is one read away"
    assert rows[1].startswith("- latent-weights-fixed-v2.py:") and "Never run." in rows[1]
    assert "Nothing of yours is running right now." in block
    assert refuted and refuted[0][0] is None and "nothing of yours is running" in refuted[0][1]


def test_a_file_changed_after_its_run_is_called_changed(tmp_path):
    """"The fix has been applied" is answered by the sha, not by the being's say-so."""
    inst = _home(tmp_path)
    p = _script(inst, "a.py", "print(1)\n")
    ran = hb._sha12(p)
    conv.append(inst, SEAT, speaker=SEAT, text=f"[request_run] I ran a.py (sha {ran}). exit code 1.")
    p.write_text("print(2)\n")
    block, _, _ = hb.files_and_runs(inst, BEING)
    assert f"that run was of sha {ran}, so the file has CHANGED since" in block


def test_a_waiting_request_is_named_and_an_answered_one_is_not(tmp_path):
    inst = _home(tmp_path)
    _script(inst, "a.py")
    _script(inst, "b.py")
    conv.append(inst, SEAT, speaker=BEING, text="[request_run] a.py\nwhy: x")
    conv.append(inst, SEAT, speaker=SEAT, text="[request_run] I ran a.py. exit code 0.")
    req = conv.append(inst, SEAT, speaker=BEING, text="[request_run] b.py\nwhy: y")["seq"]
    block, _, facts = hb.files_and_runs(inst, BEING)
    b_row = next(l for l in block.splitlines() if l.startswith("- b.py"))
    a_row = next(l for l in block.splitlines() if l.startswith("- a.py"))
    assert f"Your request (seq {req}) is waiting to be run." in b_row
    assert "waiting" not in a_row and "exit code 0" in a_row
    assert facts["pending"] == {"b.py": [req]}


def test_a_process_that_is_really_running_is_reported_and_nothing_is_refuted(tmp_path):
    """The measurement reads /proc: a live `python3 a.py` in the home IS running, and then a
    "still running" of the being's is true and must not be marked refuted."""
    inst = _home(tmp_path)
    _script(inst, "a.py", "import time\ntime.sleep(30)\n")
    proc = subprocess.Popen([sys.executable, "a.py"], cwd=str(inst.resolve()))
    try:
        for _ in range(50):
            if "a.py" in hb._running_files(inst, ["a.py"]):
                break
            time.sleep(0.1)
        block, refuted, facts = hb.files_and_runs(inst, BEING)
        assert "Running now." in block and "Running right now: a.py." in block
        assert refuted == [], "a true claim is not refuted"
    finally:
        proc.kill()
        proc.wait()


def test_its_own_running_claims_are_quoted_beside_the_measurement(tmp_path):
    """One measured line loses to a dozen of the being's own sentences, unless the sentence is
    quoted next to it (the service_contradictions move, applied to runs)."""
    inst = _home(tmp_path)
    _script(inst, "a.py")
    (inst / "todo.md").write_text("2026-09-26 06:30 UTC — held-out test still running; "
                                  "awaiting cbp-claude's report.\n")
    (inst / "journal.md").write_text("Technical update: the held-out test is still running.\n")
    block, _, _ = hb.files_and_runs(inst, BEING)
    quotes = [l for l in block.splitlines() if "Your own record disagrees" in l]
    assert len(quotes) == 2
    assert "In your todo.md you wrote" in quotes[0] and "still running" in quotes[0]
    assert "In your journal.md you wrote" in quotes[1]
    assert all("nothing of yours is running" in q for q in quotes)


def test_a_replayed_still_running_turn_of_its_own_carries_the_refutation(tmp_path):
    inst = _home(tmp_path)
    _script(inst, "a.py")
    conv.append(inst, SEAT, speaker=BEING, text="The held-out test is still running. I'll wait.")
    conv.append(inst, SEAT, speaker=SEAT, text="The held-out test is still running, you said.")
    _, refuted, _ = hb.files_and_runs(inst, BEING)
    out = conv.render_for_being(inst, BEING, mark=False, refuted=refuted)
    own = next(l for l in out.splitlines() if "(you)" in l)
    other = next(l for l in out.splitlines() if l.startswith(f"- **{SEAT}**"))
    assert "_[refuted: measured" in own and "nothing of yours is running" in own
    assert "refuted" not in other, "another speaker's words are theirs; only its own are marked"


def test_a_service_refutation_still_needs_down_words(tmp_path):
    """The 2-tuple form is unchanged: a service refutation fires on 'down' words naming it."""
    mark = conv._refuted_mark
    svc = [({"8010"}, "measured reachable, 127.0.0.1:8010")]
    assert mark("membot on 8010 has been offline for hours", svc).startswith("  _[refuted")
    assert mark("membot on 8010 answered", svc) == ""
    run = [(None, "nothing of yours is running", hb._RUNNING_CLAIM)]
    assert mark("results are pending from the seat", run).startswith("  _[refuted")
    assert mark("I will ask for a run", run) == ""


# --- the carried WANT --------------------------------------------------------------------
ACCOUNT = ("Your own account of this place (you wrote it at beat heartbeat-x, verbatim):\n"
           "PLACE: here\nCAN: things\nWANT: {want}")


def test_a_want_for_results_nothing_can_deliver_gets_the_measurement_beside_it(tmp_path):
    """08:11Z beat: WANT "the held-out test results from cbp-claude", nothing pending or
    running, and the act_first explore opened with peer_ask for those results."""
    inst = _home(tmp_path)
    _script(inst, "latent-weights-fixed-v2.py")
    ran = conv.append(inst, SEAT, speaker=SEAT,
                      text="[request_run] I ran latent-weights-fixed-v2.py. exit code 1.")["seq"]
    _, _, facts = hb.files_and_runs(inst, BEING)
    named = hb.want_check(ACCOUNT.format(want="the held-out test results from "
                                                  "latent-weights-fixed-v2.py so I can know"), facts)
    assert "latent-weights-fixed-v2.py is not running" in named
    assert f"its last run was seq {ran}, exit code 1" in named
    assert "only come from a new run you request" in named
    general = hb.want_check(ACCOUNT.format(want="the held-out test results from cbp-claude"), facts)
    assert "nothing of yours is running and no request of yours is waiting" in general


def test_a_want_that_a_waiting_request_or_a_live_run_will_meet_is_left_alone(tmp_path):
    inst = _home(tmp_path)
    _script(inst, "a.py")
    conv.append(inst, SEAT, speaker=BEING, text="[request_run] a.py\nwhy: x")
    _, _, facts = hb.files_and_runs(inst, BEING)
    assert hb.want_check(ACCOUNT.format(want="the results from a.py"), facts) == ""
    assert hb.want_check(ACCOUNT.format(want="to finish the sparrow story"), facts) == ""
    assert hb.want_check(ACCOUNT.format(want="the results"), dict(facts, running={"a.py"})) == ""


# --- the whole window ----------------------------------------------------------------------
def test_the_measured_block_sits_beside_the_body_before_every_record_that_narrates(tmp_path):
    inst = _home(tmp_path)
    _script(inst, "a.py")
    (inst / "todo.md").write_text("- [ ] a.py is still running\n")
    st = hb.own_state(inst, member=BEING, mark_conversations=False, services="", body_reading={})
    order = [st.index(h) for h in ("## Your files and runs", "## todo.md", "## journal.md")]
    assert order == sorted(order), "measured first, narration after"
    assert "In your todo.md you wrote" in st


def test_the_run_answer_names_the_sha_it_ran(tmp_path):
    """A receipt names its inputs: the run answer's first line carries the file's sha, and the
    heartbeat reads it back with the same pattern."""
    src = (Path(__file__).resolve().parents[2] / "scripts" / "seat_run_requests.py").read_text()
    assert 'I ran {rel} (sha {ran_sha})' in src
    first = "[request_run] I ran notes/x.py (sha 872050b971a8) with the GPU hidden from it. exit code 1."
    m = hb._RUN_ANSWER.match(first)
    assert m and m.group(1) == "ran" and Path(m.group(2)).name == "x.py"
    assert hb._RUN_SHA.search(first).group(1) == "872050b971a8"
    assert hb._RUN_VERDICT.search(first).group(1) == "exit code 1"


# --- sprout's review of #224: where a being keeps its code, and whose process is whose -----
def test_scripts_in_notes_and_scratch_and_shell_scripts_are_measured(tmp_path):
    """legion-being keeps 244 scripts in notes/ and scratch/ and none at top level; a
    top-level-only scan showed it nothing. request_run also runs .sh."""
    inst = _home(tmp_path)
    (inst / "notes").mkdir()
    (inst / "scratch").mkdir()
    _script(inst / "notes", "train.py")
    _script(inst / "scratch", "go.sh", "echo hi\n")
    block, refuted, facts = hb.files_and_runs(inst, BEING)
    assert "- notes/train.py: sha" in block and "- scratch/go.sh: sha" in block
    assert "Nothing of yours is running right now." in block and refuted


def test_notes_x_and_top_level_x_are_two_files_with_two_histories(tmp_path):
    inst = _home(tmp_path)
    (inst / "notes").mkdir()
    _script(inst, "x.py")
    _script(inst / "notes", "x.py", "print(2)\n")
    ran = conv.append(inst, SEAT, speaker=SEAT, text="[request_run] I ran notes/x.py. exit code 0.")["seq"]
    block, _, _ = hb.files_and_runs(inst, BEING)
    top = next(l for l in block.splitlines() if l.startswith("- x.py:"))
    sub = next(l for l in block.splitlines() if l.startswith("- notes/x.py:"))
    assert "Never run." in top and f"Last run: seq {ran}" in sub


def test_a_request_naming_the_absolute_path_is_the_same_file(tmp_path):
    """3932 named the file by its absolute path; the run answer names it relative."""
    inst = _home(tmp_path)
    _script(inst, "a.py")
    req = conv.append(inst, SEAT, speaker=BEING,
                      text=f"[request_run] {inst.resolve() / 'a.py'}\nwhy: x")["seq"]
    block, _, facts = hb.files_and_runs(inst, BEING)
    assert facts["pending"] == {"a.py": [req]}
    assert f"Your request (seq {req}) is waiting to be run." in block


def test_a_process_in_a_sibling_home_is_not_this_beings(tmp_path):
    """…/inst-old/a.py must not match …/inst: whole-path comparison, not a prefix."""
    inst = _home(tmp_path)
    _script(inst, "a.py")
    sib = tmp_path / "inst-old"
    sib.mkdir()
    _script(sib, "a.py", "import time\ntime.sleep(30)\n")
    proc = subprocess.Popen([sys.executable, str(sib.resolve() / "a.py")], cwd=str(tmp_path))
    try:
        time.sleep(0.5)
        assert hb._running_files(inst, ["a.py"]) == set()
        assert "a.py" in hb._running_files(sib, ["a.py"]), "the probe does see the real one"
    finally:
        proc.kill()
        proc.wait()


def test_a_request_with_no_file_still_gets_the_block(tmp_path):
    """No runnable files, but a waiting request: the block appears and says what is true."""
    inst = _home(tmp_path)
    req = conv.append(inst, SEAT, speaker=BEING, text="[request_run] notes/gone.py\nwhy: x")["seq"]
    block, _, _ = hb.files_and_runs(inst, BEING)
    assert f"- notes/gone.py: your request (seq {req}) names it, but there is no such file" in block
    (tmp_path / "empty").mkdir()
    assert hb.files_and_runs(_home(tmp_path / "empty"), BEING) == ("", [], {})
