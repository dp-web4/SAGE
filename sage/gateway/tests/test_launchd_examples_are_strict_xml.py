"""Every launchd example parses as STRICT XML, not only under plutil.

McNugget, 2026-09-28: the heartbeat example (SAGE #246) had `--max-steps` inside an XML comment. XML
forbids `--` in a comment. `plutil -lint` accepts it, so the example "linted clean" -- but Python's
plistlib (expat) refuses it, and hestia's agent inventory reads launchd agents with plistlib. The
inventory could not read the installed heartbeat, found no launcher, and reported the being
UNPROVISIONED while it was beating every 30 minutes. A lint that is looser than the consumer is not
evidence the consumer can read the file.

Plain asserts, so a failure fails under pytest and the script runner alike.
Run: python3 sage/gateway/tests/test_launchd_examples_are_strict_xml.py   (or pytest)
"""
import plistlib
import re
import sys
from pathlib import Path

LAUNCHD = Path(__file__).resolve().parents[1] / "launchd"
EXAMPLES = sorted(LAUNCHD.glob("*.plist*"))


def test_there_is_something_to_check():
    assert EXAMPLES, f"no launchd examples under {LAUNCHD}"


def test_every_example_parses_with_plistlib():
    """plistlib is what hestia's agent inventory uses to find a being's launcher."""
    bad = []
    for f in EXAMPLES:
        try:
            plistlib.loads(f.read_bytes())
        except Exception as e:  # noqa: BLE001 -- any refusal is the finding
            bad.append(f"{f.name}: {type(e).__name__}: {e}")
    assert bad == [], bad


def test_no_comment_contains_a_double_hyphen():
    """The specific trap, named so the failure says what to change: XML forbids `--` inside
    `<!-- … -->`, and command-line flags are exactly where it turns up."""
    bad = []
    for f in EXAMPLES:
        for m in re.finditer(r"<!--(.*?)-->", f.read_text(), re.S):
            for line in m.group(1).splitlines():
                if "--" in line:
                    bad.append(f"{f.name}: {line.strip()[:80]}")
    assert bad == [], bad


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
