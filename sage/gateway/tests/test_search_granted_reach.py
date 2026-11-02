"""search with no worktree reads a grant outside the home (CBP, 2026-10-21).

cbp-being holds read grants on the governance snapshot and has no worktree. Its `search` calls
there -- `GateDecision(` across governance/hestia, `StateGuard` across its plugins -- were refused
15 times in 12 beats with "search reads a code-repository checkout", each costing an explore
step, and memory_read find only looks inside one file the being already knows. Now, with no
worktree, a search given an absolute path outside the home is a fixed read-only grep over it:
judged by the law like git grep, confined by the dispatcher to the verdict's reach, witnessed.
The home stays memory_read find's. Hermetic: real grep on temp dirs, a fake witness chain."""
import os
import subprocess
import sys
import types

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import being_gate_client as B  # noqa: E402
from sage.gateway.being_gate_client import BeingIntent  # noqa: E402
from sage.gateway.hestia_dispatch import HestiaF1aDispatcher as D  # noqa: E402


@pytest.fixture
def tree(tmp_path):
    home = tmp_path / "home"
    (home / "notes").mkdir(parents=True)
    (home / "notes" / "n.md").write_text("GateDecision in my notes\n")
    gov = tmp_path / "gov" / "plugins"
    (gov / "_shared").mkdir(parents=True)
    (gov / "_shared" / "single_gate.py").write_text(
        "class GateDecision:\n    pass\nd = GateDecision(verdict_available=False)\n")
    (gov / ".git").mkdir()
    (gov / ".git" / "x").write_text("GateDecision inside .git\n")
    other = tmp_path / "other"
    other.mkdir()
    (other / "secret.py").write_text("GateDecision elsewhere\n")
    return types.SimpleNamespace(home=str(home), gov=str(gov), other=str(other))


def _disp(t, reach, command=None):
    d = D.__new__(D)
    d.worktree = None
    d.memory_root = t.home
    d._verdict = types.SimpleNamespace(command=command, granted_reach=tuple(reach), granted=())
    d._call = lambda name, args: {"actionId": "act-r"} if name == "hestia_begin_action" else {}
    return d


def _cmd(args, t):
    return B.search_command(args, {"worktree": None, "memory_root": t.home})


def _search(d, t, args):
    """Dispatch as the real path does: the verdict carries the exact command the gate composed
    and judged for these args (being_gate_client composes with the same home)."""
    d._verdict.command = _cmd(args, t)
    return d._do_search(BeingIntent("search", args))


def test_with_no_worktree_and_a_granted_absolute_path_the_seat_composes_a_read_only_grep(tree):
    cmd = _cmd({"pattern": r"GateDecision\(", "path": tree.gov}, tree)
    assert cmd.startswith("grep -r -n -I -E -s --max-count=30 --exclude-dir=.git -e ")
    assert B.reach_search_target(cmd) == os.path.realpath(tree.gov)
    assert "'GateDecision\\(' --" in cmd, "the pattern is one quoted argv element"


def test_no_path_still_refuses_and_says_where_search_reads_here(tree):
    with pytest.raises(ValueError) as e:
        _cmd({"pattern": "x"}, tree)
    msg = str(e.value)
    assert msg == B.NO_WORKTREE_REFUSAL["search"]
    assert "absolute path" in msg and "Reach you hold" in msg and "memory_read" in msg


@pytest.mark.parametrize("path,says", [
    ("notes", "not an absolute path"),
    ("governance/hestia", "not an absolute path"),
])
def test_a_relative_path_is_refused_with_the_absolute_form_named(tree, path, says):
    with pytest.raises(ValueError) as e:
        _cmd({"pattern": "x", "path": path}, tree)
    assert says in str(e.value) and "memory_read" in str(e.value)


def test_the_home_stays_memory_read_finds(tree):
    with pytest.raises(ValueError) as e:
        _cmd({"pattern": "x", "path": os.path.join(tree.home, "notes")}, tree)
    assert "does not read your home" in str(e.value) and "and find" in str(e.value)


def test_a_path_that_does_not_exist_is_said_so_not_searched(tree):
    with pytest.raises(ValueError) as e:
        _cmd({"pattern": "x", "path": tree.gov + "/nope"}, tree)
    assert "does not exist" in str(e.value)


