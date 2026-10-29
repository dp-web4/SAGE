"""being_skills: procedures a being can find when the situation calls for them, and write for itself (dp,
2026-10-27: "a 'skills' structure, and membot-type index for them ... model it on your own skills in
claude-code")."""
import json
import tempfile
from pathlib import Path

import pytest

from sage.gateway import being_skills as sk
from sage.gateway.being_gate_client import BeingIntent, GatewayVerdict
from sage.gateway.hestia_dispatch import HestiaF1aDispatcher
from sage.gateway.tests.test_hestia_dispatch import FakeMcp

_ALLOW = GatewayVerdict("allow")


def _write(h, **a):
    base = {"name": "probe-skill", "description": "a test procedure for test widgets",
            "when": "test widget, gizmo-17", "body": "1. look\n2. note what you saw"}
    return sk.skill(h, {**base, **a})


def test_every_fleet_skill_parses_with_a_name_a_description_and_when_words():
    fleet = sk._load(sk.FLEET_DIR, "fleet")
    assert len(fleet) >= 6
    for s in fleet:
        assert sk.NAME.match(s["name"]) and s["description"] and s["when"] and s["body"], s["name"]
        meta, _ = sk.parse(s["path"].read_text())
        assert meta["name"] == s["name"], "the header names the directory it is in"


def test_the_seeing_seed_holds_on_a_seat_without_a_cortex():
    """A fleet skill reaches every seat and cannot be shadowed (pub's review of #576): on a seat
    whose camera reads a device, it must not describe a cortex gaze as this seat's, nor steer it
    off the device that `camera` itself opens there."""
    body = (sk.FLEET_DIR / "seeing-with-your-eyes" / "SKILL.md").read_text()
    head, rest = body.split("**Where the frame comes from", 1)
    assert "cortex" not in head.split("---", 2)[2], "the steps before the split hold on every seat"
    assert "**A cortex runs your eyes**" in rest and "**A device node, no cortex**" in rest
    assert "`camera` opens that device itself" in rest


def test_the_seeing_seed_has_a_mac_branch_that_agrees_with_the_macs_camera_text():
    """#578 (NOVA's hold): a Mac's `camera` text says the seat finds the camera by name and there is no
    device node, and offers only out_path. The fleet skill every Mac being reads must not send it back to a
    device node: its Mac branch keys on the same words and offers no device, and the device-node branch says
    it is for a description that names one."""
    from sage.gateway import toolset
    rest = (sk.FLEET_DIR / "seeing-with-your-eyes" / "SKILL.md").read_text().split("**Where the frame comes from", 1)[1]
    mac = rest.split("- **A Mac**", 1)[1].split("\n- **", 1)[0]
    desc, params = toolset.MAC_CAMERA
    assert "finds the camera by its name" in mac and "finds the attached camera by its name" in desc
    assert "no device node" in mac and "no device node" in desc
    assert "there is no device to\n    name" in mac and list(params) == ["out_path"]
    assert "Name a different `device`" not in mac, "the Mac branch must not offer what the Mac does not read"
    device = rest.split("- **A device node, no cortex**", 1)[1]
    assert "ffmpeg reads a device node" in device


def test_a_skill_is_written_read_listed_and_replaced_with_every_version_kept(tmp_path):
    ok, msg, changed = _write(tmp_path)
    assert ok and changed and "wrote your skill probe-skill" in msg
    ok, text, _ = sk.skill(tmp_path, {"name": "probe-skill"})
    assert ok and "your own skill" in text and "2. note what you saw" in text
    assert "probe-skill (yours)" in sk.skill(tmp_path, {})[1]
    ok, msg, _ = _write(tmp_path, body="1. look twice", why="once was not enough")
    assert ok and "earlier version is kept" in msg
    log = [json.loads(l) for l in (tmp_path / sk.SKILLS_LOG).read_text().splitlines()]
    assert len(log) == 2 and "2. note what you saw" in log[1]["from"] and log[1]["why"] == "once was not enough"
    ok, msg, changed = _write(tmp_path, body="1. look twice")
    assert ok and not changed and msg.startswith("unchanged")


def test_the_index_puts_what_matches_the_situation_first_and_says_why(tmp_path):
    _write(tmp_path)
    block = sk.render(tmp_path, "## journal\n2026-10-27 the gizmo-17 would not turn")
    first = block.splitlines()[1]
    assert first.startswith("- probe-skill (yours)") and "matches now: gizmo-17" in first
    nothing = sk.render(tmp_path, "an ordinary beat")
    assert "matches now" not in nothing and "probe-skill" in nothing


def test_when_words_match_whole_words_only():
    s = {"name": "x", "description": "d", "when": ["run"], "source": "fleet", "body": ""}
    assert sk.match([s], "a rerun of the file") == []
    assert sk.match([s], "I will run it")[0][2] == ["run"]


