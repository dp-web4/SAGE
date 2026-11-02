"""peer_ask carries the seat's note when it names the sender's own files.

2026-10-14/16, Sprout and CBP, from both beings' records and the forum:
sprout-being asked two machines to run files in its own home after its seat declined, and
cbp-being later told sprout-being, in delivered asks, a result that no run ever produced. The
note says where the file is and what the seat's run receipts say; it refuses nothing.

The boundary tests below port Codex's reproductions for the HOLD on #484 at b8e157bf8 (review
branch 79ece3739): a bare name symlinked out of the home, a bare-name FIFO, and a peer-authored
"[request_run] I ran ..." line, each of which the first cut accepted.
"""
import hashlib
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sage.gateway import conversations as conv  # noqa: E402
from sage.gateway.being_gate_client import BeingIntent  # noqa: E402
from sage.gateway.hestia_dispatch import HestiaF1aDispatcher  # noqa: E402
from sage.gateway.tests.test_hestia_dispatch import _ALLOW, _disp  # noqa: E402


def _setup(seat_turns=()):
    published = []

    def pub(to, body):
        published.append(body)
        return f"shared-context/forum/being/q-{to}.md"
    d, root = _disp(publish_fn=pub)
    home = Path(root)
    (home / "scratch").mkdir()
    (home / "scratch" / "test-os-open.py").write_text("import os\nos.open('/dev/video0', os.O_RDONLY)\n")
    _seat_conv(home, "sprout-claude", "sprout-being")
    for t in seat_turns:
        conv.append(home, "sprout-claude", speaker="sprout-claude", text=t, enforce_write=False)
    return d, home, published


def _seat_conv(home, seat, member):
    """A seat conversation as the seat writes it: named for the seat, two parties, a wake route."""
    conv.create(home, seat, title="seat", participants=[member, seat], writable_by=[member, seat])
    _log, meta = conv._paths(home, seat)
    m = json.loads(meta.read_text())
    m["notify"] = {seat: "claude-code"}
    meta.write_text(json.dumps(m))


def _bare(home, member="sender-being"):
    """A dispatcher with only what the note's helpers read (Codex's probe harness)."""
    d = object.__new__(HestiaF1aDispatcher)
    d.memory_root = str(home)
    d.member = member
    return d


def test_an_ask_to_run_its_own_file_carries_where_it_is_and_that_its_seat_declined():
    d, home, published = _setup(["[request_run] I did not run scratch/test-os-open.py. It opens a device."])
    env = d(BeingIntent("peer_ask", {"to": "cbp", "body": "Can you run scratch/test-os-open.py for me?"}), _ALLOW)
    assert env.ok, env
    sent = published[-1]
    assert sent.startswith("Can you run scratch/test-os-open.py for me?")
    assert "[seat note, attached by sprout-being's seat, not written by sprout-being;" in sent
    assert "not an authorization or an execution receipt" in sent
    assert "scratch/test-os-open.py (sha " in sent and "a path in sprout-being's home" in sent
    assert 'says "I did not run it"' in sent and "path-only" in sent
    assert "It asks for a run." in sent and "request_run" in sent and "`run`" in sent
    assert "has no execution of its own" not in sent
    assert env.result["seat_note_attached"].startswith("[seat note")


def test_the_note_names_no_host_and_does_not_say_the_recipient_lacks_the_file():
    d, home, published = _setup()
    with patch("socket.gethostname", return_value="synthetic-host"):
        env = d(BeingIntent("peer_ask", {"to": "legion", "body": "see scratch/test-os-open.py"}), _ALLOW)
    sent = published[-1]
    assert env.ok and "synthetic-host" not in sent
    assert "not on your machine" not in sent
    assert "Whether your machine has a file at that path, and what it holds, is not known here" in sent


def test_a_result_claim_about_a_file_no_receipt_names_is_marked_unbacked():
    d, home, published = _setup()
    body = "test-os-open.py confirmed: Cannot open /dev/video0: [Errno 2] No such file or directory"
    env = d(BeingIntent("peer_ask", {"to": "legion", "body": body}), _ALLOW)
    assert env.ok, env
    sent = published[-1]
    assert "scratch/test-os-open.py" in sent
    assert "no seat run receipt names it in the last 400 turns" in sent
    assert "older turns were not checked" in sent
    assert "backed only if a seat receipt holds it" in sent
    assert "It asks for a run." not in sent