def test_the_dispatcher_runs_the_judged_grep_inside_the_grant(tree):
    d = _disp(tree, [(os.path.realpath(tree.gov), True)])
    r = _search(d, tree, {"pattern": r"GateDecision\(", "path": tree.gov})
    assert r.ok and r.witness_id == "act-r"
    assert r.result["matches"] == 1
    assert r.result["lines"][0].endswith("single_gate.py:3:d = GateDecision(verdict_available=False)")
    assert not any(".git" in ln for ln in r.result["lines"]), ".git is skipped"


def _recording(d):
    calls = []
    d._call = lambda name, args: calls.append(name) or {"actionId": "x"}
    return calls


def test_a_verdict_with_no_command_authorizes_nothing_even_inside_the_reach(tree):
    # Review hold on #505: `judged is not None and judged != cmd` let a command-less verdict
    # through, so a matching reach grant alone ran a freshly composed grep.
    d = _disp(tree, [(os.path.realpath(tree.gov), True)], command=None)
    calls = _recording(d)
    r = d._do_search(BeingIntent("search", {"pattern": "GateDecision", "path": tree.gov}))
    assert not r.ok and "nothing authorized this search" in r.error
    assert calls == [], "no witness opened, no grep run"
    d._verdict.command = ""
    r = d._do_search(BeingIntent("search", {"pattern": "GateDecision", "path": tree.gov}))
    assert not r.ok and "nothing authorized this search" in r.error and calls == []


def test_no_verdict_at_all_authorizes_nothing(tree):
    d = _disp(tree, [(os.path.realpath(tree.gov), True)])
    del d._verdict
    calls = _recording(d)
    r = d._do_search(BeingIntent("search", {"pattern": "GateDecision", "path": tree.gov}))
    assert not r.ok and "nothing authorized this search" in r.error and calls == []


def test_a_target_outside_the_verdicts_reach_is_refused_and_nothing_runs(tree):
    # judged == executed holds here (the law, by hypothesis, allowed it); the reach still refuses
    d = _disp(tree, [(os.path.realpath(tree.gov), True)])
    calls = _recording(d)
    r = _search(d, tree, {"pattern": "GateDecision", "path": tree.other})
    assert not r.ok and "outside the reach you hold" in r.error
    assert calls == [], "no witness opened, no grep run"


def test_an_exact_grant_covers_itself_only(tree):
    f = os.path.join(tree.gov, "_shared", "single_gate.py")
    d = _disp(tree, [(os.path.realpath(f), False)])
    ok = _search(d, tree, {"pattern": "class", "path": f})
    assert ok.ok and ok.result["matches"] == 1
    no = _search(d, tree, {"pattern": "class", "path": tree.gov})
    assert not no.ok and "outside the reach" in no.error


def test_a_judged_command_that_differs_is_refused(tree):
    d = _disp(tree, [(os.path.realpath(tree.gov), True)], command="grep -r -e x -- /")
    calls = _recording(d)
    r = d._do_search(BeingIntent("search", {"pattern": "x", "path": tree.gov}))
    assert not r.ok and "law judged is not the command" in r.error and calls == []


def test_no_match_is_a_bounded_absence_and_a_bad_regex_is_never_one(tree):
    d = _disp(tree, [(os.path.realpath(tree.gov), True)])
    miss = _search(d, tree, {"pattern": "zzz_absent", "path": tree.gov})
    assert miss.ok and miss.result["matches"] == 0 and "WHAT WAS SEARCHED" in miss.result["note"]
    bad = _search(d, tree, {"pattern": "a(", "path": tree.gov})
    assert not bad.ok and "not an absence" in bad.error


def test_search_is_not_marked_unavailable_on_a_seat_with_no_worktree():
    from sage.gateway import toolset
    un = toolset.unavailable({"inventory": {"verbs": []}}, None, {})
    assert "search" not in un
    assert "git_read" in un, "the other worktree verbs still say they cannot work here"


def test_the_gate_composes_a_reach_search_for_a_seat_with_no_worktree(tree):
    c = B.BeingGateClient.__new__(B.BeingGateClient)
    c.worktree = None
    c.memory_root = tree.home
    ev_cmd = B._REGISTRY["search"]["compose"]({"pattern": "x", "path": tree.gov}, c._compose_ctx())
    assert B.reach_search_target(ev_cmd) == os.path.realpath(tree.gov)
