"""A being's executable tree identifies its commit AND its uncommitted edits, and says loudly
when either is not reviewed main.

2026-09-25/26: an uncommitted guard ran in the live SAGE tree for ~12 h, then a stash pop took
the run-request path down. No beat record could say which code had run — the record carried a
head and `dirty: true`, which is the same for every possible edit. GPT's review asked for the
invariant: commit + explicit dirty-state digest, surfaced every beat."""
import subprocess

from sage.gateway import heartbeat as H
from sage.scripts import harness_state as S


def _repo(tmp_path):
    origin, ws = tmp_path / "origin.git", tmp_path / "ws"
    g = lambda *a, cwd=ws: subprocess.run(["git", "-C", str(cwd), *a], check=True, capture_output=True, text=True)
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    subprocess.run(["git", "clone", "-q", str(origin), str(ws)], check=True, capture_output=True)
    g("config", "user.email", "t@t"); g("config", "user.name", "t"); g("checkout", "-q", "-b", "main")
    (ws / "code.py").write_text("x = 1\n")
    inst = ws / "sage" / "instances" / "b"; inst.mkdir(parents=True)
    (inst / "journal.md").write_text("day one\n")
    g("add", "-A"); g("commit", "-q", "-m", "c"); g("push", "-q", "origin", "main")
    return ws, g


def test_clean_main_is_clean_and_names_only_the_commit(tmp_path):
    ws, g = _repo(tmp_path)
    (ws / "sage" / "instances" / "b" / "journal.md").write_text("day two\n")
    rev = H.harness_revision(str(ws))
    assert rev["state"] == "clean" and rev["on_main"] is True and rev["dirty_digest"] is None
    assert rev["identity"] == rev["short"]
    assert H.harness_alarm(rev) is None
    assert S.main(["--workspace", str(ws)]) == 0


def test_dirty_digest_identifies_the_edit_set(tmp_path):
    ws, g = _repo(tmp_path)
    (ws / "code.py").write_text("x = 2\n")
    a = H.harness_revision(str(ws))
    assert a["state"] == "dirty" and a["dirty_digest"] and a["identity"].startswith(a["short"] + "+")
    assert H.harness_revision(str(ws))["dirty_digest"] == a["dirty_digest"], "same edits, same digest"
    (ws / "code.py").write_text("x = 3\n")
    b = H.harness_revision(str(ws))
    assert b["dirty_digest"] != a["dirty_digest"], "a different edit on the same head is different code"
    (ws / "code.py").write_text("x = 2\n")
    (ws / "new_guard.py").write_text("GUARD = True\n")
    c = H.harness_revision(str(ws))
    assert c["dirty_digest"] not in (a["dirty_digest"], b["dirty_digest"]), "untracked source is running code too"
    alarm = H.harness_alarm(c)
    assert alarm.startswith("LIVE TREE DIRTY") and c["identity"] in alarm and "code.py" in alarm
    assert S.main(["--workspace", str(ws)]) == 1


def test_large_same_size_untracked_files_are_told_apart(tmp_path):
    """Two different untracked files of the same size above 1 MiB must not share a digest."""
    ws, g = _repo(tmp_path)
    big = ws / "weights.bin"
    big.write_bytes(b"a" * (3 << 20))
    a = H.harness_revision(str(ws))["dirty_digest"]
    big.write_bytes(b"a" * ((3 << 20) - 1) + b"b")
    b = H.harness_revision(str(ws))["dirty_digest"]
    assert a and b and a != b, "same path, same size, different bytes is different code"
    big.write_bytes(b"a" * (3 << 20))
    assert H.harness_revision(str(ws))["dirty_digest"] == a


def test_untracked_files_under_instances_do_not_count(tmp_path):
    ws, g = _repo(tmp_path)
    (ws / "sage" / "instances" / "b" / "scratch.py").write_text("print(1)\n")
    assert H.harness_revision(str(ws))["state"] == "clean"


def test_a_nested_worktree_is_named_not_counted(tmp_path):
    ws, g = _repo(tmp_path)
    (ws / "scratchpad").mkdir()
    g("worktree", "add", "-q", "-b", "side", str(ws / "scratchpad" / "wt"))
    (ws / "scratchpad" / "wt" / "code.py").write_text("x = 'edited in the other checkout'\n")
    rev = H.harness_revision(str(ws))
    assert rev["state"] == "clean" and rev["nested_checkouts"] == ["scratchpad/wt/"]
    (ws / "scratchpad" / "loose.py").write_text("y = 1\n")
    rev = H.harness_revision(str(ws))
    assert rev["state"] == "dirty" and rev["dirty_paths"] == ["scratchpad/loose.py"], "a loose file beside it still counts"


def test_a_clean_local_commit_is_unmerged(tmp_path):
    ws, g = _repo(tmp_path)
    (ws / "code.py").write_text("x = 9\n"); g("commit", "-qam", "local fix")
    rev = H.harness_revision(str(ws))
    assert rev["dirty"] is False and rev["on_main"] is False and rev["ahead_of_main"] == 1
    assert rev["state"] == "unmerged" and H.harness_alarm(rev).startswith("LIVE TREE UNMERGED")
    g("push", "-q", "origin", "main"); g("fetch", "-q")
    assert H.harness_revision(str(ws))["state"] == "clean", "once merged (and fetched) it is main"


def test_no_origin_main_is_unknown_not_clean(tmp_path):
    g = lambda *a: subprocess.run(["git", "-C", str(tmp_path), *a], check=True, capture_output=True)
    g("init", "-q"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
    (tmp_path / "c.py").write_text("x\n"); g("add", "-A"); g("commit", "-qm", "c")
    rev = H.harness_revision(str(tmp_path))
    assert rev["state"] == "unknown" and H.harness_alarm(rev).startswith("LIVE TREE UNKNOWN")


def test_main_prints_the_alarm_every_beat():
    import ast
    from pathlib import Path
    src = Path(H.__file__).read_text()
    main = [n for n in ast.parse(src).body if getattr(n, "name", "") == "main"][0]
    seg = ast.get_source_segment(src, main)
    assert "harness_alarm(_harness)" in seg and "file=sys.stderr" in seg[seg.index("harness_alarm(_harness)"):][:200]


def test_the_harness_revision_never_takes_the_index_lock(monkeypatch, tmp_path):
    """status and diff refresh the index as a side effect, under .git/index.lock. If the beat's
    timeout kills git mid-refresh the lock is left and every later git act in the checkout fails
    (nomad, 2026-09-28 and 2026-09-29). Every git the harness revision starts must pass
    --no-optional-locks, except the plumbing that never locks."""
    import subprocess
    from sage.gateway import heartbeat
    seen = []
    real = subprocess.run

    def spy(cmd, *a, **k):
        if cmd and cmd[0] == "git":
            seen.append(tuple(cmd))
        return real(cmd, *a, **k)

    monkeypatch.setattr(subprocess, "run", spy)
    root = __import__("pathlib").Path(heartbeat.__file__).resolve().parents[2]
    heartbeat.harness_revision(str(root))
    locking = [c for c in seen if any(v in c for v in ("status", "diff"))]
    assert locking, "expected the revision to run git status/diff"
    assert all(c[1] == "--no-optional-locks" for c in locking), locking
