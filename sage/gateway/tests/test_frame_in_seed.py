"""RED->GREEN organ test: a frame reaches heartbeat's seed as an images list.

Pins heartbeat.compose at head 6ca455700 (branch legion/mission-artifact):
compose() returns the user turn's content as a plain str in both arms
(L614 posture-first, L619 act-first). The wire from that string to ollama is
already complete (#76 irp half, #77 loop half), so compose() is the only
str-only site left.

CORRECTED SHAPE (measured against live qwen38-heretic:q3km-vl by the seat,
2026-09-13): ollama REJECTS parts inside content — both {'type':'text'}+
{'type':'image','image':b64} and image_url shapes return HTTP 400. The accepted
shape is an `images` LIST on the message, beside content:

    {'role':'user', 'content': user_str, 'images':[b64]}

So the minimal organ: compose takes an optional frame (base64 str or None).
When present, the user turn GAINS a sibling key images=[frame] and its content
stays a plain str. When absent, the message must NOT grow an empty images key —
ollama reads [] as "an image was sent". Nothing else changes.

RED today because compose() takes no frame arg at all — the with-frame call
raises TypeError on current code (and the images-key assertion has nothing to
hold). GREEN after adding the optional frame param to compose().

The fixture payload is synthetic bytes prefixed with a marker so an altered or
truncated base64 string fails loudly rather than passing by accident.
"""

import base64

import pytest

from sage.gateway import heartbeat


_MARKER = b"FRAME-SEED-MARKER-"
_PAYLOAD = _MARKER + b"\x01\x02\x03" * 64  # ~195 bytes, image-ish size
B64_FRAME = base64.b64encode(_PAYLOAD).decode("ascii")


def _compose_kwargs():
    return dict(
        name="legion-being", machine="legion-gemma3-12b",
        member="legion-being", posture_text="posture", nothink="",
        header="# Heartbeat", state="state", recall="", inbox="", digest="",
    )


def test_frame_lands_as_images_list():
    # With a frame: content stays a plain str AND the message gains images=[b64].
    seed, second = heartbeat.compose(
        True, frame=B64_FRAME, **_compose_kwargs())
    user_msg = seed[1]
    assert isinstance(user_msg["content"], str), (
        f"with-frame content must stay a plain str, got "
        f"{type(user_msg['content']).__name__}")
    assert "images" in user_msg, (
        "frame present but no 'images' key on the user message")
    assert user_msg["images"] == [B64_FRAME], (
        f"'images' must be exactly [b64], got {user_msg['images']!r}")


def test_no_frame_grows_no_images_key():
    # The common path: no frame -> plain str content and NO images key at all.
    seed, second = heartbeat.compose(
        False, **_compose_kwargs())
    user_msg = seed[1]
    assert isinstance(user_msg["content"], str), (
        f"no-frame seed must stay a plain str, got "
        f"{type(user_msg['content']).__name__}")
    assert "images" not in user_msg, (
        "no-frame message must NOT grow an images key (ollama reads [] as sent)")
