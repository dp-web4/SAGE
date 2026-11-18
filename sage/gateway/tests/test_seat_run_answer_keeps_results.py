"""A long run answer keeps its result lines in the part the being sees (#290).

The beat shows a long turn's first 2/5 and last 3/5 of the window. cbp-being 2026-11-12: the head kept
the banner's expectation ("scores near 1.0") and the cut took the measured `Mean identifiability score:
0.4548`; the being re-requested the same bytes 19 times. 2026-11-16: the tail was four copies of one
ConvergenceWarning and all 24 result lines were cut."""
import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "seat_run_requests.py"
_spec = importlib.util.spec_from_file_location("seat_run_requests", _SCRIPT)
srr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(srr)

CAP = 1200
HEADER = "[request_run] I ran scratch/t.py (sha 7f1eaaba50bf) with no arguments. exit code 0."
ANSWERS = "This answers your request seq 14647."
BANNER = ("=" * 60 + "\nIdentifiability test\nExpectation: Gaussian latents: scores near 1.0\n"
          "Expectation: Laplace latents: scores near 0.0\n" + "=" * 60 + "\n")


def _shown(text):
    return srr.as_shown(text, CAP)[0]


def _ident_out():
    rows = "".join(f"  [{i * 0.1:.4f} {i * 0.2:.4f} {i * 0.3:.4f} {i * 0.4:.4f}]\n" for i in range(20))
    return (BANNER + "Gaussian run...\n" + rows + "Mean identifiability score: 0.4548\n" + rows
            + "Mean identifiability score (Laplace): 0.5447\nCONCLUSION: no separation\n")


def test_the_11_12_hidden_result_is_copied_into_the_shown_tail():
    out = _ident_out()
    before = srr._compose(HEADER, srr._block("stdout", out), [], 0, srr._block("stderr", ""), ANSWERS,
                          "That is the whole output, unedited. Nothing is owed by you on this.")
    assert "Mean identifiability score: 0.4548" not in _shown(before), "the defect: the number is cut"
    text, lifted, dropped = srr.run_answer(HEADER, out, "", ANSWERS, CAP)
    shown = _shown(text)
    assert "Mean identifiability score: 0.4548" in shown, shown
    assert lifted >= 1 and dropped == 0
    assert shown.index("Lines with numbers from stdout") < shown.index("stderr: (empty)")
    assert text.endswith("Nothing is owed by you on this.") and ANSWERS in shown
    assert out.rstrip() in text, "stdout itself is posted whole and in place"


def test_the_11_16_repeated_warnings_are_counted_and_results_take_their_room():
    warn = ("/usr/lib/python3/sklearn/neural_network/_multilayer_perceptron.py:691: ConvergenceWarning: "
            "Stochastic Optimizer: Maximum iterations (1000) reached and the optimization hasn't converged yet.\n"
            "  warnings.warn(\n")
    out = "XOR classifier\nXOR is NOT linearly separable. A linear model should score ~50%.\n" + "".join(
        f"seed {s}: LogisticRegression 0.{50 + s}  MLP(4,) 0.{70 + s}  MLP(64,32) 0.{90 + s}\n" for s in range(8)
    ) + "CONCLUSION: the MLPs separate XOR\n"
    text, lifted, dropped = srr.run_answer(HEADER, out, warn * 4, ANSWERS, CAP)
    shown = _shown(text)
    assert "[the 2 lines above, 3 more times]" in text
    assert text.count("ConvergenceWarning") == 1
    assert "a run of repeated lines is shown once and counted" in text
    assert shown == text and (lifted, dropped) == (0, 0), "counted once, the whole answer fits"


def test_a_table_too_long_for_the_tail_keeps_its_newest_lines_and_says_how_many_did_not_fit():
    out = "XOR classifier\nA linear model should score ~50%.\n" + "".join(
        f"seed {s} {m}: train accuracy 0.{60 + s}{i}, test accuracy 0.{50 + s}{i}, loss 0.{30 + s}{i}1\n" for s in range(8) for i, m in enumerate(
            ("LogisticRegression", "MLP(4,)", "MLP(64,32)"))) + "CONCLUSION: the MLPs separate XOR\n"
    text, lifted, dropped = srr.run_answer(HEADER, out, "", ANSWERS, CAP)
    shown = _shown(text)
    assert lifted >= 1 and dropped >= 1
    assert "seed 7 MLP(64,32): train accuracy 0.672, test accuracy 0.572, loss 0.3721" in shown
    assert f"({dropped} earlier one{'s' if dropped != 1 else ''} did not fit here)" in shown
    assert ANSWERS in shown and "stderr: (empty)" in shown


def test_a_crash_keeps_its_traceback_last_and_still_lifts_what_fits():
    out = _ident_out().replace("CONCLUSION: no separation\n", "")
    err = ("Traceback (most recent call last):\n  File \"scratch/t.py\", line 102, in <module>\n"
           "    corr = np.corrcoef(a, b)[0, 1]\nValueError: shapes (10,) and (1,) not aligned\n")
    text, lifted, _ = srr.run_answer(HEADER.replace("exit code 0", "exit code 1"), out, err, ANSWERS, CAP)
    shown = _shown(text)
    assert "ValueError: shapes (10,) and (1,) not aligned" in shown
    assert shown.index("Lines with numbers") < shown.index("Traceback")
    assert "Mean identifiability score: 0.4548" in shown


def test_a_long_traceback_takes_priority_over_lifting():
    err = "Traceback (most recent call last):\n" + "".join(
        f"  File \"/site-packages/torch/nn/m{i}.py\", line {i}, in f{i}\n    return self.g{i}(x)\n" for i in range(12)
    ) + "RuntimeError: mat1 and mat2 shapes cannot be multiplied\n"
    text, lifted, dropped = srr.run_answer(HEADER, _ident_out(), err, ANSWERS, CAP)
    assert lifted == 0 and dropped >= 1
    assert "RuntimeError: mat1 and mat2" in _shown(text)
    assert "Lines with numbers" not in text


def test_an_answer_that_fits_is_unchanged():
    text, lifted, dropped = srr.run_answer(HEADER, "loss 0.1\nloss 0.1\n", "", ANSWERS, CAP)
    assert (lifted, dropped) == (0, 0)
    assert text == "\n".join([HEADER, "", "stdout:\nloss 0.1\nloss 0.1", "", "stderr: (empty)", "", ANSWERS,
                              "That is the whole output, unedited. Nothing is owed by you on this."])


def test_collapse_repeats():
    assert srr.collapse_repeats("a\na\na\nb") == ("a\n[the line above, 2 more times]\nb", 2)
    assert srr.collapse_repeats("w\nx\nw\nx\ny") == ("w\nx\n[the 2 lines above, 1 more time]\ny", 2)
    assert srr.collapse_repeats("a\nb\nc") == ("a\nb\nc", 0)
    assert srr.collapse_repeats("\n\n\nz") == ("\n\n\nz", 0), "blank runs are left alone"


def test_what_counts_as_a_result_line():
    assert srr.is_result_line("Final correlation: -1.000000")
    assert srr.is_result_line("Final correlation: nan"), "the 10-04 nan was a result too"
    assert srr.is_result_line("R2: 0.91")
    assert not srr.is_result_line("  [1.2e-05 3.4e-06 -5E+02]"), "an array row's only letters are exponents"
    assert not srr.is_result_line("  [0.1000 0.2000]")
    assert not srr.is_result_line("Training finished")
    assert not srr.is_result_line("Running inference now")
