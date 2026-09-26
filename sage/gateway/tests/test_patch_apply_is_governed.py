"""patch_apply: the being changes the tree it reasons about, and the LAW rules on what it changes.

dp, 2026-09-25, asked whether to build this ungoverned first and govern it after:
**"governed. that's the whole point."**

So the claim under test is not "the verb works". It is that the three things the design says
are judged are actually judged, and that the one thing it says is NOT judged is stated rather
than quietly assumed:

  1. EVERY PATH THE PATCH TOUCHES reaches `ev.paths`, PARSED OUT OF THE DIFF -- so mrh.path
     rules on each one exactly as it rules on a memory_write. Every way the two could come
     apart is a test here: a hunk body that spells a file header (body is data, never
     structure); a section git reads and the parser did not (below); and any ARG the being
     might send, which must change neither the judged paths nor the command.
  2. THE COMMAND names those same parsed paths, one `--include=` each, so git refuses what the
     law did not see. That `--include` actually constrains git is measured here against a real
     repository rather than assumed from the manual.
  3. THE DIFF'S CONTENT rides inside the judged string as a sha256, so judged==executed reaches
     the bytes and not merely the command.

WHAT THE FIRST CUT GOT WRONG, kept because it is the reason the parser has the shape it has.
It read `diff --git` headers only. `git apply` also reads plain unified-diff sections with no
such header -- measured, 2026-09-25 -- so this patch:

    diff --git a/granted.py b/granted.py    <- the law saw this file
    ...
    --- a/ungranted.py                      <- and git wrote this one too
    +++ b/ungranted.py

was judged on one path and applied to two. `--include` did stop the write (measured both ways),
but a patch the law under-reads is not saved by being lucky downstream, and the being would
have been told "applied to 1 file" about a diff that named two. The parser is now a state
machine that accounts for every section git will read and refuses anything it cannot.

And the boundary, pinned as prose because an inaccurate map of coverage is worse than a small
one: nothing here reads the hunks and forms a view about whether the change is any good.

Run: python3 sage/gateway/tests/test_patch_apply_is_governed.py   (or pytest)
"""
import inspect
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import being_gate_client as B  # noqa: E402

FAILS = []


def check(name, got, want=True):
    if got != want:
        FAILS.append(f"{name}: got {got!r}, want {want!r}")


def refuses(name, args, ctx, must_say):
    """The composer must raise ValueError, and the message must carry `must_say`.

    A refusal is only useful if it names its own cause: the being has no other channel to
    learn what to send instead (hestia operating law, point 1)."""
    try:
        B.patch_apply_command(args, ctx)
    except ValueError as e:
        if must_say.lower() not in str(e).lower():
            FAILS.append(f"{name}: refused, but the reason did not say {must_say!r}: {e}")
        return
    except Exception as e:  # noqa: BLE001
        FAILS.append(f"{name}: raised {type(e).__name__}, not a named ValueError: {e}")
        return
    FAILS.append(f"{name}: was ACCEPTED, and must not be")


def _diff(*paths, body="@@ -1 +1 @@\n-old\n+new\n"):
    return "".join(f"diff --git a/{p} b/{p}\n--- a/{p}\n+++ b/{p}\n{body}" for p in paths)


CTX = {"worktree": "/w/t"}

# A path outside the worktree, for fixtures that need one. Deliberately NOT a credential path:
# a test that spells one teaches the spelling, and the claim under test is about REACH, not
# about which file is worth reaching for.
OUT_OF_TREE = "../../other-repo/config.py"

# The measured case: a `diff --git` section followed by a section with no git header at all.
# git applies BOTH (test_git_applies_what_the_parser_now_accounts_for measures it).
MIXED = ("diff --git a/granted.py b/granted.py\n"
         "--- a/granted.py\n+++ b/granted.py\n@@ -1 +1 @@\n-a\n+b\n"
         "--- a/ungranted.py\n+++ b/ungranted.py\n@@ -1 +1 @@\n-x\n+y\n")


# ── 1. the paths the law rules on come from the diff, not from the being ───────────────────

def test_the_judged_paths_are_parsed_out_of_the_diff():
    d = _diff("sage/gateway/a.py", "sage/gateway/b.py")
    check("every header's target is returned, in order",
          B.patch_targets(d), ["sage/gateway/a.py", "sage/gateway/b.py"])
    check("...resolved against the worktree, as absolute real paths",
          B.patch_apply_paths({"diff": d}, CTX),
          [os.path.realpath("/w/t/sage/gateway/a.py"), os.path.realpath("/w/t/sage/gateway/b.py")])
    check("a file named twice is one target, not two",
          B.patch_targets(_diff("x.py") + _diff("x.py")), ["x.py"])


