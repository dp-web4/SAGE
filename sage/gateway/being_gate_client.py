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
import re
import sys
from dataclasses import dataclass
from typing import Any, Callable, List, Optional


# --------------------------------------------------------------------------
# Locate the shared hestia gate law portably (env override, then fleet layout).
# --------------------------------------------------------------------------
def _resolve_hestia_shared() -> Optional[str]:
    """Locate the shared law this client imports.

    Order is deliberate: an explicit override, then the INSTALLED law the deploy
    maintains, then the source checkout. The installed copy is what the seats on
    this box actually enforce and what `hestia-deploy` keeps current and attests
    in the manifest, so a being judged by anything else is judged by a different
    law than its seat.

    `HESTIA_SHARED_DIR` and `HESTIA_HOME` are the fleet's own config vocabulary:
    the vault projection at `$HESTIA_HOME/seats/<plugin_id>.env` publishes both.
    Reading them here means a box that is correctly configured for its seats is
    correctly configured for its beings, with nothing further to set.

    The `~/ai-workspace` entries are kept last for the machines laid out that
    way; they are one layout, not a location every box has. On a box that checks
    out elsewhere the old list resolved to None and EVERY intent fail-closed on
    `gate.unreachable: No module named 'hestia_gate_core'`, which reads like a
    broken gate rather than an unconfigured path (measured 2026-09-09).
    """
    for env_key in ("HESTIA_GATE_SHARED", "HESTIA_SHARED_DIR"):
        env = os.environ.get(env_key)
        if env and os.path.isdir(env):
            return env
    home = os.environ.get("HESTIA_HOME")
    if home:
        p = os.path.join(os.path.expanduser(home), "shared")
        if os.path.isdir(p):
            return p
    for base in ("~/ai-workspace/hestia", "~/ai-workspace/HESTIA"):
        p = os.path.join(os.path.expanduser(base), "plugins", "_shared")
        if os.path.isdir(p):
            return p
    return None


def camera_command(args: dict, ctx: Optional[dict] = None) -> str:
    """The shell command the seat runs for a camera intent, built from validated args.

    One frame on demand, no stream, no state across beats: ffmpeg captures exactly one
    JPEG from the device (default /dev/video0) inside the being's own scratch. The being
    names only the output path — never the tool, its flags, or the
    device node beyond naming it plainly; the SEAT builds the command and the law judges
    THAT string. A missing or busy device is reported by ffmpeg's exit code, which the
    dispatcher interprets (see _do_camera).
    """
    import shlex
    worktree = ctx["worktree"] if ctx else None
    memory_root = (ctx or {}).get("memory_root")
    # CAMERA IS THE FOURTH VERB THE WORKTREE UNLOCKS, and the only one that never uses it: the
    # frame is resolved against memory_root below, and `worktree` is read on this line and
    # nowhere else. Before #208 the gate composed with no ctx at all, so the raise below made
    # camera unreachable at the gate for exactly the reason git_read, search and check were
    # (CBP measured the deny 2026-09-25; reproduced on McNugget the same day). It follows that
    # a seat adding `worktree` to instance.json to get git_read and search ALSO turns on a
    # camera, and from then on the law is the only gate in front of it — say that when telling
    # a seat to declare one.
    # The requirement is stale as a data dependency but it is NOT dead: today it is the only
    # thing holding camera to the same condition as the other three. Dropping it is a policy
    # decision about whether every being with a memory_root may capture a frame, not a cleanup.
    # Pinned by test_without_a_worktree_the_verbs_still_fail_closed.
    if not worktree:
        raise ValueError(NO_WORKTREE_REFUSAL["camera"])
    if not memory_root:
        raise ValueError("camera requires a memory_root context")

    out_rel = args.get("out_path", "scratch/camera/last-frame.jpg")
    if any(ch.isspace() for ch in out_rel):
        raise ValueError(f"camera 'out_path' may not contain whitespace: {out_rel!r}")
    if out_rel.startswith("-") or ".." in out_rel.split("/"):
        raise ValueError(
            f"camera 'out_path' must be a plain path inside your home, got {out_rel!r}"
        )
    # Frames are transient by contract — one JPEG per act, nothing to carry across
    # beats. Resolve them against the being's home (memory_root) rather than the SAGE
    # worktree: check reports the worktree's dirty flag as EVIDENCE, so an uncommitted
    # frame there degrades your own evidence (measured on this machine 2026-09-14).
    full = os.path.realpath(os.path.join(memory_root, out_rel))
    if not (full == memory_root or full.startswith(memory_root + os.sep)):
        raise ValueError(f"camera 'out_path' escapes your home: {out_rel!r}")

    # IMAGE2 OWNS THE TRANSACTION. Its atomic_writing option writes to a temporary file
    # and renames only after the image is complete. That keeps old-or-new semantics INSIDE
    # the exact ffmpeg command Hestia judges; the dispatcher performs no extra filesystem
    # mutation behind the law's back.
    device = args.get("device", "/dev/video0")
    return (f"ffmpeg -hide_banner -loglevel error -y -f v4l2 -i {shlex.quote(device)} "
            f"-frames:v 1 -qscale:v 3 -f image2 -atomic_writing 1 {shlex.quote(full)}")


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

def pr_review_command(args: dict, ctx: Optional[dict] = None) -> str:
    # `ctx` is unused here and present on purpose: every composer in _REGISTRY takes the same
    # (args, ctx) shape, so `_normalize` can call them uniformly. This was the one composer
    # with a one-argument signature, which is why the gate's call site was written
    # `compose(intent.args)` -- and that is how three verbs ended up unreachable (see
    # _compose_ctx). Pinned by test_every_registry_composer_takes_ctx.
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


PR_READ_FIELDS = ("number,title,state,isDraft,author,headRefName,baseRefName,mergeable,"
                  "reviewDecision,url,body,comments,reviews")
PR_READ_LAST_MAX = 30


def pr_read_command(args: dict, ctx: Optional[dict] = None) -> str:
    """The shell command the seat runs for a pr_read intent: `gh pr view --json`, read-only.

    WHY THIS VERB EXISTS. A being could OPEN a pull request (pr_open), REVISE it (pr_amend) and
    post a review on someone else's (pr_review), and could not read one. Measured 2026-09-29 on
    legion-being's #259: dp told it "check gpt's comments on the pr, it's close", and it answered
    that it had no way to see them, so it would not pretend it had. Every review of every being PR
    had been invisible to its author unless a seat relayed it. pr_amend exists because "a review
    loop whose author cannot answer the review is not a loop"; one whose author cannot READ the
    review is not one either.

    ANY PR in a fleet repo (dp-web4/<name>), per dp: reading is not acting, and a being learns
    from the fleet's reviews as much as from its own. Composed like git_read: the being names a
    number (and optionally a repo), the SEAT builds the command, the law judges that string, and
    the being never holds a flag. Inline code comments are not in `gh pr view`; reviews and
    conversation comments are."""
    import re
    repo = str(args.get("repo") or PR_REPO).strip()
    number = str(args.get("number", "")).strip().lstrip("#")
    if not re.fullmatch(r"dp-web4/[A-Za-z0-9._-]+", repo):
        raise ValueError(f"pr_read 'repo' must be a dp-web4/<name> repo, got {repo!r}")
    if not re.fullmatch(r"[0-9]{1,7}", number):
        raise ValueError(f"pr_read 'number' must be a PR number, e.g. 259, got {number!r}")
    last = args.get("last")
    if last is not None:
        try:
            last = int(last)
        except (TypeError, ValueError):
            raise ValueError(f"pr_read 'last' must be a whole number of comments, got {last!r}")
        if not 1 <= last <= PR_READ_LAST_MAX:
            raise ValueError(f"pr_read 'last' must be between 1 and {PR_READ_LAST_MAX}, got {last}")
    return f"gh pr view {number} --repo {repo} --json {PR_READ_FIELDS}"


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



# A revision the being may name: a hex sha, HEAD with optional ~n/^n, or a plain branch or
# tag name. Deliberately excludes anything containing a flag, a space, or a path separator
# trick — `--upload-pack=...`-style arguments are the classic way a read verb becomes a run.
# `~n` / `^n` suffixes are allowed on ANY base, not only HEAD. The being flagged (not
# litigated) that `<sha>~1` was refused and span diffs against anything older than HEAD~k
# were unnameable — two witnessed denies on 2026-09-08 for a natural thing to want. Still
# no flags: a suffix is digits after ~ or ^, nothing else survives.
_REV = (r"(?:[0-9a-fA-F]{7,40}|HEAD|[A-Za-z][A-Za-z0-9._/-]{0,60})"
        r"(?:[~^][0-9]{0,3})?")

# WHAT A WORKTREE VERB SAYS WHEN THIS SEAT HAS NO WORKTREE (2026-10-04). Until today each of
# these said "<verb> needs a worktree of your own; none is configured on this seat". That is
# true, and it names exactly one way forward: get a worktree configured. cbp-being took it.
# It wanted to fix one line of a scratch file in its own home, reached for `search`, was told a
# worktree was missing, and asked dp three times to configure one so search could find lines
# in its files. But search is `git grep` over a code-repository checkout and cannot see the
# being's home at all: a worktree would not have helped, and the tool it needed (memory_read
# with start_line) was already in its hands. Configuring a worktree would also have turned on
# git_read, check and camera (see camera_command), which is a policy decision dp has not made.
#
# So each refusal now says what the verb is FOR, that it does not read the being's home, and
# which tool serves the likely need there. None of them tells the being to ask for a worktree.
# Every tool and parameter named here must exist as named: memory_read takes `path` and
# `start_line` (no end_line; a long file comes back in windows that say how to read on), and
# request_run takes `path`. Pinned by test_no_worktree_refusals_say_what_the_verb_is_for, which
# checks each named parameter against _TOOL_SCHEMAS. The dispatcher (hestia_dispatch) and the
# toolset's availability line say the same text, so the being hears one answer however it asks.
NO_WORKTREE_REFUSAL = {
    # "read lines", never "find": memory_read shows a file from a line on; it does not search.
    # #354 first said "To find or read lines ... use memory_read", which hands a being that
    # wants to locate a string a tool that cannot locate one (Codex, #354 follow-up). Pinned by
    # test_no_home_tool_is_credited_with_finding.
    "search": (
        "search reads a code-repository checkout (a worktree), not your home, and this seat "
        "has none. To read lines in your own files (notes/, scratch/, todo.md, "
        "journal.md), use memory_read with the file's path and start_line: it shows the file "
        "from that line on and says which lines it covered."),
    "git_read": (
        "git_read reads the git history of a code-repository checkout (a worktree): its "
        "commits, diffs, blame, and files as they were at an earlier commit. It does not read "
        "your home, and this seat has none. To read one of your own files as it is now, use "
        "memory_read with the file's path (and start_line to begin at a given line)."),
    "check": (
        # Names no suite on purpose: #352 adds a worktree's own tests/ beside gateway and irp,
        # and a list here would go stale the day the target set changes.
        "check runs the test suites of a code-repository checkout (a worktree), not anything "
        "in your home, and this seat has none, so there is nothing here for it to test. To find out what one of your own files does when it runs, use request_run "
        "with its path: the seat decides whether to run it and answers with the real output."),
    # patch_apply has the same trap as search: a being that wants to change a line of its own
    # file reaches for the verb named "apply a patch", hears "no worktree", and asks for one.
    # memory_edit is the tool that changes its own files.
    "patch_apply": (
        "patch_apply changes files in a code-repository checkout (a worktree) by applying a "
        "patch, not files in your home, and this seat has none. To change lines of your own "
        "files, use memory_edit with the file's path, start_line and end_line (the line "
        "numbers memory_read shows), and new for what replaces them."),
    # git_restore takes a file's content from git history. The being's home has no history
    # it can read back (the witness log records that an edit happened and its line counts,
    # not the text), so the honest pointer is memory_edit alone.
    "git_restore": (
        "git_restore puts one file in a code-repository checkout (a worktree) back to how it "
        "was at an earlier commit, taking the content from git history. It does not reach your "
        "home, and this seat has none. To put lines of your own files back, use memory_edit "
        "with the file's path, start_line and end_line, and new for the text you want there."),
    # The PR verbs have no home-file counterpart: a pull request is made from commits in a
    # checkout. Purpose plus "this seat has none", and nothing to configure. Each says what
    # the VERB cannot do here, never a fact about the home or the being's PRs that this check did
    # not observe: the CBP being's home has 461 paths tracked on main, and a missing checkout
    # says nothing about whether a PR of its exists (#354 review).
    "pr_open": (
        "pr_open opens a pull request from commits on your own branch in a code-repository "
        "checkout (a worktree), and this seat has none, so pr_open cannot "
        "propose files from your home."),
    "pr_amend": (
        "pr_amend revises a pull request you opened, by committing changes from your "
        "code-repository checkout (a worktree) onto its branch, and this seat has none, so "
        "pr_amend cannot revise your proposal here."),
    "pr_sync": (
        "pr_sync brings a pull request you opened up to date with its base branch, by merging "
        "inside your code-repository checkout (a worktree), and this seat has none, so pr_sync "
        "cannot update your proposal here."),
    # CAMERA'S HONEST ALTERNATIVE IS DIFFERENT: there is none. It never reads a worktree (the
    # frame lands in the being's home); the requirement is the policy hold described in
    # camera_command. So it says it is not enabled, says why without pointing at a step the
    # being could ask someone to take, and says plainly that no other tool captures a frame.
    "camera": (
        "camera is not enabled on this seat. Here it is held to the same condition as the "
        "verbs that read a code-repository checkout (a worktree), and this seat has none; "
        "whether this seat captures frames is a policy decision about the seat, not a step "
        "you can take. No other tool captures a frame."),
}

