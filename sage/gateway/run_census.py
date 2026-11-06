"""
run_census — what the being's run box actually has, measured, and shown beside the plan that assumes
otherwise.

WHY (dp, 2026-11-05: "it's an affordance discovery issue ... how do we fix it in sage?"). On 11-04/05
cbp-being spent about five hours trying to get uv into its run box: a uv venv install, an official
installer, a FastAPI install, three `fix-dns` scripts and ten hestia scope requests on
/etc/resolv.conf. The seat declined each run with a reason, and the being agreed each time ("fix-dns
rewrites system config, correctly declined") and then filed a variant a few beats later. The
package it wanted, imageio, had been installed on the host at 02:15 and imported in its box all
along. The seat said so in conversation (cbp-claude seq 13618). That turn never won against its own
todo.md, which showed "install imageio in sandbox's virtual environment", "add uv binary path to
sandbox's PATH and install imageio" and "uv pip install imageio" every beat.

Two defects, one shape. The AFFORDANCES text says what the box LACKS ("no network") but never what it
HAS, so the being could only learn its box by asking, one beat and one seat turn per question. And a
todo item that presupposes an affordance is a standing prompt (the 10-30 service-notes finding: "a
line shown every beat, with nothing saying it is routine, is a standing prompt"); nothing measured
stood next to it, so a single chat turn lost to it every beat.

THE MOVE is the one `_own_running_claims` makes for "still running" sentences: measure, then quote
the being's own line next to the measurement. Discovery becomes reading. Nothing here edits the
being's records or closes its items; it closes them itself (interactive selection, not deletion).

  * census(): ONE run, in a box built the way `run` builds it (same binds, no network, no grants), of
    a probe that imports a list of modules, looks up tools on PATH, tries one DNS lookup, and checks
    for /etc/resolv.conf and whether /usr is writable. Cached in the instance as run_census.json and
    re-measured after MAX_AGE_S, or as soon as a site-packages directory is newer than the cache (an
    apt or pip install on the host touches it, so an affordance change shows the next beat).
  * render(): the census as a block for the NOW part of the window.
  * todo_notes(): open todo items that name a measured module or tool, or an install/DNS step, each
    quoted beside what was measured.
  * refusal_fold(): the seat's recent `[request_run] I did not run` turns that are about installing
    or host network config, counted, so an agreement in chat survives into the next beat as a fact.

Operator switch: being_params `run_census` (default off). Turned on for one instance first, as the
service-notes off switch was, so its effect can be measured: the share of a day's acts about
install/uv/DNS, before and after.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import sysconfig
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

CACHE = "run_census.json"
MAX_AGE_S = 24 * 3600
PROBE_TIMEOUT_S = 90

#: What the probe imports. Ordered roughly by how often a being reaches for it. The operator can
#: replace it with instance.json `run_census_modules: [...]`.
DEFAULT_MODULES = ("numpy", "scipy", "imageio", "PIL", "matplotlib", "pandas", "sklearn", "cv2",
                   "torch", "pytest", "yaml", "requests", "httpx", "fastapi", "uvicorn", "flask",
                   "sympy", "networkx")
TOOLS = ("uv", "pip", "pip3", "git", "curl", "wget", "gcc", "node", "ollama")
#: An import name whose distribution is called something else (for the version lookup).
_DIST = {"PIL": "pillow", "cv2": "opencv-python", "sklearn": "scikit-learn", "yaml": "PyYAML"}

PROBE = r'''
import json, os, shutil, socket, sys
from importlib import metadata
mods, tools, dist = json.loads(sys.argv[1]), json.loads(sys.argv[2]), json.loads(sys.argv[3])
out = {"python": sys.version.split()[0], "executable": sys.executable, "modules": {}, "tools": {}}
for m in mods:
    try:
        mod = __import__(m)
    except Exception as e:
        out["modules"][m] = None if isinstance(e, ImportError) else "import fails: " + type(e).__name__
        continue
    v = ""
    try:
        v = metadata.version(dist.get(m, m))
    except Exception:
        v = str(getattr(mod, "__version__", "") or "")
    out["modules"][m] = v or "present"
for t in tools:
    out["tools"][t] = shutil.which(t)
try:
    socket.getaddrinfo("pypi.org", 443)
    out["network"] = True
except Exception as e:
    out["network"] = False
    out["network_error"] = type(e).__name__
out["resolv_conf"] = os.path.exists("/etc/resolv.conf")
out["usr_writable"] = os.access("/usr/lib", os.W_OK)
print(json.dumps(out))
'''


def _interp() -> str:
    return os.path.dirname(os.path.dirname(sys.executable))


def site_dirs() -> List[str]:
    """The directories an install on the host writes into, for the freshness check."""
    out = []
    for k in ("purelib", "platlib"):
        p = sysconfig.get_paths().get(k)
        if p and p not in out:
            out.append(p)
    ver = f"python3.{sys.version_info.minor}"
    for p in ("/usr/lib/python3/dist-packages", f"/usr/local/lib/{ver}/dist-packages",
              f"/usr/lib/{ver}/dist-packages"):
        if p not in out:
            out.append(p)
    return [p for p in out if os.path.isdir(p)]


def _newest_site_mtime() -> float:
    m = 0.0
    for p in site_dirs():
        try:
            m = max(m, os.stat(p).st_mtime)
        except OSError:
            pass
    return m


def box_command(stage: str) -> List[str]:
    """The probe's box, built as being_gate_client.run_command builds `run`'s: the same system
    mounts and interpreter, no network, HOME=/tmp, and none of the being's grants (the census
    measures the box, not the being's reach)."""
    from sage.gateway import being_gate_client as bgc
    interp = _interp()
    return shlex.split(
        f"{bgc.SANDBOX} --clearenv"
        " --ro-bind /usr /usr --ro-bind /lib /lib --ro-bind-try /lib64 /lib64 --ro-bind /bin /bin"
        " --ro-bind /etc/alternatives /etc/alternatives"
        f" --ro-bind {shlex.quote(interp)} {shlex.quote(interp)}"
        " --proc /proc --dev /dev --tmpfs /tmp"
        f" --ro-bind {shlex.quote(stage)} /work"
        " --unshare-pid --unshare-net --unshare-ipc --unshare-uts"
        " --new-session --die-with-parent"
        " --setenv HOME /tmp --setenv PYTHONUTF8 1 --setenv PYTHONDONTWRITEBYTECODE 1"
        f" --setenv PATH {shlex.quote(interp)}/bin:/usr/bin:/bin"
        f" --chdir /work {shlex.quote(interp)}/bin/python3 -I /work/probe.py")