def test_a_hunk_body_is_never_read_as_structure():
    """A hunk body is arbitrary text the being controls completely, and a `--- a/x` line inside
    one is DATA -- a removed line whose content happens to start with three dashes. Reading it
    as a file header is how a patch would name one file to the law and another to git, so the
    parser tracks the `@@` header's declared counts and treats everything inside them as body.
    """
    forged = ("diff --git a/sage/gateway/mine.py b/sage/gateway/mine.py\n"
              "--- a/sage/gateway/mine.py\n"
              "+++ b/sage/gateway/mine.py\n"
              "@@ -1,3 +1,3 @@\n"
              "-old\n"
              f"---- a/{OUT_OF_TREE}\n"
              f"-+++ b/{OUT_OF_TREE}\n"
              "+new\n"
              f"+--- a/{OUT_OF_TREE}\n"
              f"++++ b/{OUT_OF_TREE}\n")
    check("the only target is the one the section actually declares",
          B.patch_targets(forged), ["sage/gateway/mine.py"])
    paths = B.patch_apply_paths({"diff": forged}, CTX)
    check("...and nothing outside the worktree reaches the law", len(paths), 1)
    check("...specifically not the path the body spells",
          any("other-repo" in p for p in paths), False)


def test_a_headerless_section_is_accounted_for():
    """THE MEASURED ONE (2026-09-25). `git apply` reads plain unified-diff sections with no
    `diff --git` line, and applies them. The first parser read `diff --git` headers only, so a
    two-section patch was judged on one path and written to two -- measured against a real
    repository in `test_git_applies_what_the_parser_now_accounts_for` below. The law must see
    every section git will read, or `--include` is not defence in depth but the only defence."""
    check("BOTH sections are targets, so mrh.path rules on both",
          B.patch_targets(MIXED), ["granted.py", "ungranted.py"])
    cmd = B.patch_apply_command({"diff": MIXED, "why": "w"}, CTX)
    check("...and both are named in the command git will run", cmd.count("--include="), 2)
    plain = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a\n+b\n"
    check("a diff with no `diff --git` line at all is parsed, not refused",
          B.patch_targets(plain), ["x.py"])


def test_creation_and_deletion_name_the_real_file():
    """/dev/null is not a path. A new file takes its name from the `+++` side, a deleted one
    from the `---` side, and the law is handed the file that actually changes either way."""
    created = ("diff --git a/new.py b/new.py\nnew file mode 100644\nindex 0000000..e69de29\n"
               "--- /dev/null\n+++ b/new.py\n@@ -0,0 +1 @@\n+hello\n")
    check("a created file is judged by the name it will have", B.patch_targets(created), ["new.py"])
    deleted = ("diff --git a/gone.py b/gone.py\ndeleted file mode 100644\n"
               "--- a/gone.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-bye\n")
    check("a deleted file is judged by the name it had", B.patch_targets(deleted), ["gone.py"])
    check("git's metadata lines between the header and the body name no paths",
          B.patch_targets(created + deleted), ["new.py", "gone.py"])


def test_git_applies_what_the_parser_now_accounts_for():
    """THE MEASUREMENT ITSELF, against real git, because the claim is about git's behaviour and
    not about the manual's description of it. Without --include git applies BOTH sections of a
    mixed patch; the parser must therefore name both, and it does."""
    with tempfile.TemporaryDirectory() as wt:
        def g(*a):
            return subprocess.run(["git", "-C", wt, "-c", "user.email=t@t", "-c", "user.name=t", *a],
                                  capture_output=True, text=True)
        g("init", "-q")
        for n, v in (("granted.py", "a\n"), ("ungranted.py", "x\n")):
            open(os.path.join(wt, n), "w").write(v)
        g("add", "-A"), g("commit", "-qm", "base")
        pf = os.path.join(tempfile.gettempdir(), "sage-patch-test-mixed.diff")
        open(pf, "w").write(MIXED)
        try:
            r = subprocess.run(["git", "--no-pager", "-C", wt, "apply", "--whitespace=nowarn",
                                "--", pf], capture_output=True, text=True)
            check("git applied the mixed patch", r.returncode, 0)
            check("...touching the headerless section too -- this is the defect's evidence",
                  open(os.path.join(wt, "ungranted.py")).read(), "y\n")
            check("...and the parser names that file, so the law sees it",
                  "ungranted.py" in B.patch_targets(MIXED))
        finally:
            os.unlink(pf)


