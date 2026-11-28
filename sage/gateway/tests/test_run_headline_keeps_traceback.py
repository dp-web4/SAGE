"""A failed `run` leads with its traceback's verdict, and compaction keeps that sentence whole.

cbp-being, 2026-11-27: compaction keeps a result's first and last 200 characters. A run result is
JSON in key order (exit, stdout, stderr, note), so the kept head was the first stderr line (the
"Fontconfig error" warning matplotlib prints on every run in the box) and the kept tail was the
grants paragraph of `note`. The traceback's last line sat in the cut middle. The being blamed
the warning for exit 1, and at 18:24Z asked its seat "what's the traceback?" about a run whose
receipt held it.
"""
import os
import subprocess
import sys
import tempfile

from sage.gateway.being_gate_client import ResultEnvelope
from sage.gateway.being_tool_loop import HEADLINE_KEEP_MAX, _ELIDED_SIGIL, compact_convo
from sage.gateway.hestia_dispatch import _run_headline, _run_note

# The shape of the 2026-11-27 run: warnings first, then a numpy call on a torch tensor whose
# TypeError message runs over several lines. Reproduced with plain Python so no torch is needed.
_SCRIPT = '''import sys, warnings
sys.stderr.write("Fontconfig error: Cannot load default config file: No such file: (null)\\n")
warnings.warn("Unable to import Axes3D. This may be due to multiple versions of Matplotlib")

class Net:
    def train(self):
        loss = mean_of(self)
        return loss

def mean_of(x):
    raise TypeError("mean() received an invalid combination of arguments - got (axis=NoneType, ), "
                    "but expected one of:\\n * (*, torch.dtype dtype = None)\\n"
                    " * (tuple of ints dim, bool keepdim = False)")

Net().train()
'''


