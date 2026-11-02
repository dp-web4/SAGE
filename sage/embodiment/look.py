"""A frame on demand, from the cortex: how a being with CSI eyes sees (dp 2026-10-12: "with vision, the
goal is to have it understand directly what it's looking at").

Why not the `camera` act's ffmpeg: on Sprout the IMX219 sensors give only raw 10-bit Bayer (`RG10`) through
v4l2, the board's ffmpeg has no v4l2 input at all, and the cortex holds the sensors through Argus, which is
the only path here that yields a debayered image. So the frame comes from the organ that already has it.

Two halves, one file:
  * CLIENT (standard library only), `python3 -m sage.embodiment.look <out.jpg>`: what the seat runs for a
    `camera` act on a seat that declares `camera_source: "cortex"`. It leaves ITS OWN request file, waits
    for ITS OWN result file, and publishes the JPEG at <out.jpg> by temp + rename, so the path is
    old-or-new, never half-written. Exit 0 and a JSON line on success; 3 = no cortex answered; 4 = the
    cortex answered no (eyes closed, no frame yet), with the reason on stderr.
  * RESPONDER, `respond(frames, sids, gaze)`: called by the cortex on every loop. It answers pending
    requests from the frame it already holds -- no extra capture, no stream.

ONE FILE PER REQUEST (GPT's hold on #425). The first cut used one shared request file and one shared
result file: a second client overwrote the first's request, the first's timeout then deleted the second's,
and nothing stopped two responders answering one request. Now:
  * requests live at look/requests/<id>.json and results at look/results/<id>.json; a client creates,
    reads and removes ONLY files named by its own id;
  * the responder CLAIMS a request by renaming it (atomic on one filesystem); a request that is already
    gone was claimed by someone else and is skipped, so each request is answered at most once;
  * cleanup is bounded by age: an unclaimed request older than STALE_S is dropped unanswered (its asker
    has given up), results and frames older than RESULT_TTL_S are removed, and at most MAX_PER_CALL
    requests are answered per loop.

The being still decides when to look (dp 2026-09-13: the camera is "something the being should have direct
control over"): nothing here runs without its act, and closed eyes are respected, not overridden.
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from typing import List, Optional

BODY_DIR = os.environ.get("SAGE_BODY_DIR") or os.path.expanduser("~/.sprout")
LOOK_DIR = "look"
WIDTH = 1024            # ~600 prompt tokens on Qwen-VL class models (heartbeat.py measured 1024 at 591)
QUALITY = 85
WAIT_S = 8.0            # the cortex polls at POLL_HZ; an answer normally lands within ~0.2 s
STALE_S = 30.0          # an unclaimed request older than this is dropped (its asker has gone)
RESULT_TTL_S = 120.0    # results and frames older than this are removed
MAX_PER_CALL = 4        # requests answered per cortex loop
SIDES = {0: "left", 1: "right"}


def _dirs(body: str):
    root = os.path.join(body, LOOK_DIR)
    req, res, frm = (os.path.join(root, d) for d in ("requests", "results", "frames"))
    for d in (req, res, frm):
        os.makedirs(d, exist_ok=True)
    return req, res, frm


def _atomic_write(path: str, data: bytes) -> None:
    tmp = f"{path}.tmp-{os.getpid()}-{uuid.uuid4().hex[:6]}"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


# ---- the cortex's half -------------------------------------------------------------------------

def _answer(rid: str, frames: List, sids: List[int], gaze: str, frm_dir: str, now: float) -> dict:
    res = {"id": rid, "ts": round(now, 2)}
    if gaze == "closed":
        return dict(res, ok=False, why="your eyes are closed (gaze closed); open them to look")
    i = next((k for k, f in enumerate(frames) if f is not None), None)
    if i is None:
        return dict(res, ok=False, why="no eye has delivered a frame yet")
    import cv2
    f = frames[i]
    h, w = f.shape[:2]
    if w > WIDTH:
        f = cv2.resize(f, (WIDTH, int(h * WIDTH / w)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, QUALITY])
    if not ok:
        return dict(res, ok=False, why="the frame could not be encoded")
    path = os.path.join(frm_dir, f"{rid}.jpg")
    _atomic_write(path, buf.tobytes())
    return dict(res, ok=True, path=path, eye=SIDES.get(sids[i], str(sids[i])),
                width=int(f.shape[1]), height=int(f.shape[0]), bytes=len(buf))


def respond(frames: List, sids: List[int], gaze: str = "", body_dir: Optional[str] = None,
            now: Optional[float] = None) -> List[dict]:
    """Answer pending requests (oldest first, at most MAX_PER_CALL); return the results written."""
    req_dir, res_dir, frm_dir = _dirs(body_dir or BODY_DIR)
    now = time.time() if now is None else now
    pending = []
    for name in os.listdir(req_dir):
        if not name.endswith(".json"):
            continue
        p = os.path.join(req_dir, name)
        try:
            pending.append((os.path.getmtime(p), name))
        except OSError:
            continue                                   # claimed or withdrawn meanwhile
    out = []
    for _, name in sorted(pending):
        p = os.path.join(req_dir, name)
        claimed = f"{p}.claimed-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        try:
            os.rename(p, claimed)                      # THE CLAIM: exactly one responder wins
        except OSError:
            continue
        try:
            req = json.load(open(claimed))
        except Exception:
            req = {}
        _remove(claimed)
        rid = str(req.get("id") or "")
        if not rid or rid != name[:-5] or now - float(req.get("ts") or 0) > STALE_S:
            continue                                   # malformed, mislabelled, or its asker has gone
        res = _answer(rid, frames, sids, gaze, frm_dir, now)
        _atomic_write(os.path.join(res_dir, f"{rid}.json"), json.dumps(res).encode())
        out.append(res)
        if len(out) >= MAX_PER_CALL:
            break
    for d in (res_dir, frm_dir):                       # bounded by age, never by someone else's id
        for name in os.listdir(d):
            p = os.path.join(d, name)
            try:
                if now - os.path.getmtime(p) > RESULT_TTL_S:
                    _remove(p)
            except OSError:
                continue
    return out


# ---- the seat's half (what the `camera` act runs) ---------------------------------------------

def request(out_path: str, body_dir: Optional[str] = None, wait_s: float = WAIT_S) -> int:
    req_dir, res_dir, _ = _dirs(body_dir or BODY_DIR)
    rid = uuid.uuid4().hex
    mine_req, mine_res = os.path.join(req_dir, f"{rid}.json"), os.path.join(res_dir, f"{rid}.json")
    _atomic_write(mine_req, json.dumps({"id": rid, "ts": time.time()}).encode())
    end = time.time() + wait_s
    res = None
    while time.time() < end:
        try:
            res = json.load(open(mine_res))
            break
        except FileNotFoundError:
            pass
        except Exception:
            pass                                       # mid-write is impossible (rename), but never fatal
        time.sleep(0.05)
    if res is None:
        _remove(mine_req)                              # withdraw MY request only (if still unclaimed)
        print(f"no frame: the cortex did not answer within {wait_s:g} s (is it running?)", file=sys.stderr)
        return 3
    _remove(mine_res)
    if not res.get("ok"):
        print(f"no frame: {res.get('why')}", file=sys.stderr)
        return 4
    data = open(res["path"], "rb").read()
    _remove(res["path"])
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    _atomic_write(out_path, data)
    print(json.dumps({"eye": res.get("eye"), "width": res.get("width"), "height": res.get("height"),
                      "bytes": len(data), "at": res.get("ts")}))
    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: python3 -m sage.embodiment.look <out.jpg>", file=sys.stderr)
        return 2
    return request(argv[0])


if __name__ == "__main__":
    sys.exit(main())