def test_a_when_word_ending_in_punctuation_matches_what_follows_it():
    """cbp review of #576: `scope-` and `/dev/video` are prefixes of what a refusal and a device listing print."""
    fleet = {s["name"]: s for s in sk._load(sk.FLEET_DIR, "fleet")}
    assert "/dev/video" in sk.match([fleet["seeing-with-your-eyes"]], "ls /dev/video0 failed")[0][2]
    s = {"name": "x", "description": "d", "when": ["scope-"], "source": "fleet", "body": ""}
    assert "scope-" in sk.match([s], "opened scope-ac881b894a24")[0][2]
    assert sk.match([s], "telescope-ac88") == []
    # the refusal skill no longer lists `scope-` (2026-10-28): a scope id stays in the being's state long after
    # the refusal that opened it, so it marked the skill on routine beats; the refusal's own words still match
    assert sk.match([fleet["when-an-act-is-refused"]], "refused: outside your granted scope; opened scope-ac881b894a24")


def test_the_index_stays_within_its_budget_and_says_how_many_more(tmp_path):
    for i in range(40):
        _write(tmp_path, name=f"probe-{i:02d}", description="x" * 200)
    block = sk.render(tmp_path, "")
    assert len(block) <= sk.INDEX_CHARS + 200 and "more (skill with no arguments lists them all)" in block


def test_query_searches_bodies_too(tmp_path):
    _write(tmp_path, body="when the gizmo-17 hums, count to ten first")
    assert "probe-skill" in sk.skill(tmp_path, {"query": "hums"})[1]
    assert "no skill matches" in sk.skill(tmp_path, {"query": "zzzzqqq"})[1]


@pytest.mark.parametrize("args,says", [
    ({"name": "Bad Name"}, "is not"),
    ({"name": "getting-code-run"}, "fleet skill"),
    ({"body": ""}, "needs a description"),
    ({"description": "two\nlines"}, "one line each"),
    ({"body": "x" * (sk.BODY_MAX_CHARS + 1)}, "at most"),
])
def test_a_refused_write_says_why_and_changes_nothing(tmp_path, args, says):
    ok, msg, _ = _write(tmp_path, **args)
    assert not ok and says in msg, msg
    assert not (tmp_path / sk.OWN_DIR).exists() and not (tmp_path / sk.SKILLS_LOG).exists()


def test_a_hand_placed_skill_with_a_fleet_name_does_not_shadow_it(tmp_path):
    d = tmp_path / sk.OWN_DIR / "getting-code-run"
    d.mkdir(parents=True)
    (d / sk.SKILL_FILE).write_text("---\nname: getting-code-run\ndescription: not the fleet's\n---\nbody")
    names = [(s["name"], s["source"]) for s in sk.index(tmp_path)]
    assert ("getting-code-run", "fleet") in names and ("getting-code-run", "yours") not in names


def test_it_is_registered_offered_and_judged_as_a_write_of_exactly_what_it_touches(tmp_path):
    from sage.gateway import being_gate_client as g
    from sage.gateway import toolset
    assert "skill" in g._REGISTRY and "skill" in [t["function"]["name"] for t in toolset.specs()]
    ctx = {"memory_root": str(tmp_path)}
    assert g.skill_paths({}, ctx) == [] and g.skill_paths({"name": "probe-skill"}, ctx) == []
    with pytest.raises(ValueError):
        g.skill_paths({"name": "../escape", "body": "b"}, ctx)
    declared = set(g.skill_paths({"name": "probe-skill", "body": "b"}, ctx))
    for i in range(2):
        before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
        assert _write(tmp_path, body=f"v{i}")[0]
        after = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
        changed = {str(p.resolve()) for p in set(before) | set(after) if before.get(p) != after.get(p)}
        assert changed and changed <= declared, changed - declared


def _disp():
    FakeMcp.calls = []
    root = tempfile.mkdtemp(prefix="hs-")
    return HestiaF1aDispatcher("sprout-being", root, mcp_factory=lambda ep, pid: FakeMcp(ep, pid)), Path(root)


def test_the_verb_writes_and_witnesses_and_direct_writes_are_refused():
    d, root = _disp()
    env = d(BeingIntent("skill", {"name": "probe-skill", "description": "a test", "body": "steps"}), _ALLOW)
    assert env.ok and env.witness_id, env.error
    env = d(BeingIntent("skill", {"name": "getting-code-run"}), _ALLOW)
    assert env.ok and "fleet skill" in env.result and env.witness_id is None
    for verb, args in (("memory_write", {"path": "skills/probe-skill/SKILL.md", "content": "x"}),
                       ("memory_write", {"path": "skills_log.jsonl", "content": "{}"}),
                       ("memory_edit", {"path": "skills/probe-skill/SKILL.md", "old": "steps", "new": "x"})):
        env = d(BeingIntent(verb, args), _ALLOW)
        assert not env.ok and "skill" in env.error, (verb, args, env)