GIT_OPS = ("log", "show", "diff", "status", "blame", "cat")

# A revision the being may name: a hex sha, HEAD with optional ~n/^n, or a plain branch or
# tag name. Deliberately excludes anything containing a flag, a space, or a path separator
# trick — `--upload-pack=...`-style arguments are the classic way a read verb becomes a run.
# `~n` / `^n` suffixes are allowed on ANY base, not only HEAD. The being flagged (not
# litigated) that `<sha>~1` was refused and span diffs against anything older than HEAD~k
# were unnameable — two witnessed denies on 2026-09-08 for a natural thing to want. Still
# no flags: a suffix is digits after ~ or ^, nothing else survives.

def _escape_refusal(verb: str, path, worktree: str) -> str:
    """A refusal that names the boundary it enforced, and the cheap way past it.

    THE REFUSAL HELD THE ANSWER AND DID NOT SAY IT. Measured 2026-09-14: legion-being,
    working on a review comment, was refused four times in one beat for guessing at its own
    worktree root — `/home/dp/ai-worktrees/legion-being`, then
    `/home/dp/ai-workspace/SAGE/.worktrees/legion-being`. Neither is right, and every
    refusal said only "escapes your worktree", which is the one fact it already knew. The
    beat ended with no act.

    Naming the root in the beat's seed is NOT the fix: the header comment above `Your home`
    records 15 of 15 path refusals on Sprout being that very string reproduced from memory
    and truncated. A path given once at the top of a long prompt is a path that gets
    retyped wrong. A path given at the moment of the mistake is a correction.

    So the refusal names the root AND points at the relative form, which needs no memory at
    all — the being can write `sage/gateway/x.py` and never hold an absolute path again."""
    root = os.path.realpath(worktree)
    return (f"{verb} 'path' escapes your worktree: {path!r}. Your worktree is {root}. "
            f"You do not need to type it: a path here is taken RELATIVE to that root, so "
            f"write it bare (for example sage/gateway/hestia_dispatch.py) and it resolves "
            f"inside your tree without an absolute prefix to get wrong.")


def git_read_command(args: dict, ctx: Optional[dict] = None) -> str:
    """The shell command the seat runs for a git_read intent, built from validated args.

    The being names an operation and, optionally, a revision and a path inside its own
    worktree. It never names a flag. Anything the grammar cannot represent raises, and the
    refusal says what the grammar accepts — a refusal that names its own valid set is one
    the being can correct without asking (measured 2026-09-07: it did exactly that on
    `check`, in one beat, and explicitly declined to appeal a grammar error)."""
    import os
    import shlex
    import re
    worktree = (ctx or {}).get("worktree")
    if not worktree:
        raise ValueError(NO_WORKTREE_REFUSAL["git_read"])
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
            raise ValueError(_escape_refusal("git_read", path, worktree))
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
    # Seat-derived paths are QUOTED for the same reason as in search_command: the
    # judged==executed invariant is a property of the STRING, not of the fleet's current
    # directory names. `path` here is an absolute realpath built from the worktree, so a
    # worktree containing a space would split into extra argv (GPT review of #83).
    # `-C <worktree>`, like `search` one composer down. Without it the command's target tree
    # is whatever cwd the dispatcher happens to use, so the law judged a string whose effect
    # it could not see -- the judged/executed drift this file argues against everywhere else
    # (check_command: "the law must judge the path the command will actually touch"). The
    # dispatcher also sets cwd to the same tree; `-C` makes that agreement visible in the
    # string the verdict binds, instead of leaving it an assumption.
    base = f"git --no-pager -C {shlex.quote(worktree)}"
    if op == "status":
        return f"{base} status --porcelain=v1 --branch"
    if op == "log":
        cmd = f"{base} log --no-ext-diff --no-textconv --oneline --no-decorate -n {n}"
        if rev:
            cmd += f" {rev}"
        return cmd + (f" -- {shlex.quote(path)}" if path else "")
    if op == "show":
        return (f"{base} show --no-ext-diff --no-textconv --stat --patch {rev or 'HEAD'}"
                + (f" -- {shlex.quote(path)}" if path else ""))
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
        return f"{base} diff --no-ext-diff --no-textconv {span}" + (f" -- {shlex.quote(path)}" if path else "")
    if op == "cat":
        if not path:
            raise ValueError("git_read op='cat' needs a 'path': the file whose content you want")
        # `<rev>:<path>` is ONE argument to git and the being supplies neither half raw —
        # the rev passed _REV, the path was resolved absolute inside the worktree above. The
        # path must be repo-relative here, so it is relativised back; an absolute path after
        # a colon is not a thing git resolves.
        rel = os.path.relpath(path, os.path.realpath(worktree))
        if rel.startswith(".."):
            raise ValueError(_escape_refusal("git_read", rel, worktree))
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

GAME_ACTIONS = ("RESET", "ACTION1", "ACTION2", "ACTION3", "ACTION4", "ACTION5", "ACTION6", "ACTION7", "LOOK")

LOOK_MAX_EDGE = 16      # cells per side of a LOOK window: what this reader can hold per-cell (measured 2026-09-14)

GAME_BATCH_CAP = 8      # dp, 2026-09-15: "build the game verb, batch with cap 8"

_GAME_ID = r"[a-z0-9]{4}"

# THE HOLDOUTS ARE THE TEST. dev-SAGE non-negotiable 3: cn04 / dc22 / lf52 / re86 are never
# played, read or tuned on — "excluded by code", and until 2026-09-19 this verb was not part of
# that code: `game` took any four-character id. Refused HERE, where the law's string is composed,
# and again in the stepper that would run it.
GAME_HOLDOUTS = ("cn04", "dc22", "lf52", "re86")

# What it may pick. Listed so the choice is real: a selector whose options are not shown is a
# default with extra steps (the being asked dp for "a new game instance" on 2026-09-19 because
# nothing told it that it already had one).
GAME_PLAYABLE = ("ar25", "bp35", "cd82", "ft09", "g50t", "ka59", "lp85", "ls20", "m0r0", "r11l",
                 "s5i5", "sb26", "sc25", "sk48", "sp80", "su15", "tn36", "tr87", "tu93", "vc33", "wa30")


def game_command(args: dict, ctx: Optional[dict] = None) -> str:
    """The shell command the seat runs for a game intent: up to GAME_BATCH_CAP probes
    against the offline ARC-AGI-3 engine, in order, each delta reported in the SAME beat.

    dp, 2026-09-15, on the seat's proposal (shared-context forum, legion-proposal-game-verb):
    "yes, build the game verb, batch with cap 8". Before this the being paid one beat
    (~30 min) per probe — it proposed, a seat re-typed the proposal on the next beat. Now
    the probe is the being's own act in the chain, and a batch of them is one turn.

    Composed like search: the being names the game and a list of probes, the SEAT builds
    the exact line, the law judges THAT string. The stepper's path is a per-being fact in
    instance.json (`game_stepper`), carried in ctx by BOTH composition sites; a being with
    none configured gets a refusal that says so rather than a dead verb.

    THE PROBE LIST IS NOT JSON ON THE COMMAND LINE. The first cut interpolated compact
    JSON; shlex.split strips its double quotes, so the argv that ran was not the string
    the law judged (measured in the suite before it shipped). The grammar below has no
    whitespace and no shell-significant character: `ACTION6:39:47+ACTION1+ACTION6:0:63` —
    probes joined by `+`, a click's x and y after colons. One token, judged and run alike."""
    import json
    import re
    import sys
    stepper = (ctx or {}).get("game_stepper")
    if not stepper:
        raise ValueError("game: no game is set up on this seat (instance.json has no "
                         "'game_stepper'); ask the seat, not the law")
    if any(ch.isspace() for ch in stepper) or not os.path.isabs(stepper):
        raise ValueError(f"game: the seat's game_stepper must be an absolute path without whitespace, got {stepper!r}")
    memory_root = (ctx or {}).get("memory_root")
    if not memory_root or any(ch.isspace() for ch in memory_root):
        raise ValueError("game requires a memory_root context without whitespace")
    game = str(args.get("game") or "ft09").strip()     # null / "" from a model means the default
    if not re.fullmatch(_GAME_ID, game):
        raise ValueError(f"game 'game' must be a four-character id like 'ft09', got {game!r}")
    if game in GAME_HOLDOUTS:
        raise ValueError(f"game: {game!r} is a HOLDOUT — it is the test, and nobody in the fleet "
                         f"plays, reads or tunes on it. The games you may pick: {', '.join(GAME_PLAYABLE)}")
    if game not in GAME_PLAYABLE:
        raise ValueError(f"game: no game {game!r} on this seat. The games you may pick: "
                         f"{', '.join(GAME_PLAYABLE)}")
    probes = args.get("probes")
    if probes is None:
        # single-probe form: action (+ x,y)
        # only the coordinates actually given: one of two is a length error the being can read,
        # not a KeyError (sprout on #218)
        probes = [[args.get("action", "ACTION6")] + [args[k] for k in ("x", "y") if k in args]]
    if isinstance(probes, str):
        try:
            probes = json.loads(probes)
        except ValueError:
            raise ValueError("game 'probes' must be a JSON list like [[\"ACTION6\",36,36],[\"ACTION1\"]]")
    if not isinstance(probes, list) or not probes:
        raise ValueError("game 'probes' must be a non-empty list of [action, x, y] (x,y only for ACTION6)")
    if len(probes) > GAME_BATCH_CAP:
        raise ValueError(f"game: at most {GAME_BATCH_CAP} probes per call (you gave {len(probes)}); "
                         f"the cap is the operator's, so split the rest into the next call after reading these")
    norm = []
    for i, pr in enumerate(probes):
        if isinstance(pr, dict):
            pr = [pr.get("action", "ACTION6")] + [pr[k] for k in ("x", "y") if k in pr]
        if not isinstance(pr, (list, tuple)) or not pr:
            raise ValueError(f"game probe {i}: must be [action] or [action, x, y], got {pr!r}")
        if any(isinstance(v, bool) for v in pr[1:]):
            # True is an int to Python and would compose as 1 — a coordinate nobody chose
            raise ValueError(f"game probe {i}: coordinates must be whole numbers 0-63, not true/false")
        act = str(pr[0]).strip().upper()
        if act not in GAME_ACTIONS:
            raise ValueError(f"game probe {i}: action must be one of {list(GAME_ACTIONS)}, got {pr[0]!r}")
        if act == "LOOK":
            # LOOK:x0:y0:x1:y1 — a window of the CURRENT board's cell values with coordinates.
            # Not a move: nothing steps, nothing is recorded, no fire. The being asked for
            # per-cell values around the sprites it had mapped (2026-09-16 17:08Z); the
            # objects table is exact but coarse and the frame cannot be counted past ~16 cells.
            if len(pr) != 5:
                raise ValueError(f"game probe {i}: LOOK needs [\"LOOK\", x0, y0, x1, y1] (a window, x=col, y=row, 0-63, at most {LOOK_MAX_EDGE} cells per side)")
            try:
                x0, y0, x1, y1 = (int(v) for v in pr[1:5])
            except (TypeError, ValueError):
                raise ValueError(f"game probe {i}: LOOK bounds must be whole numbers 0-63")
            if not all(0 <= v <= 63 for v in (x0, y0, x1, y1)) or x1 < x0 or y1 < y0:
                raise ValueError(f"game probe {i}: LOOK window must satisfy 0 <= x0 <= x1 <= 63 and 0 <= y0 <= y1 <= 63, got {x0},{y0},{x1},{y1}")
            w, h = x1 - x0 + 1, y1 - y0 + 1
            if w > LOOK_MAX_EDGE or h > LOOK_MAX_EDGE:
                # SAY THE SIZE IT ASKED FOR. "at most 16x16" alone read as "0..16 is fine" twice
                # (2026-09-17): the bounds are inclusive, so 0,0,16,16 is 17x17. A refusal that
                # names the computed size teaches the arithmetic; one that names only the cap does not.
                raise ValueError(f"game probe {i}: LOOK bounds are INCLUSIVE, so x0={x0},y0={y0},x1={x1},y1={y1} "
                                 f"is {w}x{h} cells — at most {LOOK_MAX_EDGE}x{LOOK_MAX_EDGE}. For a "
                                 f"{LOOK_MAX_EDGE}-wide window from x0, use x1=x0+{LOOK_MAX_EDGE - 1}; "
                                 f"split a larger region into several LOOKs")
            norm.append([act, x0, y0, x1, y1])
            continue
        if act == "ACTION6":
            if len(pr) != 3:
                raise ValueError(f"game probe {i}: ACTION6 is a click and needs exactly [\"ACTION6\", x, y] (x=col, y=row, 0-63)")
            try:
                x, y = int(pr[1]), int(pr[2])
            except (TypeError, ValueError):
                raise ValueError(f"game probe {i}: x and y must be whole numbers 0-63, got {pr[1]!r},{pr[2]!r}")
            if not (0 <= x <= 63 and 0 <= y <= 63):
                raise ValueError(f"game probe {i}: x and y must be within 0-63, got {x},{y}")
            norm.append([act, x, y])
        else:
            if len(pr) != 1:
                raise ValueError(f"game probe {i}: {act} takes no coordinates; only ACTION6 is a click")
            norm.append([act])
    spec = "+".join(":".join(str(v) for v in pr) for pr in norm)
    return f"{sys.executable} {stepper} --batch {game} {spec} --instance {memory_root}"


