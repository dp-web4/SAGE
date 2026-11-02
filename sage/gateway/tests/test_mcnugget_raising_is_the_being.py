"""McNugget's raising launcher raises THE BEING by name, never an instance derived from a model.

dp, 2026-10-03: "the raising script should work with the being, we don't need a 'fallback'". The
launcher read the daemon's model from /health, fell back to the literal "gemma3:12b", and derived the
instance name from it whenever SAGE_INSTANCE was unset. A model-named instance is how this machine
grew empty homes on model swaps (mcnugget-gemma4-e4b: 0 sessions), and `sage.session --machine
mcnugget` resolves the model-named home unless SAGE_INSTANCE is exported first.

Plain asserts, so a failure fails under pytest as well as the script runner.
Run: python3 sage/gateway/tests/test_mcnugget_raising_is_the_being.py   (or pytest)
"""
import re
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "mcnugget_raising_fluid.sh"


def _code_lines():
    return [ln for ln in SCRIPT.read_text().splitlines() if not ln.lstrip().startswith("#")]


def test_the_script_parses():
    p = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr


def test_the_being_is_exported_before_the_session_runs():
    lines = _code_lines()
    export = next((i for i, ln in enumerate(lines)
                   if re.search(r'^\s*export SAGE_INSTANCE="\$\{SAGE_INSTANCE:-mcnugget-being\}"', ln)), None)
    session = next((i for i, ln in enumerate(lines) if "-m sage.session" in ln), None)
    assert export is not None, "SAGE_INSTANCE is not exported with the being as its default"
    assert session is not None, "the raising session call moved; update this test"
    assert export < session, "SAGE_INSTANCE must be exported before sage.session resolves an instance"


def test_no_instance_is_derived_from_a_model():
    code = "\n".join(_code_lines())
    assert "gemma3:12b" not in code, "a model fallback is back"
    assert not re.search(r"mcnugget-\$\{[A-Z_]*MODEL", code), "the instance name is derived from a model again"


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
