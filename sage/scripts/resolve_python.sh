#!/usr/bin/env bash
# resolve_python.sh — pick a working python3 and export SAGE_PY. Source, don't exec.
#
#   . "$(dirname "$0")/resolve_python.sh"
#   "$SAGE_PY" -m sage.session ...
#
# Why this exists: every McNugget script used to hardcode /opt/homebrew/bin/python3.
# On 2026-07-29 a `brew upgrade` left python@3.14 unlinked (3.14.4 -> 3.14.3_1) and
# that path stopped existing. Under launchd the scripts exited 127 into a log nobody
# read, and raising was dead for 29 days before anyone noticed. Two failure modes
# caused that and both are handled here:
#
#   1. A hardcoded path that can vanish under a package manager.
#   2. Failing QUIETLY. A missing interpreter must be loud, because launchd will
#      cheerfully re-run a broken script on schedule forever.
#
# ensure_daemon.sh had the mirror-image bug: it tested `-f` rather than `-x`, never
# checked the interpreter actually ran, and fell through to bare `python` — which
# does not exist on macOS since Monterey. That is a silent 127 too.
#
# Resolution order (first candidate that EXECUTES wins):
#   $SAGE_PYTHON  -> explicit operator override, always honoured first
#   python3 on PATH
#   /opt/homebrew/bin/python3   (Apple Silicon brew)
#   /usr/local/bin/python3      (Intel brew)
#   /usr/bin/python3            (Xcode CLT; present but usually lacks our deps)
#
# SAGE_PY_REQUIRE is a space-separated module list every candidate must import. It
# distinguishes "an interpreter" from "OUR interpreter", and it is not optional in
# practice: under launchd the PATH is /usr/bin:/bin, so bare `python3` resolves to
# /usr/bin/python3 (3.9.6, Xcode CLT) rather than brew's 3.14. That interpreter runs
# fine and lacks every SAGE dependency, which would turn a loud exit-127 into a
# confusing ImportError deep inside a module. So it defaults to a real dependency.
# Override with SAGE_PY_REQUIRE="" only if you genuinely want any python3.
: "${SAGE_PY_REQUIRE=requests}"

_sage_py_works() {  # $1=candidate — must execute, and import SAGE_PY_REQUIRE if set
    [ -n "${1:-}" ] || return 1
    command -v "$1" >/dev/null 2>&1 || [ -x "$1" ] || return 1
    "$1" -c 'import sys; sys.exit(0)' >/dev/null 2>&1 || return 1
    if [ -n "${SAGE_PY_REQUIRE:-}" ]; then
        for _m in $SAGE_PY_REQUIRE; do
            "$1" -c "import $_m" >/dev/null 2>&1 || return 1
        done
    fi
    return 0
}

SAGE_PY=""
for _cand in "${SAGE_PYTHON:-}" python3 /opt/homebrew/bin/python3 \
             /usr/local/bin/python3 /usr/bin/python3; do
    if _sage_py_works "$_cand"; then SAGE_PY="$_cand"; break; fi
done
unset _cand _m

if [ -z "$SAGE_PY" ]; then
    echo "resolve_python: FATAL — no working python3 found on $(hostname -s)." >&2
    echo "  tried: \$SAGE_PYTHON, python3, /opt/homebrew/bin/python3," >&2
    echo "         /usr/local/bin/python3, /usr/bin/python3" >&2
    [ -n "${SAGE_PY_REQUIRE:-}" ] && \
        echo "  each also had to import: $SAGE_PY_REQUIRE" >&2
    echo "  likely cause: brew left python@3.x unlinked. Try: brew link python@3.14" >&2
    echo "  or set SAGE_PYTHON=/path/to/python3 explicitly." >&2
    return 1 2>/dev/null || exit 1
fi
export SAGE_PY
