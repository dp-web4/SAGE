"""The SAGE console must not say "no conversations" when it was refused the list.

dp, 2026-09-27: "i still don't see separate conversations in the sage console". Two causes, and
this file pins the one that was a bug. `/conversations` answers only over loopback (the daemon's
`loopback_reader`: nothing on that route authenticates a reader). `loadConversations()` never
checked `r.ok`, so from another device the 403's JSON -- which has no `conversations` field --
became an empty list: the panel said "No conversations on this machine yet." on a machine that
had them, then fell back to the RAW-MODEL chat history, dressing the weights up as the being.

(The other cause was real emptiness: McNugget's being had no conversations because nothing in
the fleet creates them -- the seat does, once. The empty-state text now says so.)

`loadConversations` is lifted out of dashboard.html and run under node against a stubbed fetch
and DOM, so what is pinned is behaviour, not a string.

Run: python3 sage/gateway/tests/test_console_refusal_is_not_absence.py   (or pytest)
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

HTML = (Path(__file__).resolve().parents[3] / "sage-rs/sage-daemon/src/dashboard.html").read_text()


def _function(name: str) -> str:
    start = HTML.index(f"async function {name}(")
    depth, i = 0, HTML.index("{", start)
    while True:
        c = HTML[i]
        depth += c == "{"
        depth -= c == "}"
        i += 1
        if depth == 0:
            return HTML[start:i]


def _run(response: dict) -> dict:
    """Run loadConversations against one stubbed /conversations answer; report what it did."""
    prog = """
let convs = [], convId = null, convRefused = false;
const loaded = [];
// A DOM stub with what the real page uses (#397 added classList, a disabled option, and an appended tip).
const classes = new Set(), tips = [];
const convNote = { textContent: '', classList: { add: c => classes.add(c), remove: c => classes.delete(c) },
                   appendChild(el) { tips.push(el.innerHTML || ''); } };
const convSelect = { innerHTML: 'x', value: null, options: [], labels: [],
                     appendChild(o) { if (o.disabled) this.labels.push(o.textContent); else this.options.push(o.value); } };
const document = { createElement() { return {}; } };
const location = { port: '8760', hostname: 'sprout' };
const escapeHtml = s => String(s);
const convWritable = c => (c.writable_by || []).includes('dp');
async function loadConversation(id) { loaded.push(id); }
const BASE = '';
const RESP = JSON.parse(process.argv[1]);
async function fetch() { return { ok: RESP.ok, status: RESP.status, json: async () => RESP.body }; }
""" + _function("loadConversations") + """
loadConversations().then(() => process.stdout.write(JSON.stringify({
  note: convNote.textContent, refused: convRefused, convId, options: convSelect.options, loaded,
  classes: [...classes], labels: convSelect.labels, tips })));
"""
    r = subprocess.run(["node", "-e", prog, json.dumps(response)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _skip_without_node():
    if shutil.which("node") is None:
        try:
            import pytest
            pytest.skip("no node on PATH")
        except ImportError:
            print("SKIPPED: no node on PATH")
            raise SystemExit(0)


def test_a_refused_list_is_reported_as_refused_not_as_empty():
    _skip_without_node()
    out = _run({"ok": False, "status": 403, "body": {
        "error": "/conversations is readable only over loopback; 10.0.0.7 is not this machine",
        "hint": "read from the machine the being runs on (the dashboard or dp console on 127.0.0.1)"}})
    assert "No conversations" not in out["note"], f"a refusal rendered as absence: {out['note']!r}"
    assert "readable only over loopback" in out["note"], "the daemon's own reason is shown"
    assert "read from the machine the being runs on" in out["note"], "and where to read instead"
    assert out["refused"] is True, "init must know, so it does not fall back to the raw-model chat"
    assert out["convId"] is None and out["loaded"] == []
    # #397: shown AS a refusal (dp over Tailscale saw only a blank dropdown), with the way in.
    assert "refused" in out["classes"] and out["labels"] == ["(not readable from this device)"]
    assert any("ssh -N -L 8760:127.0.0.1:8760" in t for t in out["tips"]), out["tips"]


def test_an_empty_list_says_whose_move_it_is():
    _skip_without_node()
    out = _run({"ok": True, "status": 200, "body": {"being": "mcnugget-being", "conversations": []}})
    assert out["refused"] is False
    assert "No conversations exist for mcnugget-being" in out["note"]
    assert "refused" not in out["classes"], "an answered list is not shown as refused"
    assert "The seat creates them" in out["note"], "empty is a provisioning gap; say who closes it"
    assert "raw model, not the being" in out["note"], "and what the box below talks to until then"


def test_a_populated_list_opens_the_writable_conversation():
    _skip_without_node()
    out = _run({"ok": True, "status": 200, "body": {"being": "mcnugget-being", "conversations": [
        {"id": "mcnugget-claude", "title": "mcnugget-claude and mcnugget-being",
         "writable_by": ["mcnugget-claude", "mcnugget-being"]},
        {"id": "dp", "title": "dp and mcnugget-being", "writable_by": ["dp", "mcnugget-being"]}]}})
    assert out["options"] == ["mcnugget-claude", "dp"], "both conversations are offered"
    assert out["convId"] == "dp" and out["loaded"] == ["dp"], "dp's own writable one is opened"
    assert out["refused"] is False


def test_init_falls_back_to_raw_history_only_when_truly_empty():
    """The raw-model history is a fallback for a machine that HAS no conversations. A refused
    list is not that, and showing the model's prompt history there would present the weights as
    the being -- the exact confusion the conversations rewrite existed to end."""
    assert "if (!convId && !convRefused) loadChatHistory();" in HTML
    assert re.search(r"^let convRefused = false;", HTML, re.M), "declared beside convs"


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
    raise SystemExit(1 if fails else 0)