def _real_failed_run(name="xor-visualization-final.py"):
    d = tempfile.mkdtemp(prefix="run-headline-")
    p = os.path.join(d, name)
    open(p, "w").write(_SCRIPT)
    r = subprocess.run([sys.executable, name], cwd=d, capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr, d


def _run_message(rc, out, err, files, with_headline=True, stage=""):
    """The tool message for a run result, keyed as _do_run keys it."""
    h = _run_headline(rc, err, files, stage=stage) if with_headline else ""
    result = {"headline": h} if h else {}
    result.update({"script": files[0], "files": files, "exit": rc, "stdout": out.strip(),
                   "stderr": err.strip(), "note": _run_note(rc, err, files, out) + " grants " * 160,
                   "changed_in_your_grants": []})
    return ResultEnvelope(ok=True, result=result, witness_id="w1").to_tool_message()


class _LLM16k:
    num_ctx = 16384


def _compact(body):
    msgs = ([{"role": "system", "content": "S" * 6600}, {"role": "user", "content": "U" * 30000},
             {"role": "assistant", "content": "A"}, {"role": "tool", "content": body},
             {"role": "assistant", "content": "A"}, {"role": "tool", "content": "last" * 10}])
    out, _el = compact_convo(msgs, _LLM16k())
    return out[3]["content"]


def test_the_headline_quotes_the_exception_line_and_the_own_frame():
    rc, out, err, d = _real_failed_run()
    assert rc == 1 and err.startswith("Fontconfig error"), err
    h = _run_headline(rc, err, ["xor-visualization-final.py"], stage=d)
    assert h.startswith("Exit 1. The traceback at the end of stderr ends with: TypeError: mean() received"), h
    assert "line 11 of xor-visualization-final.py, in mean_of" in h, h
    assert "Fontconfig" not in h and "not what ended the run" in h
    assert len(h) < HEADLINE_KEEP_MAX


def test_an_elided_failed_run_keeps_the_verdict():
    """The real path: envelope -> tool message -> compaction. Control first: without the headline
    the verdict is cut, which is the defect; with it, the verdict survives."""
    rc, out, err, d = _real_failed_run()
    files = ["xor-visualization-final.py"]
    before = _compact(_run_message(rc, out, err, files, with_headline=False))
    assert _ELIDED_SIGIL in before, "the result WAS elided (else this proves nothing)"
    assert "Fontconfig error" in before and "TypeError" not in before, "the defect, as measured on the being"
    after = _compact(_run_message(rc, out, err, files, stage=d))
    assert _ELIDED_SIGIL in after
    assert "TypeError: mean() received an invalid combination" in after
    assert "line 11 of xor-visualization-final.py" in after


def test_no_headline_without_a_traceback_or_on_success():
    assert _run_headline(0, "Traceback (most recent call last):\n  File \"/work/a.py\", line 1, in <module>\nX: y", ["a.py"]) == ""
    assert _run_headline(1, "usage: bad option", ["a.py"]) == ""
    assert _run_headline(1, "", ["a.py"]) == ""
    # a traceback with no frame in a staged file says so rather than naming a library line as "yours"
    lib = ('Traceback (most recent call last):\n  File "/usr/lib/python3/x.py", line 9, in f\n'
           "    g()\nValueError: bad")
    h = _run_headline(1, lib, ["a.py"])
    assert "ValueError: bad" in h and "No frame of the traceback is in a file this run staged" in h


def test_the_last_traceback_wins_when_exceptions_chain():
    err = ('Traceback (most recent call last):\n  File "/work/a.py", line 2, in <module>\n'
           "    int('x')\nValueError: invalid literal\n\nDuring handling of the above exception, "
           'another exception occurred:\n\nTraceback (most recent call last):\n'
           '  File "/work/a.py", line 4, in <module>\n    raise KeyError("k")\nKeyError: \'k\'')
    h = _run_headline(1, err, ["a.py"])
    assert "KeyError: 'k'" in h and "line 4 of a.py" in h and "ValueError" not in h


_FRAME_A = '  File "/work/a.py", line 3, in step\n'


def test_a_traceback_that_did_not_end_the_run_is_not_its_verdict():
    """legion-claude on #844: a handled traceback, more output, then the wall-clock stop."""
    err = ("Traceback (most recent call last):\n" + _FRAME_A + "    risky()\nValueError: retrying\n"
           "epoch 1\nepoch 2\n[stopped: your code was still running after 60s (wall).]")
    assert _run_headline(-9, err, ["a.py"]) == ""
    stop = ("Traceback (most recent call last):\n" + _FRAME_A + "ValueError: x\n"
            "[stopped: your code used more memory than allowed.]")
    assert _run_headline(-9, stop, ["a.py"]) == ""
    # blank lines and indented continuations of the message are still the end of stderr
    cont = ("Traceback (most recent call last):\n" + _FRAME_A +
            "TypeError: bad call, expected one of:\n * (int x)\n * (str y)\n\n")
    assert "TypeError: bad call" in _run_headline(1, cont, ["a.py"])


def _lib_tb(own_path):
    lib = "/" + "/".join(["opt", "py", "site-packages", "pkg", "utils.py"])
    return ("Traceback (most recent call last):\n"
            f'  File "{own_path}", line 5, in main\n    load()\n'
            f'  File "{lib}", line 99, in load\n    raise OSError("x")\nOSError: x')


def test_a_library_file_with_a_staged_files_name_is_not_your_own():
    """legion-claude on #844: staged utils.py, deepest frame in a library's utils.py."""
    h = _run_headline(1, _lib_tb("/work/utils.py"), ["utils.py"])
    assert "line 5 of utils.py, in main" in h and "line 99" not in h, h
    # under Seatbelt the run's own file is at <stage>/<name>
    sb = _run_headline(1, _lib_tb("/st/stage-1/utils.py"), ["utils.py"], stage="/st/stage-1")
    assert "line 5 of utils.py, in main" in sb, sb
    # no frame where the run put the file: it says so rather than naming the library's line
    none = _run_headline(1, _lib_tb("/elsewhere/utils.py"), ["utils.py"])
    assert "No frame of the traceback is in a file this run staged" in none and "line 99" not in none
