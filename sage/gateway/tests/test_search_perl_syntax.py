"""search: Perl regex syntax that Python's `re` accepts runs as the ERE that means the same thing.

McNugget 2026-11-20 (Apple git 2.50, BSD grep 2.6.0): `git grep -E '\\d+'` matched the letter d, `\\s` and
`\\b` matched nothing (so `def\\sfor` and `\\bfor_beat\\b` came back as absences), and `.*?`, `+?`, `(?:`
exited 128. mcnugget-being sent 26 such searches: 14 failed, 9 came back "absent", 3 hit. The pattern
is rewritten when the command is composed, so the command the law judges is the command that runs.

The property pinned here: on a real repository, through the real git grep and grep, every line Python's
`re` finds is found (no false absence), and without a word boundary, exactly those lines."""
import os
import re
import shlex
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway.being_gate_client import search_command, search_mode, search_regex  # noqa: E402
from sage.gateway.hestia_dispatch import _literal_key  # noqa: E402

SOURCE = """\
import os
def for_beat(instance, workspace):
    see PR #792 and PR  #793
    x = 12 + y_2
    forum_beats = before_beat()
def\tfor_all(): pass
\tindented line
hub_notify_path(root)
hub_notify(x)
literal \\d and \\s stay literal
"""

PERL = [
    r"\d+",
    r"PR\s*#\d+",
    r"def\sfor",
    r"def .*?\(",
    r"hub_notify\w*\(",
    r"hub_notify_path\(.*?\)",
    r"(?:for|before)_beat",
    r"[\d_]+",
    r"[^\s]+_beat",
    r"y_\d",
    r"\D\d",
    r"\Aimport",
    r"\S+\(\)$",
    r"x{2}?|12",
    r"\W#",
]
WORD = [r"\bfor_beat\b", r"\bbeat\b"]


@pytest.fixture(scope="module")
def wt():
    d = os.path.realpath(tempfile.mkdtemp(prefix="srchp-"))
    subprocess.run(["git", "init", "-q", d], check=True)
    with open(os.path.join(d, "beats.py"), "w") as f:
        f.write(SOURCE)
    subprocess.run(["git", "-C", d, "add", "."], check=True)
    return d


# A hit is `path:line:text`, except GNU grep on a single file, which prints `line:text` (BSD grep names the
# file either way). The text itself may hold colons, so the prefix is matched, not split off.
_HIT = re.compile(r"^(?:.*?(?:beats\.py|esc\.txt):)?\d+:(.*)$")


def _lines(cmd):
    r = subprocess.run(shlex.split(cmd), capture_output=True, text=True)
    assert r.returncode in (0, 1), (cmd, r.returncode, r.stderr)
    return {_HIT.match(ln).group(1) for ln in r.stdout.splitlines()}


def _python(pattern):
    return {ln for ln in SOURCE.splitlines() if re.search(pattern, ln)}


def _both(pattern, wt):
    yield search_command({"pattern": pattern}, {"worktree": wt})
    yield search_command({"pattern": pattern, "path": os.path.join(wt, "beats.py")}, {})


@pytest.mark.parametrize("pattern", PERL)
def test_perl_syntax_finds_exactly_what_it_means(pattern, wt):
    mode, ran, note = search_regex(pattern)
    assert mode == "-E" and ran != pattern and note, (pattern, ran)
    want = _python(pattern)
    assert want, f"fixture should hold a line for {pattern!r}"
    for cmd in _both(pattern, wt):
        assert _lines(cmd) == want, (pattern, ran, cmd)


@pytest.mark.parametrize("pattern", WORD)
def test_a_dropped_word_boundary_only_widens(pattern, wt):
    mode, ran, note = search_regex(pattern)
    assert mode == "-E" and "\\b" not in ran and "partial words" in note
    for cmd in _both(pattern, wt):
        assert _python(pattern) <= _lines(cmd), (pattern, cmd)


