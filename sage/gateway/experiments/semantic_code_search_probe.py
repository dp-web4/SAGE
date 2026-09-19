"""Can membot's pieces make SAGE's own files semantically searchable? Measured, not argued.

Reuses membot's chunker and the ollama embedding backend its SERVER already uses
(MEMBOT_EMBED_BACKEND=auto -> ollama, since torch is absent on this box).
"""
import json, sys, urllib.request, numpy as np, pathlib
sys.path.insert(0, "/home/dp/ai-workspace/membot")
from cartridge_builder import chunk_text

OLLAMA = "http://127.0.0.1:11434/api/embed"

def embed(texts, prefix):
    out = []
    for i in range(0, len(texts), 24):
        batch = [f"{prefix}: {t[:8000]}" for t in texts[i:i+24]]
        body = json.dumps({"model": "nomic-embed-text", "input": batch}).encode()
        req = urllib.request.Request(OLLAMA, data=body,
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=300) as r:
            out.extend(json.loads(r.read())["embeddings"])
    a = np.array(out, dtype=np.float32)
    return a / np.linalg.norm(a, axis=1, keepdims=True)

root = pathlib.Path("/home/dp/ai-workspace/SAGE/sage/gateway")
# .py is NOT in membot's supported set — that is gap #1. Read it anyway to measure the value.
files = sorted(p for p in root.rglob("*.py") if "test" not in p.name)
passages, meta = [], []
for p in files:
    for j, ch in enumerate(chunk_text(p.read_text(errors="replace"), chunk_size=180, overlap=40)):
        passages.append(ch); meta.append((str(p.relative_to(root)), j))
print(f"{len(files)} files -> {len(passages)} chunks")
E = embed(passages, "search_document")
print(f"embedded: {E.shape}")

QUERIES = [
    "where does the beat decide how much of my state to show me",
    "how do I end my own turn early",
    "what stops two identical tool calls repeating forever",
    "which code refuses a write outside my home directory",
]
for q in QUERIES:
    qv = embed([q], "search_query")[0]
    top = np.argsort(-(E @ qv))[:3]
    print(f"\nQ: {q}")
    for i in top:
        f, j = meta[i]
        print(f"   {(E[i] @ qv):.3f}  {f}  chunk {j}: {passages[i][:90].strip()!r}")