def test_the_normalized_event_carries_those_paths_to_the_law():
    """The parse is worthless if `_normalize` does not hand the result to the gate. This is the
    wire between the two, and it is the wire that was missing for `check`, `search` and
    `git_read` for eleven days (#208)."""
    with tempfile.TemporaryDirectory() as wt:
        subprocess.run(["git", "-C", wt, "init", "-q"], check=True)
        inst = os.path.join(os.path.dirname(__file__), "..", "..", "instances", "mcnugget-gemma3-12b")
        c = B.BeingGateClient("test-being", os.path.join(inst, "identity.json"),
                              os.path.abspath("."), worktree=wt)
        d = _diff("sage/gateway/a.py", "sage/federation/b.py")
        ev = c._normalize(B.BeingIntent(effector="patch_apply", args={"diff": d, "why": "because"}))
        check("both targets are in ev.paths, which is what mrh.path iterates",
              ev.paths, [os.path.realpath(os.path.join(wt, "sage/gateway/a.py")),
                         os.path.realpath(os.path.join(wt, "sage/federation/b.py"))])
        check("...and the command was composed too", bool(ev.command))
        check("...naming the worktree the dispatcher will use", c.worktree in ev.command)
        # path_args is empty ON PURPOSE: a path the being ASSERTS is not the path the patch
        # touches, and only the derived one may be judged.
        check("the registry asserts no path arg for this verb",
              B._REGISTRY["patch_apply"]["path_args"], ())

        # NO ARG BUT THE DIFF MAY MOVE THE JUDGEMENT. Found by sabotage: making the composer
        # read `args.get("paths") or patch_targets(...)` left every test green, because none
        # of them sent such an arg. A derivation is only a derivation if the being cannot
        # supply the answer alongside it, so the extra args are sent here on purpose.
        loud = {"diff": d, "why": "because",
                "paths": ["/etc/passwd"], "path": "/etc/passwd", "targets": ["/etc/passwd"],
                "command": "rm -rf /", "worktree": "/somewhere/else"}
        ev2 = c._normalize(B.BeingIntent(effector="patch_apply", args=loud))
        check("args that name paths do not change what the law rules on", ev2.paths, ev.paths)
        check("...nor the command it rules on", ev2.command, ev.command)
        check("...and the worktree still comes from the seat, not from the being",
              c.worktree in ev2.command and "/somewhere/else" not in ev2.command)


def test_every_compose_paths_takes_ctx_and_is_consequential():
    """THE GUARD, in the shape that caught #208. A `compose_paths` with the wrong signature
    cannot be called from the single site in `_normalize`, and a path-composing verb that is
    not consequential would soft-pass when the society governor is unreachable."""
    for eff, spec in sorted(B._REGISTRY.items()):
        cp = spec.get("compose_paths")
        if cp is None:
            continue
        params = list(inspect.signature(cp).parameters)
        check(f"{eff}: compose_paths takes (args, ctx)", params[:2], ["args", "ctx"])
        check(f"{eff}: ctx has a default",
              inspect.signature(cp).parameters["ctx"].default is None)
        check(f"{eff}: derives its paths rather than asserting them", spec["path_args"], ())
        check(f"{eff}: is consequential, so it fails closed without the society governor",
              eff in B._CONSEQUENTIAL)
        check(f"{eff}: is offered to the being with a schema", eff in B._TOOL_SCHEMAS)


# ── 2. the command names exactly those paths, and --include really constrains git ──────────

def test_the_command_includes_every_target_and_quotes_it():
    d = _diff("sage/gateway/a.py", "a name with spaces.py")
    cmd = B.patch_apply_command({"diff": d, "why": "w"}, CTX)
    check("one --include per target", cmd.count("--include="), 2)
    check("the plain one is named", "--include=sage/gateway/a.py" in cmd)
    # QUOTED for the reason every path in this module is quoted: judged==executed is a property
    # of the STRING. An unquoted space splits into extra argv while the law ruled on one token.
    check("a target with a space is quoted, so the argv the law read is the argv git gets",
          "--include='a name with spaces.py'" in cmd)
    check("the worktree is named with -C", f"-C {CTX['worktree']} " in cmd)
    check("no --3way and no --reject: a patch half-landing is not a success",
          "--3way" in cmd or "--reject" in cmd, False)
    argv = B.patch_apply_argv({"diff": d, "why": "w"}, CTX)
    check("the argv form is the same command, unsplit by the space",
          "--include=a name with spaces.py" in argv)