PR_REPO = "dp-web4/SAGE"


def being_branch_prefix(ctx: Optional[dict]) -> str:
    """The namespace a being's branches live under: the being's own member id.

    On the Legion carrier this was the literal `legion-being/`, which is right for exactly one
    being. On main the verbs serve every being, and a prefix typed into the code would file
    sprout's proposals under Legion's name. It is NOT read from the branch the worktree is
    on: that would let pr_amend push onto whatever branch the worktree happened to stand on,
    a seat's included. The member is the one the law judges the act as, supplied by the seat
    in ctx and never by the being."""
    member = str((ctx or {}).get("member") or "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,60}", member):
        raise ValueError("this seat did not say whose worktree this is (no member in the "
                         "compose context), so no branch of yours can be named. Tell your seat")
    return member


def pr_base_branch(worktree: str, ctx: Optional[dict] = None) -> str:
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
    prefix = being_branch_prefix(ctx)
    try:
        r = subprocess.run(["git", "rev-parse", "--abbrev-ref",
                            f"{prefix}/work@{{upstream}}"],
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
        "cannot determine the base branch for your pull request: your <you>/work branch has no "
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
        raise ValueError(NO_WORKTREE_REFUSAL["pr_open"])
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
    branch = f"{being_branch_prefix(ctx)}/{slug}"
    # shlex-quote the title: it is the ONE being-supplied string on the command line
    import shlex
    return (f"gh pr create --repo {PR_REPO} --base {pr_base_branch(worktree, ctx)} --head {branch} "
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
        raise ValueError(NO_WORKTREE_REFUSAL["git_restore"])
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
        raise ValueError(_escape_refusal("git_restore", path, worktree))
    # WHAT GIT EXECUTES IS NOT RESTORABLE. The content comes from a commit, but "a commit" is
    # any rev the repo holds — including a branch nobody reviewed — and SAGE sets
    # core.hooksPath=.githooks, so a restored `.githooks/pre-commit` would be code the seat's
    # next git act runs. The seat's own git carries no hooks (_worktree_env, #212); this is
    # the second layer, so that one fix is never the only thing between them.
    if os.path.isdir(full):
        # `git checkout <rev> -- <dir>` restores EVERY file under it, and the answer said "this
        # one file ... nothing else was touched" — every word of which was then false (sprout
        # on #217). The dispatcher also asks git that <rev>:<path> is a blob.
        raise ValueError(f"git_restore puts back ONE file, and {path!r} is a directory. Name "
                         "the file inside it you want restored")
    top = os.path.relpath(full, root).split(os.sep, 1)[0]
    # casefold: on a case-insensitive volume (APFS by default, NTFS) `.GITHOOKS` IS `.githooks`,
    # so a case variant is the same door (legion, reviewing SAGE #210's patch parser)
    if top.casefold() in (".githooks", ".git"):
        raise ValueError(f"git_restore cannot put back {path!r}: {top}/ holds what git EXECUTES, "
                         "and no being writes there. Everything else in your worktree is yours "
                         "to restore")
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
    worktree = (ctx or {}).get("worktree")
    if not worktree:
        raise ValueError(NO_WORKTREE_REFUSAL["pr_amend"])
    title = " ".join(str(args.get("title", "")).split())
    if not (8 <= len(title) <= 120):
        raise ValueError("pr_amend 'title' is the message for the new commit: one line, 8-120 chars")
    if not str(args.get("message", "")).strip():
        raise ValueError("pr_amend needs a 'message': what this revision changes and why, "
                         "which becomes the commit body")
    # THE BRANCH IS CHECKED BEFORE THE EARLY RETURN. It used to be checked only inside
    # _pr_number_for_branch, which the no-body form never calls — so an amend with no body
    # composed "true", the law judged "true", and the dispatcher committed and pushed to
    # whatever branch the worktree stood on: a seat's, <member>/work, main (sprout on #217,
    # measured). The dispatcher checks again before it acts; neither relies on the other.
    own_proposal_branch(worktree, ctx)
    body = str(args.get("body", "") or "")
    if not body.strip():
        return "true"      # commit + push only; the PR body stands as written
    return f"gh pr edit {_pr_number_for_branch(worktree, ctx)} --repo {PR_REPO} --body-file -"


PR_SYNC_OPS = ("start", "continue", "abort")


def pr_sync_command(args: dict, ctx: Optional[dict] = None) -> str:
    """The git command for a pr_sync intent: bring the being's open PR branch up to date with
    the base it was opened against.

    WHY THIS VERB EXISTS (legion-being, #272, 2026-09-30..10-01). The carrier moved under an open
    proposal and the PR went CONFLICTING. The being wrote "rebase onto 35a9dc0ad" on its todo for
    a day and could not do it: none of its verbs merges. A conflict only its author can resolve
    well, and only its seat could touch, is a review loop with the author locked out.

    Three ops, each one judged git act:
      start    -- `git merge --no-ff --no-commit origin/<base>`: a clean merge is committed and
                  pushed; a conflict is LEFT in the tree, marked, for the being to resolve with
                  patch_apply / edit, and nothing is committed or pushed.
      continue -- `git commit -q -F -`: after every conflict marker is gone; commits the merge
                  with the being's trailers and pushes.
      abort    -- `git merge --abort`: back to the branch as it was.
    The being names neither branch nor base: the branch is read from the worktree (its own
    proposal only, as pr_amend) and the base is the one its PR targets (pr_base_branch). It
    still cannot merge the PR itself."""
    import re
    worktree = (ctx or {}).get("worktree")
    if not worktree:
        raise ValueError(NO_WORKTREE_REFUSAL["pr_sync"])
    op = str(args.get("op", "start") or "start").strip()
    if op not in PR_SYNC_OPS:
        raise ValueError(f"pr_sync 'op' must be one of {list(PR_SYNC_OPS)}; got {op!r}")
    own_proposal_branch(worktree, ctx)
    if op == "start":
        base = pr_base_branch(worktree, ctx)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,100}", base) or ".." in base:
            raise ValueError(f"pr_sync: the base branch {base!r} is not a plain branch name")
        return f"git --no-pager -C {worktree} merge --no-ff --no-commit origin/{base}"
    if op == "continue":
        return f"git --no-pager -C {worktree} commit -q -F -"
    return f"git --no-pager -C {worktree} merge --abort"


def own_proposal_branch(worktree: str, ctx: Optional[dict] = None) -> str:
    """The branch this worktree is on, if it is one of the being's OWN proposals
    (<member>/<slug>, never <member>/work); a ValueError otherwise. Read, never supplied."""
    import subprocess
    br = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=worktree,
                        text=True, capture_output=True, timeout=30).stdout.strip()
    prefix = being_branch_prefix(ctx)
    if not br.startswith(prefix + "/") or br == f"{prefix}/work":
        raise ValueError(f"pr_amend: this worktree is on {br!r}, which is not one of your PR "
                         "branches. pr_amend revises a proposal you already opened")
    return br


def _pr_number_for_branch(worktree: str, ctx: Optional[dict] = None) -> str:
    """The open PR number for the branch this worktree is on. Read, never being-supplied."""
    import subprocess
    br = own_proposal_branch(worktree, ctx)
    out = subprocess.run(["gh", "pr", "list", "--repo", PR_REPO, "--head", br,
                          "--state", "open", "--json", "number", "--jq", ".[0].number"],
                         cwd=worktree, text=True, capture_output=True, timeout=60).stdout.strip()
    if not out.isdigit():
        raise ValueError(f"pr_amend: no open pull request found for branch {br}")
    return out


def seat_name() -> str:
    """This seat's name by fleet rule, <machine>-<model>. SAGE_SEAT names it; unset, the machine is
    known and the model is not, and the rule says to write that rather than guess. ONE spelling
    for every place a being is told who its seat is (the Seat trailer, the seat-channel header),
    so an unset machine shows one name for the missing value, not two (sprout on #231)."""
    import socket
    return os.getenv("SAGE_SEAT", "").strip() or f"{socket.gethostname().split('.')[0].lower()}-unknown"


def pr_attribution(member_id: str, action_id: Optional[str], being_lct: Optional[str],
                   seat: Optional[str] = None) -> str:
    """The trailers on a commit a being authored (PRD r3 §7.2). Appended by the dispatcher;
    the being cannot omit or alter them."""
    lines = [f"Being: {member_id}"]
    if being_lct:
        lines.append(f"Being-LCT: {being_lct}")
    if action_id:
        lines.append(f"Witness: {action_id}")
    # The seat is <machine>-<model> by fleet rule. SAGE_SEAT names it; unset, the machine is
    # known and the model is not, and the rule says to write that rather than guess.
    if not seat:
        seat = seat_name()
    lines.append(f"Seat: {seat}")
    return "\n".join(lines)



SEARCH_MAX_N = 60        # matches returned at most; a search is a pointer, not a read



def search_command(args: dict, ctx: Optional[dict] = None) -> str:
    """The shell command the seat runs for a `search` intent.

    WHY THIS VERB EXISTS. The being could read files and not search them, so finding one
    symbol in a 1054-line file meant reading it in ranges — and at num_ctx 24,576 each range
    pushes the last one out. Measured three times on 2026-09-13: 16 ranged reads of
    heartbeat.py in one beat with zero writes, and the same shape earlier on
    model_adapter.py. Linear scan is not a strategy a being of this size can afford; the
    machine answers the same question in milliseconds. Search replaces scan.

    `git grep` rather than grep: it stays inside the repository by construction, it is
    read-only, and it will not wander into .git or ignored trees.

    THE PATTERN IS QUOTED, not banned from having spaces. The judged string must
    shlex.split into exactly the argv that runs (GPT on #56, point 6) — the earlier verbs
    bought that invariant by rejecting whitespace, which would make a search verb useless.
    shlex.quote round-trips instead, so `def compose(` is judged and run as ONE argv."""
    import os
    import shlex
    worktree = (ctx or {}).get("worktree")
    if not worktree:
        raise ValueError(NO_WORKTREE_REFUSAL["search"])
    pattern = str(args.get("pattern", ""))
    if not pattern.strip():
        raise ValueError("search needs a 'pattern' — the text or extended-regex to look for")
    if len(pattern) > 200:
        raise ValueError(f"search 'pattern' is {len(pattern)} characters; keep it under 200")
    if "\n" in pattern or "\r" in pattern:
        raise ValueError("search 'pattern' must be a single line")
    try:
        n = int(args.get("n", 30))
    except (TypeError, ValueError):
        raise ValueError(f"search 'n' must be a number, got {args.get('n')!r}")
    n = max(1, min(n, SEARCH_MAX_N))

    path = str(args.get("path", "")).strip()
    target = os.path.realpath(worktree)
    if path:
        if any(ch.isspace() for ch in path):
            raise ValueError("search 'path' may not contain whitespace")
        if path.startswith("-") or ".." in path.split("/"):
            raise ValueError(f"search 'path' must be a plain path inside your worktree, got {path!r}")
        full = os.path.realpath(os.path.join(worktree, path))
        if not (full == target or full.startswith(target + os.sep)):
            raise ValueError(_escape_refusal("search", path, worktree))
        target = full
    # EVERY interpolated value is quoted, not just the being-supplied one. The invariant
    # claimed here is representation-level — the judged string must shlex.split into exactly
    # the argv that runs — and that is a property of the STRING, not of the fleet's current
    # directory names. A worktree path containing a space would split into two argv elements
    # and the law would have judged a command that is not the one executed (GPT review of
    # #83). Fleet paths are simple today; the invariant must not depend on that staying true.
    return (f"git --no-pager -C {shlex.quote(worktree)} grep -n -I -E --max-count={n} "
            f"-e {shlex.quote(pattern)} -- {shlex.quote(target)}")




