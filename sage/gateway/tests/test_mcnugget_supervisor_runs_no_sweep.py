"""McNugget's supervisor launches no ARC sweep and loads no model.

dp, 2026-10-03: "we are no longer doing arc sweeps. you can fully disable it and remove the model".
Step 2 launched dev-SAGE's sweep_all_25.py on phi4-fa whenever dev-SAGE moved, as `nohup … &` from a
launchd job, which reaps it when the job exits: 583 launches, 0 finished games, and a 9 GB model kept
on a 16 GB machine beside the being's. phi4 is removed from the seat, so a sweep put back would also
fail at the model.

Plain asserts, so a failure fails under pytest as well as the script runner.
Run: python3 sage/gateway/tests/test_mcnugget_supervisor_runs_no_sweep.py   (or pytest)
"""
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "mcnugget_supervisor.sh"


def _code():
    return "\n".join(ln for ln in SCRIPT.read_text().splitlines() if not ln.lstrip().startswith("#"))


def test_the_script_parses():
    p = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr


def test_no_sweep_is_launched():
    assert "sweep_all_25" not in _code(), "the ARC sweep launch is back"


def test_no_model_is_configured():
    code = _code()
    for token in ("phi4", "SAGE_OLLAMA_MODEL"):
        assert token not in code, f"{token} is configured again"


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
