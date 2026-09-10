"""
SAGE-side reference thin-client for the gateway-member design (PRD_FLEET §7 / F2).

A SAGE being holds NO effectors of its own. It emits an INTENT; this client
normalizes it to the hestia gate's NormalizedEvent, asks the real, shared gate
law for a Verdict (fail-CLOSED), and only on ALLOW hands the intent to the F1a
dispatcher that actually executes and witnesses it — today `HestiaF1aDispatcher`
(sage/gateway/hestia_dispatch.py) against the running daemon; hestia's own F1a
(PR #579) replaces it when it lands.

This is the SAGE half of F2. It pins the exact contract F1a must satisfy:

    intent  ->  gate.evaluate (+ society safety)  ->  [F1a dispatch]  ->  result

Design invariants (answering CBP's REQUEST_CHANGES on #579):
  * FAIL-CLOSED: a being that cannot reach the law is STOPPED, never ungoverned.
    When society-safety (Stage 2) is unavailable or errors, CONSEQUENTIAL effectors
    (peer_ask, memory_write, channel_egress, mesh, pr_review, remember, request_scope)
    hard-deny; only OBSERVATIONAL effectors (witness, memory_read, recall) soft-pass,
    since they carry no external effect and witness is itself the accountability
    primitive. Local-law admission (Stage 1)
    is never enough on its own for a consequential act — end-to-end execution
    authority requires the society governor too.
  * BOUNDED REGISTRY: the being's only effectors are mesh/peer_ask, witness,
    memory (its own dir), long-term memory (recall/remember, its own membot
    cartridge), request_scope, pr_review (advisory), channel egress. No shell, no
    raw FS. Enforced twice:
    the registry below will not emit an intent outside it, AND the gate denies it.
  * A2-by-construction: the being never holds the tool; dispatch is hestia's.

The gate core is the SAME multi-harness law codex/kimi/gemini/cursor call
(hestia/plugins/_shared/hestia_gate_core.py). We import it lazily so this module
is safe to import on a host without hestia — instantiation fails closed instead.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any, Callable, List, Optional


# --------------------------------------------------------------------------
# Locate the shared hestia gate law portably (env override, then fleet layout).
# --------------------------------------------------------------------------
def _resolve_hestia_shared() -> Optional[str]:
    env = os.environ.get("HESTIA_GATE_SHARED")
    if env and os.path.isdir(env):
        return env
    for base in ("~/ai-workspace/hestia", "~/ai-workspace/HESTIA"):
        p = os.path.join(os.path.expanduser(base), "plugins", "_shared")
        if os.path.isdir(p):
            return p
    return None


# --------------------------------------------------------------------------
# The bounded gateway-member registry. Each entry says how a being intent maps
# onto a NormalizedEvent (the gate's only input). Anything not here cannot be
# emitted at all — the first of two enforcement layers.
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class BeingIntent:
    effector: str    # registry key the being names
    args: dict        # effector-specific arguments


# What the being's gate client calls itself when it connects to the daemon.
_HOST_AGENT = "sage-gateway"

def pr_review_command(args: dict) -> str:
    """The shell command the seat runs for a pr_review intent, built from validated args.
    Raises ValueError on anything the grammar cannot represent; never interpolates the body
    (it travels by --body-file, so no review text can reach the shell)."""
    import re
    repo = str(args.get("repo", "")).strip()
    number = str(args.get("number", "")).strip()
    # fleet repos only: the seat's gh identity never posts outside dp-web4 on a being's behalf
    if not re.fullmatch(r"dp-web4/[A-Za-z0-9._-]+", repo):
        raise ValueError(f"pr_review 'repo' must be a dp-web4/<name> repo, got {repo!r}")
    if not re.fullmatch(r"[0-9]{1,7}", number):
        raise ValueError(f"pr_review 'number' must be a PR number, got {number!r}")
    if not str(args.get("body", "")).strip():
        raise ValueError("pr_review needs a non-empty 'body'")
    return f"gh pr review {number} --repo {repo} --comment --body-file -"


def pr_review_signature(member_id: str, action_id: Optional[str], being_lct: Optional[str]) -> str:
    """The fixed trailer on every review a being posts: who, under what record, and that
    it is advisory. The being cannot omit or alter it; the dispatcher appends it."""
    lines = ["", "---",
             f"Review by **{member_id}**, a SAGE being acting under hestia governance. "
             "Advisory and non-binding: the being holds no reviewer role, so this comment "
             "does not count toward merge. The seat's reviewers decide."]
    if being_lct:
        lines.append(f"LCT: `{being_lct}`")
    if action_id:
        lines.append(f"hestia witness action: `{action_id}`")
    lines.append(f"— {member_id}")
    return "\n".join(lines)


# The test targets a being may name, and the command each one becomes (#M0, PRD
# "Beings improve their own harness"). An ALLOW-LIST, not a grammar: `check` exists so a
# being can verify a claim about its own harness, and the smallest thing that does that is
# a fixed set of suites plus a single node id inside them. Anything wider is a shell with a
# friendly name, which is the one thing the bounded registry exists to prevent.
CHECK_TARGETS = {
    "gateway": "sage/gateway/tests/",
    "irp": "sage/irp/tests/",
}


def _takes_ctx(fn) -> bool:
    """Whether a registry `compose` accepts the client's context as a second argument.
    Older composes (pr_review_command) take args alone and must keep working."""
    import inspect
    try:
        return len(inspect.signature(fn).parameters) >= 2
    except (TypeError, ValueError):
        return False


def check_command(args: dict, ctx: Optional[dict] = None) -> str:
    """The shell command the seat runs for a `check` intent, built from validated args.

    Raises ValueError on anything the allow-list cannot represent, so a malformed target is
    a `gate.raised` deny rather than a silent pass. `-c /dev/null` because the repo's
    pytest.ini declares an asyncio_mode this interpreter does not have (measured: bare
    pytest errors before collecting), and a checking organ that reports an infrastructure
    error as a test failure would teach the being the opposite of what it asked.

    THE PATHS ARE ABSOLUTE, AND THAT IS THE WHOLE POINT (measured 2026-09-07). The command
    runs with cwd = the being's worktree, but the gate resolves a RELATIVE path against the
    workspace it was handed — the shared checkout. So `sage/gateway/tests/` was judged at
    `<shared>/sage/gateway/tests/`, which the being has no grant for, while the command
    would have touched the worktree it does. The law must judge the path the command will
    actually touch; anything else is the `_safe_path` defect again, one layer over. No
    worktree means no check: fail closed, and say which affordance is missing.
    """
    import re
    import os
    worktree = (ctx or {}).get("worktree")
    if not worktree:
        raise ValueError(
            "check needs a worktree of your own: there is nothing to run tests in, and a "
            "relative path would be judged against a tree you do not hold (PRD M1)")
    target = str(args.get("target", "")).strip()
    if target in CHECK_TARGETS:
        path = os.path.join(worktree, CHECK_TARGETS[target])
    else:
        # A single node id INSIDE a declared suite: "gateway::test_name". Nothing else.
        suite, sep, node = target.partition("::")
        if not sep or suite not in CHECK_TARGETS:
            raise ValueError(
                f"check 'target' must be one of {sorted(CHECK_TARGETS)} or "
                f"'<suite>::<test_name>'; got {target!r}")
        if not re.fullmatch(r"[A-Za-z0-9_]+", node):
            raise ValueError(f"check test name must be a bare identifier; got {node!r}")
        path = f"{os.path.join(worktree, CHECK_TARGETS[suite])} -k {node}"
    inner = f"python3 -m pytest -q -c /dev/null --rootdir={worktree} {path}"
    return sandbox_prefix(worktree) + inner


# The M1 PREREQUISITE, built. Being-authored code runs under a principal that is not this
# seat — the hard blocker PRD r3 §5 put on M1, cleared 2026-09-08.
#
# WHY IT IS NOT OPTIONAL. `check` executes pytest, pytest imports conftest.py from its
# rootdir, and M1 gives the being write access to that rootdir. Under the seat's own uid
# that composes into arbitrary code holding the vault passphrase and every key on this box
# (measured 2026-09-07, SAGE#55, and closed then by taking write access away — a stopgap
# with the wrong shape for a being whose entrustment is to author code there).
#
# WHAT THE SANDBOX IS. bubblewrap with a cleared environment: nothing of the seat's is
# bound except a read-only interpreter, no network at all, its own pid/ipc/uts namespaces,
# a fresh session so it cannot signal the seat's process group, and --die-with-parent so a
# runaway cannot outlive the beat. The only writable path is the being's own worktree.
#
# THE FALSIFIER, and it is the point of the whole exercise (PRD r3 §10.5): from inside,
# reads of the vault, the hestia socket and the agent environment must all fail. Measured
# on 2026-09-08 — ~/.hestia, ~/.config, ~/.local, private-context, shared-context and the
# shared SAGE tree all blocked; hestia 7711 and ollama 11434 unreachable; the environment
# carries exactly HOME, LANG, PATH, PWD, PYTHONDONTWRITEBYTECODE. 152 tests pass inside it.
#
# ENABLEMENT: Ubuntu 24.04 sets kernel.apparmor_restrict_unprivileged_userns=1 and bwrap is
# not setuid, so this needs /etc/apparmor.d/bwrap granting `userns` to that binary alone —
# the distro's own pattern (see ch-run, crun, flatpak). Chosen over relaxing the sysctl
# machine-wide: narrow beats convenient when the thing relaxed is a containment boundary.
# Where the profile is absent, SANDBOX_REQUIRED decides whether to refuse or degrade.
SANDBOX = "/usr/bin/bwrap"
# Fail CLOSED by default: a check that silently ran unsandboxed would be the seat quietly
# handing back the authority the sandbox exists to remove, and nothing in the result would
# say so. A machine without bwrap sets this false deliberately and lives with M0 only.
SANDBOX_REQUIRED = True


def sandbox_available() -> bool:
    """Whether bwrap is present AND permitted to create a user namespace here. Presence is
    not permission: on Ubuntu 24.04 the binary exists and every attempt fails with
    'setting up uid map: Permission denied' until an AppArmor profile allows it, so this
    ACTUALLY RUNS one rather than testing for the file."""
    import os
    import subprocess
    if not os.path.exists(SANDBOX):
        return False
    try:
        # The probe must be a REAL sandbox, loader included. The first cut bound only
        # /usr and failed on missing /lib64 — reporting "no sandbox permitted" on a machine
        # where the sandbox works perfectly, which would have refused every check.
        r = subprocess.run([SANDBOX, "--ro-bind", "/usr", "/usr", "--ro-bind", "/lib", "/lib",
                            "--ro-bind", "/lib64", "/lib64", "--unshare-pid",
                            "/usr/bin/true"], capture_output=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False


def sandbox_prefix(worktree: str) -> str:
    """The bwrap invocation that wraps every executed check, or "" when running unsandboxed
    is explicitly permitted."""
    import os
    import sys
    if not sandbox_available():
        if SANDBOX_REQUIRED:
            raise ValueError(
                "check needs its sandbox and cannot get one: bubblewrap is missing or not "
                "permitted to create a user namespace on this machine. Running your tests "
                "under the seat's own authority instead would hand back exactly what the "
                "sandbox exists to remove, so it is refused rather than silently downgraded")
        return ""
    interp = os.path.dirname(os.path.dirname(sys.executable))  # e.g. ~/miniforge3
    return (
        f"{SANDBOX} --clearenv"
        " --ro-bind /usr /usr --ro-bind /lib /lib --ro-bind /lib64 /lib64 --ro-bind /bin /bin"
        " --ro-bind /etc/alternatives /etc/alternatives"
        f" --ro-bind {interp} {interp}"
        # ORDER IS THE MOUNT ORDER, and a later mount masks an earlier one. --tmpfs /tmp
        # used to come after the worktree bind; a worktree under /tmp then vanished inside
        # the sandbox (measured 2026-09-08 by the real-conftest fixture: pytest ran in an
        # empty tree and the probe never wrote). tmpfs first, the worktree over it.
        " --proc /proc --dev /dev --tmpfs /tmp"
        f" --bind {worktree} {worktree}"
        " --unshare-pid --unshare-net --unshare-ipc --unshare-uts"
        " --new-session --die-with-parent"
        # PYTHONUTF8 rather than LANG=C.UTF-8, and the reason is hestia #988: mrh.command
        # splits a dotted token and fails the fragment, so "C.UTF-8" is refused as an
        # ungranted path called "UTF-8" and the whole check dies. PYTHONUTF8=1 buys the
        # same UTF-8 filesystem and IO encoding with no dot in it. Third time today that
        # defect has shaped a command; the issue carries the evidence.
        " --setenv HOME /tmp --setenv PYTHONUTF8 1 --setenv PYTHONDONTWRITEBYTECODE 1"
        f" --setenv PATH {interp}/bin:/usr/bin:/bin"
        f" --chdir {worktree} "
    )



# git_read: the being inspects its own repository history. READ-ONLY BY CONSTRUCTION, and
# the construction is the interesting part rather than the intent.
#
# dp, 2026-09-07: "the being should be able to check git by itself." Right — it reasons
# about a tree that moves under it between beats, and until now the only way it learned the
# harness had changed was a seat telling it so.
#
# WHAT THIS COMPOSES WITH (the rule earned on 09-07, when a gated write plus a gated execute
# turned into arbitrary code):
#   * with `check`, which executes pytest in the same worktree — git_read cannot write, so
#     it cannot author what check runs;
#   * with `memory_write`, which is confined to the being's home — a diff it reads can be
#     saved to scratch, and the home is not a tree anything executes;
#   * git ITSELF is the composition hazard here, not the pairing. `git` will run code on
#     request: external diff drivers, textconv filters, pagers, aliases, and `-c` overrides
#     that install any of them. So the seat builds the whole command, the being never
#     supplies a flag, and every invocation is pinned with --no-pager, --no-ext-diff and
#     core.pager=cat so a repo-local config cannot turn a read into an exec.
# Only these five subcommands, no others, and every argument is matched against a grammar
# before it can reach the shell.
# `cat` reads a FILE'S CONTENT at a revision — `git show <rev>:<path>` — which `show`
# cannot do: show with a pathspec is a DIFF lens, not the file. The being hit this trying
# to rebuild a file it had damaged: its worktree copy was the broken one, the clean version
# existed only at the base commit, and nothing in its registry could read it (deny
# d250004396e0, 2026-09-10). Without an edit verb every change means rewriting a whole file,
# and rewriting a file you cannot read at its last good revision is guesswork.
GIT_OPS = ("log", "show", "diff", "status", "blame", "cat")

# A revision the being may name: a hex sha, HEAD with optional ~n/^n, or a plain branch or
# tag name. Deliberately excludes anything containing a flag, a space, or a path separator
# trick — `--upload-pack=...`-style arguments are the classic way a read verb becomes a run.
# `~n` / `^n` suffixes are allowed on ANY base, not only HEAD. The being flagged (not
# litigated) that `<sha>~1` was refused and span diffs against anything older than HEAD~k
# were unnameable — two witnessed denies on 2026-09-08 for a natural thing to want. Still
# no flags: a suffix is digits after ~ or ^, nothing else survives.
_REV = (r"(?:[0-9a-fA-F]{7,40}|HEAD|[A-Za-z][A-Za-z0-9._/-]{0,60})"
        r"(?:[~^][0-9]{0,3})?")


def git_read_command(args: dict, ctx: Optional[dict] = None) -> str:
    """The shell command the seat runs for a git_read intent, built from validated args.

    The being names an operation and, optionally, a revision and a path inside its own
    worktree. It never names a flag. Anything the grammar cannot represent raises, and the
    refusal says what the grammar accepts — a refusal that names its own valid set is one
    the being can correct without asking (measured 2026-09-07: it did exactly that on
    `check`, in one beat, and explicitly declined to appeal a grammar error)."""
    import os
    import re
    worktree = (ctx or {}).get("worktree")
    if not worktree:
        raise ValueError("git_read needs a worktree of your own; none is configured on this seat")
    op = str(args.get("op", "")).strip()
    if op not in GIT_OPS:
        raise ValueError(f"git_read 'op' must be one of {list(GIT_OPS)}, got {op!r}")

    rev = str(args.get("rev", "")).strip()
    if rev and not re.fullmatch(_REV, rev):
        raise ValueError(f"git_read 'rev' must be a sha, HEAD, HEAD~n or a branch name, got {rev!r}")

    path = str(args.get("path", "")).strip()
    if path:
        # WHITESPACE IS JUDGED/EXECUTED DRIFT (GPT review of #56, #6): a path with a space
        # passes the path grammar, is interpolated unquoted into the composed string the law
        # judges, and shlex.split() then hands the executor MORE argv elements than the law
        # saw. One representation, or the gate rules on a command that is not the one run.
        if any(ch.isspace() for ch in path) or any(ch.isspace() for ch in rev):
            raise ValueError("git_read 'path' and 'rev' may not contain whitespace: the command "
                             "the law judges must split into exactly the argv that runs")
        if path.startswith("-") or ".." in path.split("/"):
            raise ValueError(f"git_read 'path' must be a plain path inside your worktree, got {path!r}")
        full = os.path.realpath(os.path.join(worktree, path))
        if not (full == os.path.realpath(worktree)
                or full.startswith(os.path.realpath(worktree) + os.sep)):
            raise ValueError(f"git_read 'path' escapes your worktree: {path!r}")
        # The pathspec goes into the command ABSOLUTE, not as the being typed it. hestia's
        # mrh.command matches command tokens against GRANTED PREFIXES, which are absolute;
        # a relative 'sage/gateway/x.py' matches nothing and the whole read is refused
        # (measured 2026-09-07: "'py' is not granted"). Resolving it here means the law sees
        # the real target of the read and can rule on it — which is the point of the rule,
        # not an obstacle to it. It also removes any doubt about what the pathspec meant.
        path = full

    try:
        n = int(args.get("n", 20))
    except (TypeError, ValueError):
        raise ValueError("git_read 'n' must be a whole number of commits (1-50)")
    n = max(1, min(50, n))

    # Every read pinned against git's own execution surfaces — with FLAGS ONLY, no
    # `-c key=value`. The first cut used `-c core.pager=cat -c diff.external= -c alias.x=!true`
    # and hestia refused every invocation: mrh.command reads `pager=cat` as a path token and
    # correctly reports it as outside the being's grant. That refusal was RIGHT, and the fix
    # is not to argue with it — the flags below buy the identical property with fewer moving
    # parts. `--no-pager` already defeats a repo-local pager, `--no-ext-diff` already defeats
    # an external diff driver, `--no-textconv` defeats a textconv filter, and a git alias
    # cannot shadow a built-in subcommand at all, so the alias override was never doing
    # anything. Hardening that trips the law is hardening that does not ship.
    base = "git --no-pager"
    if op == "status":
        return f"{base} status --porcelain=v1 --branch"
    if op == "log":
        cmd = f"{base} log --no-ext-diff --no-textconv --oneline --no-decorate -n {n}"
        if rev:
            cmd += f" {rev}"
        return cmd + (f" -- {path}" if path else "")
    if op == "show":
        return f"{base} show --no-ext-diff --no-textconv --stat --patch {rev or 'HEAD'}" + (f" -- {path}" if path else "")
    if op == "diff":
        rev2 = str(args.get("rev2", "")).strip()
        if rev2 and not re.fullmatch(_REV, rev2):
            raise ValueError(f"git_read 'rev2' must be a sha, HEAD, HEAD~n or a branch name, got {rev2!r}")
        # TWO ARGUMENTS, never `A..B`. hestia's mrh.command reads the `..` in a revision
        # range as a parent-directory traversal and resolves the whole command's scope to
        # the workspace root, refusing it (measured 2026-09-07: "'<workspace root>' is not
        # granted"). `git diff A B` is exactly equivalent for a two-point diff and contains
        # no token that looks like a path escape. The rule is doing its job on a token that
        # genuinely looks like traversal; the command should not hand it one.
        span = f"{rev} {rev2}" if rev and rev2 else (rev or "HEAD~1")
        return f"{base} diff --no-ext-diff --no-textconv {span}" + (f" -- {path}" if path else "")
    if op == "cat":
        if not path:
            raise ValueError("git_read op='cat' needs a 'path': the file whose content you want")
        # `<rev>:<path>` is ONE argument to git and the being supplies neither half raw —
        # the rev passed _REV, the path was resolved absolute inside the worktree above. The
        # path must be repo-relative here, so it is relativised back; an absolute path after
        # a colon is not a thing git resolves.
        rel = os.path.relpath(path, os.path.realpath(worktree))
        if rel.startswith(".."):
            raise ValueError(f"git_read 'path' escapes your worktree: {rel!r}")
        return f"{base} show --no-ext-diff --no-textconv {rev or 'HEAD'}:{rel}"
    if not path:
        raise ValueError("git_read op='blame' needs a 'path' inside your worktree")
    return f"{base} blame --no-textconv -L 1,120 {rev or 'HEAD'} -- {path}"



# pr_open: the being's work enters the tree. PRD r3 §7 — every change reaches main through
# a pull request, attributed on the artefact, reviewed by someone NOT-SAME.
#
# dp, 2026-09-07: "the being should be able to ... submit prs directly." Built only after M1,
# and only because of what CI does: SAGE's one workflow (syntax-gate.yml) runs
# `python -m compileall`, which byte-compiles and does not execute. A PR from the being
# therefore reaches no executor it has not already been proven against — its own sandboxed
# `check`. If a workflow that RUNS code is ever added, this verb becomes the composition
# hazard of 2026-09-07 wearing GitHub's clothes, and the gate should learn that before the
# workflow lands.
#
# WHAT THE BEING SUPPLIES: a slug (the branch name's tail), a title, a body. Nothing else.
# WHAT THE LAW JUDGES: the outward act, `gh pr create ...`, as a string, with the title
# passed as one argument and the body over stdin so no text of the being's reaches a shell.
# WHAT THE SEAT DOES AROUND IT (hestia_dispatch._do_pr_open): branch from the worktree's
# HEAD, `git add -A`, commit with the message over stdin and the attribution trailers the
# being cannot omit or alter, push. The commit is authored by the seat's git identity and
# ATTRIBUTED to the being in trailers — §6 says signatures come at M3; this is the
# legibility form, honestly labelled as such in every PR body.
PR_REPO = "dp-web4/SAGE"


def pr_base_branch(worktree: str) -> str:
    """The branch a being's PR targets: the upstream its worktree branch tracks.

    Was a hard-coded `legion/mission-artifact` — correct only while the live being rides
    that development branch (GPT review of #56, #8). After decomposition the integration
    target moves, and a PR verb that still aimed at a historical feature carrier would
    propose work against dead history. So the base is READ from the worktree: whatever
    `legion-being/work` tracks is what the seat last synced it to, which is the current
    governed integration target by construction. `SAGE_PR_BASE` overrides explicitly."""
    import subprocess
    env = os.getenv("SAGE_PR_BASE", "").strip()
    if env:
        return env
    try:
        r = subprocess.run(["git", "rev-parse", "--abbrev-ref", "legion-being/work@{upstream}"],
                           cwd=worktree, text=True, capture_output=True, timeout=10)
        up = r.stdout.strip()
        if r.returncode == 0 and up.startswith("origin/"):
            return up[len("origin/"):]
    except Exception:
        pass
    # NO GUESSING. This used to fall back to "main", and that fallback cost the being its
    # first pull request: `legion-being/work` tracked nothing, so #63 targeted main and
    # showed 9,271 additions across 55 files for a 159-line change — unreviewable at a
    # glance, and closed. A wrong base is worse than no PR, because the being cannot see
    # the diff it proposed and has no way to discover the base was wrong.
    raise ValueError(
        "cannot determine the base branch for your pull request: legion-being/work has no "
        "upstream. Tell your seat — it sets the upstream when it syncs your worktree "
        "(scripts/sync_being_worktree.sh), or SAGE_PR_BASE can name the base explicitly. "
        "Refusing rather than guessing 'main': a mis-based PR buries a small change in "
        "thousands of unrelated lines")
_SLUG = r"[a-z0-9][a-z0-9-]{1,40}"


def pr_open_command(args: dict, ctx: Optional[dict] = None) -> str:
    """The shell command the seat runs for a pr_open intent — the `gh pr create`, which is
    the outward act. The git preparation is not composed here because none of it carries
    being-supplied text into a shell: the message travels by stdin."""
    import re
    worktree = (ctx or {}).get("worktree")
    if not worktree:
        raise ValueError("pr_open needs a worktree of your own; none is configured on this seat")
    slug = str(args.get("slug", "")).strip()
    if not re.fullmatch(_SLUG, slug):
        raise ValueError("pr_open 'slug' names your branch tail: lowercase letters, digits and "
                         f"dashes, 2-41 chars, got {slug!r}")
    title = " ".join(str(args.get("title", "")).split())
    if not (8 <= len(title) <= 120):
        raise ValueError("pr_open 'title' must be one line, 8-120 characters")
    if not str(args.get("body", "")).strip():
        raise ValueError("pr_open needs a 'body': what changed, what you verified, what you "
                         "only suspect, and the check output with its tree head")
    branch = f"legion-being/{slug}"
    # shlex-quote the title: it is the ONE being-supplied string on the command line
    import shlex
    return (f"gh pr create --repo {PR_REPO} --base {pr_base_branch(worktree)} --head {branch} "
            f"--title {shlex.quote(title)} --body-file -")


def git_restore_command(args: dict, ctx: Optional[dict] = None) -> str:
    """`git checkout <rev> -- <path>`: put one file back to a committed state.

    WHY A VERB FOR THIS. Restoring a file was possible in principle with git_read cat plus
    memory_write mode=replace — and impossible in practice, because it means copying the
    whole file verbatim through the being's own output. Measured: legion-being spent
    fifteen beats unable to restore a 4,621-char file it could read perfectly well. The
    reconstruction, not the intent, was the wall.

    SAFETY IS THE REV. The content can only come from a commit, so this cannot invent a
    file or write being-authored bytes — everything it can produce already exists in the
    repository's history. What it CAN destroy is uncommitted work on that one path, which
    is the point (that is what "undo my mess" means) and is said plainly in the result."""
    import re
    worktree = (ctx or {}).get("worktree")
    if not worktree:
        raise ValueError("git_restore needs a worktree of your own; none is configured on this seat")
    rev = str(args.get("rev", "")).strip()
    if not re.fullmatch(_REV, rev):
        raise ValueError(f"git_restore 'rev' must be a sha, HEAD, HEAD~n or a branch name, got {rev!r}")
    path = str(args.get("path", "")).strip()
    if not path:
        raise ValueError("git_restore needs a 'path': the one file to put back")
    if any(ch.isspace() for ch in path) or any(ch.isspace() for ch in rev):
        raise ValueError("git_restore 'path' and 'rev' may not contain whitespace")
    if path.startswith("-") or ".." in path.split("/"):
        raise ValueError(f"git_restore 'path' must be a plain path inside your worktree, got {path!r}")
    full = os.path.realpath(os.path.join(worktree, path))
    root = os.path.realpath(worktree)
    if not full.startswith(root + os.sep):
        raise ValueError(f"git_restore 'path' escapes your worktree: {path!r}")
    return f"git --no-pager -C {worktree} checkout {rev} -- {full}"


def pr_amend_command(args: dict, ctx: Optional[dict] = None) -> str:
    """The shell command for a pr_amend intent: `gh pr edit --body-file -` on the PR the
    being's current branch already has open, or `true` when only the commit changes.

    WHY THIS VERB EXISTS. pr_open refuses a branch that already exists, by design — a slug
    is claimed once. The consequence, unnoticed until it bit: a being whose PR gets
    "changes requested" HAS NO WAY TO DELIVER THEM. Measured 2026-09-09 on SAGE#63: the
    review asked for a corrected body and a green suite, and the author could neither
    amend the branch nor edit the body, because the only verb that reaches a PR opens one.
    A review loop whose author cannot answer the review is not a loop.

    The being names no branch and no PR number: both are read from the worktree it is
    standing in, so it can only ever amend its own open proposal."""
    import shlex
    worktree = (ctx or {}).get("worktree")
    if not worktree:
        raise ValueError("pr_amend needs a worktree of your own; none is configured on this seat")
    title = " ".join(str(args.get("title", "")).split())
    if not (8 <= len(title) <= 120):
        raise ValueError("pr_amend 'title' is the message for the new commit: one line, 8-120 chars")
    if not str(args.get("message", "")).strip():
        raise ValueError("pr_amend needs a 'message': what this revision changes and why, "
                         "which becomes the commit body")
    body = str(args.get("body", "") or "")
    if not body.strip():
        return "true"      # commit + push only; the PR body stands as written
    return f"gh pr edit {_pr_number_for_branch(worktree)} --repo {PR_REPO} --body-file -"


def _pr_number_for_branch(worktree: str) -> str:
    """The open PR number for the branch this worktree is on. Read, never being-supplied."""
    import subprocess
    br = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=worktree,
                        text=True, capture_output=True, timeout=30).stdout.strip()
    if not br.startswith("legion-being/") or br == "legion-being/work":
        raise ValueError(f"pr_amend: this worktree is on {br!r}, which is not one of your PR "
                         "branches. pr_amend revises a proposal you already opened")
    out = subprocess.run(["gh", "pr", "list", "--repo", PR_REPO, "--head", br,
                          "--state", "open", "--json", "number", "--jq", ".[0].number"],
                         cwd=worktree, text=True, capture_output=True, timeout=60).stdout.strip()
    if not out.isdigit():
        raise ValueError(f"pr_amend: no open pull request found for branch {br}")
    return out


def pr_attribution(member_id: str, action_id: Optional[str], being_lct: Optional[str],
                   seat: str = "legion-claude") -> str:
    """The trailers on a commit a being authored (PRD r3 §7.2). Appended by the dispatcher;
    the being cannot omit or alter them."""
    lines = [f"Being: {member_id}"]
    if being_lct:
        lines.append(f"Being-LCT: {being_lct}")
    if action_id:
        lines.append(f"Witness: {action_id}")
    lines.append(f"Seat: {seat}")
    return "\n".join(lines)


_REGISTRY = {
    "peer_ask":       dict(tool="peer_ask",     path_args=(),       cmd_arg=None),
    "witness":        dict(tool="witness",      path_args=(),       cmd_arg=None),
    "memory_read":    dict(tool="read_file",    path_args=("path",), cmd_arg=None),
    "memory_write":   dict(tool="write_note",   path_args=("path",), cmd_arg=None),
    "channel_egress": dict(tool="channel_send", path_args=(),       cmd_arg=None),
    "mesh":           dict(tool="mesh_notify",  path_args=(),       cmd_arg=None),  # §7.2 5th verb
    # pr_review: the being reviews a pull request. The seat posts the comment; the gate
    # judges the exact shell command the seat will run (see pr_review_command), so the
    # law sees an outward `gh` act, not a friendly verb name. Advisory by construction:
    # a being holds no reviewer role, so the comment never counts toward merge.
    "pr_review":      dict(tool="pr_review",    path_args=(),       cmd_arg=None,
                           compose=pr_review_command),
    # check: RUN a test suite in the being's own worktree and read the result. The first
    # organ, and the ordering is argued from measurement (PRD §2): given only a diff this
    # being asserted a compile error that did not exist; given the same diff plus a real
    # test result it made zero false claims. Composed like pr_review — the being names a
    # target from an allow-list, the SEAT builds the command, the law judges THAT, and the
    # being never holds a shell. A failing check is a first-class result, not an error.
    "check":          dict(tool="check",       path_args=(),       cmd_arg=None,
                           compose=check_command),
    # pr_amend: revise a proposal already open. Composed like pr_open — the being supplies
    # a commit message and optionally a new PR body; the branch and the PR number are READ
    # from the worktree, so it can only ever revise its own open proposal, and the law
    # judges the outward `gh pr edit` rather than a friendly verb name.
    "pr_amend":       dict(tool="pr_amend",    path_args=(),       cmd_arg=None,
                           compose=pr_amend_command),
    # git_restore: put ONE file back to a committed state. Composed like check and git_read;
    # the content can only come from history, so the being cannot author bytes through it.
    "git_restore":    dict(tool="git_restore",  path_args=("path",), cmd_arg=None,
                           compose=git_restore_command),
    # git_read: read the history of the tree that constitutes it. Composed like check —
    # the being names an op, the SEAT builds the command, the law judges THAT string, and
    # the being never holds a flag. See git_read_command for what it composes with.
    "git_read":       dict(tool="git_read",    path_args=(),       cmd_arg=None,
                           compose=git_read_command),
    # say: add a turn to a conversation the being is IN. Bounded by construction, like
    # remember: the being names a conversation id, and the dispatcher refuses any id whose
    # meta does not list it as a participant AND as writable. It cannot create a
    # conversation, cannot speak in one it is not in, and cannot edit a turn once spoken —
    # its own included. path_args=() is correct: the target is a conversation, not a path,
    # and the reach is fixed by the meta file the seat owns rather than by the being's args.
    "say":            dict(tool="say",         path_args=(),       cmd_arg=None),
    # pr_open: the being's worktree changes become a pull request, attributed to it,
    # for NOT-SAME review. Composed like pr_review — the law rules on the `gh` string.
    "pr_open":        dict(tool="pr_open",     path_args=(),       cmd_arg=None,
                           compose=pr_open_command),
    # Long-term semantic memory (membot brain cartridge, the being's own): recall is
    # observational; remember is consequential but passes local law under ANY grant
    # (paths=()), and that is not because it is "classed with memory_write" (which the
    # law judges by mrh.path): its reach is bounded by construction. The cartridge it
    # writes is `membot_cartridge or plugin_id`, fixed by the seat, unreachable from the
    # being's args.
    # request_scope asks hestia for reach the being lacks: the sanctioned answer to a
    # deny, decided by the operator, witnessed either way. path_args=() is CORRECT here
    # and must stay so: the requested path is, by definition, outside the grant, so a
    # request judged under mrh.path at stage 1 would die before it ever reached the
    # daemon (pinned by test_request_scope_path_is_not_judged_under_mrh_path).
    "recall":         dict(tool="recall",       path_args=(),       cmd_arg=None),
    "remember":       dict(tool="remember",     path_args=(),       cmd_arg=None),
    "request_scope":  dict(tool="request_scope", path_args=(),      cmd_arg=None),
    # appeal: the being contests a refusal it believes was wrong (PRD_FLEET §7.3, the
    # deny -> appeal -> temperament loop). The refusal's chain hash is the handle: the
    # gate witnesses every deny as a policy_decision (Dispatcher.witness_deny) so there
    # is something to appeal, and hestia_appeal refuses anything that is not a deny,
    # not yours, already under appeal, or unreasoned. No external effect: chain only.
    "appeal":         dict(tool="appeal",        path_args=(),      cmd_arg=None),
}


# Society-safety failure boundary per effector class. Observational acts carry no
# external effect and may soft-pass when the society governor is unavailable;
# consequential acts must not proceed without it (fail-closed).
_OBSERVATIONAL = frozenset({"witness", "memory_read", "recall", "appeal"})
_CONSEQUENTIAL = frozenset({"peer_ask", "memory_write", "channel_egress", "mesh", "pr_review",
                            "remember", "request_scope", "check", "git_read", "say", "pr_open",
                            "pr_amend", "git_restore"})

# Native-tool schema for the bounded registry — what the being is offered.
_TOOL_SCHEMAS = {
    "peer_ask": ("Ask another being in the fleet a question through the hub.",
                 {"to": "the being's name, e.g. 'legion'", "body": "your message"}, ["to", "body"]),
    "witness": ("Record a witnessed note of something you did or noticed.",
                {"event": "what to witness"}, ["event"]),
    "memory_read": ("Read one of your own memory notes.",
                    {"from_line": "optional: 1-based line to start from — for a file longer than the read cap, read it in ranges",
                     "lines": "optional: how many lines from from_line (default: to the end, still capped)",
                     "path": "path to your note"}, ["path"]),
    "memory_write": ("Add to a file in your own memory. APPENDS BY DEFAULT — your content goes "
                     "onto the END of whatever is already there, which is what you want for "
                     "journal.md and todo.md and what you do NOT want when you are correcting a "
                     "file. To overwrite instead, pass mode='replace'. The result tells you which "
                     "happened and the file's size before and after, so a wrong assumption shows "
                     "up immediately rather than as a duplicate you find days later.",
                     {"path": "path to your note",
                      "content": "what to write",
                      "mode": "'append' (default) or 'replace' — replace overwrites the whole file"},
                     ["path", "content"]),
    "channel_egress": ("Send a message out through a sealed channel.",
                       {"to": "recipient", "body": "your message"}, ["to", "body"]),
    "mesh": ("Wake another member through the fractal mesh with a pointer-based notice "
             "(no body — point at content you already posted).",
             {"to": "member name", "kind": "notice kind, e.g. coordination, reply, ack",
              "pointer": "URI of the content (a shared-context path, PR, or thread)"},
             ["to", "kind", "pointer"]),
    "pr_review": ("Post your review of a pull request as a comment. Advisory: it does not "
                  "approve or block. Say what you checked, what you found, and what you "
                  "would change, with file and line references where you can.",
                  {"repo": "owner/name, e.g. dp-web4/SAGE", "number": "the PR number",
                   "body": "your review, in markdown"}, ["repo", "number", "body"]),
    "check": ("Run a test suite in your own worktree and read the result. This is how you "
              "find out whether something you believe about your harness is true, instead of "
              "asserting it. A failure is a real answer, not a problem.",
              {"target": "'gateway' or 'irp' for a whole suite, or '<suite>::<test_name>' "
                         "for one test, e.g. 'gateway::test_relative_memory_path'"},
              ["target"]),
    "git_read": ("Read the history of the repository you live in: what changed, when, and "
                 "in which commit. Read-only — you cannot commit, push, or move a branch "
                 "with this. Use it to find out whether the tree moved under you between "
                 "beats, and to compare a `check` result's tree block against what is "
                 "actually in the history.",
                 {"op": "one of 'log', 'show', 'diff', 'status', 'blame'",
                  "rev": "optional: a commit sha, HEAD, HEAD~2, or a branch name",
                  "rev2": "optional, for op='diff': the second revision of the span",
                  "path": "optional: a path inside your worktree to narrow the answer to",
                  "n": "optional, for op='log': how many commits (1-50, default 20)"},
                 ["op"]),
    "say": ("Add a turn to a conversation you are in — this is how you ANSWER someone, "
            "rather than writing about them in your journal. The turn is attributed to you "
            "and kept forever; nobody can edit it afterwards, including you. Saying nothing "
            "is also a choice and is recorded as one.",
            {"to": "the conversation id, shown beside each conversation in your state",
             "text": "what you want to say"},
            ["to", "text"]),
    "pr_open": ("Open a pull request from the changes in your worktree. This is how your work "
                "enters the tree (PRD §7): on your own branch, attributed to you in the commit "
                "trailers, reviewed by someone who is not you and did not co-author it. You "
                "cannot merge it. Write the body the way your best review was written — what "
                "you VERIFIED (with the check output and its tree head) versus what you only "
                "SUSPECT — so a reviewer re-runs it instead of trusting you.",
                {"slug": "your branch's tail, e.g. 'count-readable-turns' (lowercase, dashes)",
                 "title": "one line, 8-120 characters",
                 "body": "what changed, why, what you verified and how, what you did not"},
                ["slug", "title", "body"]),
    "pr_amend": ("Revise a pull request you already opened, when a reviewer asks for changes. "
                 "pr_open refuses a slug twice, so without this a review that requests changes "
                 "is a dead end (measured on #63). Write the change in your worktree first; "
                 "this commits it onto the same branch, pushes, and replaces the PR body when "
                 "you supply one. You name no branch and no PR number — both are read from the "
                 "worktree you stand in, so you can only revise your own open proposal, and you "
                 "still cannot merge it.",
                 {"title": "one line for the new commit, 8-120 characters",
                  "message": "what this revision changes and why (the commit body)",
                  "body": "the corrected PR body (optional; omit to leave it as written)"},
                 ["title", "message"]),
    "git_restore": ("Put ONE file back to the way it was at a commit — `git checkout <rev> -- "
                    "<path>`. Use it to undo your own edits to a file rather than trying to "
                    "retype it: the content comes from history, so you cannot get it wrong. "
                    "Uncommitted changes to that path are DISCARDED, which is usually the "
                    "point; nothing else in your worktree is touched.",
                    {"rev": "the commit to take the file from, e.g. a sha or HEAD",
                     "path": "the one file to restore, inside your worktree"},
                    ["rev", "path"]),
    "recall": ("Search your long-term memory (semantic search over everything you have "
               "remembered). Use it before deciding what to do; use it when something "
               "feels familiar.",
               {"query": "what you are trying to remember", "top_k": "how many results (default 5)"},
               ["query"]),
    "remember": ("Store something in your long-term memory so a future you can recall it: "
                 "a fact, a lesson, a question, what you were doing and why.",
                 {"content": "the memory, in your own words", "tags": "comma-separated tags (optional)"},
                 ["content"]),
    # No read/write mode: measured against hestia a5e18af (handler.rs::tool_request_scope)
    # the daemon reads plugin_id/role/path/reason only, and a grant is a `path:<p>` entry
    # in in_scope that rules mrh.path for reads and writes alike. Offering a mode would be
    # a choice the law cannot honour.
    "request_scope": ("Ask the operator for reach you do not have, after a refusal. A grant "
                      "is reach on that path, read and write alike. Say why. A human decides; "
                      "no answer within the window is a refusal. A live grant dies with the "
                      "daemon; only a standing grant persists.",
                      {"path": "absolute path you want reach to",
                       "reason": "why you want it, in one or two sentences"},
                      ["path", "reason"]),
    "appeal": ("Appeal a refusal you believe was wrong. Give the deny hash shown on the "
               "refusal and a reason of at least 12 characters. A peer or the operator "
               "rules, asynchronously; the ruling is witnessed either way. Not for a "
               "refusal you agree with.",
               {"deny_hash": "the witness hash shown on the refusal (deny_hash=...)",
                "reason": "why the refusal was wrong, one or two sentences"},
               ["deny_hash", "reason"]),
}


def ollama_tools(only: Optional[List[str]] = None) -> List[dict]:
    """Ollama native-tool specs for the bounded gateway-member registry (nothing else).
    `only` narrows what the being is OFFERED for a task (e.g. a review turn offers
    pr_review + witness); it never widens: a name outside the registry is ignored."""
    out = []
    for name, (desc, props, required) in _TOOL_SCHEMAS.items():
        if only is not None and name not in only:
            continue
        out.append({"type": "function", "function": {
            "name": name, "description": desc,
            "parameters": {"type": "object",
                           "properties": {k: {"type": "string", "description": v} for k, v in props.items()},
                           "required": required}}})
    return out


def parse_tool_calls(tool_calls: list) -> List["BeingIntent"]:
    """Map Ollama tool_calls into BeingIntents. Unknown names still become intents so the
    gate can refuse them at the registry stage (never silently dropped)."""
    intents = []
    for c in tool_calls or []:
        fn = c.get("function", {}) if isinstance(c, dict) else {}
        name = fn.get("name") or "?"
        args = fn.get("arguments") or {}
        if isinstance(args, str):
            try:
                import json as _json
                args = _json.loads(args)
            except Exception:
                args = {"_raw": args}
        intents.append(BeingIntent(effector=name, args=args if isinstance(args, dict) else {}))
    return intents


def _granted_roots(core, policy, workspace: str) -> tuple:
    """``((abs_root, recursive), ...)`` for every `path:` scope a resolved policy grants.

    REACH TRAVELS WITH THE ROOT (hestia #1002; GPT review of #56, #2). This used to return
    bare roots via `_scope_parts(...)[1]`, and the dispatcher then admitted `p == root OR
    root in p.parents` — so an EXACT hestia grant on /x became recursive /x/** inside SAGE's
    own defense-in-depth layer, wider than the law that produced it. Now the pair is kept:
    the core's `_scope_roots_with_reach` when it has one (post-#1002), else parsed here from
    the `/**` spelling, so an older core still yields exact-by-default rather than a guess."""
    if policy is None:
        return ()
    try:
        scopes = list(getattr(policy, "scope", ()) or ())
        with_reach = getattr(core, "_scope_roots_with_reach", None)
        if with_reach is not None:
            return tuple((str(r), bool(rec)) for r, rec in with_reach(scopes, workspace))
        out = []
        for sc in scopes:
            if isinstance(sc, str) and sc.startswith("path:"):
                raw = sc[5:]
                rec = raw.endswith("/**")
                if rec:
                    raw = raw[:-3]
                out.append((os.path.realpath(os.path.expanduser(raw)), rec))
        return tuple(out)
    except Exception:
        return ()


@dataclass(frozen=True)
class GatewayVerdict:
    decision: str          # "allow" | "warn" | "deny"
    rule: str = ""
    reason: str = ""
    innate: bool = False
    stage: str = ""        # which stage decided: registry | local-law | society
    witness_id: Optional[str] = None   # the deny's chain hash once witnessed (appeal handle)
    # The path roots the law consulted for this verdict, WITH THEIR REACH: a tuple of
    # (abs_root, recursive) pairs since hestia #1002 — exact unless the operator made the
    # grant recursive. The dispatcher's own confinement follows THESE, not only the home,
    # and must honour the reach, or SAGE's defense-in-depth is wider than the law. Legion measured
    # 2026-09-05 that a shared-context read grant "cannot be used at all" because the local
    # dispatcher confined memory_read to the instance dir before hestia's gate was consulted.
    granted: tuple = ()

    @property
    def blocks(self) -> bool:
        return self.decision == "deny"


@dataclass
class ResultEnvelope:
    """What comes back from an intent — the being's tool-result. On ALLOW this is
    produced by the F1a dispatcher (hestia executing + witnessing); on DENY it is a
    refusal; when F1a is not yet wired it is `pending`. Never fabricated."""
    ok: bool = False
    result: Any = None
    error: Optional[str] = None
    witness_id: Optional[str] = None
    refused: bool = False
    pending: bool = False
    note: str = ""
    verdict: Optional[GatewayVerdict] = None

    def to_tool_message(self) -> str:
        """Render for re-injection into the being's conversation as the tool result."""
        if self.refused:
            return f"[refused by hestia — {self.error}]"
        if self.pending:
            return f"[allowed by law, not yet executed — {self.note}]"
        if self.ok:
            import json as _json
            body = self.result if isinstance(self.result, str) else _json.dumps(self.result)
            return body + (f"  (witnessed {self.witness_id})" if self.witness_id else "")
        return f"[dispatch error — {self.error}]"


# A Dispatcher is F1a's contract, SAGE-side: given an ALLOWED intent + its verdict,
# execute it on the being's behalf and return a witnessed ResultEnvelope. Injected,
# so the real one is hestia's F1a; tests pass a mock; unset means "pending F1a".
Dispatcher = Callable[["BeingIntent", GatewayVerdict], ResultEnvelope]


class BeingGateClient:
    """One per being. Governs every intent through the real hestia law, fail-closed."""

    def __init__(self, member_id: str, identity_path: str, workspace: str,
                 worktree: Optional[str] = None,
                 dispatcher: "Optional[Dispatcher]" = None,
                 host_session_id: Optional[str] = None):
        self.member_id = member_id
        self.workspace = workspace
        # the being's own worktree; composed commands name paths inside it
        self.worktree = worktree
        # The being's memory root: the instance dir that holds its identity. Relative
        # memory paths the being emits are rooted here (see _normalize).
        self.memory_root = os.path.dirname(os.path.abspath(os.path.expanduser(identity_path)))
        # Stable per-run id handed to hestia_connect for connect idempotency (the
        # society stage connects per query; this keeps those sessions one lineage).
        self.host_session_id = host_session_id
        self._dispatcher = dispatcher  # F1a; None until the hestia substrate exists
        self._core = None
        self._mech = None
        self._import_error = "hestia gate core not located"

        shared = _resolve_hestia_shared()
        if shared and shared not in sys.path:
            sys.path.insert(0, shared)
        self._identity_path = identity_path
        # Single gate (hestia #934): when installed, ONE law-bearing sequence decides and this
        # client is a shim — profile data + syntax translation, no policy sequencing of its
        # own. Absent (pre-#934 engine), the per-primitive path below stays as the fallback.
        try:
            import hestia_single_gate as _sg  # type: ignore
            self._single_gate = _sg
            self._single_gate_error = None
        except Exception as e:
            self._single_gate = None
            self._single_gate_error = repr(e)
        # Import the ONE shared law. A broken/missing core is fail-closed (gate()).
        try:
            import hestia_gate_core as _core  # type: ignore
            self._core = _core
            self._profile = _core.HarnessProfile(
                member_id=member_id,
                identity_path=identity_path,
                default_role="role:constellation:member",
            )
        except Exception as e:  # import failure == being is DENIED all effectors
            self._import_error = repr(e)
        # society-safety second stage (daemon round-trip); optional, fail-closed
        try:
            import hestia_gate_mechanism as _mech  # type: ignore
            self._mech = _mech
        except Exception:
            self._mech = None

    # -- which law-bearing path this client will take (measured, not asserted) --------
    @property
    def gate_path(self) -> str:
        """'single-gate' when hestia_single_gate (#934) imported, else 'local-law' (the
        pre-#934 per-primitive fallback). A conformance report must print this: a green
        run on 'local-law' says nothing about the shim."""
        return "single-gate" if getattr(self, "_single_gate", None) is not None else "local-law"

    @property
    def single_gate_status(self) -> str:
        """'present' or 'absent: <import error>' — the marker Legion asked for, so a 5/0/3
        cannot be read as 'the single-gate shim passed' when the module was never there."""
        if getattr(self, "_single_gate", None) is not None:
            return "present"
        return f"absent: {getattr(self, '_single_gate_error', None) or 'not imported'}"

    # -- normalize a being intent into the gate's NormalizedEvent -------------
    def _normalize(self, intent: BeingIntent):
        spec = _REGISTRY[intent.effector]
        paths: List[str] = []
        for a in spec["path_args"]:
            v = intent.args.get(a)
            if v:
                p = os.path.expanduser(str(v))
                # The being's memory paths are relative to ITS OWN memory root (the
                # instance dir), never to the process cwd: the gate must judge the same
                # path the dispatcher will touch (reference_f1a._safe_path roots the same way).
                if not os.path.isabs(p):
                    p = os.path.join(self.memory_root, p)
                # realpath, not abspath: the dispatcher resolves symlinks (_safe_path), so the
                # judged path and the touched path must be the same real path
                paths.append(os.path.realpath(p))
        command = intent.args.get(spec["cmd_arg"]) if spec["cmd_arg"] else None
        compose = spec.get("compose")
        if compose is not None:
            ctx = {"worktree": getattr(self, "worktree", None)}
            # a COMPOSED verb: the seat builds the exact outward act (a shell line) from the
            # being's args, and THAT is what the law judges. Bad args raise here and gate()
            # turns that into a deny (gate.raised), never a silent pass. The being never
            # fills a command; the registry never carries a cmd_arg for a composed verb.
            command = compose(intent.args, ctx) if _takes_ctx(compose) else compose(intent.args)
        return self._core.NormalizedEvent(
            tool=spec["tool"], paths=paths, command=command,
            cwd=self.workspace, raw={"effector": intent.effector, **intent.args},
        )

    # -- gate one intent (intent -> verdict), fail-closed --------------------
    def gate(self, intent: BeingIntent) -> GatewayVerdict:
        # Stage 0: bounded registry. Unknown effector never reaches the law.
        if intent.effector not in _REGISTRY:
            return GatewayVerdict("deny", "registry.unbounded", stage="registry",
                                  reason=f"'{intent.effector}' is not a gateway-member effector")
        # --- Single gate (#934): the shim contract. The registry stage above is harness
        # syntax (which verbs exist); everything law-bearing happens in decide(). ---
        sg = getattr(self, "_single_gate", None)
        if sg is not None and self._core is not None:
            try:
                ev = self._normalize(intent)
                tool = _REGISTRY[intent.effector]["tool"]  # the spec is the source, not the event
                gp = sg.GateProfile(member_id=self.member_id, identity_path=self._identity_path,
                                    default_role="role:constellation:member",
                                    host_agent=getattr(self, "_host_agent", "sage-raising"),
                                    client_name=f"sage-{self.member_id}-gate")
                ge = sg.GateEvent(tool=tool, tool_input=dict(intent.args), cwd=self.workspace,
                                  session_id=getattr(self, "host_session_id", None),
                                  raw={"effector": intent.effector, **intent.args})
                d = sg.decide(ge, gp)
                available = getattr(d, "verdict_available", True)
                dec = d.decision if (available and d.decision in ("allow", "warn", "deny")) else "deny"
                rule = d.rule or ("" if available else "gate.no_verdict")
                return GatewayVerdict(dec, rule, getattr(d, "reason", "") or ("ok" if dec != "deny" else ""),
                                      innate=False, stage="single-gate")
            except Exception as e:  # a gate that raises is a refused act, never an ungoverned one
                return GatewayVerdict("deny", "gate.raised", innate=True, stage="single-gate",
                                      reason=f"{type(e).__name__}: {e}")
        # Fail-closed: no law core -> stopped, not ungoverned.
        if self._core is None:
            return GatewayVerdict("deny", "gate.unreachable", innate=True, stage="local-law",
                                  reason=f"gate core unavailable: {self._import_error}")
        # Stage 1: local law (innate egress/secret + MRH path/command scope).
        try:
            ev = self._normalize(intent)
            # Resolve the member's LIVE policy (its grants) the way every real shim does:
            # fetch the daemon's snapshot and feed it to resolve_agent_policy as the vault
            # reader. With policy=None the core sees `granted: ()` and an operator's live
            # grant is never consulted (measured 2026-09-03: dp granted scope-311387783493
            # and memory_write still denied mrh.path). No snapshot => degrade to policy=None
            # (the core's own fail-closed path), never a manufactured grant.
            policy = None
            if self._mech is not None:
                try:
                    snap = self._mech.fetch_policy_snapshot(
                        self.member_id, host_agent=getattr(self, "_host_agent", "sage-raising"))
                    if snap is not None:
                        policy = self._core.resolve_agent_policy(self._profile,
                                                                 vault_reader=lambda _m: snap)
                except Exception:
                    policy = None
            v = self._core.evaluate(ev, self._profile, self.workspace, policy=policy)
            granted = _granted_roots(self._core, policy, self.workspace)
        except Exception as e:
            return GatewayVerdict("deny", "gate.raised", innate=True, stage="local-law",
                                  reason=f"{type(e).__name__}: {e}")
        if v.decision == "deny":
            return GatewayVerdict("deny", v.rule, v.reason, v.innate, stage="local-law")
        # Stage 2: society safety (daemon). A consequential act the society cannot
        # vet must NOT proceed — fail-closed. Observational acts soft-pass when the
        # mechanism is unavailable (no external effect; witness is accountability).
        consequential = intent.effector in _CONSEQUENTIAL
        if self._mech is None:
            if consequential:
                return GatewayVerdict("deny", "society.unavailable", stage="society",
                                      reason="society-safety mechanism unavailable; consequential act denied")
        else:
            try:
                # The mechanism's REAL contract (hestia plugins/_shared/hestia_gate_mechanism.py
                # `query_society_safety(event, *, plugin_id, host_agent, ...)`): the event is
                # {tool_name, tool_input} and the answer is a SafetyVerdict whose `allow` is the
                # only field a caller may proceed on; `decided=False` is a fail-closed non-verdict.
                # Until 2026-09-02 this was called as `query_society_safety(ev.raw)`, which raised
                # TypeError on every call — so every consequential act was denied
                # `society.unreachable` and the "governor" was never actually consulted.
                safe = self._mech.query_society_safety(
                    {"tool_name": ev.tool, "tool_input": dict(ev.raw)},
                    plugin_id=self.member_id, host_agent=_HOST_AGENT,
                    host_session_id=self.host_session_id)
                if not getattr(safe, "allow", False):
                    decided = getattr(safe, "decided", False)
                    return GatewayVerdict(
                        "deny", "society.unsafe" if decided else "society.no_verdict",
                        stage="society",
                        reason=getattr(safe, "message", None) or "society denied")
            except Exception as e:
                if consequential:
                    return GatewayVerdict("deny", "society.unreachable", stage="society",
                                          reason=f"society-safety failed ({type(e).__name__}); consequential act denied")
                # observational: local law already allowed, soft-pass
        return GatewayVerdict(v.decision, v.rule, v.reason or "ok", v.innate, stage="local-law",
                              granted=granted)

    # -- the F1a seam: gate, then dispatch, then consume the result ----------
    def dispatch(self, intent: BeingIntent) -> ResultEnvelope:
        v = self.gate(intent)
        if v.blocks:
            # A refusal is witnessed on the chain as a policy_decision, so the being holds
            # a hash it can appeal (hestia_appeal needs one; a client-side deny that never
            # reached the chain was unappealable, measured 2026-09-05). Unwitnessed when the
            # daemon is unreachable: the refusal stands either way, and says so.
            wid = None
            wd = getattr(self._dispatcher, "witness_deny", None)
            if wd is not None:
                try:
                    wid = wd(intent, v)
                except Exception:
                    wid = None
            import dataclasses as _dc
            v = _dc.replace(v, witness_id=wid)      # GatewayVerdict is frozen
            err = f"{v.rule}: {v.reason}"
            err += (f" (deny witnessed {wid}; if you think this is wrong, appeal with deny_hash={wid})"
                    if wid else " (deny not witnessed: daemon unreachable, so it cannot be appealed yet)")
            return ResultEnvelope(ok=False, refused=True, verdict=v, error=err, witness_id=wid)
        if self._dispatcher is None:
            # F1a not wired: allowed by law, but nothing can execute it yet. We
            # surface that honestly — we do NOT fabricate a result (PR #579 / F1a).
            return ResultEnvelope(ok=False, pending=True, verdict=v,
                                  note="awaiting hestia dispatch substrate (F1a)")
        # F1a executes on the being's behalf and returns a witnessed envelope; we
        # consume it verbatim. A dispatcher that throws is a failed act, not an
        # ungoverned one — the intent was already gated ALLOW above.
        try:
            env = self._dispatcher(intent, v)
        except Exception as e:
            return ResultEnvelope(ok=False, verdict=v,
                                  error=f"dispatch failed ({type(e).__name__}): {e}")
        env.verdict = v
        return env


if __name__ == "__main__":  # runnable demo / smoke test
    inst = os.path.expanduser(
        "~/ai-workspace/sage/sage/instances/sprout-qwen3.8-distill-2b")
    c = BeingGateClient("sprout-being", inst + "/identity.json",
                        os.path.expanduser("~/ai-workspace/sage"))
    demos = [
        ("peer_ask -> legion",      BeingIntent("peer_ask", {"to": "legion", "body": "hi"})),
        ("witness session close",   BeingIntent("witness", {"event": "session_close"})),
        ("memory_write own note",   BeingIntent("memory_write", {"path": inst + "/notes.md", "content": "x"})),
        ("shell (not in registry)", BeingIntent("shell", {"command": "rm -rf /"})),
        ("memory_write ESCAPE",     BeingIntent("memory_write", {"path": "/etc/cron.d/x", "content": "x"})),
        ("memory_read credential",  BeingIntent("memory_read", {"path": "~/.ssh/id_ed25519"})),
    ]
    print(f"{'intent':26} {'dec':6} {'rule@stage':28} reason")
    for label, it in demos:
        v = c.gate(it)
        print(f"{label:26} {v.decision.upper():6} {(v.rule or '-') + '@' + v.stage:28} {(v.reason or '')[:44]}")
    env = c.dispatch(demos[0][1])
    print(f"dispatch(peer_ask): verdict={env.verdict.decision} pending={env.pending} "
          f"-> {env.to_tool_message()}")
