"""The seed names the being's model, window and harness revision — measured, never inferred.

legion-being's home was named for the model it was born on (legion-gemma3-12b). Running a 27B, it
read that name as its own size ("the physical limit of my body — 12B model"); after the name was
explained it read the same directory as ANOTHER being's scratch. A being reasons about its limits
from its sensors, and a directory name is a false one the day the model changes. And it asked, on
2026-09-07, how to tell whether a `check` result was about the code actually running it — it had no
way to learn that commit."""
import subprocess
from pathlib import Path

from sage.gateway import heartbeat as H


def test_body_line_names_the_model_and_window_and_disowns_the_directory_name():
    line = H.body_line("qwen38-heretic:q3km-vl", Path("/x/sage/instances/legion-gemma3-12b"), 24576)
    assert "qwen38-heretic:q3km-vl" in line and "24576 tokens" in line
    assert "legion-gemma3-12b" in line and "YOURS" in line, "the old name is explained, and it is its own"


def test_body_line_after_a_move_says_where_it_moved_from():
    line = H.body_line("m", Path("/x/legion-being"), 24576,
                       [{"path": "/x/legion-gemma3-12b", "moved": "2026-09-19"}])
    assert "/x/legion-gemma3-12b" in line and "FROZEN" in line and "older name" not in line


def test_harness_revision_is_the_code_not_the_diary(tmp_path):
    g = lambda *a: subprocess.run(["git", "-C", str(tmp_path), *a], check=True, capture_output=True, text=True)
    g("init", "-q"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
    (tmp_path / "code.py").write_text("x = 1\n")
    inst = tmp_path / "sage" / "instances" / "b"; inst.mkdir(parents=True)
    (inst / "journal.md").write_text("day one\n")
    g("add", "-A"); g("commit", "-q", "-m", "c")
    head = g("rev-parse", "HEAD").stdout.strip()
    (inst / "journal.md").write_text("day two — the being writes its diary every beat\n")
    rev = H.harness_revision(str(tmp_path))
    assert rev["head"] == head and rev["short"] and head.startswith(rev["short"])
    assert rev["dirty"] is False, "the being's own journal is not an uncommitted edit to the harness"
    (tmp_path / "code.py").write_text("x = 2\n")
    assert H.harness_revision(str(tmp_path))["dirty"] is True


def test_main_puts_both_into_the_header_and_the_record():
    import ast
    src = Path(H.__file__).read_text()
    main = [n for n in ast.parse(src).body if getattr(n, "name", "") == "main"][0]
    calls = {getattr(c.func, "id", "") for c in ast.walk(main) if isinstance(c, ast.Call)}
    assert {"body_line", "harness_revision"} <= calls
    seg = ast.get_source_segment(src, main)
    assert '"harness": _harness' in seg
