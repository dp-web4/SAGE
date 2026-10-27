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
