"""memory_read of a binary file says what it is and never returns its bytes as text (sprout-being,
2026-10-26: reads of its own .jpg frames preceded its model emitting byte soup as thinking)."""
from sage.gateway.being_gate_client import BeingIntent
from sage.gateway.tests.test_being_self import _ALLOW, _disp

JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00" + bytes(range(256)) * 40


def test_an_image_is_described_not_dumped():
    d, root = _disp()
    (root / "scratch").mkdir()
    (root / "scratch" / "frame.jpg").write_bytes(JPEG)
    env = d(BeingIntent("memory_read", {"path": "scratch/frame.jpg"}), _ALLOW)
    assert env.ok and env.witness_id
    assert "a JPEG image" in env.result and f"{len(JPEG)} bytes" in env.result and "camera" in env.result
    assert "JFIF" not in env.result and "�" not in env.result and len(env.result) < 600


def test_find_on_an_image_is_not_run_over_its_bytes():
    d, root = _disp()
    (root / "frame.jpg").write_bytes(JPEG)
    env = d(BeingIntent("memory_read", {"path": "frame.jpg", "find": "JFIF"}), _ALLOW)
    assert env.ok and "a JPEG image" in env.result and "�" not in env.result


def test_other_binary_is_named_and_text_is_unchanged():
    d, root = _disp()
    (root / "blob.bin").write_bytes(b"abc\x00def" * 10)
    (root / "note.md").write_text("plain words\nsecond line\n")
    env = d(BeingIntent("memory_read", {"path": "blob.bin"}), _ALLOW)
    assert env.ok and "binary data" in env.result and "camera" not in env.result
    env = d(BeingIntent("memory_read", {"path": "note.md"}), _ALLOW)
    assert env.ok and "plain words" in env.result and "not text" not in env.result
