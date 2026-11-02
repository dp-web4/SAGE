"""One name per sibling, the same before and after a hub rename (dp, 2026-10-01: "on hub the beings are
'sprout-SAGE' not 'sprout-being' ... or i could rename them in hub manually"). sprout-being's inbox drained
1,430 times with 0 deliveries: senders said sprout-being, the hub member is sprout-sage, and the mapping lived
in per-machine alias envs that nobody had for it."""
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway.hestia_dispatch import HestiaF1aDispatcher  # noqa: E402


def _roster(monkeypatch, names):
    d = tempfile.mkdtemp(prefix="hub-mesh-")
    with open(os.path.join(d, "members.json"), "w") as f:
        json.dump({"members": [{"name": n} for n in names]}, f)
    monkeypatch.setenv("HUB_MESH_STATE", d)


def _d(**kw):
    monkey_factory = lambda ep, pid: None  # noqa: E731  never connects in these tests
    return HestiaF1aDispatcher("sprout-being", tempfile.mkdtemp(prefix="pn-"), mcp_factory=monkey_factory, **kw)


TODAY = ["Sprout", "sprout-SAGE", "legion", "legion-sage", "cbp", "cbp-sage", "mcnugget", "dp", "Sovereign"]


def test_being_names_reach_the_sage_members_today(monkeypatch):
    _roster(monkeypatch, TODAY)
    d = _d()
    assert d.resolve_peer("sprout-being") == "sprout-SAGE", "the roster's own spelling"
    assert d.resolve_peer("legion-being") == "legion-sage" and d.resolve_peer("CBP-being") == "cbp-sage"
    assert d.resolve_peer("legion-being/hub") == "legion-sage/hub", "a routed address keeps its route"
    assert d.resolve_peer("legion") == "legion", "a seat name is left alone"


def test_after_a_rename_the_name_as_written_wins_and_a_stale_alias_never_does(monkeypatch):
    _roster(monkeypatch, ["Sprout", "sprout-being", "legion-being", "cbp-being", "dp"])
    d = _d(peer_aliases={"legion-being": "legion-sage"})
    assert d.resolve_peer("sprout-being") == "sprout-being"
    assert d.resolve_peer("legion-being") == "legion-being", "the alias target is gone from the roster"


def test_an_explicit_alias_still_wins_over_the_derived_name(monkeypatch):
    _roster(monkeypatch, TODAY + ["legion-two"])
    assert _d(peer_aliases={"legion-being": "legion-two"}).resolve_peer("legion-being") == "legion-two"


def test_an_unknown_name_is_refused_with_the_list_and_a_being_name_is_known(monkeypatch):
    _roster(monkeypatch, TODAY)
    d = _d()
    assert d._unknown_peer("sprout-being") is None and d._unknown_peer("legion-being") is None
    assert "sprout-being" in d.known_peers() and "legion-being" in d.known_peers()
    refused = d._unknown_peer("to")
    assert refused and "legion-being" in refused
    assert d.resolve_peer("mcnugget-being") == "mcnugget-being", "no mcnugget-sage member: nothing to derive"
    assert d._unknown_peer("mcnugget-being"), "and so it is refused, not sent nowhere"


def test_an_unreadable_roster_keeps_the_old_behavior(monkeypatch):
    monkeypatch.setenv("HUB_MESH_STATE", tempfile.mkdtemp(prefix="empty-"))
    d = _d(peer_aliases={"legion-being": "legion-sage"})
    assert d.resolve_peer("legion-being") == "legion-sage" and d.resolve_peer("sprout-being") == "sprout-being"
    assert d.known_peers() == set() and d._unknown_peer("anything") is None
