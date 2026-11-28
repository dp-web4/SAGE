#!/usr/bin/env python3
"""Serve Bonsai 2.5 Q2_0 with stock llama.cpp (>= b11556) at each context size and run probe.py against it.

Ollama 0.33.1 cannot load this file ("tensor output.weight size overflow"), so Bonsai is served by
llama-server on a private port. gemma4:12b is unloaded first (both do not fit in 16 GB) and is reloaded
with keep_alive -1 at the end, whatever happens.

Usage: run_bonsai.py <llama-server binary> <gguf> [ctx ...]   (default ctx: 16384 32768)
"""
import json, os, subprocess, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8091
LABEL = "ternary-bonsai-2.5-27b-q2_0"


def ollama(body, timeout=600):
    req = urllib.request.Request("http://127.0.0.1:11434/api/generate", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def healthy():
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


def main():
    server, gguf = sys.argv[1], sys.argv[2]
    ctxs = [int(c) for c in sys.argv[3:]] or [16384, 32768]
    log = open(os.path.join(HERE, "results", "llama-server.log"), "a")
    try:
        ollama({"model": "gemma4:12b", "prompt": "", "keep_alive": 0})
        for ctx in ctxs:
            log.write(f"\n===== ctx {ctx} {time.strftime('%FT%TZ', time.gmtime())}\n"); log.flush()
            t0 = time.time()
            p = subprocess.Popen([server, "-m", gguf, "--port", str(PORT), "--host", "127.0.0.1", "-c", str(ctx),
                                  "-np", "1", "-ngl", "99", "--jinja", "--no-webui",
                                  *os.environ.get("BONSAI_EXTRA", "").split()], stdout=log, stderr=log)
            try:
                while not healthy():
                    if p.poll() is not None:
                        print(f"llama-server exited rc={p.returncode} at ctx {ctx}; see results/llama-server.log")
                        break
                    if time.time() - t0 > 900:
                        print("llama-server not healthy after 900 s"); break
                    time.sleep(3)
                else:
                    print(f"ctx {ctx}: server healthy after {time.time() - t0:.0f} s, pid {p.pid}", flush=True)
                    label = LABEL + ("-tuned" if os.environ.get("BONSAI_EXTRA") else "")
                    subprocess.run([sys.executable, "-I", "-u", os.path.join(HERE, "probe.py"), "--llama-server",
                                    f"http://127.0.0.1:{PORT}", str(ctx), str(p.pid), label])
            finally:
                p.terminate()
                try:
                    p.wait(60)
                except subprocess.TimeoutExpired:
                    p.kill()
    finally:
        ollama({"model": "gemma4:12b", "prompt": "", "keep_alive": -1})
        print("gemma4:12b reloaded with keep_alive -1")


if __name__ == "__main__":
    main()