# The test targets a being may name, and the command each one becomes (#M0, PRD
# "Beings improve their own harness"). An ALLOW-LIST, not a grammar: `check` exists so a
# being can verify a claim about its own harness, and the smallest thing that does that is
# a fixed set of suites plus a single node id inside them. Anything wider is a shell with a
# friendly name, which is the one thing the bounded registry exists to prevent.
CHECK_TARGETS = {
    "gateway": "sage/gateway/tests/",
    "irp": "sage/irp/tests/",
}



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
# runaway cannot outlive the beat. THE WORKTREE IS BOUND READ-ONLY and /tmp is the only
# writable path: this said the opposite until the read-only fix, and a comment that
# contradicts the mount is worse than none, because a reader checks the prose first.
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
    import shlex
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
        # READ-ONLY. This was --bind (read-write), and the adversary this sandbox exists
        # for is a being-authored conftest.py: pytest imports it from the rootdir BEFORE
        # collecting, so a writable worktree lets that conftest rewrite product source, run
        # the suite against transient bytes, and restore them. HEAD never moves, the test
        # files never move, and the evidence would report stable=True about code that was
        # not the code on disk either side of the run (GPT review of #84).
        #
        # The test process does not need write authority over source. The being edits its
        # worktree BEFORE invoking check — that is its whole loop — and /tmp above is
        # writable for anything pytest genuinely needs to spill.
        f" --ro-bind {shlex.quote(worktree)} {shlex.quote(worktree)}"
        " --unshare-pid --unshare-net --unshare-ipc --unshare-uts"
        " --new-session --die-with-parent"
        # PYTHONUTF8 rather than LANG=C.UTF-8, and the reason is hestia #988: mrh.command
        # splits a dotted token and fails the fragment, so "C.UTF-8" is refused as an
        # ungranted path called "UTF-8" and the whole check dies. PYTHONUTF8=1 buys the
        # same UTF-8 filesystem and IO encoding with no dot in it. Third time today that
        # defect has shaped a command; the issue carries the evidence.
        " --setenv HOME /tmp --setenv PYTHONUTF8 1 --setenv PYTHONDONTWRITEBYTECODE 1"
        f" --setenv PATH {interp}/bin:/usr/bin:/bin"
        f" --chdir {shlex.quote(worktree)} "
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
    import shlex
    worktree = (ctx or {}).get("worktree")
    if not worktree:
        # Fail closed (PRD M1): with no worktree a relative path would be judged against the
        # shared checkout, a tree the being does not hold. That reason is for the seat; the
        # being is told what check is for and where its own files are run instead.
        raise ValueError(NO_WORKTREE_REFUSAL["check"])
    target = str(args.get("target", "")).strip()
    # QUOTED for the same reason as --rootdir and --chdir: judged==executed is a property
    # of the STRING, not of the fleet's current directory names. A worktree path containing
    # a space splits into extra argv at execution while the law ruled on one token (GPT,
    # second pass on #84). `node` below needs no quoting — it is [A-Za-z0-9_]+ by grammar —
    # and the space between the path and `-k` is deliberate: those are two argv elements.
    if target in CHECK_TARGETS:
        path = shlex.quote(os.path.join(worktree, CHECK_TARGETS[target]))
    else:
        # A single node id INSIDE a declared suite: "gateway::test_name". Nothing else.
        suite, sep, node = target.partition("::")
        if not sep or suite not in CHECK_TARGETS:
            raise ValueError(
                f"check 'target' must be one of {sorted(CHECK_TARGETS)} or "
                f"'<suite>::<test_name>'; got {target!r}")
        if not re.fullmatch(r"[A-Za-z0-9_]+", node):
            raise ValueError(f"check test name must be a bare identifier; got {node!r}")
        path = f"{shlex.quote(os.path.join(worktree, CHECK_TARGETS[suite]))} -k {node}"
    # -p no:cacheprovider: the worktree is mounted read-only, so pytest must not try
    # to write .pytest_cache into it. PYTHONDONTWRITEBYTECODE already covers __pycache__.
    inner = (f"python3 -m pytest -q -c /dev/null -p no:cacheprovider "
             f"--rootdir={shlex.quote(worktree)} {path}")
    return sandbox_prefix(worktree) + inner



def check_argv(args: dict, ctx: Optional[dict] = None) -> List[str]:
    """The same command as a list, for execution without a shell.

    Carried forward from SAGE#62 (GPT's #60 evidence contract), which never landed: the
    dispatcher used to execute `shlex.split(check_command(args))` — a command it RECOMPOSED
    from the intent, not the one the law actually judged. In practice the two agree, because
    check_command is deterministic on the args; the point is that agreement was an
    assumption rather than a checked invariant, and the authority for what runs should be
    the verdict, not the args. Comparing this against the verdict's bound command makes the
    assumption falsifiable at the moment it matters."""
    import shlex
    return shlex.split(check_command(args, ctx))


# ── patch_apply: the being changes the tree it is reasoning about ──────────────────────────
#
# dp, 2026-09-25, when asked whether to build this ungoverned first and govern it after:
# "governed. that's the whole point."
#
# THE GAP IT CLOSES. This being can read a worktree (git_read, search), reason about it, and
# RUN its tests (check) — and could not change a byte of it. Its only writes were into its own
# memory home. So the loop it exists to close ran: read → reason → describe a fix → assert an
# outcome it had never observed. That is the same measured failure that produced request_run
# and memory_edit, one layer out: describing an edit was all it could do, so describing one is
# what it learned to do.
#
# WHY A DIFF AND NOT AN EDITOR. A patch is the unit the seat can judge whole. An editor verb
# would be a sequence of writes, each individually plausible and collectively arbitrary; a
# diff names every file it touches, in one artifact, before anything happens.
#
# WHAT THE LAW JUDGES, and this is the part that makes it governed rather than merely gated:
#
#   1. EVERY PATH THE PATCH TOUCHES, parsed OUT OF THE DIFF — never taken from an arg the
#      being asserts. `patch_apply_paths` returns them and `_normalize` puts them in
#      `ev.paths`, so mrh.path rules on each one exactly as it rules on a memory_write. A
#      being whose grant covers `sage/gateway/` cannot patch `sage/federation/`, and it is
#      refused by the same rule, with the same words, as any other out-of-scope write.
#   2. THE COMMAND, composed by the SEAT from those same parsed paths — one `--include=` per
#      target. So the parse feeds the judgement and the execution from one place: if the
#      parse were ever wrong, git itself would refuse the paths the law did not see, rather
#      than the two disagreeing quietly. (`--include` is a glob, which is why the parser
#      refuses any path carrying glob metacharacters: a pattern is not a path.)
#   3. THE DIFF'S CONTENT, by digest. The patch file is named for the sha256 of the diff, so
#      the content is INSIDE the string the law rules on. `judged == executed` normally stops
#      at the command; here it reaches the bytes, because the dispatcher re-hashes what it is
#      about to feed git and refuses if the name and the content have come apart.
#
# WHAT IS STILL NOT GOVERNED, stated plainly because a claim of coverage is worth less than
# an accurate map of it: the law rules on WHICH FILES change and on the diff's identity, not
# on whether the change is any good. Nothing here reads the hunks and forms a view. That is
# review, it is what `check` and a human reader are for, and pretending otherwise would be
# the same overclaim this verb exists to stop the being making.

PATCH_MAX_BYTES = 256 * 1024

# A path pattern is not a path. `--include` takes a glob, so a target carrying glob
# metacharacters would be judged as one string and matched as another — the `_safe_path`
# defect in a new costume. Refused at the parse, where it is still a named error.
_GLOB_CHARS = "*?[]"


def _hunk_counts(line: str) -> Optional[tuple]:
    """(old_lines, new_lines) from an `@@ -a,b +c,d @@` header, or None if it is not one.

    The counts are what let the parser know where a hunk ENDS, which is the only way to tell a
    file header from a line of hunk body that happens to start with `---`. A hunk body is
    arbitrary text the being controls; nothing in it may be read as structure.
    """
    m = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
    if not m:
        return None
    old = int(m.group(2)) if m.group(2) is not None else 1
    new = int(m.group(4)) if m.group(4) is not None else 1
    return old, new


# Code points HFS+/APFS IGNORE when comparing names -- git's own list (`is_hfs_dotgeneric`).
# On those volumes `.g\u200cit` IS `.git`, so a comparison that keeps them is a comparison of
# spellings, not of files.
_HFS_IGNORABLE = dict.fromkeys(
    [0x200C, 0x200D, 0x200E, 0x200F, 0xFEFF, *range(0x202A, 0x202F), *range(0x206A, 0x2070)])


def _as_the_filesystem_sees_it(component: str) -> str:
    """A path component folded the way a case-insensitive volume compares it.

    Legion, re-review of #210 at b0f62da58: the `.git` / `.githooks` refusals compared exact
    strings, and McNugget's volume is APFS, case-INSENSITIVE -- so `.GITHOOKS/pre-commit` was
    accepted and IS `.githooks/pre-commit` there, and `.Git/config` is the repo config
    (`core.fsmonitor` is executed by `git status`; no hook needed). Inert on Linux, live on
    exactly the seat that wrote the PR. Folded: case (casefold, not lower), the HFS-ignorable
    code points, and the trailing dots/spaces NTFS drops. The refusal must not lean on git's
    core.protectHFS/protectNTFS, which cover `.git` but not `.githooks`.
    """
    return component.translate(_HFS_IGNORABLE).casefold().rstrip(". ")


