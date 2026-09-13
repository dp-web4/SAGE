# Model recipes

Ollama models the fleet builds locally rather than pulls from the library.

## qwen3.8-distill:4b (CBP, 2026-09-12)

empero-ai/Qwen3.8-4B-Distill: Qwen3.5-4B architecture (hybrid Gated DeltaNet, small KV
cache), distilled from Qwen3.8 2.4T-A95B, Apache-2.0, reasoning model with native function
calling per the Qwen3.5 spec. The 2B sibling is Sprout's frontal lobe since 2026-08-28.

The Hugging Face GGUF keeps Qwen3.5's multi-token-prediction head as a 33rd block
(`qwen35.nextn_predict_layers = 1`). Ollama 0.20.7 (CBP) refuses to load it:
`qwen3next: layer 32 missing attn_qkv/attn_gate projections`. Sprout's 0.30.8 loads the
2B file, so the defect is version-local. A raw `hf.co/...` pull also reports capabilities
`[completion]` only, because the HF import carries no `RENDERER`/`PARSER`; the library
qwen3.5 models have `RENDERER qwen3.5` / `PARSER qwen3.5`, which is what turns on native
`tools` and `thinking` in `/api/show`.

Recipe:

    ollama pull hf.co/empero-ai/Qwen3.8-4B-Distill-GGUF:Q6_K
    BLOB=$(python3 -c "import json;m=json.load(open('/usr/share/ollama/.ollama/models/manifests/hf.co/empero-ai/Qwen3.8-4B-Distill-GGUF/Q6_K'));print([l['digest'] for l in m['layers'] if l['mediaType'].endswith('image.model')][0].replace(':','-'))")
    python3 -m venv /tmp/gguf-venv && /tmp/gguf-venv/bin/pip install gguf
    /tmp/gguf-venv/bin/python sage/scripts/models/strip_mtp_head.py \
        /usr/share/ollama/.ollama/models/blobs/$BLOB /tmp/Qwen3.8-4B-Distill-Q6_K-nomtp.gguf
    sed "s|^FROM .*|FROM /tmp/Qwen3.8-4B-Distill-Q6_K-nomtp.gguf|" sage/scripts/models/qwen3.8-distill-4b.Modelfile > /tmp/Modelfile
    ollama create qwen3.8-distill:4b -f /tmp/Modelfile
    curl -s localhost:11434/api/show -d '{"model":"qwen3.8-distill:4b"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['capabilities'])"
    # -> ['completion', 'tools', 'thinking']

Measured on CBP (RTX 2060 SUPER 8GB, Windows host holding about 2.1GB of it, Ollama
0.20.7), `/api/chat` with `tools` and `think: true`, native tool call returned on turn 1
and prose on turn 2 after the tool result:

| model | num_ctx | working set | placement | gen tok/s |
|---|---|---|---|---|
| qwen3.8-distill:4b (Q6_K, stripped) | 16384 | 6.0 GB | 100% GPU, or 17% CPU when the host holds more | 40 |
| qwen3.5:4b (library, Q4_K_M, vision tower) | 16384 | 6.8 GB | 27% CPU | 22 |
| qwen3.5:4b | 8192 | 6.4 GB | 29% CPU | 19 |
| gemma4:e4b | 16384 | 10 GB | 66% CPU | 35 |
| gemma4:e2b | 16384 | 7.9 GB | 73% CPU | 52 |

The stock qwen3.5:4b never fits here because its vision tower rides along; the text-only
distill at a higher quant is both smaller and faster.
