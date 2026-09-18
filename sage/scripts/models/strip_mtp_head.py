#!/usr/bin/env python3
"""Strip the trailing multi-token-prediction (nextn) head from a Qwen3.5-architecture GGUF.

Ollama 0.20.x through 0.24.x (ollama/ollama#16282) iterate every block in `<arch>.block_count`
through the attention path, so a GGUF that keeps the MTP head as its last block fails with
"qwen3next: layer N missing attn_qkv/attn_gate projections". The head is only used for
speculative decoding; dropping it changes nothing about normal inference.

Usage: python3 strip_mtp_head.py <in.gguf> <out.gguf>   (needs `pip install gguf` in a venv)
"""
import sys
from gguf import GGUFReader, GGUFWriter, GGUFValueType
src, dst = sys.argv[1], sys.argv[2]
r = GGUFReader(src)
def scalar(f): return f.parts[f.data[0]].tolist()[0]
arch = bytes(r.fields["general.architecture"].parts[r.fields["general.architecture"].data[0]]).decode()
nblk_key = f"{arch}.block_count"; nextn_key = f"{arch}.nextn_predict_layers"
nblk = int(scalar(r.fields[nblk_key])); nextn = int(scalar(r.fields[nextn_key])) if nextn_key in r.fields else 0
keep = nblk - nextn
print(f"arch={arch} block_count={nblk} nextn={nextn} -> keeping {keep} blocks")
w = GGUFWriter(dst, arch)
skip = {"GGUF.version","GGUF.tensor_count","GGUF.kv_count","general.architecture", nextn_key}
adders = {GGUFValueType.UINT8:"add_uint8",GGUFValueType.INT8:"add_int8",GGUFValueType.UINT16:"add_uint16",GGUFValueType.INT16:"add_int16",
          GGUFValueType.UINT32:"add_uint32",GGUFValueType.INT32:"add_int32",GGUFValueType.FLOAT32:"add_float32",GGUFValueType.BOOL:"add_bool",
          GGUFValueType.UINT64:"add_uint64",GGUFValueType.INT64:"add_int64",GGUFValueType.FLOAT64:"add_float64"}
for f in r.fields.values():
    if f.name in skip: continue
    if f.name == nblk_key: w.add_uint32(nblk_key, keep); continue
    ts = f.types
    if not ts: continue
    if ts[0] == GGUFValueType.ARRAY:
        if ts[1] == GGUFValueType.STRING:
            w.add_array(f.name, [bytes(f.parts[i]).decode("utf-8") for i in f.data])
        else:
            w.add_array(f.name, [f.parts[i].tolist()[0] for i in f.data])
    elif ts[0] == GGUFValueType.STRING:
        w.add_string(f.name, bytes(f.parts[f.data[0]]).decode("utf-8"))
    else:
        getattr(w, adders[ts[0]])(f.name, scalar(f))
dropped = 0
for t in r.tensors:
    if t.name.startswith("blk.") and int(t.name.split(".")[1]) >= keep:
        dropped += 1; continue
    w.add_tensor(t.name, t.data, raw_dtype=t.tensor_type)
print(f"dropped {dropped} tensors")
w.write_header_to_file(); w.write_kv_data_to_file(); w.write_tensors_to_file(progress=False); w.close()
print("wrote", dst)