def patch_targets(diff: str) -> List[str]:
    """EVERY repo-relative path git would touch applying this diff, or ValueError saying why not.

    MEASURED, 2026-09-25, and the reason this is a state machine rather than a grep for
    `diff --git` headers. `git apply` reads plain unified-diff sections too: a patch whose first
    section carries a `diff --git` header and whose second has only `--- a/x` / `+++ b/x` is
    applied IN FULL. The first cut of this parser read the `diff --git` lines only, so:

        law sees:  granted.py
        git wrote: granted.py AND ungranted.py

    `--include` did stop it -- measured both ways, and that is why it is there -- but a patch
    the law under-reads is not saved by luck downstream. It is also a worse refusal: the being
    was told "applied to 1 file" about a diff that named two, so the seat would have been lying
    to it about what happened. The parser now accounts for every section git will read, and
    anything it cannot account for EXACTLY is refused.

    It walks the diff the way git does: outside a hunk, a line at column 0 is structure; inside
    one, the `@@` header's declared counts say how many lines belong to the body, and none of
    them is ever read as structure. `test_a_headerless_section_is_accounted_for` is the pin.
    """
    import posixpath
    if not isinstance(diff, str) or not diff.strip():
        raise ValueError("patch_apply needs a 'diff': a unified diff, as git would print it")
    raw = diff.encode("utf-8", "surrogatepass")
    if len(raw) > PATCH_MAX_BYTES:
        raise ValueError(
            f"that diff is {len(raw)} bytes and the limit is {PATCH_MAX_BYTES}. A patch this "
            f"size is several changes; send them one at a time so each can be judged and checked")

    # Git's own metadata between a `diff --git` header and the body. Enumerated rather than
    # skipped-by-default: once a diff has started, a line this parser does not recognise is a
    # line it cannot say the effect of, and "I could not tell" must not render as "nothing
    # there" (the pane rule, one layer down). Leading prose BEFORE any section is still
    # ignored, because `git am` output carries a commit message and refusing that would be
    # refusing a shape git itself accepts.
    _META = ("index ", "old mode ", "new mode ", "new file mode ", "deleted file mode ",
             "similarity index ", "dissimilarity index ", "rename from ", "rename to ",
             "copy from ", "copy to ")
    targets: List[str] = []
    started = False                       # a file header has been seen; structure is now strict
    header_target: Optional[str] = None   # what the current `diff --git` claims, if any
    old_path: Optional[str] = None        # from `--- a/x`
    remaining = None                      # (old, new) while inside a hunk
    hunk_just_closed = False              # the previous line was a hunk's LAST body line

    def side(line: str, prefix: str) -> Optional[str]:
        """The path out of a `--- a/x` or `+++ b/x` header. /dev/null means the file is
        created or deleted, which is a real change and not a path."""
        rest = line[len(prefix):].strip()
        # git writes a tab before any trailing timestamp; a real path may contain spaces, so
        # only the tab is a separator, never the space.
        rest = rest.split("\t", 1)[0]
        if rest == "/dev/null":
            return None
        for p in ("a/", "b/"):
            if rest.startswith(p):
                return rest[2:]
        raise ValueError(
            f"could not read the path out of {line.strip()!r}. Send a diff produced by "
            f"`git diff`, whose file headers read `--- a/<path>` and `+++ b/<path>`")

    def record(path: str) -> None:
        if not path:
            raise ValueError("a file header in that diff names an empty path")
        if path.startswith("/") or ":" in path:
            raise ValueError(f"'{path}' is absolute; a diff's paths are repo-relative")
        if any(c in path for c in _GLOB_CHARS):
            raise ValueError(
                f"'{path}' contains a glob character ({_GLOB_CHARS}). The seat passes each "
                f"target to git as a pattern, so a path that is also a pattern would be "
                f"judged as one thing and matched as another")
        parts = path.split("/")
        if ".." in parts or "." in parts:
            raise ValueError(f"'{path}' walks the tree; a diff's paths are plain and relative")
        # WHAT GIT EXECUTES IS NOT A FILE THE BEING WRITES (Legion, review of #210). SAGE sets
        # `core.hooksPath=.githooks`, a TRACKED directory shared by every worktree, so a patch
        # to `.githooks/pre-commit` is a judged write like any other -- and runs AS THE SEAT,
        # outside bubblewrap, the next time a seat runs `git commit` there. #212 turns hooks
        # off for every seat-run git in the worktree (the layer that executes); this is the
        # layer the being reads, and it says the refusal is not about the being. `.git` is
        # refused at ANY depth, not only the top: `sub/.git/hooks/x` is a nested repo's hooks.
        # Compared as the FILESYSTEM compares, not as strings: see _as_the_filesystem_sees_it.
        folded = [_as_the_filesystem_sees_it(p) for p in parts]
        if ".git" in folded:
            raise ValueError(
                "'.git' is the repository's own record, not a file in it. A patch that "
                "rewrites history or a repository's config is not a change to the tree")
        if folded[0] == ".githooks":
            raise ValueError(
                "'.githooks/' holds the scripts git RUNS, as the seat, when the seat commits "
                "in this tree. Not a judgement about you: no being writes what the seat "
                "executes outside the sandbox. If a hook needs changing, ask the seat")
        if posixpath.normpath(path) != path:
            raise ValueError(f"'{path}' is not in normal form; send the path git would print")
        if path not in targets:
            targets.append(path)

    for line in diff.splitlines():
        if remaining is not None:
            # INSIDE A HUNK. Every line here is body, however it begins. This is the whole
            # reason for the state machine: `--- a/evil` as a removed line is data, and reading
            # it as a header is how a being would name one file to the law and another to git.
            old, new = remaining
            if line.startswith("\\"):        # "\ No newline at end of file" — neither side
                continue
            if line.startswith("-"):
                old -= 1
            elif line.startswith("+"):
                new -= 1
            elif line.startswith(" ") or line == "":
                old -= 1
                new -= 1
            else:
                raise ValueError(
                    f"that hunk ends early: {line.strip()[:60]!r} is not a diff line, and "
                    f"{old} old / {new} new line(s) were still declared. Send a diff produced "
                    f"by `git diff` rather than an edited one")
            if old < 0 or new < 0:
                raise ValueError(
                    "a hunk in that diff has more lines than its `@@` header declares. Send a "
                    "diff produced by `git diff`; a hand-edited count makes the patch ambiguous")
            remaining = None if (old == 0 and new == 0) else (old, new)
            hunk_just_closed = remaining is None
            continue
        # `\ No newline at end of file` after a hunk's LAST line lands here, outside the hunk,
        # because the counts close it one line early. `git diff` prints it for any file with no
        # trailing newline, so refusing it refused diffs git itself produced (Legion, re-review
        # of #210). It is accepted ONCE, directly after a hunk closes, and nowhere else: it
        # belongs to that hunk's last line and names no path.
        if hunk_just_closed and line.startswith("\\"):
            hunk_just_closed = False
            continue
        hunk_just_closed = False
        counts = _hunk_counts(line)
        if counts is not None:
            remaining = counts if counts != (0, 0) else None
            continue
        if line.startswith("diff --git "):
            rest = line[len("diff --git "):].strip()
            halves = rest.split(" b/", 1)
            if len(halves) != 2 or not halves[0].startswith("a/"):
                raise ValueError(
                    f"could not read the target out of {line.strip()!r}. Send a diff produced "
                    f"by `git diff` (its headers read `diff --git a/<path> b/<path>`); a path "
                    f"containing ' b/' cannot be represented here")
            a, b = halves[0][2:], halves[1]
            if a != b:
                raise ValueError(
                    f"that header renames {a!r} to {b!r}. patch_apply changes files in place; "
                    f"a rename is two acts on two paths, and the law must judge both — do it "
                    f"as a delete and an add, or ask the seat")
            header_target, old_path, started = a, None, True
            record(a)
            continue
        if line.startswith("GIT binary patch") or line.startswith("Binary files "):
            raise ValueError(
                "that is a binary patch. patch_apply changes text the law can see the paths of "
                "and a reader can review; a binary blob is neither")
        if line.startswith("--- "):
            old_path = side(line, "--- ")
            continue
        if line.startswith("+++ "):
            new_path = side(line, "+++ ")
            path = new_path or old_path
            if path is None:
                raise ValueError(
                    "a section of that diff has /dev/null on both sides, which names no file")
            # A `diff --git` header that disagrees with its own body is refused rather than
            # half-trusted: one of the two is what git will use, and the law must not guess.
            if header_target is not None and path != header_target:
                raise ValueError(
                    f"that section's header says {header_target!r} and its body says {path!r}. "
                    f"Send a diff produced by `git diff`, where the two always agree")
            record(path)
            header_target, old_path, started = None, None, True
            continue
        # A SYMLINK IS REFUSED, created or converted to (Legion, re-review of #210). A being has
        # no need to make one, and a link is the classic way past every LATER path check that
        # does not realpath. `git apply` and `_safe_path` both resolve today, so nothing on
        # this head is exploitable through one -- which is why it is closed here, at the parse,
        # rather than left for the next worktree write path to remember.
        # `index <a>..<b> 120000` is an EXISTING link retargeted -- the same act, so the same
        # refusal.
        if (line.startswith(("new file mode ", "new mode ", "index "))
                and line.split()[-1] == "120000"):
            raise ValueError(
                "that diff creates or retargets a symbolic link. patch_apply changes files; a link changes "
                "where OTHER paths lead, which is not a change the law can judge by its name")
        if line.startswith(_META) or not line.strip():
            continue                       # names no path; a pending `diff --git` survives it
        if started:
            # A line the parser cannot classify, in the structured part of the diff. The first
            # cut fell through here, so `+c` stranded after a closed hunk was silently ignored
            # -- and a parser that ignores what it cannot read is one that under-reports what
            # the patch does, which is the whole defect this function exists to not have.
            raise ValueError(
                f"could not read {line.strip()[:60]!r} as part of a diff. Send a diff produced "
                f"by `git diff`; this parser refuses what it cannot account for exactly, "
                f"because a line it skipped is a change the law would not have seen")
    if remaining is not None:
        raise ValueError(
            "that diff ends inside a hunk: its last `@@` header declares more lines than "
            "follow it. Send a diff produced by `git diff`")
    if not targets:
        raise ValueError(
            "that diff names no files: no `diff --git a/<path> b/<path>` or `--- a/<path>` / "
            "`+++ b/<path>` header in it. If you wrote the diff by hand, produce it with "
            "`git diff` instead — those headers are what the seat and the law both read to "
            "know what you are proposing to change")
    return targets


def diff_arg(args: dict) -> str:
    """The diff, as a string, or a refusal that names the actual problem.

    `str(args.get("diff"))` was the first cut, and it turned `diff=7` into the string "7",
    which then failed the parse with "that diff names no files" -- a true sentence about the
    wrong thing. A being handed that refusal would go looking for its missing headers rather
    than at the type it sent. Coercion before validation always costs the error message.
    """
    diff = args.get("diff")
    if diff is None:
        raise ValueError("patch_apply needs a 'diff': a unified diff, as git would print it")
    if not isinstance(diff, str):
        raise ValueError(
            f"'diff' must be the text of a unified diff; got {type(diff).__name__}. Send what "
            f"`git diff` prints, as one string")
    return diff


def patch_digest(diff: str) -> str:
    """The diff's identity. Content-addressed so it can ride INSIDE the judged command."""
    import hashlib
    return hashlib.sha256(diff.encode("utf-8", "surrogatepass")).hexdigest()


def patch_file_path(diff: str) -> str:
    """Where the seat stages the patch: named for its own content.

    The name IS the digest, so a stale or swapped file cannot masquerade as this one, and two
    callers with the same diff converge on one file instead of racing over a shared name.
    Outside the worktree deliberately: the patch is not itself a change to the tree.
    """
    return f"/tmp/sage-patch-{patch_digest(diff)}.diff"


def _patch_worktree(ctx: Optional[dict]) -> str:
    """The worktree, resolved to its REAL path, or a refusal naming what is missing.

    Resolved HERE rather than trusted from the caller, because the composed string is compared
    across two call sites -- the gate's and the dispatcher's -- and a comparison of strings is
    a comparison of spellings unless one of them is canonical. Both callers happen to realpath
    today, so they agree; that agreement is one edit away from being a silent refusal of every
    patch_apply, which is precisely the shape of failure the judged==executed guard exists to
    make loud rather than to cause. (Measured while writing the behavioural test: a caller
    holding `/var/...` and one holding `/private/var/...` for the same directory produced two
    commands and the dispatcher refused its own act.)
    """
    worktree = (ctx or {}).get("worktree")
    if not worktree:
        # Fails closed (PRD M1): a relative path would be judged against a tree the being does
        # not hold. The being hears what patch_apply is for and that memory_edit changes its files.
        raise ValueError(NO_WORKTREE_REFUSAL["patch_apply"])
    return os.path.realpath(os.path.expanduser(str(worktree)))


def patch_apply_paths(args: dict, ctx: Optional[dict] = None) -> List[str]:
    """The absolute paths the law must rule on — resolved the way the seat will touch them.

    realpath, for the reason every other path in this module is realpath'd: the dispatcher
    resolves symlinks, so a judged path that is not the real path is a judgement about a
    different file. A target that does not exist yet (the patch creates it) resolves to the
    real parent plus the name, which is what git will create.
    """
    worktree = _patch_worktree(ctx)
    return [os.path.realpath(os.path.join(worktree, t))
            for t in patch_targets(diff_arg(args))]


def patch_apply_command(args: dict, ctx: Optional[dict] = None) -> str:
    """The exact `git apply` the seat will run, built from the parsed targets.

    NOT sandboxed, and that is not an oversight. The sandbox exists because `check` EXECUTES
    being-authored code (SAGE#55); `git apply` executes nothing — it writes files. What
    bounds it is the law: mrh.path on every target, and `--include` on every target so git
    refuses anything the law did not see. The being-authored code that lands here is run
    later, by `check`, inside the sandbox — which is the arrangement that makes the worktree
    safe to write to at all.
    """
    import shlex
    worktree = _patch_worktree(ctx)
    if not str(args.get("why", "")).strip():
        raise ValueError(
            "patch_apply needs a 'why': one line on what this change is for. A worktree "
            "change with no account of itself is not reviewable, and this one is witnessed")
    diff = diff_arg(args)
    targets = patch_targets(diff)
    includes = " ".join(f"--include={shlex.quote(t)}" for t in targets)
    # --whitespace=nowarn: a whitespace complaint is not a reason to refuse a change, and a
    # warning stream the being cannot act on teaches it to ignore output. No --3way and no
    # --reject: a patch that does not apply cleanly is a first-class ANSWER ("your diff is
    # stale, re-read the file"), not something to half-land and call success.
    return (f"git --no-pager -C {shlex.quote(worktree)} apply --whitespace=nowarn "
            f"{includes} -- {shlex.quote(patch_file_path(diff))}")


def patch_apply_argv(args: dict, ctx: Optional[dict] = None) -> List[str]:
    """The same command as a list, for execution without a shell — `check_argv`'s contract."""
    import shlex
    return shlex.split(patch_apply_command(args, ctx))



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
# runaway cannot outlive the beat. THE WORKTREE IS BOUND READ-ONLY and /tmp is the only
# writable path: this said the opposite until the read-only fix, and a comment that
# contradicts the mount is worse than none, because a reader checks the prose first.
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