def test_the_beat_lists_the_skills_and_matches_them_against_its_own_state(tmp_path):
    (tmp_path / "journal.md").write_text("2026-10-27 12:00 UTC: tried ffmpeg on the device node again\n")
    from sage.gateway.heartbeat import own_state
    state = own_state(tmp_path, "sprout-being", body_reading={})
    block = state[state.index("## Skills"):]
    assert "- seeing-with-your-eyes:" in block.splitlines()[1] and "matches now: ffmpeg" in block


def test_another_beings_skills_are_not_writable_through_a_grant(tmp_path):
    """cbp review of #576: the skills guard reaches any home a grant reaches, as its neighbours do (#546)."""
    d, root = _disp()
    other = tmp_path / "other-home"
    other.mkdir()
    (other / "identity.json").write_text("{}\n")
    reach = GatewayVerdict("allow", granted=(str(root), str(other)),
                           granted_reach=((str(root), True), (str(other), True)))
    env = d(BeingIntent("memory_write", {"path": str(other / "skills/x/SKILL.md"), "content": "x"}), reach)
    assert not env.ok and "skill" in env.error, env
    assert not (other / "skills").exists()
    # a granted directory that is no home keeps its own skills/ writable: the guard is about records
    plain = tmp_path / "plain"
    plain.mkdir()
    reach = GatewayVerdict("allow", granted=(str(root), str(plain)),
                           granted_reach=((str(root), True), (str(plain), True)))
    env = d(BeingIntent("memory_write", {"path": str(plain / "skills/x/SKILL.md"), "content": "x"}), reach)
    assert env.ok, env.error


def test_a_case_variant_of_the_skills_dir_or_log_is_refused_too():
    # macOS opens Skills/x/SKILL.md as skills/x/SKILL.md: an exact-case guard would let memory_write past the log
    d, root = _disp()
    for path in ("Skills/probe-skill/SKILL.md", "SKILLS/probe-skill/SKILL.md", "Skills_Log.jsonl"):
        env = d(BeingIntent("memory_write", {"path": path, "content": "x"}), _ALLOW)
        assert not env.ok and "changed only with skill" in env.error, (path, env)


def test_a_routine_beat_marks_no_skill_but_a_failure_does():
    """2026-10-28: on sprout-being's state, 4 of 6 skills were marked every beat by words that every beat's
    receipts carry (request_run, exit code, memory_edit, scope-, pending). A mark that is always on says nothing."""
    fleet = sk._load(sk.FLEET_DIR, "fleet")
    routine = ("[request_run] I ran scratch/a.py (sha 1) with no arguments. exit code 0. UNCHANGED since the request "
               "at seq 4. memory_edit: replaced lines 3-3. scope-ac881b894a24 granted. pending: 0. sandbox run ok.")
    assert sk.match(fleet, routine) == []
    assert [s["name"] for _, s, _ in sk.match(fleet, "Traceback ... NameError: name 'x' is not defined; exit code 1")] \
        == ["getting-code-run"]
    for failed in ("exit code 127", "exit code 137", "exit code -9", "timed out after 60 s"):
        assert [s["name"] for _, s, _ in sk.match(fleet, failed)] == ["getting-code-run"], failed


class _I:
    def __init__(self, effector, **args):
        self.effector, self.args = effector, args


class _E:
    def __init__(self, ok=True, result=None):
        self.ok, self.result = ok, result


def test_worked_out_names_a_target_that_failed_then_worked_in_one_beat():
    trace = [(_I("run", path="scratch/a.py"), _E(True, {"exit": 1})),
             (_I("memory_edit", path="scratch/a.py"), _E(True, "edited")),
             (_I("run", path="scratch/a.py"), _E(True, {"exit": 1})),
             (_I("run", path="scratch/a.py"), _E(True, {"exit": 0}))]
    said = sk.worked_out(trace)
    assert "`run scratch/a.py` failed 2 times and then worked, on try 3" in said and "`skill`" in said