def test_include_actually_constrains_git():
    """MEASURED, not read off the manual. The whole design leans on `--include` refusing what
    the law did not see, so it is exercised against a real repository: a two-file patch applied
    with only one file included must leave the other untouched."""
    with tempfile.TemporaryDirectory() as wt:
        def g(*a):
            return subprocess.run(["git", "-C", wt, "-c", "user.email=t@t", "-c", "user.name=t", *a],
                                  capture_output=True, text=True)
        g("init", "-q")
        for name in ("kept.txt", "other.txt"):
            open(os.path.join(wt, name), "w").write("old\n")
        g("add", "-A"), g("commit", "-qm", "base")
        for name in ("kept.txt", "other.txt"):
            open(os.path.join(wt, name), "w").write("new\n")
        diff = g("diff").stdout
        g("checkout", "--", ".")
        check("the fixture diff names both files", sorted(B.patch_targets(diff)),
              ["kept.txt", "other.txt"])
        patch = os.path.join(wt, "..", "p.diff")
        patch = os.path.abspath(patch)
        open(patch, "w").write(diff)
        r = subprocess.run(["git", "--no-pager", "-C", wt, "apply", "--whitespace=nowarn",
                            "--include=kept.txt", "--", patch], capture_output=True, text=True)
        check("git applied the included file", r.returncode, 0)
        check("...and changed it", open(os.path.join(wt, "kept.txt")).read(), "new\n")
        check("...and did NOT touch the excluded one -- --include is a real boundary",
              open(os.path.join(wt, "other.txt")).read(), "old\n")
        os.unlink(patch)


# ── 3. the content rides inside the judged string ──────────────────────────────────────────

def test_the_diff_is_named_by_its_own_digest():
    d = _diff("x.py")
    cmd = B.patch_apply_command({"diff": d, "why": "w"}, CTX)
    check("the patch file's name IS the digest, so the content is inside what the law judged",
          B.patch_digest(d) in cmd)
    check("...and the path is outside the worktree: the patch is not itself a tree change",
          B.patch_file_path(d).startswith("/tmp/") and CTX["worktree"] not in B.patch_file_path(d))
    other = B.patch_apply_command({"diff": _diff("x.py", body="@@ -1 +1 @@\n-old\n+DIFFERENT\n"),
                                   "why": "w"}, CTX)
    check("a different body is a different judged command, even with the same target",
          cmd != other)
    check("...while the targets are identical -- so the content, not just the paths, is bound",
          B.patch_targets(d), ["x.py"])