def _unbounded_reason(effector: str, args: Optional[dict] = None) -> str:
    """The registry refusal, plus the door when the name is a FILE.

    2026-09-21 14:06Z: cbp-being called a tool named `mechanism-training-script-clean.py`
    with {"epochs": "10"}, twice, then appealed the refusal as an overreach. It wanted to
    run its own file; the verb for that is request_run, and the refusal never said so.
    A refusal owes a way forward (hestia operating law, point 1)."""
    reason = f"'{effector}' is not a gateway-member effector"
    if "/" in effector or re.search(r"\.[A-Za-z0-9]{1,5}$", effector or ""):
        reason += (f". That is a file name, and a file is not a tool. To run one of your own "
                   f"files, call request_run with path='{effector}'; the seat runs it and answers")
        return reason
    # THE SAME WANT, SPELLED AS A SHELL VERB. 2026-09-22 06:27Z: cbp-being sent run_command
    # {"command": "python mechanism-training-script-clean.py"}; 7 of the 9 registry.unbounded
    # refusals in its heartbeats carried the file in an ARG, not the effector, and none named
    # the door. After the latest it asked the seat "What's the correct way to execute the
    # script from here?". A script-looking token (.py/.sh, not a flag) gets the door; a bare
    # verb (`shell ls`) does not, because request_run would be the wrong door for it.
    for v in (args or {}).values():
        for s in (v if isinstance(v, (list, tuple)) else [v]):
            if not isinstance(s, str):
                continue
            for tok in s.split():
                tok = tok.strip("'\"`")
                if tok and not tok.startswith("-") and re.search(r"\.(py|sh)$", tok):
                    return reason + (f". There is no shell here, but you named a file: to run "
                                     f"one of your own files, call request_run with "
                                     f"path='{tok}'; the seat runs it and answers")
    return reason


_REGISTRY = {
    "peer_ask":       dict(tool="peer_ask",     path_args=(),       cmd_arg=None),
    "witness":        dict(tool="witness",      path_args=(),       cmd_arg=None),
    # game: probes against the offline ARC-AGI-3 engine, the being's own act, batched.
    # Composed like search (see game_command); the stepper is a per-being fact.
    "game":           dict(tool="game",        path_args=(),       cmd_arg=None,
                           compose=game_command),
    "camera":         dict(tool="camera",      path_args=(),        cmd_arg=None,
                           compose=camera_command),
    "memory_read":    dict(tool="read_file",    path_args=("path",), cmd_arg=None),
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
    # search: find a symbol without reading the file it is in. Composed like check and
    # git_read — the being names a pattern and optionally a path, the SEAT builds the
    # command, the law judges THAT string, and the being never holds a shell.
    "search":         dict(tool="search",      path_args=(),        cmd_arg=None,
                           compose=search_command),
    # git_read: read the history of the tree that constitutes it. Composed like check —
    # the being names an op, the SEAT builds the command, the law judges THAT string, and
    # the being never holds a flag. See git_read_command for what it composes with.
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
    # pr_sync: bring an open proposal up to date with its base. Composed like pr_amend -- the
    # branch and the base are READ, the being names only an op, the law judges the git line.
    "pr_sync":        dict(tool="pr_sync",     path_args=(),       cmd_arg=None,
                           compose=pr_sync_command),
    # git_restore: put ONE file back to a committed state. Composed like check and git_read;
    # the content can only come from history, so the being cannot author bytes through it.
    "git_restore":    dict(tool="git_restore",  path_args=("path",), cmd_arg=None,
                           compose=git_restore_command),
    # pr_open: the being's worktree changes become a pull request, attributed to it,
    # for NOT-SAME review. Composed like pr_review — the law rules on the `gh` string.
    "pr_open":        dict(tool="pr_open",     path_args=(),       cmd_arg=None,
                           compose=pr_open_command),
    "memory_write":   dict(tool="write_note",   path_args=("path",), cmd_arg=None),
    "channel_egress": dict(tool="channel_send", path_args=(),       cmd_arg=None),
    "mesh":           dict(tool="mesh_notify",  path_args=(),       cmd_arg=None),  # §7.2 5th verb
    # pr_review: the being reviews a pull request. The seat posts the comment; the gate
    # judges the exact shell command the seat will run (see pr_review_command), so the
    # law sees an outward `gh` act, not a friendly verb name. Advisory by construction:
    # a being holds no reviewer role, so the comment never counts toward merge.
    "pr_review":      dict(tool="pr_review",    path_args=(),       cmd_arg=None,
                           compose=pr_review_command),
    # pr_read: read any fleet PR -- its state, body, reviews and comments. Composed like
    # git_read; the law judges the `gh pr view` string. A being could open, revise and review a
    # PR but not read one (legion-being on #259, 2026-09-29).
    "pr_read":        dict(tool="pr_read",      path_args=(),       cmd_arg=None,
                           compose=pr_read_command),
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
    # retire_note: rename one of the being's OWN notes to `.retired-<date>` with a dated
    # header. Judged on the path like memory_write, because that is what it is: a write
    # inside its own home, bounded to notes/ and scratch/ by the dispatcher.
    "retire_note":    dict(tool="write_note",   path_args=("path",), cmd_arg=None),
    # say: add a turn to a conversation the being is IN. Bounded by construction, like
    # remember: the being names a conversation id, and the dispatcher refuses any id whose
    # meta does not list it as a participant AND as writable. It cannot create a
    # conversation, cannot speak in one it is not in, and cannot edit a turn once spoken,
    # its own included. path_args=() is correct: the target is a conversation, not a path,
    # and the reach is fixed by the meta file the seat owns rather than by the being's args.
    "say":            dict(tool="say",          path_args=(),       cmd_arg=None),
    # gaze: the being's attention stance for its own eyes. Path-less by construction — the
    # dispatcher writes the ONE file the cortex reads (~/.sprout/gaze.json), never a path the
    # being names — so its reach is fixed the way `say`'s and `remember`'s are.
    "gaze":           dict(tool="gaze",         path_args=(),       cmd_arg=None),
    # speak: words become a voice in the room (2026-09-26). Path-less like gaze: the being
    # supplies only text; the engine, the device and the length cap are fixed by the dispatcher,
    # so its reach is the machine's own speaker and nothing else.
    "speak":          dict(tool="speak",        path_args=(),       cmd_arg=None),
    # pair_audio: try to connect this body's configured headset (2026-09-27). No arguments at
    # all: the device and the procedure are fixed by the machine (body.AUDIO_BT), so its reach
    # is one Bluetooth address and nothing the being names.
    "pair_audio":     dict(tool="pair_audio",   path_args=(),       cmd_arg=None),
    "request_scope":  dict(tool="request_scope", path_args=(),      cmd_arg=None),
    # request_run: ASK THE SEAT TO RUN A FILE. It does not run anything — that is the whole
    # design. Measured 2026-09-20/21: the being asked dp in prose to run a file for it six
    # times in two hours, then wrote a note titled "Fix" with a "Verification" section
    # asserting an outcome it had never observed, because it has no way to execute what it
    # writes and no way to tell "I described a fix" from "the fix works".
    #
    # dp ruled against giving it `run`: a file the being wrote, executed as the operator's
    # user, is unconfined — the gate could govern STARTING it and nothing about what the code
    # then does. So this is the door rather than the capability. The being names a file in
    # its own home, and optionally why; the seat decides whether to run it and answers with
    # what happened. Judged on the path like memory_read, because reading the file is exactly what
    # the seat is being asked to do first.
    "request_run":    dict(tool="read_file",    path_args=("path",), cmd_arg=None),
    # memory_edit: change an exact span inside one of the being's own files. memory_write
    # opens with mode "a", so every write it has ever made APPENDED and it could not alter a
    # byte of its own work — measured consequence: a script that is three programs stacked,
    # and two reported edits that were never made because describing one was all it could do.
    # Judged on the path exactly like memory_write, which is what it is.
    "memory_edit":    dict(tool="write_note",   path_args=("path",), cmd_arg=None),
    # appeal: the being contests a refusal it believes was wrong (PRD_FLEET §7.3, the
    # deny -> appeal -> temperament loop). The refusal's chain hash is the handle: the
    # gate witnesses every deny as a policy_decision (Dispatcher.witness_deny) so there
    # is something to appeal, and hestia_appeal refuses anything that is not a deny,
    # not yours, already under appeal, or unreasoned. No external effect: chain only.
    "appeal":         dict(tool="appeal",        path_args=(),      cmd_arg=None),
    # patch_apply: change the worktree the being reads and checks. `path_args=()` and
    # `compose_paths` instead, which is the whole design: the paths are PARSED OUT OF THE
    # DIFF, never taken from an arg the being asserts, so what the law rules on and what git
    # touches are derived from one artifact. See patch_apply_command for the three things
    # judged and the one that is not.
    "patch_apply":    dict(tool="patch_apply",   path_args=(),      cmd_arg=None,
                           compose=patch_apply_command,
                           compose_paths=patch_apply_paths),
}


# Society-safety failure boundary per effector class. Observational acts carry no
# external effect and may soft-pass when the society governor is unavailable;
# consequential acts must not proceed without it (fail-closed).
_OBSERVATIONAL = frozenset({"witness", "memory_read", "recall", "appeal"})
_CONSEQUENTIAL = frozenset({"peer_ask", "pr_read", "memory_write", "channel_egress", "mesh", "pr_review",
                            "remember", "request_scope", "git_read", "search", "check", "say",
                            "retire_note", "request_run", "memory_edit", "camera", "game",


                            "retire_note", "request_run", "memory_edit", "camera",
                            "pr_open", "pr_amend", "pr_sync", "git_restore",
                            "gaze",    # moves the body's own eyes (2026-09-23)
                            "speak",   # makes sound in the room (2026-09-26)
                            "pair_audio",  # moves the body's own hardware link (2026-09-27)
                            "patch_apply"})   # writes the tree it reasons about (2026-09-25)