def measure(modules=DEFAULT_MODULES, tools=TOOLS, runner=subprocess.run) -> Dict:
    """Run the probe once in the box. Never raises: a failure is returned as {"error": ...}."""
    from sage.gateway import being_gate_client as bgc
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    try:
        if bgc.run_sandbox_kind() != "bwrap":
            return {"error": "no bwrap run box on this machine", "measured_at": stamp, "ts": time.time()}
        with tempfile.TemporaryDirectory(prefix="sage-census-") as stage:
            Path(stage, "probe.py").write_text(PROBE)
            cmd = box_command(stage) + [json.dumps(list(modules)), json.dumps(list(tools)),
                                        json.dumps(_DIST)]
            r = runner(cmd, capture_output=True, text=True, timeout=PROBE_TIMEOUT_S)
        line = (r.stdout or "").strip().splitlines()[-1:] or [""]
        data = json.loads(line[0])
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)[:200]}", "measured_at": stamp, "ts": time.time()}
    data["measured_at"] = stamp
    data["ts"] = time.time()
    return data


def census(instance: Path, modules=None, force: bool = False, measure_fn=None) -> Dict:
    """The cached census, re-measured when stale or when the host's site-packages changed."""
    p = Path(instance) / CACHE
    cached = None
    try:
        cached = json.loads(p.read_text())
    except Exception:
        cached = None
    mods = tuple(modules) if modules else DEFAULT_MODULES
    fresh = (cached and not cached.get("error")
             and time.time() - float(cached.get("ts", 0)) < MAX_AGE_S
             and float(cached.get("ts", 0)) >= _newest_site_mtime()
             and list(cached.get("modules", {}).keys()) == list(mods))
    if fresh and not force:
        return cached
    data = (measure_fn or measure)(mods)
    if data.get("error") and cached and not cached.get("error"):
        cached["stale_because"] = data["error"]     # keep the last good measurement, say why
        return cached
    try:
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=1))
        os.replace(tmp, p)
    except OSError:
        pass
    return data


