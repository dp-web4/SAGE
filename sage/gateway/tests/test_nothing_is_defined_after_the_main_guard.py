"""Nothing may be defined below `if __name__ == "__main__":` in a module that is RUN.

Measured 2026-09-22T07:07Z, the first beat after a reconciliation landed: `sage-heartbeat.service`
exited 1 within a second — `NameError: name 'install_kill_handler' is not defined` — while the
whole gateway suite was green. The port helper had appended fourteen module-level definitions to
the END of heartbeat.py, i.e. after the guard. Under `import` the guard is False, every def runs,
and every test passes. Under `python -m sage.gateway.heartbeat` — the way the unit starts the
being — execution reaches `sys.exit(main())` first and the names below it do not exist yet.

A test that imports the module cannot see this. This one parses it, which is the only way to ask
the question the runtime asks. hestia_dispatch had seven such definitions the same day, harmless
only because nothing runs it as __main__."""
import ast
from pathlib import Path

import pytest

GATEWAY = Path(__file__).resolve().parent.parent
MODULES = sorted(p for p in GATEWAY.glob("*.py") if p.name != "__init__.py")


def _guard_index(body):
    for i, node in enumerate(body):
        if isinstance(node, ast.If) and "__main__" in ast.unparse(node.test):
            return i
    return None


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_the_main_guard_is_the_last_statement(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    i = _guard_index(tree.body)
    if i is None:
        pytest.skip("no __main__ guard")
    after = [ast.unparse(n)[:60] for n in tree.body[i + 1:]
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Assign, ast.Import, ast.ImportFrom))]
    assert not after, (f"{path.name}: {len(after)} definition(s) after the __main__ guard — invisible "
                       f"to every import-based test, undefined when the module is RUN: {after[:3]}")