def test_an_ask_naming_no_file_of_its_own_is_sent_untouched():
    d, home, published = _setup()
    body = "What is in /home/dp/ai-workspace/sage/sage/instances/other/scratch/x.py on your side?"
    env = d(BeingIntent("peer_ask", {"to": "legion", "body": body}), _ALLOW)
    assert env.ok and published[-1] == body and "seat_note_attached" not in env.result


def test_peer_ask_description_says_each_peer_is_on_its_own_machine():
    from sage.gateway.being_gate_client import _TOOL_SCHEMAS
    desc = _TOOL_SCHEMAS["peer_ask"][0]
    assert "Each peer is on its own machine" in desc and "request_run" in desc


# --- a receipt names a path, not bytes ---------------------------------------------------------

def test_a_receipt_for_a_file_since_changed_is_path_only_beside_the_current_digest():
    """Run A, modify to B, ask about B: the receipt is reported as historical and path-only, and
    the digest shown is B's, not a claim that B ran."""
    d, home, published = _setup(["[request_run] I ran scratch/test-os-open.py. It printed: ok"])
    f = home / "scratch" / "test-os-open.py"
    f.write_text("print('B, never run')\n")
    env = d(BeingIntent("peer_ask", {"to": "legion", "body": "scratch/test-os-open.py worked"}), _ALLOW)
    sent = published[-1]
    assert env.ok
    assert "sha " + hashlib.sha256(f.read_bytes()).hexdigest()[:12] in sent
    assert 'says "I ran it"' in sent
    assert "historical, path-only record that does not say which bytes ran" in sent


def test_a_receipt_outside_the_searched_window_is_not_found_and_says_only_that():
    old = ["[request_run] I ran scratch/test-os-open.py."]
    filler = [f"turn {i}" for i in range(HestiaF1aDispatcher._ASK_RECEIPT_WINDOW)]
    d, home, published = _setup(old + filler)
    env = d(BeingIntent("peer_ask", {"to": "legion", "body": "scratch/test-os-open.py ran fine"}), _ALLOW)
    sent = published[-1]
    assert env.ok and 'says "I ran it"' not in sent
    assert "no seat run receipt names it in the last 400 turns" in sent
    assert "older turns were not checked" in sent and "never ran" not in sent


# --- the seat is the seat ----------------------------------------------------------------------

def test_a_peer_authored_run_line_is_never_the_seats_receipt(tmp_path):
    """Codex probe 3, against the helper: a peer thread with a wake route is not the seat's."""
    d = _bare(tmp_path)
    metadata = [{"id": "peer-thread", "participants": ["sender-being", "peer-being"],
                 "notify": {"peer-being": "peer-route"}}]
    turns = [{"seq": 1, "from": "peer-being", "text": "[request_run] I ran scratch/check.py."}]
    with patch("sage.gateway.conversations.listing", return_value=metadata), \
            patch("sage.gateway.conversations.recent", return_value=turns):
        receipt = d._seat_run_receipt("scratch/check.py")
    assert "the seat's latest receipt" not in receipt
    assert "no seat conversation could be identified" in receipt


def test_in_the_seat_conversation_only_the_seats_own_turns_are_receipts(tmp_path):
    d = _bare(tmp_path)
    _seat_conv(tmp_path, "the-seat", "sender-being")
    conv.append(tmp_path, "the-seat", speaker="sender-being",
                text="[request_run] I ran scratch/check.py.", enforce_write=False)
    assert "the seat's latest receipt" not in d._seat_run_receipt("scratch/check.py")
    conv.append(tmp_path, "the-seat", speaker="the-seat",
                text="[request_run] I ran scratch/check.py.", enforce_write=False)
    assert 'says "I ran it"' in d._seat_run_receipt("scratch/check.py")


