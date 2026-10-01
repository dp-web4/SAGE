"""shared-context is found beside the SAGE checkout, not assumed at ~/ai-workspace.

McNugget, 2026-09-28: mcnugget-being's FIRST escalation was written to ~/ai-workspace/shared-context
-- the Linux seats' layout -- which on McNugget is not a checkout (its repos are in ~/repos), so it
never landed; and every beat read the forum from a directory with no forum in it. Four sites had
the path hard-coded. They now share sage/gateway/fleet_paths.py.

Plain asserts, so a failure fails under pytest as well as the script runner.
Run: python3 sage/gateway/tests/test_shared_context_is_found_not_assumed.py   (or pytest)
"""
import importlib
import os
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
from sage.gateway import fleet_paths  # noqa: E402


def _with(sage_root, explicit=None, home=None):
    """fleet_paths re-read under a chosen SAGE root, override and HOME."""
    saved = (fleet_paths._SAGE_ROOT, os.getenv("SAGE_SHARED_CONTEXT"), os.getenv("HOME"))
    try:
        fleet_paths._SAGE_ROOT = Path(sage_root)
        if explicit is None:
            os.environ.pop("SAGE_SHARED_CONTEXT", None)
        else:
            os.environ["SAGE_SHARED_CONTEXT"] = explicit
        if home:
            os.environ["HOME"] = str(home)
        return fleet_paths.shared_context_root()
    finally:
        fleet_paths._SAGE_ROOT = saved[0]
        for k, v in (("SAGE_SHARED_CONTEXT", saved[1]), ("HOME", saved[2])):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_beside_the_sage_checkout_wins_over_the_old_default():
    with tempfile.TemporaryDirectory() as d:
        repos = Path(d) / "repos"; (repos / "SAGE").mkdir(parents=True); (repos / "shared-context").mkdir()
        assert _with(repos / "SAGE", home=Path(d)) == repos / "shared-context"


def test_the_linux_layout_resolves_to_exactly_the_old_path():
    """No behaviour change on the seats whose SAGE is ~/ai-workspace/SAGE."""
    with tempfile.TemporaryDirectory() as d:
        ws = Path(d) / "ai-workspace"; (ws / "SAGE").mkdir(parents=True); (ws / "shared-context").mkdir()
        assert _with(ws / "SAGE", home=Path(d)) == Path(d) / "ai-workspace" / "shared-context"


def test_an_explicit_override_wins():
    with tempfile.TemporaryDirectory() as d:
        repos = Path(d) / "repos"; (repos / "SAGE").mkdir(parents=True); (repos / "shared-context").mkdir()
        assert _with(repos / "SAGE", explicit=str(Path(d) / "elsewhere")) == Path(d) / "elsewhere"


def test_with_nothing_beside_it_falls_back_to_the_old_default():
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "lonely" / "SAGE").mkdir(parents=True)
        assert _with(Path(d) / "lonely" / "SAGE", home=Path(d)) == Path(d) / "ai-workspace" / "shared-context"


def test_no_gateway_module_hard_codes_the_path_again():
    """The four sites that did: escalate.NOTE_DIR and the forum defaults of heartbeat, governed_turn
    and dp_console. Comments may name the old path; code may not."""
    offenders = []
    for py in sorted((HERE.parent).glob("*.py")):
        if py.name == "fleet_paths.py":
            continue
        for n, line in enumerate(py.read_text().splitlines(), 1):
            code = line.split("#", 1)[0]
            if re.search(r"ai-workspace/shared-context", code):
                offenders.append(f"{py.name}:{n}")
    assert offenders == [], offenders


def test_escalations_land_in_the_resolved_checkout():
    from sage.gateway import escalate
    importlib.reload(escalate)
    assert escalate.NOTE_DIR == str(fleet_paths.escalations_dir())


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except AssertionError as e:
                fails += 1
                print(f"FAIL {name}: {e}")
    print(f"{'FAILED' if fails else 'ok'}: {fails} failure(s)")
    sys.exit(1 if fails else 0)