def test_the_dispatcher_rehashes_before_it_runs():
    """The last link, pinned at source: the seat re-READS the staged file and re-hashes it, so
    a stale or swapped /tmp file cannot be applied under a digest the law approved."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "hestia_dispatch.py")).read()
    body = src[src.index("def _do_patch_apply"):src.index("def _test_source_identity")]
    check("it reads the file back rather than trusting what it wrote", 'open(staged, "r"' in body)
    check("...re-hashes what came back", "patch_digest(on_disk)" in body)
    check("...and refuses on a mismatch instead of applying", "does not hash to the digest" in body)
    check("a verdict that bound no command is not an authority to run one",
          "judged is not None and judged != cmd" in body)
    check("the act is witnessed BEFORE the tree changes",
          body.index("hestia_begin_action") < body.index("subprocess.run(argv"))
    check("an unreachable witness means nothing is changed",
          "UNWITNESSED" in body and "nothing was changed" in body)
    check("a patch that does not apply says the tree moved on, not that the being erred",
          "the file moved on since you read it" in body)
    check("...and carries git's own words, which name the file and the hunk", "git said" in body)
    check("a landed patch says it is NOT yet verified",
          "has NOT been verified" in body)


# ── the refusals: every shape the parser cannot represent EXACTLY ──────────────────────────

def test_the_parser_refuses_what_it_cannot_represent_exactly():
    ok = {"diff": _diff("x.py"), "why": "w"}
    B.patch_apply_command(ok, CTX)                      # the control: this one is fine

    refuses("no worktree at all fails closed", ok, {}, "worktree")
    refuses("no worktree key fails closed", ok, None, "worktree")
    refuses("an empty diff", {"diff": "", "why": "w"}, CTX, "needs a 'diff'")
    # NOT "names no files". The first cut coerced with str(), so `diff=7` became "7" and was
    # refused for the wrong reason -- a true sentence about a problem the being did not have.
    refuses("a diff that is not a string names the TYPE, not a missing header",
            {"diff": 7, "why": "w"}, CTX, "must be the text of a unified diff")
    refuses("a missing diff key", {"why": "w"}, CTX, "needs a 'diff'")
    refuses("prose with no file header of any kind",
            {"diff": "I would change x.py so that it does the other thing\n", "why": "w"}, CTX,
            "names no files")
    refuses("a diff that ends inside a hunk",
            {"diff": "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1,3 +1,3 @@\n-a\n",
             "why": "w"}, CTX, "ends inside a hunk")
    # Two distinct shapes, and the refusals must tell them apart: a hunk interrupted while it
    # still owes lines, and a stray line after a hunk has closed. The second was ACCEPTED by
    # the first parser -- silently, which is the failure mode that matters, because a line the
    # parser skips is a change the law never sees.
    refuses("a hunk interrupted while it still owes lines",
            {"diff": "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1,3 +1,3 @@\n-a\n"
                     "not a diff line\n", "why": "w"}, CTX, "ends early")
    refuses("a stray line after a hunk has closed",
            {"diff": "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a\n+b\n+c\n",
             "why": "w"}, CTX, "could not read '+c'")
    # NOT `must_say="binary"`: that word also appears in the generic "could not read
    # 'GIT binary patch' as part of a diff" refusal, so the pin passed with the dedicated
    # branch deleted. Matched on wording only that branch produces (found by sabotage).
    refuses("a binary patch, whose change no reader can review",
            {"diff": "diff --git a/i.png b/i.png\nGIT binary patch\nliteral 4\n", "why": "w"},
            CTX, "a binary blob is neither")
    refuses("a section whose header and body name different files",
            {"diff": "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/other.py\n@@ -1 +1 @@\n-a\n+b\n",
             "why": "w"}, CTX, "body says")
    refuses("an absolute path", {"diff": _diff("/etc/passwd"), "why": "w"}, CTX, "absolute")
    refuses("a path that walks out", {"diff": _diff("../../.ssh/authorized_keys"), "why": "w"},
            CTX, "walks the tree")
    refuses("a path into .git", {"diff": _diff(".git/config"), "why": "w"}, CTX, "repository's own record")
    refuses("a .git directory at depth -- a nested repo's hooks",
            {"diff": _diff("sub/.git/hooks/pre-commit"), "why": "w"}, CTX, "repository's own record")
    # Legion's hold on #210: SAGE's hooksPath is a TRACKED `.githooks/`, so a patched hook would
    # run as the seat, outside bwrap, at the seat's next commit in this tree.
    refuses("a git hook, which the seat would EXECUTE",
            {"diff": _diff(".githooks/pre-commit"), "why": "w"}, CTX, "scripts git RUNS")
    # Legion's re-review at b0f62da58: those refusals compared exact strings, and McNugget's
    # volume is APFS, case-INSENSITIVE -- `.GITHOOKS/pre-commit` IS the hook there, and
    # `.Git/config` is the repo config (core.fsmonitor runs on `git status`, no hook needed).
    for spelled in (".GITHOOKS/pre-commit", ".GitHooks/pre-commit", ".githooks./pre-commit"):
        refuses(f"a git hook spelled {spelled!r}, which the volume folds to the hook",
                {"diff": _diff(spelled), "why": "w"}, CTX, "scripts git RUNS")
    for spelled in (".Git/config", "sub/.GIT/hooks/pre-commit", ".g\u200cit/config", ".git /config"):
        refuses(f"the repository's record spelled {spelled!r}",
                {"diff": _diff(spelled), "why": "w"}, CTX, "repository's own record")
    # A symlink is refused however it arrives: made new, a file turned into one, or an existing
    # one pointed somewhere else. Each is a change to where OTHER paths lead.
    for how, meta in (("a new symlink", "new file mode 120000\n"),
                      ("a file turned into a symlink", "old mode 100644\nnew mode 120000\n"),
                      ("an existing symlink retargeted", "index 1111111..2222222 120000\n")):
        refuses(how, {"diff": "diff --git a/hk b/hk\n" + meta +
                      "--- a/hk\n+++ b/hk\n@@ -1 +1 @@\n-x\n+.githooks\n", "why": "w"},
                CTX, "symbolic link")
    # ...while an ordinary executable file is still just a file.
    check("a new executable file is not a symlink",
          B.patch_targets("diff --git a/run.sh b/run.sh\nnew file mode 100755\n--- /dev/null\n"
                          "+++ b/run.sh\n@@ -0,0 +1 @@\n+echo hi\n"), ["run.sh"])
    # The no-newline marker is accepted ONCE, directly after a hunk closes -- and not as a
    # licence for any backslash line anywhere in the structured part of the diff.
    refuses("a no-newline marker that does not follow a hunk",
            {"diff": "diff --git a/x.py b/x.py\n\\ No newline at end of file\n--- a/x.py\n"
                     "+++ b/x.py\n@@ -1 +1 @@\n-a\n+b\n", "why": "w"}, CTX, "could not read")
    refuses("a second marker after the one a hunk may carry",
            {"diff": _diff("x.py", body="@@ -1 +1 @@\n-a\n+b\n\\ No newline at end of file\n"
                                        "\\ No newline at end of file\n"), "why": "w"},
            CTX, "could not read")
    # ...and only the hooks directory: an ordinary file NAMED like it elsewhere is a file.
    check("a non-hook path that merely contains the word is still allowed",
          B.patch_targets(_diff("docs/githooks.md")), ["docs/githooks.md"])
    refuses("a glob character, which --include would match as a pattern",
            {"diff": _diff("sage/*.py"), "why": "w"}, CTX, "glob")
    refuses("a bracket glob", {"diff": _diff("sage/x[12].py"), "why": "w"}, CTX, "glob")
    refuses("a rename, which is two acts on two paths",
            {"diff": "diff --git a/old.py b/new.py\n", "why": "w"}, CTX, "renames")
    refuses("a header the parser cannot split", {"diff": "diff --git nonsense\n", "why": "w"},
            CTX, "could not read the target")
    refuses("a patch bigger than the cap",
            {"diff": _diff("x.py", body="@@ -1 +1 @@\n" + "+x\n" * 200000), "why": "w"},
            CTX, "send them one at a time")
    # A worktree change with no account of itself is not reviewable, and this one is witnessed.
    refuses("no why", {"diff": _diff("x.py")}, CTX, "needs a 'why'")
    refuses("a blank why", {"diff": _diff("x.py"), "why": "   "}, CTX, "needs a 'why'")


def test_a_file_without_a_trailing_newline_can_be_patched():
    """Legion, re-review of #210: `git diff` prints `\\ No newline at end of file` for any file
    that lacks one, and the parser refused that line -- so a being editing such a file was told
    "could not read" about a diff git itself produced. Measured against real git both ways: the
    diff is PRODUCED by git, parsed here, and APPLIED by git."""
    with tempfile.TemporaryDirectory() as d:
        def g(*a, **kw):
            return subprocess.run(["git", "-C", d, *a], capture_output=True, text=True, **kw)
        g("init", "-q")
        for name, text in (("tail.txt", "a\nb"), ("both.txt", "x")):
            with open(os.path.join(d, name), "w") as f:
                f.write(text)
        g("add", "."); g("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base")
        with open(os.path.join(d, "tail.txt"), "w") as f:
            f.write("a\nB")                           # old AND new lack the newline
        with open(os.path.join(d, "both.txt"), "w") as f:
            f.write("y\n")                            # the marker lands mid-hunk
        diff = g("diff").stdout
        check("git really printed the marker (else this test proves nothing)",
              diff.count("No newline at end of file"), 3)
        try:
            got = B.patch_targets(diff)
        except ValueError as e:
            got = f"REFUSED: {e}"
        check("a git-produced diff of a file with no trailing newline is read", got,
              ["both.txt", "tail.txt"])
        g("checkout", "-q", "--", ".")
        r = g("apply", "-", input=diff)
        check("...and git applies the same diff", r.returncode, 0)


def test_the_boundary_is_stated_rather_than_implied():
    """An inaccurate map of coverage is worse than a small one. The module must say, in its own
    prose, that it rules on WHICH files change and not on whether the change is any good --
    because the being will read the schema, and a verb that implies review would teach it the
    exact overclaim this verb exists to stop it making."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "being_gate_client.py")).read()
    block = src[src.index("# ── patch_apply:"):src.index("def patch_apply_argv")]
    # Comment prose wraps, so match the SENTENCE rather than the line: strip the `#` markers
    # and collapse whitespace. A prose pin that only holds while the reflow is lucky is a pin
    # that will be "fixed" by the next person who rewraps a paragraph.
    prose = " ".join(l.lstrip().lstrip("#").strip() for l in block.splitlines())
    prose = " ".join(prose.split())
    check("the limit of the governance is written down", "WHAT IS STILL NOT GOVERNED" in prose)
    check("...and says review is what check and a reader are for",
          "not on whether the change is any good" in prose)
    schema = B._TOOL_SCHEMAS["patch_apply"][0]
    check("the being is told to check afterwards, in the schema it actually reads",
          "applying a patch is not evidence that it works" in schema)
    check("...and that a non-applying patch is about the tree moving, not about it",
          "moved on since you read it" in schema)


