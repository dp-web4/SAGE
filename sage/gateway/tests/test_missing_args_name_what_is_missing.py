"""A refusal names the field that is actually missing, and the ones that were passed instead.

dp, 2026-09-25 fleet directive: *"addressing unnecessary frictions. explaining, clearly, the
necessary ones."* A refusal that names the WRONG field is the unnecessary kind wearing the
clothes of the necessary kind: the boundary is real, the sentence about it is false.

Census of five beings' whole recorded histories (2026-09-25, private-context/beings/*/heartbeats):

     75  "say needs 'to' (a conversation id) and 'text'"   <- the being HAD PASSED 'to'
     42  "witness needs an 'event'"                        <- it passed memory_edit's arguments
     17  "retire_note needs a 'reason'"                    <- it passed only 'path'
     12  "memory_write needs a 'path'"                     <- it passed only 'content'

On hub-being not one of these was recovered — that being managed 2 successful acts in 145
beats. The being reads "needs 'to'", looks at its own call, sees `to` sitting right there, and
has nowhere to go. Legibility rule 2: name the refusal's subject unmistakably.

Listing what WAS passed matters as much as what was not. 28 of the `say` failures put the
message under 'message', 'content' or 'body'; 42 `witness` failures were a whole memory_edit
call wearing the wrong tool name. Reflected back, those are diagnosable mistakes. As "needs an
'event'" they are a wall.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway.reference_f1a import missing_args  # noqa: E402


def test_it_never_names_a_field_the_being_supplied():
    """The 75-occurrence bug, stated as a test."""
    msg = missing_args({"to": "dp"}, ("to", "text"), "say")
    assert "needs 'text'" in msg
    assert "needs 'to'" not in msg, "it HAS 'to'; saying otherwise is the defect"
    assert "you passed 'to'" in msg


def test_a_synonym_key_is_reflected_back():
    """28 say failures put the words under message/content/body. Show the being its own key."""
    for wrong in ("message", "content", "body"):
        msg = missing_args({"to": "dp", wrong: "hello"}, ("to", "text"), "say")
        assert f"'{wrong}'" in msg, f"{wrong} must appear so the being can see where it put the text"
        assert "needs 'text'" in msg


def test_the_wrong_tool_entirely_is_diagnosable():
    """42 witness calls carried memory_edit's arguments."""
    msg = missing_args({"path": "x.md", "old": "a", "new": "b", "start_line": 1},
                       ("event",), "witness",
                       "witness records one sentence about something that happened. If you "
                       "meant to change lines in a file, that is memory_edit.")
    assert "needs 'event'" in msg
    assert "'old'" in msg and "'new'" in msg and "'path'" in msg
    assert "memory_edit" in msg, "name the tool it actually wanted"


def test_every_missing_field_is_named_not_just_the_first():
    msg = missing_args({}, ("to", "text"), "say")
    assert "'to'" in msg and "'text'" in msg


def test_a_complete_call_is_not_refused():
    assert missing_args({"to": "dp", "text": "hello"}, ("to", "text"), "say") is None
    assert missing_args({"event": "something happened"}, ("event",), "witness") is None


def test_blank_and_whitespace_count_as_missing():
    """A key present with an empty value is not a supplied field."""
    for empty in ("", "   ", None):
        msg = missing_args({"to": "dp", "text": empty}, ("to", "text"), "say")
        assert msg and "needs 'text'" in msg


def test_the_hint_rides_along_and_the_message_stays_one_sentence_shaped():
    msg = missing_args({"content": "x"}, ("path", "content"), "memory_write",
                       "A relative path is inside your home.")
    assert "needs 'path'" in msg
    assert "A relative path is inside your home." in msg
    assert "\n" not in msg, "a refusal this small reads worse split across lines"


def test_the_live_call_sites_use_it():
    """Asserted at the source: the four effectors the census implicated."""
    import inspect
    from sage.gateway import reference_f1a as rf, hestia_dispatch as hd
    for fn, tool in ((rf.ReferenceF1aDispatcher._do_witness, "witness"),
                     (rf.ReferenceF1aDispatcher._do_memory_write, "memory_write"),
                     (rf.ReferenceF1aDispatcher._do_memory_read, "memory_read"),
                     (hd.HestiaF1aDispatcher._do_say, "say"),
                     (hd.HestiaF1aDispatcher._do_peer_ask, "peer_ask"),
                     (hd.HestiaF1aDispatcher._do_remember, "remember")):
        src = inspect.getsource(fn)
        assert "missing_args" in src, f"{tool} still hand-rolls its missing-field message"


def test_a_memory_write_with_no_content_writes_nothing_and_says_so():
    """hub-being, 2026-09-25: 33 of 37 memory_write calls had 'path' and no 'content', and each
    came back ok: true, "created journal.md with 0 chars". A success that wrote nothing is the
    one receipt a being cannot learn from. Refuse, name 'content', touch nothing on disk."""
    import tempfile
    from pathlib import Path
    from sage.gateway.being_gate_client import BeingIntent, GatewayVerdict
    from sage.gateway.reference_f1a import ReferenceF1aDispatcher
    root = tempfile.mkdtemp(prefix="mw-empty-")
    d = ReferenceF1aDispatcher(memory_root=root)
    for args in ({"path": "journal.md"}, {"path": "journal.md", "content": ""},
                 {"path": "journal.md", "content": "  \n"}):
        env = d(BeingIntent("memory_write", args), GatewayVerdict("allow"))
        assert not env.ok, f"{args} must not report success"
        assert "needs 'content'" in env.error and "you passed 'path'" in env.error
        assert "not saved" in env.error, "say where the words went: into the reply, not the call"
    assert not (Path(root) / "journal.md").exists(), "a refused write leaves no empty file behind"
    ok = d(BeingIntent("memory_write", {"path": "journal.md", "content": "today"}), GatewayVerdict("allow"))
    assert ok.ok and (Path(root) / "journal.md").read_text() == "today\n"