def _has(c: Dict) -> Dict[str, str]:
    return {m: v for m, v in (c.get("modules") or {}).items() if v and not str(v).startswith("import fails")}


def render(c: Dict, fold: str = "") -> str:
    if not c or c.get("error"):
        return ""
    has = _has(c)
    lacks = [m for m, v in (c.get("modules") or {}).items() if m not in has]
    tools = c.get("tools") or {}
    on = [t for t, w in tools.items() if w]
    off = [t for t, w in tools.items() if not w]
    lines = [f"## Your run box, measured {c.get('measured_at', '')} (this is where `run` executes your code)",
             f"- Python {c.get('python', '?')} ({c.get('executable', '?')})"]
    if has:
        lines.append("- These import: " + ", ".join(f"{m} {v}" if v != "present" else m for m, v in has.items()))
    if lacks:
        lines.append("- These do not: " + ", ".join(lacks))
    if on or off:
        lines.append("- On PATH: " + (", ".join(on) or "none of the checked tools")
                     + (("; not on PATH: " + ", ".join(off)) if off else ""))
    if c.get("network"):
        lines.append("- Network: a lookup worked.")
    else:
        lines.append("- Network: none. A lookup fails there by design, so a DNS error inside the box says "
                     "nothing about the host."
                     + ("" if c.get("resolv_conf") else " /etc/resolv.conf is not in the box at all: the "
                        "box mounts no /etc, so it is not missing or broken."))
    if not c.get("network") and not c.get("usr_writable"):
        lines.append("- Installing inside the box cannot work: no network to fetch from, and /usr is "
                     "read-only there. A module above that imports needs no install.")
    if c.get("stale_because"):
        lines.append(f"- (Re-measuring failed: {c['stale_because']}. This is the last good measurement.)")
    if fold:
        lines.append(fold)
    lines.append("Where your todo, journal or settled notes disagree with this, this was measured; they "
                 "were written earlier.")
    return "\n".join(lines)


_INSTALL = re.compile(r"\b(install|pip|venv|virtual env|virtualenv)\w*", re.I)
_DNS = re.compile(r"\b(dns|resolv\.conf|resolv|nameserver)\b", re.I)
_NET = re.compile(r"\b(network|internet|download|fetch)\b", re.I)


