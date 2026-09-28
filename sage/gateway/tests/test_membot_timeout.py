"""Membot gets its own timeout (Sprout 2026-09-27: p90 2.9 s, max 3.9 s, 4 timeouts/day at hestia's 4 s)."""
import http.server
import os
import sys
import threading
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import hestia_witness as hw  # noqa: E402
from sage.gateway import hestia_dispatch as hd  # noqa: E402


def test_hestia_clients_keep_four_seconds_and_membot_gets_its_own():
    assert hw._Mcp("http://x", "p").timeout == hw._TIMEOUT == 4.0
    assert hd.HestiaF1aDispatcher.MEMBOT_TIMEOUT_S >= 10


def test_the_membot_session_uses_it(monkeypatch):
    made = []

    class Fake:
        timeout = 4.0
        def __init__(self, *a): made.append(self)
        def init(self): pass
        def call(self, name, args): return {"result": {"content": [{"type": "text", "text": "Mounted"}]}}

    d = hd.HestiaF1aDispatcher.__new__(hd.HestiaF1aDispatcher)
    d._mcp_factory, d.membot_endpoint, d.plugin_id, d.membot_cartridge = Fake, "http://x", "p", "c"
    d._mb = None
    try:
        d._membot()
    except Exception:
        pass            # whatever the mount check decides, the session was built first
    assert made and made[0].timeout == hd.HestiaF1aDispatcher.MEMBOT_TIMEOUT_S


def test_a_slow_answer_inside_the_new_limit_is_not_a_timeout():
    """A real HTTP server that answers in 4.5 s: past hestia's limit, inside membot's."""
    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            time.sleep(4.5)
            body = b'{"jsonrpc":"2.0","id":1,"result":{"ok":true}}'
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        def log_message(self, *a): pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    c = hw._Mcp(url, "p")
    c.timeout = hd.HestiaF1aDispatcher.MEMBOT_TIMEOUT_S
    assert c._req({"jsonrpc": "2.0", "id": 1, "method": "x"}) is not None
    srv.shutdown()