def test_without_the_rewrite_these_were_false_absences_or_failures(wt):
    """What the being got before, on this box: the reason for the change, measured each run."""
    raw = {p: subprocess.run(["git", "-C", wt, "grep", "-n", "-E", "-e", p, "--", "beats.py"],
                             capture_output=True, text=True) for p in (r"def\sfor", r"def .*?\(")}
    seen = {p: (r.returncode, {_HIT.match(ln).group(1) for ln in r.stdout.splitlines()}) for p, r in raw.items()}
    # Linux (glibc) ERE knows \s, BSD's does not; neither knows a lazy quantifier everywhere.
    wrong = [p for p, (rc, got) in seen.items() if rc > 1 or got != _python(p)]
    if not wrong:
        pytest.skip("this platform's ERE already reads these Perl shapes")
    assert wrong


@pytest.mark.parametrize("pattern", [r"(?=beat)", r"(?i)beat", r"(?P<n>x)", r"a++", r"[\S]", r"[\D]"])
def test_what_ere_cannot_say_is_searched_literally(pattern):
    assert search_regex(pattern) == ("-F", pattern, "")
    assert search_mode(pattern) == "-F"
    assert "literal" in _literal_key(pattern)


@pytest.mark.parametrize("pattern", [r"a|b", r"def compose\(", r"[[:digit:]]+", r"\.\*", r"x\\d", "plain"])
def test_an_ere_already_is_unchanged_and_says_nothing(pattern, wt):
    assert search_regex(pattern) == ("-E", pattern, "")
    assert _literal_key(pattern) == {}
    argv = shlex.split(search_command({"pattern": pattern}, {"worktree": wt}))
    assert "-E" in argv and argv[argv.index("-e") + 1] == pattern


def test_the_receipt_names_what_ran():
    key = _literal_key(r"PR\s*#\d+")
    assert set(key) == {"translated"}
    assert "PR[[:space:]]*#[[:digit:]]+" in key["translated"]


def test_the_judged_command_is_the_one_that_runs(wt):
    cmd = search_command({"pattern": r"def .*?\("}, {"worktree": wt})
    argv = shlex.split(cmd)
    assert argv[argv.index("-e") + 1] == r"def .*\("


ESC_SOURCE = "def\tfor_all(): pass\nbell\x07 here\nback\x08space\nx]y\na-b\ncaret^c\nslash\\s\nfoo.bar\nA hex\n"
ESCAPES = [r"def\tfor", r"[\t]for", r"[\b]", r"bell\a", r"[\a]", r"x[\]]y", r"a[\-]b", r"caret[\^]c",
           r"slash[\\]s", r"foo[\.]bar", r"\x41 hex", r"[\x41] hex", r"A hex", r"\0"]


@pytest.fixture(scope="module")
def esc_wt():
    d = os.path.realpath(tempfile.mkdtemp(prefix="srchp-esc-"))
    subprocess.run(["git", "init", "-q", d], check=True)
    with open(os.path.join(d, "esc.txt"), "w") as f:
        f.write(ESC_SOURCE)
    subprocess.run(["git", "-C", d, "add", "."], check=True)
    return d


@pytest.mark.parametrize("pattern", ESCAPES)
def test_an_escape_naming_one_character_is_never_a_false_absence(pattern, esc_wt):
    """NOVA (#797 review): `[\\b]` is a backspace in Python, not a word boundary. The same class:
    `\\t`, `\\a`, `\\x41` and an escaped `]` `-` `^` in a bracket were absences on BSD git grep."""
    mode, ran, note = search_regex(pattern)
    assert mode == "-E" and "\\" not in ran.replace("[\\]", ""), (pattern, ran)
    want = {ln for ln in ESC_SOURCE.splitlines() if re.search(pattern, ln)}
    got = _lines(search_command({"pattern": pattern}, {"worktree": esc_wt}))
    assert want <= got, (pattern, ran, want, got)


def test_a_bracket_ere_cannot_spell_runs_as_any_character_and_says_so():
    mode, ran, note = search_regex(r"x[\]]y")
    assert (mode, ran) == ("-E", "x.y") and "any character" in note


def test_backspace_in_a_bracket_is_not_a_word_boundary():
    mode, ran, note = search_regex(r"[\b]")
    assert ran == "[[:cntrl:]]" and "word boundaries" not in note
