"""A run's imports resolve from the being's home, as its file paths do.

The seat runs `python scratch/X.py` with cwd = home. Python puts scratch/ on sys.path, so
`from data.m import f` failed while `open("data/...")` worked: four runs on CBP spent on it.
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "seat_run_requests.py"
_spec = importlib.util.spec_from_file_location("seat_run_requests", _SCRIPT)
srr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(srr)


def _home(tmp_path: Path) -> Path:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "m.py").write_text("VALUE = 7\n")
    (tmp_path / "scratch").mkdir()
    (tmp_path / "scratch" / "x.py").write_text("from data.m import VALUE\nprint(VALUE)\n")
    return tmp_path


def _run(home: Path, env: dict):
    return subprocess.run([sys.executable, str(home / "scratch" / "x.py")], cwd=str(home),
                          env=env, capture_output=True, text=True, timeout=30)


def test_a_home_package_imports_from_a_scratch_script(tmp_path):
    home = _home(tmp_path)
    r = _run(home, srr.child_env(False, str(home)))
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "7"


def test_without_the_home_the_import_fails_as_measured(tmp_path, monkeypatch):
    monkeypatch.delenv("PYTHONPATH", raising=False)
    home = _home(tmp_path)
    r = _run(home, srr.child_env(False))
    assert "No module named 'data'" in r.stderr, "the control: this is the failure being fixed"


def test_the_seats_own_pythonpath_is_kept_after_the_home(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", "/seat/own")
    env = srr.child_env(False, str(tmp_path))
    assert env["PYTHONPATH"].split(":") == [str(tmp_path), "/seat/own"]
