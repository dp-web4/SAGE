"""A failing `check` says WHICH tests failed and why, and compaction keeps that sentence whole.

legion-being, #272, 2026-09-30..10-01: the check headline said "FAIL -- 1 failed, 13 passed"
and the failing test's name and error line sat in the middle of `output`. Compaction keeps a
result's first and last 200 characters, so on a long beat the being could see THAT it failed and
never WHICH or WHY. It spent a day reading saved spills through scripts, and edited code that
was already right to satisfy a test it could not read.
"""
import json
import os
import subprocess
import sys
import tempfile

from sage.gateway.being_gate_client import ResultEnvelope
from sage.gateway.being_tool_loop import (COMPACT_KEEP_CHARS, HEADLINE_KEEP_MAX, _ELIDED_SIGIL,
                                          compact_convo)
from sage.gateway.hestia_dispatch import (CHECK_FAILURES_SHOWN, check_failures, check_headline)


def _real_pytest_output(n_fail=2, n_pass=3):
    """A REAL pytest run (same flags as check's inner command) of a suite with failures."""
    d = tempfile.mkdtemp(prefix="check-real-")
    src = "".join(f"def test_ok_{i}():\n    assert True\n\n" for i in range(n_pass))
    src += "".join(f"def test_bad_{i}():\n    assert {i} == {i} + 1, 'off by one in case {i}'\n\n"
                   for i in range(n_fail))
    open(os.path.join(d, "test_sample.py"), "w").write(src)
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-c", "/dev/null", "-p",
                        "no:cacheprovider", f"--rootdir={d}", "test_sample.py"], cwd=d, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def test_the_failures_are_read_from_pytests_own_summary():
    rc, out = _real_pytest_output(2, 3)
    assert rc == 1
    f = check_failures(out)
    assert [t for t, _ in f] == ["test_sample.py::test_bad_0", "test_sample.py::test_bad_1"]
    assert "off by one in case 0" in f[0][1]
    assert check_failures("5 passed in 0.01s") == []


def test_a_failing_headline_names_each_failing_test_and_its_error():
    rc, out = _real_pytest_output(2, 3)
    h = check_headline(False, out.strip().splitlines()[-1], check_failures(out))
    assert h.startswith("FAIL — ") and "Failing (2): test_sample.py::test_bad_0 — " in h
    assert "off by one in case 1" in h
    assert "'the call worked' is not 'the tests passed'" in h, "the old warning stays"
    passing = check_headline(True, "5 passed", [])
    assert passing.startswith("PASS — 5 passed.") and "Failing" not in passing


def test_many_failures_are_counted_not_listed_without_end():
    f = [(f"t.py::test_{i}", "AssertionError: " + "x" * 400) for i in range(10)]
    h = check_headline(False, "10 failed", f)
    assert h.count("t.py::test_") == CHECK_FAILURES_SHOWN
    assert f"and {10 - CHECK_FAILURES_SHOWN} more" in h
    assert len(h) < HEADLINE_KEEP_MAX, "a capped headline still fits the kept prefix"


def _check_message(passed, out):
    """The tool message the being receives for a check result, rendered as the loop renders it."""
    f = check_failures(out)
    result = {"headline": check_headline(passed, out.strip().splitlines()[-1], f),
              "target": "gateway", "passed": passed, "verdict": "PASS" if passed else "FAIL",
              "failures": [{"test": t, "error": m} for t, m in f],
              "output": "." * 6000 + "\n" + out, "evidence": {"command": "x" * 500}}
    return ResultEnvelope(ok=True, result=result, witness_id="w1").to_tool_message()


class _LLM16k:
    num_ctx = 16384


def test_an_elided_check_result_keeps_its_whole_headline():
    """The real path: envelope -> tool message -> compaction. The failing test names survive."""
    rc, out = _real_pytest_output(2, 3)
    body = _check_message(False, out)
    msgs = ([{"role": "system", "content": "S" * 6600}, {"role": "user", "content": "U" * 30000},
             {"role": "assistant", "content": "A"}, {"role": "tool", "content": body},
             {"role": "assistant", "content": "A"}, {"role": "tool", "content": "last" * 10}])
    compacted, el = compact_convo(msgs, _LLM16k())
    stub = compacted[3]["content"]
    assert _ELIDED_SIGIL in stub, "the result WAS elided (else this proves nothing)"
    assert "test_sample.py::test_bad_0" in stub and "off by one in case 1" in stub
    headline = json.loads(body[:body.index('", "target"') + 1] + "}")["headline"]
    assert stub.startswith(body[:len(headline)]), "the headline is kept from the start, whole"
    rec = el[0]
    assert rec["chars"] + rec["kept"] == len(body), "the accounting names what was really kept"


def test_a_body_without_a_headline_is_elided_as_before():
    plain = "x" * 6000 + "\nFAILED tests/test_a.py::test_b\n1 failed, 182 passed"
    msgs = [{"role": "user", "content": "u" * 3000},
            {"role": "assistant", "content": ""}, {"role": "tool", "content": plain},
            {"role": "assistant", "content": ""}, {"role": "tool", "content": "y" * 3000}]

    class LLM:
        num_ctx = 4000
    out, el = compact_convo(msgs, LLM())
    assert out[2]["content"].startswith("x" * (COMPACT_KEEP_CHARS // 2) + "\n[…")
    assert el[0]["chars"] == len(plain) - COMPACT_KEEP_CHARS


def test_an_overlong_headline_is_cut_like_any_body():
    body = json.dumps({"headline": "FAIL — " + "z" * (HEADLINE_KEEP_MAX + 500), "output": "o" * 9000})
    msgs = ([{"role": "system", "content": "S" * 6600}, {"role": "user", "content": "U" * 30000},
             {"role": "assistant", "content": "A"}, {"role": "tool", "content": body},
             {"role": "assistant", "content": "A"}, {"role": "tool", "content": "last" * 10}])
    out, el = compact_convo(msgs, _LLM16k())
    assert el and el[0]["kept"] == COMPACT_KEEP_CHARS, "no unbounded protected prefix"
