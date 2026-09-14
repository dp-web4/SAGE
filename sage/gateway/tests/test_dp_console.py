"""dp console: loopback is not browser authentication (GPT review of SAGE#81).

A page open in any browser on this machine can submit a form to 127.0.0.1. Every form the
console renders carries a per-process token, and a POST without it writes nothing."""
import importlib
import os
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))


def _console(tmp_path, monkeypatch):
    home = tmp_path / "being"
    home.mkdir()
    monkeypatch.setenv("SAGE_INSTANCE", str(home))
    monkeypatch.setenv("SAGE_BEING", "t-being")
    monkeypatch.setenv("SAGE_FORUM_DIR", str(tmp_path / "forum"))
    from sage.gateway import dp_console, conversations as conv, arousal
    dp_console = importlib.reload(dp_console)
    conv.create(home, "dp", title="dp", participants=["dp", "t-being"], writable_by=["dp", "t-being"])
    # never wake anything real from a test
    monkeypatch.setattr(arousal, "respond", lambda *a, **k: {"engage": False, "reason": "test"})
    from http.server import ThreadingHTTPServer
    srv = ThreadingHTTPServer(("127.0.0.1", 0), dp_console.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return dp_console, conv, home, srv


def _post(port, path, fields):
    data = urllib.parse.urlencode(fields).encode()
    r = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, method="POST")
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def test_a_post_without_the_form_token_writes_nothing(tmp_path, monkeypatch):
    dpc, conv, home, srv = _console(tmp_path, monkeypatch)
    port = srv.server_address[1]
    try:
        for fields in ({"to": "dp", "text": "forged by a web page"},
                       {"to": "dp", "text": "stale page", "csrf": "not-the-token"}):
            code, body = _post(port, "/say", fields)
            assert code == 403 and "form token" in body, (code, body)
        code, _ = _post(port, "/note", {"text": "forged note"})
        assert code == 403
        assert conv.count(home, "dp") == 0
        assert not (home / "notes" / "from-dp.md").exists()

        page = urllib.request.urlopen(f"http://127.0.0.1:{port}/c/dp", timeout=20).read().decode()
        assert f'name="csrf" value="{dpc.FORM_TOKEN}"' in page, "the rendered form must carry the token"
        code, body = _post(port, "/say", {"to": "dp", "text": "really me", "csrf": dpc.FORM_TOKEN})
        assert code == 200, body
        assert conv.recent(home, "dp", limit=1)[-1]["text"] == "really me"
    finally:
        srv.shutdown()