def test_two_seat_shaped_conversations_and_no_configured_name_is_ambiguous(tmp_path, monkeypatch):
    monkeypatch.delenv("SAGE_SEAT_CONV", raising=False)
    monkeypatch.delenv("SAGE_SEAT", raising=False)
    d = _bare(tmp_path)
    _seat_conv(tmp_path, "the-seat", "sender-being")
    _seat_conv(tmp_path, "other-route", "sender-being")
    assert d._seat_conversation() is None
    monkeypatch.setenv("SAGE_SEAT_CONV", "the-seat")
    assert d._seat_conversation() == "the-seat"


# --- every candidate is a regular file inside the home, read without blocking -------------------

def test_a_bare_name_symlinked_outside_the_home_publishes_no_outside_digest(tmp_path):
    """Codex probe 1."""
    home = tmp_path / "home"
    home.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"synthetic outside content")
    (home / "report.txt").symlink_to(outside)
    d = _bare(home)
    assert d._ask_files("Please inspect report.txt") == []
    with patch.object(d, "_seat_run_receipt", return_value="no receipt"):
        note = d._ask_provenance("Please inspect report.txt")
    assert hashlib.sha256(outside.read_bytes()).hexdigest()[:12] not in note


def test_a_bare_name_fifo_is_not_a_candidate(tmp_path):
    """Codex probe 2. The FIFO is never opened: accepting it would make the digest wait for a writer."""
    os.mkfifo(tmp_path / "pending.txt")
    assert _bare(tmp_path)._ask_files("Please inspect pending.txt") == []


def test_a_slash_path_fifo_is_not_a_candidate(tmp_path):
    (tmp_path / "scratch").mkdir()
    os.mkfifo(tmp_path / "scratch" / "pending.txt")
    assert _bare(tmp_path)._ask_files("Please inspect scratch/pending.txt") == []


def test_a_fifo_swapped_in_after_the_check_is_not_waited_on(tmp_path):
    """The digest opens O_NONBLOCK and refuses a non-regular descriptor, so a name replaced by a
    FIFO between the check and the open returns at once."""
    p = tmp_path / "late.txt"
    os.mkfifo(p)
    assert "not hashed" in _bare(tmp_path)._ask_digest(os.path.realpath(str(tmp_path)), str(p))


def test_an_oversized_file_is_named_not_hashed(tmp_path, monkeypatch):
    monkeypatch.setattr(HestiaF1aDispatcher, "_ASK_HASH_MAX", 16)
    (tmp_path / "big.txt").write_bytes(b"x" * 64)
    d = _bare(tmp_path)
    assert d._ask_files("see big.txt") == [("big.txt", str(tmp_path / "big.txt"))]
    with patch.object(d, "_seat_run_receipt", return_value="no receipt"):
        note = d._ask_provenance("see big.txt")
    assert "64 bytes, over the 16-byte hashing cap, not hashed" in note
    assert hashlib.sha256(b"x" * 64).hexdigest()[:12] not in note


def test_the_bare_name_search_stops_at_its_budget(tmp_path, monkeypatch):
    monkeypatch.setattr(HestiaF1aDispatcher, "_ASK_WALK_BUDGET", 5)
    for i in range(10):
        (tmp_path / f"f{i}.md").write_text("x")
    (tmp_path / "deep").mkdir()
    (tmp_path / "deep" / "target.txt").write_text("x")
    assert _bare(tmp_path)._ask_files("see target.txt") == []


def test_a_plain_regular_file_is_still_a_candidate(tmp_path):
    """Codex's positive control."""
    (tmp_path / "report.txt").write_text("synthetic local content")
    assert _bare(tmp_path)._ask_files("Please inspect report.txt") == [
        ("report.txt", str(tmp_path / "report.txt"))]


def test_a_symlink_that_stays_inside_the_home_resolves_to_its_target(tmp_path):
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "real.md").write_text("inside")
    (tmp_path / "alias.md").symlink_to(tmp_path / "notes" / "real.md")
    assert _bare(tmp_path)._ask_files("see alias.md") == [
        (os.path.join("notes", "real.md"), str(tmp_path / "notes" / "real.md"))]