# ── the dispatcher, driven end to end against a real repository ────────────────────────────
#
# The source pins above say the code is SHAPED right. These say it BEHAVES right, which is the
# only thing that survives a refactor. Both were needed: a sabotage that reordered the witness
# call slipped past the source pin (the string still appeared before the string), and the
# behavioural test catches it by looking at the tree.


class _FakeMcp:
    """Enough of the daemon to reach patch_apply. `fail` holds one door shut so a test can ask
    what the dispatcher does with a refusal -- the FakeMcp idiom from test_hestia_dispatch."""

    def __init__(self, endpoint, plugin_id, fail=()):
        self.plugin_id, self.fail = plugin_id, set(fail)
        self.calls = []

    def init(self):
        pass

    def call(self, name, args):
        self.calls.append((name, dict(args)))
        if name in self.fail:
            body = {"_hestia_error": {"code": "hestia.test_forced",
                                      "message": "the witness substrate is down"}}
        elif name == "hestia_connect":
            body = {"sessionId": "sid-1"}
        else:
            body = {"actionId": "act-1"}
        return {"result": {"content": [{"type": "text", "text": json.dumps(body)}]}}


def _repo(tmp):
    """A worktree with one committed file, and the diff that changes it."""
    def g(*a):
        return subprocess.run(["git", "-C", tmp, "-c", "user.email=t@t", "-c", "user.name=t", *a],
                              capture_output=True, text=True)
    g("init", "-q")
    open(os.path.join(tmp, "f.py"), "w").write("old\n")
    g("add", "-A"), g("commit", "-qm", "base")
    open(os.path.join(tmp, "f.py"), "w").write("new\n")
    diff = g("diff").stdout
    g("checkout", "--", ".")
    return diff


