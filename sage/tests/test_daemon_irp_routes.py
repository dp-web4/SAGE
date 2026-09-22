#!/usr/bin/env python3
"""DaemonIRP talks to the daemon's SYNCHRONOUS model route, and to no other.

sage-rs 77bcb395b (2026-09-13) split the daemon's chat surface: `/chat/raw` is the synchronous
model route this client needs; `/chat` became the operator's conversation WITH the being -- it
appends the message to the `dp` conversation as dp, rouses a beat, and returns a receipt with no
`response`. This client kept posting to `/chat`, and both outcomes were silent:

  no `dp` conversation -> 503, recorded as SAGE's reply. McNugget sessions 491-496: six sessions,
                          twelve turns each, of "[Daemon unreachable: HTTP Error 503 ...]".
  a `dp` conversation  -> the tutor's prompts written into dp's conversation UNDER DP'S NAME, the
                          being roused by each, and '' recorded as every reply.

The second is why the fallback is pinned as narrowly as it is: `/chat` may be tried ONLY when
`/chat/raw` answers 404 (a daemon older than the split, whose `/chat` is still synchronous).
Falling back on a 503 or a 500 would write into a person's conversation because a model was busy.

stdlib unittest + a loopback stub; runs with bare python3.
"""

import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent


def _load(rel: str):
    """Load ONE file, not its package. `sage.irp` imports torch at package level, and on a Mac
    with two OpenMP runtimes that aborts the interpreter -- a client that is pure stdlib must be
    testable on a seat where the vision stack is not."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(Path(rel).stem, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


DaemonIRP = _load('sage/irp/plugins/daemon_irp.py').DaemonIRP


class _Stub:
    """A daemon that answers each route with a scripted (status, body) and records every hit."""

    def __init__(self, routes):
        self.routes, self.hits = routes, []
        stub = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, status, body):
                raw = json.dumps(body).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                self._send(200, {'status': 'ok'})

            def do_POST(self):
                n = int(self.headers.get('Content-Length') or 0)
                stub.hits.append((self.path, json.loads(self.rfile.read(n) or b'{}')))
                self._send(*stub.routes.get(self.path, (404, {'error': 'no such route'})))

        self.server = HTTPServer(('127.0.0.1', 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def port(self):
        return self.server.server_address[1]

    def close(self):
        self.server.shutdown()
        self.server.server_close()


RECEIPT = {'to': 'x-being', 'conversation': 'dp', 'turn': 7, 'note': 'the being answers on its own rhythm'}


class DaemonIRPRouteTests(unittest.TestCase):

    def _ask(self, routes):
        stub = _Stub(routes)
        self.addCleanup(stub.close)
        irp = DaemonIRP({'daemon_host': '127.0.0.1', 'daemon_port': stub.port, 'max_wait_seconds': 5})
        state = irp.step(irp.init_state({'prompt': 'Hello SAGE.'}))
        return state['current_response'], [p for p, _ in stub.hits]

    def test_a_current_daemon_is_asked_on_chat_raw_and_chat_is_never_touched(self):
        reply, hits = self._ask({'/chat/raw': (200, {'response': 'Yes, I am here.'}), '/chat': (200, RECEIPT)})
        self.assertEqual(reply, 'Yes, I am here.')
        self.assertEqual(hits, ['/chat/raw'], "the operator's conversation must not be written to")

    def test_a_daemon_older_than_the_split_still_works(self):
        reply, hits = self._ask({'/chat': (200, {'response': 'old daemon, same answer'})})
        self.assertEqual((reply, hits), ('old daemon, same answer', ['/chat/raw', '/chat']))

    def test_only_a_404_falls_back(self):
        """A busy or broken model route must NOT turn into a write to dp's conversation."""
        for status in (500, 502, 503, 429):
            with self.subTest(status=status):
                reply, hits = self._ask({'/chat/raw': (status, {'error': 'busy'}), '/chat': (200, RECEIPT)})
                self.assertEqual(hits, ['/chat/raw'], f"fell back to /chat on a {status}")
                self.assertTrue(reply.startswith('[Daemon unreachable:'), reply)

    def test_a_receipt_is_never_recorded_as_an_empty_reply(self):
        reply, _ = self._ask({'/chat/raw': (200, RECEIPT)})
        self.assertTrue(reply.startswith("[Daemon error: no 'response' in reply"), repr(reply))
        # ...and the marker is one the raising summary filter already refuses to splice forward.
        prefixes = _load('sage/raising/prev_summary_filter.py')._ADAPTER_ERROR_PREFIXES
        self.assertTrue(any(reply.startswith(p) for p in prefixes))

    def test_an_empty_string_reply_is_still_a_reply(self):
        reply, _ = self._ask({'/chat/raw': (200, {'response': ''})})
        self.assertEqual(reply, '', "the model said nothing; that is the model's answer, not an error")

    def test_a_daemon_reported_error_is_surfaced(self):
        reply, _ = self._ask({'/chat/raw': (200, {'error': 'model not loaded'})})
        self.assertEqual(reply, '[Daemon error: model not loaded]')


if __name__ == '__main__':
    unittest.main()
