"""A REAL daemon turn through the REAL arousal policy (GPT review of SAGE#81).

The Rust daemon's /chat appends a turn and then runs `python3 -m sage.gateway.arousal ...`,
reading the decision as JSON. The direct decide()/respond() tests never exercised that
contract, and it was broken twice without a red test: the CLI entry point was deleted
(723c04d73) and every daemon turn reported "arousal policy unreadable". This test starts
the built daemon on a spare port against a throwaway root and being home, speaks one turn
over loopback, and checks the turn landed and arousal answered as a policy.

It also checks the other half of the review: conversation CONTENT is refused to a peer that
is not loopback, and so is a speaker.

Skipped (not passed) when no built daemon binary exists; CI has no Rust build. Build with
`cd sage-rs && cargo build --release -p sage-daemon`, or point SAGE_DAEMON_BIN at one.
SAGE_AROUSAL_DRY_RUN=1 keeps arousal from writing the live wake marker or starting a unit.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from sage.gateway import conversations as conv  # noqa: E402


def _daemon_bin():
    cands = [os.getenv("SAGE_DAEMON_BIN", "")]
    tgt = os.getenv("CARGO_TARGET_DIR", "")
    if tgt:
        cands.append(os.path.join(tgt, "release", "sage-daemon"))
    cands.append(str(REPO / "sage-rs" / "target" / "release" / "sage-daemon"))
    for c in cands:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _outbound_ip():
    """This machine's non-loopback address, or None. A UDP connect sends nothing."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()
    return None if ip.startswith("127.") else ip


def _req(url, body=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method="POST" if body is not None else "GET",
                               headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


@pytest.fixture(scope="module")
def daemon():
    binary = _daemon_bin()
    if not binary:
        pytest.skip("no built sage-daemon binary (cargo build --release -p sage-daemon)")
    root = Path(tempfile.mkdtemp(prefix="sage-root-"))
    (root / "sage" / "federation").mkdir(parents=True)
    (root / "sage" / "instances").mkdir(parents=True)
    # an empty fleet: the test must not poll real peers
    (root / "sage" / "federation" / "fleet.json").write_text(json.dumps({"machines": {}}))
    being = root / "being"
    being.mkdir()
    conv.create(being, "dp", title="dp and e2e-being", participants=["dp", "e2e-being"],
                writable_by=["dp", "e2e-being"])
    port = _free_port()
    env = dict(os.environ)
    env.update({
        "SAGE_ROOT": str(root), "SAGE_PORT": str(port), "SAGE_MACHINE": "e2e",
        "SAGE_MODEL": "none", "SAGE_BEING": "e2e-being", "SAGE_BEING_INSTANCE": str(being),
        "SAGE_NO_BROWSER": "1", "SAGE_AROUSAL_DRY_RUN": "1", "PYTHONPATH": str(REPO),
    })
    proc = subprocess.Popen([binary], env=env, cwd=str(root),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            if _req(base + "/health", timeout=2)[0] == 200:
                break
        except OSError:
            time.sleep(0.3)
    else:
        proc.kill()
        pytest.fail("daemon did not come up on its SAGE_PORT")
    yield {"base": base, "port": port, "being": being}
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    shutil.rmtree(root, ignore_errors=True)


def test_a_chat_turn_lands_and_arousal_answers_as_a_policy(daemon):
    code, body = _req(daemon["base"] + "/chat", {"message": "hello from the e2e test"})
    assert code == 200, body
    assert body["conversation"] == "dp" and body["to"] == "e2e-being"
    turns = conv.recent(daemon["being"], "dp", limit=5)
    assert turns and turns[-1]["text"] == "hello from the e2e test"
    assert turns[-1].get("via") == "daemon-loopback"
    ar = body["arousal"]
    assert "unreadable" not in ar.get("reason", ""), f"daemon could not read the arousal CLI: {ar}"
    assert ar.get("kind") == "dp_turn" and "salience" in ar and "engage" in ar, ar
    assert ar.get("dry_run") is True, "the test must not start a real beat"


def test_conversation_content_is_served_over_loopback(daemon):
    code, body = _req(daemon["base"] + "/conversations")
    assert code == 200 and any(c.get("id") == "dp" for c in body["conversations"]), body
    code, body = _req(daemon["base"] + "/conversations/dp")
    assert code == 200 and body["total"] >= 1, body


def test_a_non_loopback_peer_can_neither_read_nor_speak(daemon):
    ip = _outbound_ip()
    if not ip:
        pytest.skip("no non-loopback address on this machine to connect from")
    base = f"http://{ip}:{daemon['port']}"
    for path in ("/conversations", "/conversations/dp"):
        code, body = _req(base + path)
        assert code == 403 and "loopback" in body.get("error", ""), (path, code, body)
    code, body = _req(base + "/chat", {"message": "from the network"})
    assert code == 403, body
    assert all(t["text"] != "from the network" for t in conv.recent(daemon["being"], "dp", limit=50))


def test_both_writers_hold_one_sequence_through_a_rollback(daemon):
    """GPT's exact falsifier from the review of SAGE#126 — run against the REAL Rust writer.

    There are two canonical writers of a conversation log: the Python heartbeat (`say`) and the
    Rust daemon (a turn typed in the dashboard). The first high-water repair lived only in
    Python and counted lines, so after Python resumed past a gap at seq 6 in a two-line file,
    a daemon turn would have been written as seq 3: "numbering never goes backwards" was false
    on one of the two writers. And its witness sat in the tracked meta, inside the rollback.

      1. turns 1..5 through BOTH paths      4. Rust   -> 7, same scar
      2. roll the log back to turn 1        5. Python -> 8, same scar
      3. Python -> 6, one truncation scar   6. roll back EVERY tracked artifact; still detected
    """
    being, base = daemon["being"], daemon["base"]
    conv.create(being, "hw", title="high water", participants=["dp", "e2e-being"],
                writable_by=["dp", "e2e-being"])
    say = lambda text: _req(base + "/conversations/hw/say", {"message": text, "from": "dp"})[1]["turn"]["seq"]
    py = lambda text: conv.append(being, "hw", speaker="e2e-being", text=text)["seq"]

    assert [py("1"), say("2"), py("3"), say("4"), py("5")] == [1, 2, 3, 4, 5]                 # 1
    log, meta = being / "conversations" / "hw.jsonl", being / "conversations" / "hw.meta.json"
    snapshot_log, snapshot_meta = log.read_text().splitlines()[0] + "\n", meta.read_text()
    wp = conv.witness_path(being, "hw")
    assert json.loads(wp.read_text())["high_water_seq"] == 5, "the Rust turns advanced the witness too"

    log.write_text(snapshot_log)                                                              # 2
    assert py("after rollback") == 6                                                          # 3
    scar = json.loads(wp.read_text())["truncations"]      # compared as VALUES: the Rust writer
    assert len(scar) == 1                                 # re-serialises with sorted keys
    assert say("rust after the gap") == 7                                                     # 4
    assert py("python again") == 8                                                            # 5
    assert json.loads(wp.read_text())["truncations"] == scar, "one event, one scar, both writers"

    log.write_text(snapshot_log); meta.write_text(snapshot_meta)                              # 6
    assert say("rust, after every tracked file rolled back together") == 9
    w = json.loads(wp.read_text())
    assert len(w["truncations"]) == 2 and w["truncations"][1]["high_water"] == 8, \
        "the witness is outside Git's rewrite domain, so a joint rollback is still seen"
