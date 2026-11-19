"""git_read op='cat' reads a file from its start, in parts that say where they are.

mcnugget-being, 2026-11-17 13:28Z and 14:10Z: three `cat`s of sage/gateway/egress_drain.py (329 lines,
18.7k chars) per beat, and each returned the same LAST 6,000 chars behind "[… truncated: 12756 earlier
characters withheld …]". The top of the file was never shown, and `start_line: '200'` was not taken."""
import os
import subprocess
import sys
import types

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway.being_gate_client import BeingIntent, _TOOL_SCHEMAS as TOOL_SCHEMAS  # noqa: E402
from sage.gateway.hestia_dispatch import HestiaF1aDispatcher as D, cat_window  # noqa: E402

LINES = [f"line {i:03d} " + "x" * 50 for i in range(1, 331)]       # 330 lines, ~20k chars


def _d(tmp_path):
    wt = tmp_path / "wt"
    (wt / "pkg").mkdir(parents=True)
    (wt / "pkg" / "big.py").write_text("\n".join(LINES) + "\n")
    (wt / "pkg" / "small.py").write_text("a = 1\nb = 2\n")
    for c in (["init", "-q"], ["add", "-A"],
              ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "x"]):
        subprocess.run(["git", "-C", str(wt)] + c, check=True, capture_output=True)
    d = D.__new__(D)
    d.worktree = str(wt)
    d._verdict = types.SimpleNamespace(command=None)
    d._call = lambda name, args: {"actionId": "act-g"} if name == "hestia_begin_action" else {}
    d._worktree_revision = lambda: {}
    return d


def _cat(d, **kw):
    r = d._do_git_read(BeingIntent("git_read", {"op": "cat", "path": "pkg/big.py", **kw}))
    assert r.ok, r.error
    return r.result["output"]


def test_a_long_file_starts_at_its_top_and_names_the_start_line_that_reads_on(tmp_path):
    out = _cat(_d(tmp_path))
    assert out.startswith("[lines 1-"), out[:80]
    assert "line 001 " in out and "withheld" not in out
    nxt = int(out.rsplit("start_line ", 1)[1].split()[0])
    assert f"[lines {nxt}-330 are not shown: git_read op 'cat' path 'pkg/big.py' start_line {nxt} reads on]" in out
    assert f"\nline {nxt - 1:03d} " in out and f"\nline {nxt:03d} " not in out, "whole lines, none skipped"
    assert len(out) < 6300


def test_start_line_is_taken_even_as_a_string_and_the_parts_cover_the_file(tmp_path):
    d = _d(tmp_path)
    out = _cat(d, start_line="200")
    assert out.startswith("[lines 200-299 of 330 of 'pkg/big.py'; lines 1-199 are above]")
    assert "start_line 300 reads on]" in out
    seen, start = [], 1
    for _ in range(10):
        part = _cat(d, start_line=start)
        seen += [ln for ln in part.split("\n") if ln.startswith("line ")]
        if part.endswith("[that is the end]"):
            break
        start = int(part.rsplit("start_line ", 1)[1].split()[0])
    assert seen == LINES


def test_a_file_that_fits_is_unchanged_and_a_line_past_the_end_says_so(tmp_path):
    d = _d(tmp_path)
    r = d._do_git_read(BeingIntent("git_read", {"op": "cat", "path": "pkg/small.py"}))
    assert r.result["output"] == "a = 1\nb = 2"
    assert _cat(d, start_line=999) == ("['pkg/big.py' has 330 lines, so start_line 999 names no line. "
                                       "start_line 1 reads it from the top.]")


def test_other_ops_keep_their_cut():
    assert cat_window("a\nb", "x", 10) == "a\nb", "an unreadable start_line reads from the top"


def test_the_schema_offers_start_line_for_cat():
    params = TOOL_SCHEMAS["git_read"][1]
    assert "start_line" in params and "op='cat'" in params["start_line"]
