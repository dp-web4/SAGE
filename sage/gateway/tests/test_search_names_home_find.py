"""A search that misses the worktree names memory_read find for a home file (SAGE #781).

2026-11-18: mcnugget-being searched heartbeats.jsonl for `transport_faults` twice and was told home
files "cannot be searched at all" -- untrue since memory_read got `find` (#351). It then read the
1,949-line file from its start, with every hit far past the window, across parts of 3 beats."""
import subprocess
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sage.gateway.being_gate_client import BeingIntent  # noqa: E402
from sage.gateway.hestia_dispatch import HestiaF1aDispatcher as D  # noqa: E402


def _disp(tmp_path, home_files=()):
    wt = tmp_path / "wt"; (wt / "pkg").mkdir(parents=True)
    (wt / "pkg" / "mod.py").write_text("x = 1\n")
    subprocess.run(["git", "init", "-q", str(wt)], check=True)
    subprocess.run(["git", "-C", str(wt), "add", "-A"], check=True, capture_output=True)
    home = tmp_path / "home"; home.mkdir()
    for name in home_files:
        (home / name).write_text('{"egress": {"transport_faults": []}}\n')
    d = D.__new__(D); d.worktree = str(wt); d.memory_root = str(home)
    d._verdict = types.SimpleNamespace(command=None)
    d._call = lambda n, a: {"actionId": "act-s"} if n == "hestia_begin_action" else {}
    return d


def _search(d, path, pattern):
    return d._do_search(BeingIntent("search", {"pattern": pattern, "path": path}))


def test_a_home_file_gets_the_exact_find_call(tmp_path):
    env = _search(_disp(tmp_path, ["heartbeats.jsonl"]), "heartbeats.jsonl", "transport_faults")
    assert env.ok is False and "NOT an absence" in env.error
    assert "IS a file in your instance home" in env.error, env.error
    assert 'memory_read {"path": "heartbeats.jsonl", "find": "transport_faults"}' in env.error, env.error
    assert "cannot be searched at all" not in env.error


def test_a_regex_pattern_is_not_handed_to_literal_find(tmp_path):
    env = _search(_disp(tmp_path, ["todo.md"]), "todo.md", r"done\(")
    assert '"find": "<literal text>"' in env.error and "not a regex" in env.error, env.error


def test_a_path_in_neither_tree_names_find_without_claiming_the_file_exists(tmp_path):
    env = _search(_disp(tmp_path), "nowhere.md", "abc")
    assert env.ok is False and "IS a file" not in env.error, env.error
    assert "memory_read that file with find" in env.error, env.error
    assert "cannot be searched at all" not in env.error


def test_a_path_escaping_the_home_is_not_called_a_home_file(tmp_path):
    (tmp_path / "outside.txt").write_text("abc\n")
    env = _search(_disp(tmp_path), "../outside.txt", "abc")
    assert "IS a file in your instance home" not in (env.error or ""), env.error


def test_memory_read_find_does_reach_the_home_file_the_refusal_names(tmp_path):
    from sage.gateway.reference_f1a import ReferenceF1aDispatcher
    from sage.gateway.being_gate_client import GatewayVerdict
    home = tmp_path / "h"; home.mkdir()
    rows = ['{"n": %d, "egress": {"transport_faults": []}}' % i for i in range(1, 2000)]
    rows[1500] = '{"n": 1501, "egress": {"transport_faults": [{"why": "send-failed"}]}}'
    (home / "heartbeats.jsonl").write_text("\n".join(rows) + "\n")
    env = ReferenceF1aDispatcher(memory_root=str(home))(
        BeingIntent("memory_read", {"path": "heartbeats.jsonl", "find": "send-failed"}),
        GatewayVerdict("allow"))
    assert env.ok and "1501" in env.result, env.result[:400]