def test_worked_out_is_silent_without_a_failure_before_a_success_on_the_same_target():
    assert sk.worked_out([]) is None
    assert sk.worked_out([(_I("run", path="a.py"), _E(True, {"exit": 0}))]) is None
    assert sk.worked_out([(_I("run", path="a.py"), _E(True, {"exit": 1})),
                          (_I("run", path="b.py"), _E(True, {"exit": 0}))]) is None, "another file is not the same task"
    assert sk.worked_out([(_I("run", path="a.py"), _E(True, {"exit": 0})),
                          (_I("run", path="a.py"), _E(True, {"exit": 1}))]) is None, "worked then broke is not worked out"
    assert sk.worked_out([(_I("run", path="a.py"), _E(True, {"exit": 1})), (_I("run", path="a.py"), _E(True, {"exit": 0})),
                          (_I("run", path="a.py"), _E(True, {"exit": 1}))]) is None, "found then broke again (#585 legion)"
    assert "`run b.py`" in sk.worked_out([(_I("run", path="b.py"), _E(True, {"exit": 1})),
                                          (_I("run", path="b.py"), _E(True, {"exit": 0})),
                                          (_I("run", path="a.py"), _E(True, {"exit": 1})),
                                          (_I("run", path="a.py"), _E(True, {"exit": 0})),
                                          (_I("run", path="a.py"), _E(True, {"exit": 1}))]), "another target still worked"
    assert sk.worked_out([(_I("camera"), _E(False)), (_I("camera"), _E(True, {"out_path": "x.jpg"}))]).startswith(
        "This beat, `camera` failed 1 time")


def test_a_filed_request_run_is_not_reported_as_worked():
    """#585 reviews (mcnugget, cbp): request_run's ok=True means the request was filed; nothing has run."""
    assert sk.worked_out([(_I("request_run", path="a.py"), _E(False)),
                          (_I("request_run", path="a.py"), _E(True, "filed"))]) is None


def test_worked_out_counts_the_last_struggle_and_one_spelling_of_a_path():
    said = sk.worked_out([(_I("run", path="a.py"), _E(True, {"exit": 1})), (_I("run", path="a.py"), _E(True, {"exit": 0})),
                          (_I("run", path="a.py"), _E(True, {"exit": 1})), (_I("run", path="a.py"), _E(True, {"exit": 0}))])
    assert "failed 1 time and then worked, on try 2" in said
    assert "`run a.py` failed 1 time" in sk.worked_out([(_I("run", path="./a.py"), _E(True, {"exit": 1})),
                                                       (_I("run", path="a.py"), _E(True, {"exit": 0}))])


def test_a_skill_of_its_own_can_be_retired_with_its_text_kept(tmp_path):
    # dp, 2026-10-28: "does it have ways to update or remove skills?" It could replace one, never remove one.
    _write(tmp_path)
    ok, msg, changed = sk.skill(tmp_path, {"name": "probe-skill", "retire": "true", "why": "the steps did not work"})
    assert ok and changed and "retired your skill probe-skill" in msg
    assert "probe-skill" not in [s["name"] for s in sk.index(tmp_path)]
    assert not (tmp_path / sk.OWN_DIR / "probe-skill").exists()
    last = json.loads((tmp_path / sk.SKILLS_LOG).read_text().splitlines()[-1])
    assert last["op"] == "retire" and "2. note what you saw" in last["from"] and last["why"] == "the steps did not work"
    ok, msg, _ = _write(tmp_path, body="new steps")              # the name is free again
    assert ok and "wrote your skill probe-skill" in msg


@pytest.mark.parametrize("name,says", [("getting-code-run", "fleet skill"), ("no-such-skill", "no skill called"),
                                       ("Bad Name", "not a skill name")])
def test_a_refused_retire_says_why_and_changes_nothing(tmp_path, name, says):
    _write(tmp_path)
    before = sorted(p.name for p in tmp_path.rglob("*"))
    ok, msg, changed = sk.skill(tmp_path, {"name": name, "retire": "true"})
    assert not ok and not changed and says in msg, msg
    assert sorted(p.name for p in tmp_path.rglob("*")) == before


def test_a_retire_that_cannot_be_logged_removes_nothing(tmp_path):
    _write(tmp_path)
    (tmp_path / sk.SKILLS_LOG).unlink()
    (tmp_path / sk.SKILLS_LOG).mkdir()
    ok, msg, _ = sk.skill(tmp_path, {"name": "probe-skill", "retire": "true"})
    assert not ok and "skill stays" in msg and (tmp_path / sk.OWN_DIR / "probe-skill" / sk.SKILL_FILE).exists()


def test_the_gate_declares_what_a_retire_touches(tmp_path):
    from sage.gateway import being_gate_client as g
    _write(tmp_path)
    declared = set(g.skill_paths({"name": "probe-skill", "retire": "true"}, {"memory_root": str(tmp_path)}))
    before = {str(p.resolve()) for p in tmp_path.rglob("*")}
    assert sk.skill(tmp_path, {"name": "probe-skill", "retire": "true"})[0]
    after = {str(p.resolve()) for p in tmp_path.rglob("*")}
    gone = before - after
    assert gone and gone <= declared, gone - declared
    assert str((tmp_path / sk.SKILLS_LOG).resolve()) in declared


def test_reflection_names_skill_and_offers_it():
    from sage.gateway import heartbeat as hb
    assert "skill" in hb.REFLECT_TOOLS
    assert "keep the steps instead with skill" in hb.reflect_prompt(date="d", say_line="", say_first="")