SKIPPED = []


def _dispatch(tmp, diff, fail=(), verdict_command="from the law"):
    """Run one patch_apply through the real dispatcher. `verdict_command` defaults to the
    command the law would actually have bound; pass something else to test the mismatch.

    Returns (None, None) when the dispatcher cannot be BUILT on this seat. The signing stack
    (PyNaCl) is imported lazily inside `__init__` -- not at module import -- so the guard has
    to wrap the construction, which is where McNugget actually falls over (2026-09-25). A SKIP
    is said out loud and counted; it is never allowed to read as a pass, because this arm is
    the half that survives a refactor.
    """
    from sage.gateway.hestia_dispatch import HestiaF1aDispatcher
    args = {"diff": diff, "why": "closing the loop"}
    if verdict_command == "from the law":
        verdict_command = B.patch_apply_command(args, {"worktree": tmp})
    mcp = _FakeMcp(None, "test-being", fail=fail)
    try:
        d = HestiaF1aDispatcher("test-being", tempfile.mkdtemp(prefix="pa-"),
                                mcp_factory=lambda ep, pid: mcp, worktree=tmp)
    except Exception as e:  # noqa: BLE001
        SKIPPED.append(f"{type(e).__name__}: {e}")
        return None, None
    v = B.GatewayVerdict("allow", "ok", command=verdict_command)
    return d(B.BeingIntent("patch_apply", args), v), mcp


def test_the_patch_lands_and_the_answer_says_it_is_not_yet_verified():
    with tempfile.TemporaryDirectory() as tmp:
        diff = _repo(tmp)
        env, mcp = _dispatch(tmp, diff)
        if env is None:
            return
        check("the act succeeded", env.ok, True)
        check("the file actually changed -- this is the whole verb",
              open(os.path.join(tmp, "f.py")).read(), "new\n")
        check("it names what it touched", env.result.get("targets"), ["f.py"])
        check("it was witnessed", env.witness_id, "act-1")
        check("the evidence carries the diff's digest", env.result["evidence"]["patch_sha256"],
              B.patch_digest(diff))
        check("...and records that the law bound the command it ran",
              env.result["evidence"]["law_bound_command"], True)
        # THE HABIT THIS VERB EXISTS TO BREAK: asserting an outcome never observed.
        check("the answer says applying is not verifying",
              "has NOT been verified" in env.result.get("next", ""))


def test_nothing_changes_when_the_witness_is_unreachable():
    """BEHAVIOURAL, because the source pin could not tell a real reorder from a moved string.
    An unwitnessed change to the tree the being reasons about is one it could never account
    for afterwards, so the tree must be untouched -- not merely the log unwritten."""
    with tempfile.TemporaryDirectory() as tmp:
        diff = _repo(tmp)
        env, mcp = _dispatch(tmp, diff, fail={"hestia_begin_action"})
        if env is None:
            return
        check("the act failed", env.ok, False)
        check("...saying the witness was the thing missing", "UNWITNESSED" in (env.error or ""))
        check("THE TREE IS UNTOUCHED", open(os.path.join(tmp, "f.py")).read(), "old\n")


def test_a_command_the_law_did_not_bind_is_refused():
    """The verdict is the authority for what runs. A dispatcher that would execute something
    else must refuse, not reconcile -- and the tree must be untouched when it does."""
    with tempfile.TemporaryDirectory() as tmp:
        diff = _repo(tmp)
        env, mcp = _dispatch(tmp, diff, verdict_command="git --no-pager -C /elsewhere apply x")
        if env is None:
            return
        check("refused", env.ok, False)
        check("...naming the law as the authority", "the law judged" in (env.error or ""))
        check("THE TREE IS UNTOUCHED", open(os.path.join(tmp, "f.py")).read(), "old\n")
        check("...and it never even asked for a witness",
              [n for n, _ in mcp.calls if n == "hestia_begin_action"], [])