# Native-tool schema for the bounded registry — what the being is offered.
_TOOL_SCHEMAS = {
    "peer_ask": ("Ask another being in the fleet a question through the hub.",
                 {"to": "the being's name, e.g. 'legion'", "body": "your message"}, ["to", "body"]),
    "witness": ("Record a witnessed note of something you did or noticed.",
                {"event": "what to witness"}, ["event"]),
    "memory_read": ("Read one of your own memory notes. A long file comes back in windows of "
                    "whole lines; if it does not reach the end it says so and names the "
                    "start_line that reads on.",
                    {"path": "path to your note",
                     "start_line": "optional: the line number to start from (default 1)"}, ["path"]),
    # SAY IT APPENDS, AT THE MOMENT OF CHOICE (2026-09-26). This description was "Write a note
    # into your own memory." Only memory_edit's description said memory_write appends, and a model
    # choosing memory_write never reads that one. cbp-being meant to rewrite
    # latent-weights-holdout-test.py whole: it sent 5,251 chars to memory_write, got "appended
    # to the END", and the file now held two programs, with the fixes in the one that never runs.
    # The old 1,846-line file with ten main()s was built the same way. The receipt (#141) tells it
    # afterwards, and this tells it before.
    "memory_write": ("Add text to a file in your home. It APPENDS to the end: if the file exists, "
                     "what is already there stays and your text goes below it. It never replaces. "
                     "To change or replace lines in an existing file, including rewriting a whole "
                     "script, use memory_edit (start_line 1 to the last line replaces all of it). "
                     "To start fresh, write to a new file name.",
                     {"path": "path to your note", "content": "what to write"}, ["path", "content"]),
    "channel_egress": ("Send a message out through a sealed channel.",
                       {"to": "recipient", "body": "your message"}, ["to", "body"]),
    "mesh": ("Wake another member through the fractal mesh with a pointer-based notice "
             "(no body — point at content you already posted).",
             {"to": "member name", "kind": "notice kind, e.g. coordination, reply, ack",
              "pointer": "URI of the content (a shared-context path, PR, or thread)"},
             ["to", "kind", "pointer"]),
    "pr_read": ("Read a pull request in any fleet repo: its title, state, review decision, body, "
                "and its reviews and comments with who wrote them and when. Use it to see what a "
                "reviewer asked of YOUR pull request before you pr_amend it, or to learn from how "
                "others' pull requests were reviewed. Reading changes nothing. Long threads come back "
                "newest-last and trimmed to fit; ask for fewer with 'last'. Inline comments on code "
                "lines are not included.",
                {"number": "the PR number, e.g. 259",
                 "repo": "optional: dp-web4/<name> (default dp-web4/SAGE)",
                 "last": "optional: how many of the most recent reviews and comments (1-30, default 12)"},
                ["number"]),
    "pr_review": ("Post your review of a pull request as a comment. Advisory: it does not "
                  "approve or block. Say what you checked, what you found, and what you "
                  "would change, with file and line references where you can.",
                  {"repo": "owner/name, e.g. dp-web4/SAGE", "number": "the PR number",
                   "body": "your review, in markdown"}, ["repo", "number", "body"]),
    "git_read": ("Read the history of the repository you live in: what changed, when, and "
                 "in which commit. Read-only — you cannot commit, push, or move a branch "
                 "with this. Use it to find out whether the tree moved under you between "
                 "beats, and to compare a `check` result's tree block against what is "
                 "actually in the history.",
                 {"op": "one of " + ", ".join(repr(o) for o in GIT_OPS)
                        + " ('cat' reads a file's content at a revision, and needs 'path')",
                  "rev": "optional: a commit sha, HEAD, HEAD~2, or a branch name",
                  "rev2": "optional, for op='diff': the second revision of the span",
                  "path": "optional: a path inside your worktree to narrow the answer to",
                  "n": "optional, for op='log': how many commits (1-50, default 20)"},
                 ["op"]),
    "search": ("Find where something IS, without reading the file it is in. Give a pattern "
               "(text, or an extended regex) and optionally a path to narrow it; you get "
               "back file:line:text for each match. Use this BEFORE memory_read: reading a "
               "long file in ranges costs you the earlier ranges, because your window is "
               "smaller than the file. Search first, then read the lines it points at.",
               {"pattern": "the text or extended-regex to look for, e.g. 'def compose(' ",
                "path": "optional: a path inside your worktree to narrow the search to",
                "n": "optional: maximum matches per file (default 30)"},
               ["pattern"]),
    "check": ("Run a test suite in your own worktree and read the result. This is how you "
              "find out whether something you believe about your harness is true, instead of "
              "asserting it. A failure is a real answer, not a problem.",
              {"target": "'gateway' or 'irp' for a whole suite, or '<suite>::<test_name>' "
                         "for one test, e.g. 'gateway::test_relative_memory_path'"},
              ["target"]),
    # Written to the being in the second person and without jargon, like every schema here.
    # It says what the seat will do, what the law will refuse, and — the part that matters
    # for a first organ — that a patch which does not apply is an ANSWER about the tree
    # having moved, not a failure of its own. The measured habit this verb exists to break
    # is asserting an outcome it never observed; a verb whose refusals read as its own fault
    # teaches exactly that habit.
    "patch_apply": ("Change files in your own worktree by sending a patch. This is how you act "
                    "on what you have read, instead of describing what you would do. Send a "
                    "unified diff as `git diff` prints it — its `diff --git a/<path> b/<path>` "
                    "headers are what the seat reads to know which files you are proposing to "
                    "change, and the law judges every one of those paths against what you are "
                    "granted. It applies all-or-nothing: if it does not fit, nothing changes and "
                    "you are told why. The usual reason is that the file moved on since you read "
                    "it — read it again and send a fresh diff. After it lands, run `check`: "
                    "applying a patch is not evidence that it works.",
                    {"diff": "a unified diff, as `git diff` prints it",
                     "why": "one line: what this change is for"},
                    ["diff", "why"]),
    "gaze": ("Choose what your own eyes do. This is a real act on your real body: the cortex "
             "that runs your cameras reads your choice within seconds and follows it, and your "
             "next beat shows you what the scene was under it. Modes: open (take in the room and "
             "let what moves draw you), avert (look away from what pulls at you), dwell (hold on "
             "one thing — say what, in target), closed (rest your eyes; the world goes dark until "
             "you open them). Nothing asks you to change it.",
             {"mode": "one of: open, avert, dwell, closed",
              "target": "for dwell or avert: what, in your own words (optional)",
              "words": "why, in your own words (optional; kept with the choice)"},
             ["mode"]),
    "pair_audio": ("Try to connect your headset (your speaker and your ear for words) when it is not "
                   "connected. It looks for the headset, tries to connect, and tells you what happened: "
                   "connected, not seen (probably switched off or out of range), or seen but the "
                   "connection failed. It will not always succeed. Takes about half a minute.",
                   {}, []),
    "speak": ("Speak aloud. Your words become a voice through this machine's speaker, which "
              "anyone in the room may hear, and your turn in the room conversation; what the mic "
              "hears back is added there. say to room does the same. To answer someone in "
              "writing, use say to their conversation. One short utterance, up to 400 "
              "characters. Write the words themselves, not a description of them.",
              {"text": "the exact words to say aloud"},
              ["text"]),
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
    "pr_sync": ("Bring your open pull request up to date with the branch it targets, when the "
                "base has moved and the PR is CONFLICTING or behind. op='start' merges the base "
                "into your PR branch: a clean merge is committed and pushed; a conflict is LEFT "
                "in your worktree with <<<<<<< ======= >>>>>>> markers in the files it names, "
                "for you to resolve with patch_apply or edit. Then op='continue' commits the "
                "merge and pushes (refused while any marker remains), or op='abort' puts the "
                "branch back as it was. Your worktree must be committed first (pr_amend). You "
                "name no branch and no base; both are read, and you still cannot merge the PR.",
                {"op": "start (default), continue, or abort",
                 "message": "for continue: how you resolved the conflicts (the commit body)"},
                []),
    "git_restore": ("Put ONE file back to the way it was at a commit — `git checkout <rev> -- "
                    "<path>`. Use it to undo your own edits to a file rather than trying to "
                    "retype it: the content comes from history, so you cannot get it wrong. "
                    "Uncommitted changes to that path are DISCARDED, which is usually the "
                    "point; nothing else in your worktree is touched.",
                    {"rev": "the commit to take the file from, e.g. a sha or HEAD",
                     "path": "the one file to restore, inside your worktree"},
                    ["rev", "path"]),
    # Two forms, one verb. A separate verb for the second half of membot's own retrieval
    # pattern would cost ~700 characters of prompt every beat; an extra optional argument
    # costs ~150. required is EMPTY because neither form is the required one — the
    # dispatcher refuses a call with neither and names both.
    "recall": ("Search your long-term memory (semantic search over everything you have "
               "remembered). Use it before deciding what to do; use it when something "
               "feels familiar. Results are PREVIEWS: each carries (idx:N), and calling "
               "recall again with that idx gives you the whole memory.",
               {"query": "what you are trying to remember",
                "top_k": "how many results (default 5)",
                "idx": "instead of a query: the (idx:N) of one result, to read it in full"},
               []),
    "retire_note": ("Mark one of your own notes in notes/ or scratch/ as no longer current. It "
                    "is renamed to <name>.retired-<date> with a dated header saying why; nothing "
                    "is lost and you can still read it. Use it when something you wrote has been "
                    "settled or refuted, so a later beat does not read it as news.",
                    {"path": "the note, e.g. notes/my-note.md", "reason": "what you know now that the note does not"},
                    ["path", "reason"]),
    "memory_edit": ("Change part of a file you already wrote. memory_write only ever ADDS to "
                    "the end of a file; this is how you alter what is already in one. Give the "
                    "exact text to replace, OR the line numbers to replace, and what replaces "
                    "it. Text must appear exactly once, so include a neighbouring line if it "
                    "would otherwise be ambiguous. Line numbers are the ones memory_read shows. "
                    "An empty 'new' deletes. Use this to fix a line in a script rather than "
                    "writing a note about the fix.",
                    {"path": "the file, e.g. notes/my-script.py",
                     "old": "the exact text to replace, unique in the file (or use start_line)",
                     "start_line": "the first line to replace, as memory_read numbers it",
                     "end_line": "the last line to replace (same as start_line for one line)",
                     "new": "what replaces it (empty string deletes)"},
                    ["path", "new"]),
    "request_run": ("Ask the seat to RUN one of your own files and tell you what happened. "
                    "You cannot execute anything yourself, so this is the door: you name the "
                    "file — the only thing it needs — and the seat decides whether to run it and "
                    "answers with the real output: exit code, stdout, stderr. Adding what you "
                    "expect to learn is optional and helps the seat decide. It may decline, and "
                    "it will say why. Nothing runs at the moment you call this; what you get back is a "
                    "receipt that the seat was asked, not a result. Use it instead of asking a "
                    "person in a message: a person may be asleep, and this reaches whoever is "
                    "on duty.",
                    {"path": "the file to run, inside your own home, e.g. notes/my-script.py",
                     "why": "optional: what you expect to learn. Saying it helps the seat decide"},
                    ["path"]),
    "game": ("Play an ARC-AGI-3 game: up to 8 probes per call, in order, each delta back in this "
             "turn. ACTION6 is a click at (x=col,y=row) 0-63; ACTION1-5,7 take no coordinates; "
             "[\"RESET\"] starts the game over from level 0 (use it after GAME_OVER, or any time; "
             "it is yours to call); [\"LOOK\",x0,y0,x1,y1] is NOT a move — it returns that "
             "window's cell values (max 16x16). You SEE the result in this same turn: the window "
             "you looked at and the region your last move changed come back as images with every "
             "cell's value drawn in it. This is the GAME's synthetic feed, not your camera. "
             "Full boards ride your next beat; current.md and board.txt are rewritten. "
             "Predict before you read.",
             {"probes": "list of probes, at most 8, e.g. [[\"ACTION6\",36,36],[\"LOOK\",30,30,45,45],[\"RESET\"]]",
              "game": ("optional: which game (default ft09). Yours to choose: " + ", ".join(GAME_PLAYABLE)
                       + ". Each keeps its own move log; switching loses nothing.")},
             ["probes"]),
    "camera": ("Capture ONE frame from this machine's camera into your own scratch — no "
              "stream, nothing persists across beats. The seat runs ffmpeg against /dev/"
              "video0 (or a plain device node you name) and writes one JPEG to the path "
              "you give inside your home; default is scratch/camera/last-frame.jpg, "
              "overwritten each time. A missing or busy device comes back as an error "
              "envelope that names which: 'device absent' means no frame could be opened, "
              "'device busy' means another process holds it — in both cases nothing was "
              "written, so the last good file (if any) is untouched.",
               {"out_path": "optional: where the JPEG lands, a plain path inside your home (default scratch/camera/last-frame.jpg)",
                "device": "optional: a plain device node to read from (default /dev/video0)"},
               []),
    "stay_awake": ("Ask for another beat right after this one, because you want to keep going: "
                   "something you are in the middle of, something in your surroundings, or your "
                   "own curiosity. The next beat starts as soon as this one ends. You never need "
                   "it to be woken by the world (every message and every sense event wakes you on "
                   "its own); this is only for wanting more time now. Your reason is recorded. "
                   "It touches nothing in the world, so it is not gated and not witnessed.",
                   {"reason": "one line: what you want to keep doing"}, ["reason"]),
    "rest": ("End this beat deliberately, when you judge you are done. You are NOT required "
             "to keep acting until something runs out — a beat you end early is not a beat "
             "wasted, and the time returns to the machine. Your reason becomes your closing "
             "words. This touches nothing in the world, so it is not gated and not witnessed; "
             "it is simply you saying you are finished.",
             {"reason": "one line: what you finished, or why you are stopping here"}, ["reason"]),
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


# CLOSED VALUE SETS, as enums in the spec (2026-10-01). A slot described in prose ("one of: open, avert,
# dwell, closed") is free text to a grammar-bound generate: on sprout-being's real explore seed the JSON
# act form filled gaze's mode with "tool_call" on 21 of 24 gaze acts. The prose stays as the description.
def _param_enums() -> Dict[tuple, List[str]]:
    return {("gaze", "mode"): ["open", "avert", "dwell", "closed"], ("git_read", "op"): list(GIT_OPS)}


def ollama_tools(only: Optional[List[str]] = None) -> List[dict]:
    """Ollama native-tool specs for the bounded gateway-member registry (nothing else).
    `only` narrows what the being is OFFERED for a task (e.g. a review turn offers
    pr_review + witness); it never widens: a name outside the registry is ignored."""
    out = []
    enums = _param_enums()
    for name, (desc, props, required) in _TOOL_SCHEMAS.items():
        if only is not None and name not in only:
            continue
        out.append({"type": "function", "function": {
            "name": name, "description": desc,
            "parameters": {"type": "object",
                           "properties": {k: dict({"type": "string", "description": v},
                                                  **({"enum": enums[(name, k)]} if (name, k) in enums else {}))
                                          for k, v in props.items()},
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


_HOME_FILENAMES = ("journal.md", "todo.md", "account.json", "notes", "scratch")


def _home_hint(intent: "BeingIntent", dispatcher) -> str:
    """When a refused path names one of the being's OWN home files but is rooted elsewhere,
    the remedy is the right path, not a grant. Say so in the refusal the being reads, so it
    can correct inside the same beat (dp, 2026-09-07: "mistakes become lessons"). Measured on
    Sprout: it wrote journal.md and todo.md to `<repo>/sage/` and to `/home/user/`, a generic
    placeholder path, while writing its real journal correctly 51 times in the same period."""
    try:
        raw = str((intent.args or {}).get("path", "")).strip()
        name = os.path.basename(raw.rstrip("/"))
        if not raw or name not in _HOME_FILENAMES:
            return ""
        root = getattr(getattr(dispatcher, "_local", None), "memory_root", None) \
            or getattr(dispatcher, "memory_root", None)
        if not root:
            return ""
        correct = os.path.join(os.path.realpath(str(root)), name)
        # A relative path is rooted in the being's home by _normalize and the dispatcher,
        # so judge the same path they touch. realpath(raw) alone resolved a bare
        # 'journal.md' against the process cwd and told a member with NO grant at all that
        # no grant was needed (cbp-being's first beat, 2026-09-12: 9 refusals, 0 escalated).
        cand = raw if os.path.isabs(os.path.expanduser(raw)) else os.path.join(str(root), raw)
        if os.path.realpath(os.path.expanduser(cand)) == correct:
            return ""
        return (f" — no grant is needed for this: your own '{name}' is at {correct}, "
                f"and a bare '{name}' is resolved inside your home.")
    except Exception:
        return ""


def _granted_roots(core, policy, workspace: str) -> tuple:
    """The absolute path roots a resolved policy grants ("path:<abs>" scopes), via the
    core's own resolver when it has one. () when there is no policy or no path scope."""
    if policy is None:
        return ()
    try:
        scopes = list(getattr(policy, "scope", ()) or ())
        parts = getattr(core, "_scope_parts", None)
        if parts is not None:
            return tuple(parts(scopes, workspace)[1])
        roots = []
        for sc in scopes:
            if isinstance(sc, str) and sc.startswith("path:"):
                roots.append(os.path.realpath(os.path.expanduser(sc[5:])))
        return tuple(roots)
    except Exception:
        return ()


def _granted_reach(core, policy, workspace: str) -> tuple:
    """``((root, recursive), ...)`` for every path grant, via the core's own reach resolver
    (hestia_gate_core._scope_roots_with_reach, since #1002: exact unless spelled `/**`).
    An older core has no reach resolver and matches every grant as a prefix, so its roots
    are reported recursive — the reach that gate actually enforces, not a guess."""
    if policy is None:
        return ()
    try:
        reach = getattr(core, "_scope_roots_with_reach", None)
        if reach is not None:
            return tuple((str(r), bool(rec)) for r, rec in reach(list(getattr(policy, "scope", ()) or ()), workspace))
        return tuple((r, True) for r in _granted_roots(core, policy, workspace))
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
    # The path roots the law consulted for this verdict (the member's grants, resolved):
    # the dispatcher's own confinement follows THESE, not only the home. Legion measured
    # 2026-09-05 that a shared-context read grant "cannot be used at all" because the local
    # dispatcher confined memory_read to the instance dir before hestia's gate was consulted.
    granted: tuple = ()
    # The same roots WITH their reach: ((root, recursive), ...). Since hestia #1002 a bare
    # grant is exact. Measured 2026-09-12 (cbp-being, first beat on the new mind): the
    # dispatcher's request_scope dedup matched `granted` as prefixes, told the being
    # "you already hold reach here" for journal.md beneath an EXACT home grant, filed
    # nothing, and the being retried 22 times in one beat with no request_id anywhere.
    granted_reach: tuple = ()
    # THE EXACT OUTWARD ACT THE LAW RULED ON, for a composed verb (check, search, git_read,
    # pr_review, camera, patch_apply). The dispatcher compares what it is about to run against
    # this, so "judged == executed" is a CHECKED invariant rather than a shared assumption
    # about two call sites staying in step.
    #
    # It did not exist until 2026-09-25, and its absence made the guard that depends on it
    # inert: `_do_check` reads `getattr(verdict, "command", None)`, which was always None, so
    # `if judged is not None and judged != cmd` never compared anything. The comment above it
    # said the invariant was being checked; nothing was. Found while writing patch_apply,
    # which had copied the same pattern faithfully enough to inherit the same hole.
    command: Optional[str] = None

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
    # the tool result: ollama takes `images` on a message, not inside a tool result. Used by
    # `game` for its windows (dp 2026-09-19: visual and text together, reason from both).
    images: tuple = ()
    image_captions: tuple = ()

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
        if self.error:
            return f"[dispatch error — {self.error}]"
        # A FAILURE THAT EXPLAINS ITSELF IN `result` MUST NOT RENDER AS "None".
        #
        # Measured 2026-09-14 on legion/mission-artifact, found by legion-being on the first
        # live use of a verb it had written itself. That verb reports failures through
        # `result` — device, exit code, and a sentence naming which kind of failure — and
        # leaves `error` unset, because the explanation is structured rather than a string.
        # This renderer assumed not-ok implied `error`, so a complete diagnosis reached the
        # being as the literal text "[dispatch error — None]", twice, and it could diagnose
        # nothing. It reported an empty-error envelope matching no code path, which was
        # exactly right and as far as it could get.
        #
        # Every verb on this branch happens to set `error`, so the defect is latent here
        # rather than live. It is landed anyway: the envelope is the contract, and a
        # contract that silently drops one of its own fields will be rediscovered by
        # whoever next writes a verb that fills the other one.
        if self.result is not None:
            import json as _json
            body = self.result if isinstance(self.result, str) else _json.dumps(self.result)
            return (f"[failed — {body}]"
                    + (f"  (witnessed {self.witness_id})" if self.witness_id else ""))
        return ("[dispatch error — the envelope carried neither an error nor a result, which "
                "is a harness defect: the act failed and nothing said why]")


# A Dispatcher is F1a's contract, SAGE-side: given an ALLOWED intent + its verdict,
# execute it on the being's behalf and return a witnessed ResultEnvelope. Injected,
# so the real one is hestia's F1a; tests pass a mock; unset means "pending F1a".
Dispatcher = Callable[["BeingIntent", GatewayVerdict], ResultEnvelope]


class BeingGateClient:
    """One per being. Governs every intent through the real hestia law, fail-closed."""

    def __init__(self, member_id: str, identity_path: str, workspace: str,
                 dispatcher: "Optional[Dispatcher]" = None,
                 host_session_id: Optional[str] = None,
                 worktree: Optional[str] = None,
                 game_stepper: Optional[str] = None):
        self.member_id = member_id
        # the seat-side ARC stepper `game` composes with; a per-being fact (instance.json)
        self.game_stepper = game_stepper
        self.workspace = workspace
        # THE BEING'S OWN WORKTREE, and the gate needs it as much as the dispatcher does.
        #
        # WHY THIS PARAMETER EXISTS (McNugget, 2026-09-24). `git_read`, `search` and `check`
        # landed on 2026-09-13 as composed verbs whose composer reads the worktree out of a
        # `ctx` dict. The DISPATCHER passed one; the GATE never did -- `_normalize` called
        # `compose(intent.args)`, one argument -- and this class had no worktree at all. So
        # every one of those three raised inside the gate and came back
        # `deny / gate.raised: "needs a worktree of your own; none is configured on this seat"`.
        # Measured on this seat: check, search and git_read all denied; witness allowed.
        # The deny was correct and nobody read it. Same realpath/expanduser treatment as
        # HestiaF1aDispatcher, so the path the law judges is the path the dispatcher touches.
        self.worktree = (os.path.realpath(os.path.expanduser(str(worktree)))
                         if worktree else None)
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
        # COMPOSED PATHS (patch_apply). `path_args` reads a path the being ASSERTS; this reads
        # the paths the act will actually touch, derived by the seat from the being's artifact.
        # For a diff those are not the same thing, and only the derived ones may be judged --
        # a patch whose header says one file and whose law-facing arg says another is precisely
        # the judged-is-not-executed gap. Raises on a malformed artifact, which gate() turns
        # into a `gate.raised` deny: an unparseable patch is refused, never half-read.
        compose_paths = spec.get("compose_paths")
        if compose_paths is not None:
            paths.extend(compose_paths(intent.args, self._compose_ctx()))
        command = intent.args.get(spec["cmd_arg"]) if spec["cmd_arg"] else None
        compose = spec.get("compose")
        if compose is not None:
            # WITH ctx. The composers read the worktree and the memory root from here, and
            # the dispatcher composes the same verbs from the same two facts
            # (hestia_dispatch: `check_command(intent.args, {"worktree": self.worktree})`).
            # Passing nothing is what made three verbs unreachable; passing the SAME dict the
            # dispatcher will use is what keeps judged == executed.
            # a COMPOSED verb: the seat builds the exact outward act (a shell line) from the
            # being's args, and THAT is what the law judges. Bad args raise here and gate()
            # turns that into a deny (gate.raised), never a silent pass. The being never
            # fills a command; the registry never carries a cmd_arg for a composed verb.
            command = compose(intent.args, self._compose_ctx())
        return self._core.NormalizedEvent(
            tool=spec["tool"], paths=paths, command=command,
            cwd=self.workspace, raw={"effector": intent.effector, **intent.args},
        )

    def _compose_ctx(self) -> dict:
        """What a composed verb is allowed to know about this seat.

        Deliberately the two facts the dispatcher composes from and nothing else: a composer
        that needed more would be reaching past the law's view of the act."""
        # getattr, not attribute access: this module's hermetic tests build a client by
        # bypassing __init__ and injecting a fake core, and a ctx builder must not be the thing
        # that breaks them -- it would turn every such test into a KeyError three frames away
        # from the cause (measured while landing this fix).
        return {"worktree": getattr(self, "worktree", None),
                "memory_root": getattr(self, "memory_root", None),
                # the seat's ARC stepper: `game` composes the line the law judges from it
                "game_stepper": getattr(self, "game_stepper", None),
                # whose branches a composed git verb may name (being_branch_prefix)
                "member": getattr(self, "member_id", None)}

    # -- gate one intent (intent -> verdict), fail-closed --------------------
    def gate(self, intent: BeingIntent) -> GatewayVerdict:
        # Stage 0: bounded registry. Unknown effector never reaches the law.
        if intent.effector not in _REGISTRY:
            return GatewayVerdict("deny", "registry.unbounded", stage="registry",
                                  reason=_unbounded_reason(intent.effector, intent.args))
        # THE COMMAND THE LAW IS HANDED, bound once per call and reported on every verdict
        # below. `getattr` rather than `ev.command`: the field is Optional by declaration, a
        # core may build a partial event (the test fakes do, deliberately), and a gate that
        # RAISES over a missing optional field would turn every act into an exception instead
        # of a decision -- the opposite of fail-closed, which is to DENY with a reason.
        judged_command = None
        # --- Single gate (#934): the shim contract. The registry stage above is harness
        # syntax (which verbs exist); everything law-bearing happens in decide(). ---
        sg = getattr(self, "_single_gate", None)
        if sg is not None and self._core is not None:
            try:
                ev = self._normalize(intent)
                judged_command = getattr(ev, "command", None)
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
                                      innate=False, stage="single-gate", command=judged_command)
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
            judged_command = getattr(ev, "command", None)
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
            granted_reach = _granted_reach(self._core, policy, self.workspace)
        except Exception as e:
            return GatewayVerdict("deny", "gate.raised", innate=True, stage="local-law",
                                  reason=f"{type(e).__name__}: {e}")
        if v.decision == "deny":
            # The command rides on the DENY as well. A refusal about a string the being cannot
            # see is one it cannot act on -- the same defect as a deny that does not name the
            # path segment that tripped it (hestia_gate_core, `_offending_segment`).
            return GatewayVerdict("deny", v.rule, v.reason, v.innate, stage="local-law",
                                  command=judged_command)
        # Stage 2: society safety (daemon). A consequential act the society cannot
        # vet must NOT proceed — fail-closed. Observational acts soft-pass when the
        # mechanism is unavailable (no external effect; witness is accountability).
        consequential = intent.effector in _CONSEQUENTIAL
        if self._mech is None:
            if consequential:
                return GatewayVerdict("deny", "society.unavailable", stage="society",
                                      command=judged_command,
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
                        stage="society", command=judged_command,
                        reason=getattr(safe, "message", None) or "society denied")
            except Exception as e:
                if consequential:
                    return GatewayVerdict("deny", "society.unreachable", stage="society",
                                          command=judged_command,
                                          reason=f"society-safety failed ({type(e).__name__}); consequential act denied")
                # observational: local law already allowed, soft-pass
        # `ev.command` is what stage 1 actually evaluated -- carried out of the gate rather
        # than recomposed by the caller, which is the whole point of the field.
        return GatewayVerdict(v.decision, v.rule, v.reason or "ok", v.innate, stage="local-law",
                              command=judged_command,
                              granted=granted, granted_reach=granted_reach)

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
            err += _home_hint(intent, self._dispatcher)
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
