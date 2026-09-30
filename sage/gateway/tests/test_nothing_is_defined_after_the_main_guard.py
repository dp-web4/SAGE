"""Nothing may be defined below `if __name__ == "__main__":` in a module that can be RUN.

Measured 2026-09-22T07:07Z, the first beat after a reconciliation landed: `sage-heartbeat.service`
exited 1 within a second — `NameError: name 'install_kill_handler' is not defined` — while the
whole gateway suite was green. The port helper had appended fourteen module-level definitions to
the END of heartbeat.py, i.e. after the guard. Under `import` the guard is False, every def runs,
and every test passes. Under `python -m sage.gateway.heartbeat` — the way the unit starts the
being — execution reaches `sys.exit(main())` first and the names below it do not exist yet.

A test that imports the module cannot see this. This one parses it, which is the only way to ask
the question the runtime asks. Scope: sage/gateway (run as `-m` modules) and sage/scripts (run
directly, so the guard is always taken). Test modules are not scanned: pytest imports them, and
several define tests below their own guard by design of the `python test_x.py` convenience.
Everything after the FIRST guard is checked, so a second guard further down is covered too."""
import ast
from pathlib import Path

import pytest

SAGE = Path(__file__).resolve().parents[2]
MODULES = sorted(p for d in ("gateway", "scripts") for p in (SAGE / d).glob("*.py")
                 if p.name != "__init__.py")
DEFINES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Assign, ast.AnnAssign,
           ast.Import, ast.ImportFrom)


def _guard_index(body):
    for i, node in enumerate(body):
        if isinstance(node, ast.If) and "__main__" in ast.unparse(node.test):
            return i
    return None


def _after_guard(src: str):
    body = ast.parse(src).body
    i = _guard_index(body)
    if i is None:
        return None
    return [ast.unparse(n)[:60] for n in body[i + 1:] if isinstance(n, DEFINES)]


def test_the_scan_sees_something():
    assert len(MODULES) > 20, MODULES
    assert any(p.name == "heartbeat.py" for p in MODULES)


@pytest.mark.parametrize("path", MODULES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_the_main_guard_is_the_last_statement(path):
    after = _after_guard(path.read_text(encoding="utf-8"))
    if after is None:
        pytest.skip("no __main__ guard")
    assert not after, (f"{path.name}: {len(after)} definition(s) after the __main__ guard — invisible "
                       f"to every import-based test, undefined when the module is RUN: {after[:3]}")


def test_the_rule_catches_each_kind_of_late_definition():
    guard = 'if __name__ == "__main__":\n    main()\n'
    for late in ("def f(): pass", "class C: pass", "X = 1", "X: int = 1", "import os",
                 "from os import path", "async def g(): pass"):
        assert _after_guard("def main(): pass\n" + guard + late + "\n"), late
    # a guard that is last, a second guard, and a module with none
    assert _after_guard("def main(): pass\n" + guard) == []
    assert _after_guard(guard + guard) == []
    assert _after_guard("x = 1\n") is None