def test_the_verdict_actually_carries_the_command_now():
    """THE FINDING THIS TURNED UP (2026-09-25). `GatewayVerdict` had no `command` field, so
    `_do_check`'s `getattr(verdict, "command", None)` was always None and its judged==executed
    guard -- documented in a five-line comment as a checked invariant -- could never fire.
    patch_apply had copied the pattern faithfully enough to inherit the hole. The field exists
    now and `gate()` fills it, which makes BOTH guards live."""
    import dataclasses
    names = [f.name for f in dataclasses.fields(B.GatewayVerdict)]
    check("the verdict has somewhere to carry the judged command", "command" in names)

    # EVERY verdict built from a normalized event must carry it, on ALLOW as much as on DENY.
    # Pinned at source because this seat holds no grant for a temp worktree, so the live call
    # below only ever exercises the deny path -- and a sabotage that dropped `command` from the
    # ALLOW return left the whole file green (found 2026-09-25). A deny carries it too, and
    # must: a refusal about a string the being cannot see is one it cannot act on.
    src = open(os.path.join(os.path.dirname(__file__), "..", "being_gate_client.py")).read()
    gate = src[src.index("    def gate(self, intent: BeingIntent) -> GatewayVerdict:"):
               src.index("    def _compose_ctx", src.index("    def gate(self, intent"))
               if "    def _compose_ctx" in src[src.index("    def gate(self, intent"):]
               else len(src)]
    built_from_ev = [ln for ln in gate.splitlines()
                     if "GatewayVerdict(" in ln and "gate.raised" not in ln
                     and "gate.unreachable" not in ln and "registry.unbounded" not in ln]
    check("gate() builds verdicts from the event in more than one place", len(built_from_ev) >= 3)
    check("...and EVERY such verdict reports the command the law ruled on",
          gate.count("command=judged_command"), len(built_from_ev))
    # Bound ONCE, with getattr, so a core that builds a partial event cannot make gate() raise.
    # Fail-closed means DENY WITH A REASON; an exception out of the gate is neither.
    check("the command is bound once per call, not read off the event six times",
          gate.count('judged_command = getattr(ev, "command", None)'), 2)
    with tempfile.TemporaryDirectory() as wt:
        subprocess.run(["git", "-C", wt, "init", "-q"], check=True)
        inst = os.path.join(os.path.dirname(__file__), "..", "..", "instances", "mcnugget-gemma3-12b")
        c = B.BeingGateClient("test-being", os.path.join(inst, "identity.json"),
                              os.path.abspath("."), worktree=wt)
        args = {"diff": _diff("x.py"), "why": "w"}
        ev = c._normalize(B.BeingIntent("patch_apply", args))
        v = c.gate(B.BeingIntent("patch_apply", args))
        # Whatever the decision on this machine, the verdict must report the string that was
        # ruled on -- that is what the dispatcher compares against.
        check("the gate reports the command it ruled on", v.command, ev.command)
        check("...and it is the one the dispatcher would build",
              v.command, B.patch_apply_command(args, {"worktree": c.worktree}))


def test_a_stale_diff_is_an_answer_about_the_tree():
    """A patch that does not apply is the commonest case in a real loop, and the being must
    read it as "the file moved on", not as "I did something wrong" -- an organ whose refusals
    sound like the being's fault is one it learns not to use."""
    with tempfile.TemporaryDirectory() as tmp:
        diff = _repo(tmp)
        open(os.path.join(tmp, "f.py"), "w").write("something else entirely\n")
        env, _ = _dispatch(tmp, diff)
        if env is None:
            return
        check("not ok, because nothing landed", env.ok, False)
        check("...and it says the tree moved on", "moved on since you read it" in (env.error or ""))
        check("...carrying git's own words, which name the file",
              "f.py" in env.result.get("git_output", ""))
        check("the tree is exactly as the being left it",
              open(os.path.join(tmp, "f.py")).read(), "something else entirely\n")


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]


def main():
    for fn in TESTS:
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            FAILS.append(f"{fn.__name__} raised {type(e).__name__}: {e}")
    for f in FAILS:
        print("FAIL", f)
    if SKIPPED:
        # NAMED, not swallowed. Four behavioural tests did not run, and a green line that did
        # not say so would be the report claiming coverage it does not have.
        print(f"SKIPPED: the dispatcher arm (4 tests) -- it could not be imported here "
              f"({SKIPPED[0][:90]}). The source pins above still ran; CI is the authority.")
    print(f"{'FAILED' if FAILS else 'ok'}: {len(FAILS)} failure(s) across "
          f"{len(TESTS) - (4 if SKIPPED else 0)} tests that ran")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
