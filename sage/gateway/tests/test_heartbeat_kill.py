"""A SIGTERM mid-beat must unwind to the record, not vanish (04:30Z 2026-09-09)."""
import os
import signal
import subprocess
import sys
import time


def test_sigterm_becomes_beat_killed_inside_the_beat():
    prog = (
        "import time, sys\n"
        "from sage.gateway.heartbeat import install_kill_handler, BeatKilled\n"
        "install_kill_handler()\n"
        # 'ready' INSIDE the try: printed before it, a SIGTERM landing in the gap raised
        # BeatKilled outside the handler and the child exited 1 (flaky on sprout, 2026-09-26)
        "try:\n"
        "    print('ready', flush=True)\n"
        "    time.sleep(30)\n"
        "except BeatKilled as k:\n"
        "    print('record written after', k, flush=True)\n"
    )
    p = subprocess.Popen([sys.executable, "-c", prog], stdout=subprocess.PIPE, text=True,
                         cwd=os.getcwd())
    assert p.stdout.readline().strip() == "ready"
    p.send_signal(signal.SIGTERM)
    out = p.stdout.read()
    assert p.wait(timeout=10) == 0
    assert "record written after signal 15 (SIGTERM)" in out


def test_every_model_turn_in_the_beat_runs_under_the_kill_handler():
    """The handler only helps if the phases it interrupts are inside the `try` that catches it,
    and the record says the beat was killed. Structural, because a beat needs a model to run."""
    import ast
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "heartbeat.py").read_text()
    main = [n for n in ast.parse(src).body if getattr(n, "name", "") == "main"][0]
    tries = [n for n in ast.walk(main) if isinstance(n, ast.Try)
             and any(isinstance(h.type, ast.Name) and h.type.id == "BeatKilled" for h in n.handlers)]
    assert tries, "main() catches no BeatKilled"
    inside = {id(c) for t in tries for s in t.body for c in ast.walk(s)}
    turns = [c for c in ast.walk(main) if isinstance(c, ast.Call)
             and getattr(c.func, "id", "") == "run_ollama_tool_turn"]
    assert turns, "no model turns found; the check would be vacuous"
    outside = [c.lineno for c in turns if id(c) not in inside]
    assert not outside, f"model turn(s) outside the kill handler at lines {outside}"
    calls = {getattr(c.func, "id", "") for c in ast.walk(main) if isinstance(c, ast.Call)}
    assert "install_kill_handler" in calls, "main() never installs the handler"
    assert '"killed"' in src or "'killed'" in src, "the record never says it was killed"


def test_a_sigterm_during_a_model_call_is_not_turned_into_model_text():
    """Where a beat actually spends its time: blocked in OllamaIRP.get_chat_response, which ends
    in `except Exception` and returns the error AS TEXT. McNugget on #213, measured: with
    BeatKilled(Exception) the kill came back as '[OllamaIRP: Error: signal 15 (SIGTERM)]' after
    1.2 s and the beat carried on. The earlier test sleeps outside any `except Exception`, so it
    was green either way. This one signals INSIDE the model call.

    `_ollama_available = True` matters: left False, the call first runs _check_ollama, the
    kill lands there, outside the swallowing `try`, and the test passes for the wrong reason."""
    prog = (
        "import socket, sys, threading\n"
        "srv = socket.socket(); srv.bind(('127.0.0.1', 0)); srv.listen(1)\n"
        "port = srv.getsockname()[1]\n"
        "held = []\n"
        # the server says 'connected' only once it has READ the request, so the client is
        # certainly blocked waiting for a reply when the parent signals (was: sleep 1.0, a guess
        # that a slow seat could lose, and then the kill landed before the model call)
        # OllamaIRP's constructor probes /api/tags on this same server, so a bare accept would
        # report the PROBE (before the handler exists). Answer every probe; hold the chat.
        "def serve():\n"
        "    while True:\n"
        "        c, _ = srv.accept(); req = c.recv(65536)\n"
        "        if b'/api/tags' in req.split(b'\\r\\n', 1)[0]:\n"
        "            body = b'{\"models\": [{\"name\": \"m\"}]}'\n"
        "            c.sendall(b'HTTP/1.1 200 OK\\r\\nContent-Type: application/json\\r\\n'\n"
        "                      b'Content-Length: %d\\r\\nConnection: close\\r\\n\\r\\n' % len(body) + body)\n"
        "            c.close(); continue\n"
        "        held.append(c); print('connected', flush=True)\n"
        "threading.Thread(target=serve, daemon=True).start()\n"
        "from sage.irp.plugins.ollama_irp import OllamaIRP\n"
        "from sage.gateway.heartbeat import install_kill_handler, BeatKilled\n"
        "llm = OllamaIRP({'model_name': 'm', 'ollama_host': f'http://127.0.0.1:{port}',\n"
        "                 'timeout_seconds': 60})\n"
        "llm._ollama_available = True\n"
        "install_kill_handler()\n"
        "try:\n"
        "    print('ready', flush=True)\n"
        "    r = llm.get_chat_response([{'role': 'user', 'content': 'hi'}])\n"
        "    print('SWALLOWED', repr((r or {}).get('content'))[:120], flush=True)\n"
        "except BeatKilled as k:\n"
        "    print('PROPAGATED', k, flush=True)\n"
    )
    p = subprocess.Popen([sys.executable, "-c", prog], stdout=subprocess.PIPE, text=True,
                         cwd=os.getcwd())
    # OllamaIRP prints its adapter banner first; wait until the SERVER has the request
    while (line := p.stdout.readline()) and line.strip() != "connected":
        pass
    assert line.strip() == "connected", "the request never reached the server"
    p.send_signal(signal.SIGTERM)
    out = p.stdout.read()
    p.wait(timeout=20)
    assert "PROPAGATED signal 15 (SIGTERM)" in out, out