def todo_notes(c: Dict, items: List, most: int = 6) -> List[str]:
    """Open todo items beside the census. `items` is [(text, since)] as heartbeat.todo_open gives."""
    if not c or c.get("error"):
        return []
    has = _has(c)
    mods = list((c.get("modules") or {}).keys())
    tools = c.get("tools") or {}
    found = []          # (rank, line): a named module or tool says the most, a generic install/DNS step least
    for text, _since in items:
        t = str(text)
        low = t.lower()
        said, rank = [], 3
        for m in mods:
            if re.search(rf"(?<![\w.-]){re.escape(m.lower())}(?![\w-])", low):
                rank = min(rank, 0)
                said.append(f"{m} imports in your box ({has[m]})" if m in has
                            else f"{m} does not import in your box")
        installing = bool(_INSTALL.search(t))
        for tool, where in tools.items():
            # a present tool beside an install step reads as "use this instead" (pip beside "uv pip
            # install"): say only what is absent there, since no tool can install without a network
            if where and installing and not c.get("network"):
                continue
            if re.search(rf"(?<![\w.-]){re.escape(tool)}(?![\w-])", low):
                rank = min(rank, 1)
                said.append(f"{tool} is {'on PATH at ' + where if where else 'not on PATH'} in your box")
        if _DNS.search(t) and not c.get("network"):
            rank = min(rank, 2)
            said.append("the box has no network by design, and no /etc at all; DNS there cannot be fixed")
        elif (_INSTALL.search(t) or _NET.search(t)) and not c.get("network"):
            rank = min(rank, 2)
            said.append("installing or downloading needs a network the box does not have")
        if said:
            found.append((rank, f"- \"{t[:160]}\": measured, " + "; ".join(dict.fromkeys(said)) + "."))
    found.sort(key=lambda x: x[0])          # stable: newest first within a rank, as todo_open orders them
    out = [line for _, line in found[:most]]
    if len(found) > most:
        out.append(f"- … and {len(found) - most} more open items that this measurement also answers.")
    if not out:
        return []
    return (["## Your open todo items, beside your run box's measurement (you close them; nothing here "
             "edits your todo)"] + out)


_DECLINE = "[request_run] I did not run"
# Network config first: a DNS decline also says why ("only to let an installer fetch packages").
_FOLD_CLASSES = (("change the host's network config", re.compile(r"resolv|network config|\bdns\b", re.I)),
                 ("install packages", re.compile(r"install|package|\bpip\b|\buv\b|venv", re.I)))


def _tail_lines(p: Path, nbytes: int = 600_000) -> List[str]:
    try:
        with open(p, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - nbytes))
            lines = f.read().decode("utf-8", "replace").splitlines()
        return lines[1:] if size > nbytes else lines
    except OSError:
        return []


def refusal_fold(instance: Path, member: str, hours: int = 48, now: Optional[datetime] = None) -> str:
    """One line counting the seat's recent declines by class, so a rule agreed to in chat stays in view.
    Reads every conversation in the home: the decline marker is written only by the seat's request_run
    answer, whichever channel it lands in, and a turn from the being itself is never counted."""
    lines: List[str] = []
    try:
        convs = sorted((Path(instance) / "conversations").glob("*.jsonl"))
    except OSError:
        convs = []
    for p in convs:
        lines += _tail_lines(p)
    now = now or datetime.now(timezone.utc)
    cut = now - timedelta(hours=hours)
    counts: Dict[str, List[int]] = {}
    for ln in lines:
        try:
            d = json.loads(ln)
        except Exception:
            continue
        if not d.get("from") or d.get("from") == member:
            continue
        text = str(d.get("text") or d.get("message") or "")
        if not text.startswith(_DECLINE):
            continue
        try:
            ts = datetime.strptime(d.get("ts", ""), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if ts < cut:
            continue
        for name, rx in _FOLD_CLASSES:
            if rx.search(text):
                counts.setdefault(name, []).append(int(d.get("seq") or 0))
                break
    if not counts:
        return ""
    parts = [f"{len(v)} that would {k} (latest seq {max(v)})" for k, v in counts.items()]
    return (f"- In the last {hours} h the seat declined " + " and ".join(parts)
            + " of your run requests. The seat applies these as standing rules; a new wording of the same "
              "request gets the same answer.")


def blocks(instance: Path, todo_items: List, member: str, modules=None, measure_fn=None) -> tuple:
    """(census block, todo block) for the window. Fail-open: any error gives ("", "")."""
    try:
        c = census(instance, modules=modules, measure_fn=measure_fn)
        fold = refusal_fold(instance, member)
        notes = todo_notes(c, todo_items)
        return render(c, fold), "\n".join(notes)
    except Exception:
        return "", ""
