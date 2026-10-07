"""
proprioception — the being senses its machine body: GPU, CPU, memory, disk.

dp, 2026-10-06: *"sage feature request - basic proprioception: gpu (usage, memory, temp), cpu (usage,
memory, temp), disk (usage, space). basically awareness of its embodied resources. and indicators for
same. this is necessary for situational awareness, its physical metabolic state. need to account for
shared/split memory systems."* Then: *"make sure it's compatible with all the machines in the fleet"*
and *"we also have amd gpus."*

THE RULES THIS FILE KEEPS
  * An indicator, not a control. Nothing here throttles, gates or decides. It reports the body.
  * Only actual state. Every reading is {"value": x, "source": "<where it came from>"} or
    {"value": None, "unavailable": "<why>"}. Nothing is estimated, copied from another field, or
    defaulted. A being with no instrument invents the data; a being with an honest gap does not.
  * Universal body sense. One code path for every machine: WSL2, native Linux, Jetson, macOS; NVIDIA,
    AMD, Intel, Apple. A missing tool is a reported gap, never a crash. Standard library only;
    psutil is used if present and never required.
  * Never on the beat's critical path. The daemon runs this on a cadence (sage-daemon/src/body.rs) and
    serves the last snapshot at GET /body; the beat reads that snapshot, it does not sample.

MEMORY TOPOLOGY, THE CENTRAL POINT
  * discrete          the GPU has its own VRAM pool: VRAM used/total is reported on the GPU and system
                      RAM separately on `memory`.
  * unified           GPU and CPU draw from ONE pool (Jetson, Apple Silicon, Intel iGPU). The pool is
                      `memory`; the GPU carries no VRAM numbers (they would be the same RAM counted
                      twice), only `shared_memory_used_bytes` where the platform measures the GPU's share.
  * unified_carveout  an AMD APU: firmware reserves a VRAM carve-out from the same physical RAM (it is
                      NOT in the OS-visible total) and the GPU also maps system RAM through GTT (which IS
                      inside the OS-visible used). Both are reported as shares; neither is added to RAM.
  * mixed             more than one GPU with different topologies (a dGPU next to an iGPU).
  * unknown           no GPU was sensed; `gpu_unavailable` says why.
  On WSL the guest sees its cap, not the host: `memory` is the guest, `wsl_host` is the Windows host,
  labelled and timestamped separately.

STANDALONE (read-only: no daemon, no GPU work, no writes)
    python3 -m sage.gateway.proprioception            # the snapshot, as the being's line + JSON
    python3 -m sage.gateway.proprioception --json     # the snapshot JSON only
    options: --disk LABEL=PATH (repeatable), --cpu-window SECONDS, --no-wsl-host
"""
from __future__ import annotations

import glob
import json
import os
import platform as _platform
import re
import shutil
import socket
import subprocess
import sys
import time
from typing import Dict, List, Optional, Tuple

SCHEMA = "sage.body/1"
GIB = float(1 << 30)
CMD_TIMEOUT_S = 5.0
CPU_WINDOW_S = 0.5       # /proc/stat is read twice this far apart: utilization over that window

# PCI vendor ids (the kernel's own numbers in /sys/bus/pci/devices/*/vendor)
VENDORS = {"0x10de": "nvidia", "0x1002": "amd", "0x8086": "intel"}
# The kernel's DRM card nodes (ABI, not configuration); a module constant so tests can point it
# at a fixture tree.
DRM_GLOB = "/sys/class/drm/card[0-9]*"


# --------------------------------------------------------------------------------------------
# readings
# --------------------------------------------------------------------------------------------

def ok(value, source: str) -> Dict:
    return {"value": value, "source": source}


def gap(why: str) -> Dict:
    return {"value": None, "unavailable": why}


def val(r) -> Optional[float]:
    return r.get("value") if isinstance(r, dict) else None


def _num(s) -> Optional[float]:
    """A number, or None for N/A, [N/A], Not Supported, '', etc. Never a default."""
    if s is None:
        return None
    if isinstance(s, (int, float)) and not isinstance(s, bool):
        return float(s)
    s = str(s).strip()
    try:
        return float(s)
    except ValueError:
        return None


def _read(path: str) -> Optional[str]:
    try:
        with open(path) as f:
            return f.read()
    except Exception:
        return None


def _run(argv: List[str], timeout: float = CMD_TIMEOUT_S) -> Tuple[Optional[str], str]:
    """(stdout, '') or (None, why). Never raises."""
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return None, f"{os.path.basename(argv[0])} not found"
    except subprocess.TimeoutExpired:
        return None, f"{os.path.basename(argv[0])} timed out after {timeout:.0f} s"
    except Exception as e:
        return None, f"{os.path.basename(argv[0])} failed: {type(e).__name__}: {e}"
    if p.returncode != 0:
        msg = (p.stderr or p.stdout or "").strip().splitlines()
        return None, f"{os.path.basename(argv[0])} exit {p.returncode}" + (f": {msg[0][:160]}" if msg else "")
    return p.stdout, ""


# --------------------------------------------------------------------------------------------
# platform
# --------------------------------------------------------------------------------------------

def detect_platform() -> Dict:
    sysname = _platform.system().lower()
    if sysname == "darwin":
        return {"os": "macos", "kind": "macos",
                "detail": f"macOS {_platform.mac_ver()[0]} {_platform.machine()}"}
    if sysname != "linux":
        return {"os": sysname, "kind": "other", "detail": _platform.platform()}
    rel = (_read("/proc/sys/kernel/osrelease") or "").strip()
    model = (_read("/proc/device-tree/model") or "").replace("\x00", "").strip()
    if "microsoft" in rel.lower() or "wsl" in rel.lower():
        return {"os": "linux", "kind": "wsl2", "detail": rel}
    if "jetson" in model.lower() or (model and os.path.exists("/etc/nv_tegra_release")):
        return {"os": "linux", "kind": "jetson", "detail": model}
    return {"os": "linux", "kind": "linux", "detail": rel}


def _wsl_tool_dirs() -> List[str]:
    """Where WSL publishes the host GPU driver's tools (nvidia-smi): WSL writes it into
    /etc/ld.so.conf.d itself. A systemd unit's PATH does not include it, so the daemon would
    otherwise report "nvidia-smi not found" on a machine that has it."""
    dirs = []
    for f in glob.glob("/etc/ld.so.conf.d/*wsl*.conf"):
        for line in (_read(f) or "").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and os.path.isdir(line):
                dirs.append(line)
    return dirs


def which(tool: str, plat: Optional[Dict] = None) -> Optional[str]:
    p = shutil.which(tool)
    if p:
        return p
    if (plat or {}).get("kind") == "wsl2":
        for d in _wsl_tool_dirs():
            c = os.path.join(d, tool)
            if os.access(c, os.X_OK):
                return c
    return None


# --------------------------------------------------------------------------------------------
# parsers — pure, fixture-tested
# --------------------------------------------------------------------------------------------

NVSMI_FIELDS = "index,pci.bus_id,name,utilization.gpu,memory.used,memory.total,temperature.gpu"


def parse_nvidia_smi(text: str) -> List[Dict]:
    """`nvidia-smi --query-gpu=<NVSMI_FIELDS> --format=csv,noheader,nounits`. memory in MiB.
    '[N/A]' / 'N/A' / '[Not Supported]' (what a unified-memory part prints) become None."""
    out = []
    for line in (text or "").splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 7:
            continue
        idx, bus, name, util, used, total, temp = parts[:7]
        out.append({"index": int(_num(idx)) if _num(idx) is not None else len(out),
                    "bus": _norm_bus(bus), "name": name, "util": _num(util),
                    "used_mib": _num(used), "total_mib": _num(total), "temp": _num(temp),
                    "raw_memory": f"{used} / {total}"})
    return out


def parse_nvidia_smi_apps(text: str) -> Dict[str, float]:
    """`nvidia-smi --query-compute-apps=gpu_bus_id,used_memory --format=csv,noheader,nounits`:
    MiB per GPU bus. Rows whose memory is N/A are skipped, so a GPU with no numeric row is absent."""
    out: Dict[str, float] = {}
    for line in (text or "").splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2:
            continue
        mib = _num(parts[1])
        if mib is None:
            continue
        b = _norm_bus(parts[0])
        out[b] = out.get(b, 0.0) + mib
    return out


def _norm_bus(bus: str) -> str:
    """'00000000:01:00.0' (nvidia-smi) and '0000:01:00.0' (sysfs) -> '01:00.0'."""
    bus = (bus or "").strip().lower()
    return bus[-7:] if len(bus) >= 7 else bus


def parse_tegrastats(line: str) -> Dict:
    """One tegrastats line (Orin JetPack 5/6, optionally timestamp-prefixed; Thor JetPack 7).
    Returns {'ram_used_mib','ram_total_mib','gpu_util','temps':{name:C}} with absent keys absent."""
    d: Dict = {"temps": {}}
    m = re.search(r"\bRAM (\d+)/(\d+)MB", line or "")
    if m:
        d["ram_used_mib"], d["ram_total_mib"] = float(m.group(1)), float(m.group(2))
    m = re.search(r"\bGR3D_FREQ (\d+)%", line or "")
    if m:
        d["gpu_util"] = float(m.group(1))
    for name, c in re.findall(r"\b([A-Za-z][A-Za-z0-9_]*)@(-?\d+(?:\.\d+)?)C\b", line or ""):
        d["temps"][name.lower()] = float(c)
    return d


def parse_meminfo(text: str) -> Dict[str, int]:
    """/proc/meminfo -> bytes."""
    out = {}
    for line in (text or "").splitlines():
        m = re.match(r"(\w+):\s+(\d+)(?:\s+kB)?", line)
        if m:
            out[m.group(1)] = int(m.group(2)) * (1024 if "kB" in line else 1)
    return out


def parse_proc_stat(text: str) -> Optional[Tuple[int, int]]:
    """(busy, total) jiffies from the aggregate cpu line. busy excludes idle and iowait."""
    for line in (text or "").splitlines():
        if line.startswith("cpu "):
            f = [int(x) for x in line.split()[1:]]
            idle = f[3] + (f[4] if len(f) > 4 else 0)
            # guest/guest_nice (f[8], f[9]) are already counted inside user/nice
            total = sum(f[:8]) if len(f) >= 8 else sum(f)
            return total - idle, total
    return None


def cpu_util_from(a: Tuple[int, int], b: Tuple[int, int]) -> Optional[float]:
    dt = b[1] - a[1]
    if dt <= 0:
        return None
    return round(100.0 * (b[0] - a[0]) / dt, 1)


def parse_vm_stat(text: str) -> Dict:
    """macOS `vm_stat`. -> {'page_size': n, '<key>': pages} with keys lower_snake."""
    out: Dict = {}
    m = re.search(r"page size of (\d+) bytes", text or "")
    if m:
        out["page_size"] = int(m.group(1))
    for line in (text or "").splitlines():
        m = re.match(r'\s*"?([^":]+?)"?:\s+(\d+)\.?\s*$', line)
        if m:
            out[re.sub(r"[^a-z0-9]+", "_", m.group(1).lower()).strip("_")] = int(m.group(2))
    return out


def macos_used_bytes(vm: Dict) -> Optional[int]:
    """Activity Monitor's "Memory Used" = app memory + wired + compressed, from vm_stat:
    (anonymous - purgeable) + wired down + occupied by compressor."""
    ps = vm.get("page_size")
    need = ("anonymous_pages", "pages_purgeable", "pages_wired_down", "pages_occupied_by_compressor")
    if not ps or any(k not in vm for k in need):
        return None
    return (vm["anonymous_pages"] - vm["pages_purgeable"] + vm["pages_wired_down"]
            + vm["pages_occupied_by_compressor"]) * ps


def parse_ioreg_accel(text: str) -> Dict:
    """macOS `ioreg -r -d 1 -w 0 -c IOAccelerator`: the GPU's PerformanceStatistics, no sudo.
    -> {'name', 'util', 'in_use_bytes'} with absent keys absent."""
    d: Dict = {}
    m = re.search(r'"model"\s*=\s*"([^"]+)"', text or "") or re.search(r"\+-o (\S+)", text or "")
    if m:
        d["name"] = m.group(1)
    m = re.search(r'"Device Utilization %"\s*=\s*(\d+)', text or "")
    if m:
        d["util"] = float(m.group(1))
    m = re.search(r'"In use system memory"\s*=\s*(\d+)', text or "")
    if m:
        d["in_use_bytes"] = int(m.group(1))
    return d


def parse_rocm_smi(text: str) -> List[Dict]:
    """`rocm-smi --showuse --showmemuse --showtemp --showmeminfo vram --json`:
    {"card0": {"GPU use (%)": "3", "Temperature (Sensor edge) (C)": "41.0",
    "VRAM Total Memory (B)": "...", "VRAM Total Used Memory (B)": "..."}, ...}"""
    try:
        d = json.loads(text)
    except Exception:
        return []
    out = []
    for card in sorted(k for k in d if k.startswith("card")):
        c = d[card] or {}
        temps = {}
        for k, v in c.items():
            m = re.match(r"Temperature \(Sensor (\w+)\) \(C\)", k)
            if m and _num(v) is not None:
                temps[m.group(1).lower()] = _num(v)
        out.append({"card": card, "util": _num(c.get("GPU use (%)")),
                    "vram_used": _num(c.get("VRAM Total Used Memory (B)")),
                    "vram_total": _num(c.get("VRAM Total Memory (B)")),
                    "gtt_used": _num(c.get("GTT Total Used Memory (B)")),
                    "temps": temps})
    return out


def _amd_val(x):
    """amd-smi writes {"value": 3, "unit": "%"} (ROCm 6.1+) or a bare number (6.0)."""
    if isinstance(x, dict):
        return _num(x.get("value")), str(x.get("unit") or "")
    return _num(x), ""


def _amd_bytes(x) -> Optional[float]:
    v, unit = _amd_val(x)
    if v is None:
        return None
    mult = {"B": 1, "KB": 1 << 10, "MB": 1 << 20, "GB": 1 << 30}.get(unit.upper(), 1 << 20)
    return v * mult    # amd-smi reports MB when it gives no unit


def parse_amd_smi(text: str) -> List[Dict]:
    """`amd-smi metric --json`: a list of per-GPU dicts, or {"gpu_data": [...]} (ROCm 6.4+)."""
    try:
        d = json.loads(text)
    except Exception:
        return []
    if isinstance(d, dict):
        d = d.get("gpu_data") or []
    out = []
    for g in d if isinstance(d, list) else []:
        if not isinstance(g, dict):
            continue
        usage = g.get("usage") or {}
        mem = g.get("mem_usage") or {}
        temps = {}
        for k, v in (g.get("temperature") or {}).items():
            t, _ = _amd_val(v)
            if t is not None:
                temps["junction" if k == "hotspot" else k] = t
        out.append({"gpu": g.get("gpu"), "util": _amd_val(usage.get("gfx_activity"))[0],
                    "vram_used": _amd_bytes(mem.get("used_vram")),
                    "vram_total": _amd_bytes(mem.get("total_vram")),
                    "gtt_used": _amd_bytes(mem.get("used_gtt")), "temps": temps})
    return out


# --------------------------------------------------------------------------------------------
# sensors — each returns readings, never raises
# --------------------------------------------------------------------------------------------

def _thermal_zones() -> List[Tuple[str, float]]:
    out = []
    for z in sorted(glob.glob("/sys/class/thermal/thermal_zone*")):
        t, v = _read(z + "/type"), _num(_read(z + "/temp"))
        if t and v is not None:
            out.append((t.strip(), v / 1000.0))
    return out


def _hwmon_cpu_temp() -> Optional[Tuple[float, str]]:
    """x86 package temperature from hwmon (coretemp / k10temp / zenpower)."""
    for h in sorted(glob.glob("/sys/class/hwmon/hwmon*")):
        name = (_read(h + "/name") or "").strip()
        if name not in ("coretemp", "k10temp", "zenpower"):
            continue
        best = None
        for lab in sorted(glob.glob(h + "/temp*_label")):
            label = (_read(lab) or "").strip()
            v = _num(_read(lab.replace("_label", "_input")))
            if v is not None and label in ("Package id 0", "Tctl", "Tdie"):
                best = (v / 1000.0, f"hwmon {name} {label}")
                if label != "Tctl":
                    break
        if best:
            return best
    return None


def cpu_temp(plat: Dict, zones: Optional[List[Tuple[str, float]]] = None,
             hwmon=None) -> Dict:
    if plat["kind"] == "wsl2":
        return gap("not exposed inside WSL")
    if plat["kind"] == "macos":
        return gap("macOS exposes CPU temperature only to root (powermetrics) or private SMC APIs")
    zones = _thermal_zones() if zones is None else zones
    for t, c in zones:
        tl = t.lower()
        if tl in ("x86_pkg_temp",) or tl.startswith("cpu"):
            return ok(round(c, 1), f"thermal_zone {t}")
    h = _hwmon_cpu_temp() if hwmon is None else hwmon
    if h:
        return ok(round(h[0], 1), h[1])
    return gap("no CPU sensor in /sys/class/thermal or hwmon")


def sense_cpu(plat: Dict, window: float = CPU_WINDOW_S) -> Dict:
    cores = os.cpu_count()
    out: Dict = {"cores": cores, "model": _cpu_model(plat)}
    if plat["os"] == "linux":
        a = parse_proc_stat(_read("/proc/stat") or "")
        time.sleep(max(0.05, window))
        b = parse_proc_stat(_read("/proc/stat") or "")
        u = cpu_util_from(a, b) if a and b else None
        out["utilization_pct"] = ok(u, f"/proc/stat over {window:g} s") if u is not None \
            else gap("/proc/stat unreadable")
    else:
        try:
            import psutil  # optional
            out["utilization_pct"] = ok(round(psutil.cpu_percent(interval=window), 1),
                                        f"psutil over {window:g} s")
        except ImportError:
            out["utilization_pct"] = gap("no /proc/stat on this OS and psutil is not installed")
        except Exception as e:
            out["utilization_pct"] = gap(f"psutil failed: {type(e).__name__}")
    try:
        l1, l5, _ = os.getloadavg()
        out["load_1m"], out["load_5m"] = ok(round(l1, 2), "getloadavg"), ok(round(l5, 2), "getloadavg")
    except OSError:
        out["load_1m"] = out["load_5m"] = gap("load average not available")
    out["temperature_c"] = cpu_temp(plat)
    return out


def _cpu_model(plat: Dict) -> Optional[str]:
    if plat["os"] == "macos":
        o, _ = _run(["sysctl", "-n", "machdep.cpu.brand_string"])
        return o.strip() if o else None
    info = _read("/proc/cpuinfo") or ""
    for line in info.splitlines():
        if line.lower().startswith("model name"):
            return line.split(":", 1)[1].strip()
    # aarch64 /proc/cpuinfo has no "model name" (sprout, 2026-10-07: Cortex-A78AE read as null).
    # lscpu names the core from its own tables; without it, the raw ids are still a fact.
    o, _ = _run(["lscpu"])
    for line in (o or "").splitlines():
        if line.lower().startswith("model name"):
            return line.split(":", 1)[1].strip()
    part = re.search(r"^CPU part\s*:\s*(\S+)", info, re.M)
    impl = re.search(r"^CPU implementer\s*:\s*(\S+)", info, re.M)
    if part:
        return f"ARM CPU part {part.group(1)}" + (f" (implementer {impl.group(1)})" if impl else "")
    return None


def parse_swapusage(text: str) -> Optional[Tuple[int, int]]:
    """`sysctl -n vm.swapusage`: 'total = 2048.00M  used = 1024.50M  free = ...' -> (total, used) bytes."""
    unit = {"K": 1 << 10, "M": 1 << 20, "G": 1 << 30}
    got = {}
    for k, n, u in re.findall(r"(total|used)\s*=\s*([\d.]+)([KMG])", text or ""):
        got[k] = int(float(n) * unit[u])
    return (got["total"], got["used"]) if "total" in got and "used" in got else None


def _macos_swap() -> Dict:
    o, why = _run(["sysctl", "-n", "vm.swapusage"])
    sw = parse_swapusage(o or "")
    if not sw:
        return {"swap_used_bytes": gap(why or "unparseable vm.swapusage"),
                "swap_total_bytes": gap(why or "unparseable vm.swapusage")}
    return {"swap_used_bytes": ok(sw[1], "sysctl vm.swapusage"), "swap_total_bytes": ok(sw[0], "sysctl vm.swapusage")}


def sense_memory(plat: Dict, unified: bool) -> Dict:
    pool = "unified" if unified else "system"
    if plat["os"] == "macos":
        total_o, why_t = _run(["sysctl", "-n", "hw.memsize"])
        vm_o, why_v = _run(["vm_stat"])
        total = _num(total_o)
        used = macos_used_bytes(parse_vm_stat(vm_o or "")) if vm_o else None
        return {"pool": pool, "scope": "machine",
                "total_bytes": ok(int(total), "sysctl hw.memsize") if total else gap(why_t or "sysctl gave no number"),
                "used_bytes": ok(used, "vm_stat (app + wired + compressed)") if used is not None
                else gap(why_v or "vm_stat lacks the page counts"),
                "anon_bytes": gap("no /proc/meminfo on macOS"), "cache_bytes": gap("no /proc/meminfo on macOS"),
                "available_bytes": gap("no /proc/meminfo on macOS"),
                **_macos_swap()}
    mi = parse_meminfo(_read("/proc/meminfo") or "")
    if "MemTotal" not in mi:
        return {"pool": pool, "scope": "unknown", "total_bytes": gap("/proc/meminfo unreadable"),
                "used_bytes": gap("/proc/meminfo unreadable")}
    avail = mi.get("MemAvailable")
    return {"pool": pool,
            "scope": "wsl guest (its cap, not the host)" if plat["kind"] == "wsl2" else "machine",
            "total_bytes": ok(mi["MemTotal"], "/proc/meminfo MemTotal"),
            "used_bytes": ok(mi["MemTotal"] - avail, "/proc/meminfo MemTotal-MemAvailable")
            if avail is not None else gap("MemAvailable missing (kernel < 3.14)"),
            # THE BREAKDOWN (dp, 2026-10-06: CBP "regularly runs in 28-31.5g range, always razor
            # thin"). `used` excludes the page cache, and on WSL the VM still holds that cache on
            # the HOST, so "used" alone reads as plenty of room on a machine near its edge.
            "anon_bytes": _mi(mi, "AnonPages"),
            "cache_bytes": ok(mi["Cached"] + mi["Buffers"], "/proc/meminfo Cached+Buffers")
            if "Cached" in mi and "Buffers" in mi else gap("Cached/Buffers missing from /proc/meminfo"),
            "available_bytes": _mi(mi, "MemAvailable"),
            "free_bytes": _mi(mi, "MemFree"),
            "swap_used_bytes": ok(mi.get("SwapTotal", 0) - mi.get("SwapFree", 0), "/proc/meminfo")
            if "SwapTotal" in mi else gap("no swap fields"),
            "swap_total_bytes": ok(mi["SwapTotal"], "/proc/meminfo") if "SwapTotal" in mi else gap("no swap fields")}


def _mi(mi: Dict[str, int], key: str) -> Dict:
    return ok(mi[key], f"/proc/meminfo {key}") if key in mi else gap(f"{key} missing from /proc/meminfo")


def _windows_powershell() -> Optional[str]:
    """powershell.exe, found from WSL's own mount of the Windows system drive (/proc/mounts,
    drvfs 'path=C:\\'), not from a typed path. PATH first, for an interactive shell."""
    p = shutil.which("powershell.exe")
    if p:
        return p
    for line in (_read("/proc/mounts") or "").splitlines():
        f = line.split()
        if len(f) > 3 and "path=C:" in f[3]:
            c = os.path.join(f[1], "Windows", "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
            if os.path.exists(c):
                return c
    return None


# The host query: one Windows process, one JSON answer. vmmem / vmmemWSL is the WSL VM's own
# process on the host; its working set is what the VM holds in physical RAM right now (the guest's
# page cache included), its private bytes what it has committed.
WIN_HOST_PS = (
    "$o=Get-CimInstance Win32_OperatingSystem; "
    "$p=@(Get-Process -Name vmmem,vmmemWSL -ErrorAction SilentlyContinue | "
    "Select-Object Name,WorkingSet64,PrivateMemorySize64); "
    "$v=@(Get-CimInstance Win32_VideoController | Select-Object Name,Status,DriverVersion); "
    "[pscustomobject]@{total_kib=$o.TotalVisibleMemorySize; free_kib=$o.FreePhysicalMemory; "
    "commit_limit_kib=$o.TotalVirtualMemorySize; commit_free_kib=$o.FreeVirtualMemory; vm=$p; video=$v} "
    "| ConvertTo-Json -Compress -Depth 3")

# A neutral marker, stated in the snapshot with its threshold. It controls nothing.
LOW_HEADROOM_FRACTION = 0.10


def parse_win_host(text: str, now: float) -> Dict:
    """The WIN_HOST_PS answer -> the `wsl_host` block. Every field a reading; a missing one says why."""
    try:
        d = json.loads(text)
        total, free = int(d["total_kib"]) * 1024, int(d["free_kib"]) * 1024
    except Exception:
        why = "unparseable Win32_OperatingSystem answer"
        return {"sampled_at": now, "memory_total_bytes": gap(why), "memory_used_bytes": gap(why),
                "memory_available_bytes": gap(why), "wsl_vm_working_set_bytes": gap(why)}
    src = "Windows Win32_OperatingSystem"
    out = {"sampled_at": now,
           "memory_total_bytes": ok(total, src + " TotalVisibleMemorySize"),
           "memory_used_bytes": ok(total - free, src + " TotalVisibleMemorySize-FreePhysicalMemory"),
           "memory_available_bytes": ok(free, src + " FreePhysicalMemory")}
    try:
        cl, cf = int(d["commit_limit_kib"]) * 1024, int(d["commit_free_kib"]) * 1024
        out["commit_limit_bytes"] = ok(cl, src + " TotalVirtualMemorySize")
        out["committed_bytes"] = ok(cl - cf, src + " TotalVirtualMemorySize-FreeVirtualMemory")
    except Exception:
        out["commit_limit_bytes"] = out["committed_bytes"] = gap("commit fields missing from the answer")
    vm = d.get("vm")
    vm = [vm] if isinstance(vm, dict) else (vm or [])
    vm = [v for v in vm if isinstance(v, dict) and v.get("WorkingSet64") is not None]
    if vm:
        names = "+".join(sorted({str(v.get("Name")) for v in vm}))
        out["wsl_vm_working_set_bytes"] = ok(sum(int(v["WorkingSet64"]) for v in vm),
                                             f"Get-Process {names} WorkingSet64")
        priv = [v.get("PrivateMemorySize64") for v in vm]
        out["wsl_vm_private_bytes"] = ok(sum(int(x) for x in priv), f"Get-Process {names} PrivateMemorySize64") \
            if all(x is not None for x in priv) else gap("PrivateMemorySize64 not reported")
    else:
        why = ("no vmmem/vmmemWSL process visible to this Windows user (it runs elevated or under "
               "another session on some hosts)")
        out["wsl_vm_working_set_bytes"] = out["wsl_vm_private_bytes"] = gap(why)
    # The host's display adapters, as Windows names them (nomad and hub, 2026-10-07: an Iris Xe
    # and a W5500 the guest cannot see). Names only: nothing about them is measurable from WSL.
    video = d.get("video")
    video = [video] if isinstance(video, dict) else (video or [])
    out["gpus"] = [{"name": str(v.get("Name")), "status": v.get("Status"), "driver": v.get("DriverVersion")}
                   for v in video if isinstance(v, dict) and v.get("Name")]
    low = free < LOW_HEADROOM_FRACTION * total
    out["low_headroom"] = {"value": low, "threshold": f"available < {LOW_HEADROOM_FRACTION:.0%} of host physical",
                           "source": "this snapshot", "controls": "nothing (an indicator)"}
    return out


def sense_wsl_host() -> Dict:
    """The Windows host's memory, as Windows reports it, and the WSL VM's own footprint on it.
    ~0.6 s (a Windows process), so the daemon asks for it on a slower cadence than the rest and
    carries the block, with its own `sampled_at`, into the samples between."""
    ps = _windows_powershell()
    now = time.time()
    if not ps:
        why = "powershell.exe not reachable from this WSL guest"
        return {"sampled_at": now, "memory_total_bytes": gap(why), "memory_used_bytes": gap(why),
                "memory_available_bytes": gap(why), "wsl_vm_working_set_bytes": gap(why)}
    o, why = _run([ps, "-NoProfile", "-NonInteractive", "-Command", WIN_HOST_PS], timeout=15)
    if not o:
        return {"sampled_at": now, "memory_total_bytes": gap(why), "memory_used_bytes": gap(why),
                "memory_available_bytes": gap(why), "wsl_vm_working_set_bytes": gap(why)}
    return parse_win_host(o, now)


# ---- GPUs -----------------------------------------------------------------------------------

def _gpu(vendor: str, name: str, topology: str, **readings) -> Dict:
    g = {"vendor": vendor, "name": name, "topology": topology}
    for k in ("utilization_pct", "memory_used_bytes", "memory_total_bytes", "temperature_c",
              "shared_memory_used_bytes"):
        g[k] = readings.get(k) or gap("not measured on this GPU")
    if readings.get("temperatures"):
        g["temperatures"] = readings["temperatures"]
    return g


UNIFIED_NO_POOL = "unified memory: the GPU has no separate pool (see memory)"


def nvidia_from_smi(row: Dict, apps_mib: Optional[Dict[str, float]], unified: bool) -> Dict:
    src = "nvidia-smi"
    na = lambda what: gap(f"nvidia-smi reports {what} as not available")
    topo = "unified" if unified else "discrete"
    if unified:
        used = total = gap(UNIFIED_NO_POOL)
        share = (ok(int(apps_mib[row["bus"]] * (1 << 20)), "nvidia-smi compute-apps used_memory")
                 if apps_mib and row["bus"] in apps_mib
                 else gap("the GPU's share of the unified pool is not reported (no per-process memory)"))
    else:
        used = ok(int(row["used_mib"] * (1 << 20)), src) if row["used_mib"] is not None else na("memory.used")
        total = ok(int(row["total_mib"] * (1 << 20)), src) if row["total_mib"] is not None else na("memory.total")
        share = gap("discrete GPU: its memory is VRAM")
    return _gpu("nvidia", row["name"], topo,
                utilization_pct=ok(row["util"], src) if row["util"] is not None else na("utilization"),
                memory_used_bytes=used, memory_total_bytes=total,
                temperature_c=ok(row["temp"], src) if row["temp"] is not None else na("temperature"),
                shared_memory_used_bytes=share)


def _drm_cards() -> List[Dict]:
    """Every GPU the kernel has a DRM card for: {'card', 'dev', 'vendor', 'bus'}."""
    out = []
    for c in sorted(glob.glob(DRM_GLOB)):
        if not re.search(r"card\d+$", c):
            continue          # card0-HDMI-A-1 etc. are connectors
        dev = c + "/device"
        vendor = (_read(dev + "/vendor") or "").strip().lower()
        try:
            bus = os.path.basename(os.path.realpath(dev))
        except Exception:
            bus = ""
        out.append({"card": os.path.basename(c), "dev": dev, "vendor": VENDORS.get(vendor, vendor or "unknown"),
                    "bus": _norm_bus(bus)})
    return out


def amd_sysfs(dev: str) -> Dict:
    """What amdgpu exposes with no ROCm at all."""
    r = lambda f: _num(_read(os.path.join(dev, f)))
    temps = {}
    for lab in sorted(glob.glob(dev + "/hwmon/hwmon*/temp*_input")):
        v = _num(_read(lab))
        if v is None:
            continue
        label = (_read(lab.replace("_input", "_label")) or os.path.basename(lab)).strip().lower()
        temps[label] = v / 1000.0
    return {"util": r("gpu_busy_percent"), "vram_used": r("mem_info_vram_used"),
            "vram_total": r("mem_info_vram_total"), "gtt_used": r("mem_info_gtt_used"), "temps": temps}


def amd_gpu(card: Dict, readings: Dict, sources: Dict, integrated: Optional[bool],
            name: str) -> Dict:
    """One AMD GPU from merged readings. `sources[field]` names where each came from."""
    def rd(k, conv=lambda x: x, missing="not exposed by amd-smi, rocm-smi or amdgpu sysfs"):
        v = readings.get(k)
        return ok(conv(v), sources[k]) if v is not None else gap(missing)
    # A sensor that reads exactly 0 C on a running GPU is unsupported, not cold (pub, 2026-10-07:
    # the W5500's hwmon "mem" reads 0). Named, never shown as a temperature.
    raw = readings.get("temps") or {}
    temps = {k: v for k, v in raw.items() if v != 0}
    zero = {k: "sensor reads 0 C (not supported on this ASIC)" for k, v in raw.items() if v == 0}
    tkey = "edge" if "edge" in temps else ("junction" if "junction" in temps else next(iter(temps), None))
    temp = ok(round(temps[tkey], 1), f"{sources.get('temps', 'sysfs')} ({tkey})") if tkey else gap("no GPU temperature sensor")
    gtt = rd("gtt_used", int, "GTT use not exposed")
    if integrated is True:
        topo = "unified_carveout"
        used = rd("vram_used", int)
        total = rd("vram_total", int)
        for r in (used, total):
            if r.get("source"):
                r["source"] += " (carve-out reserved from system RAM, outside the OS-visible total)"
        share = gtt
        if share.get("source"):
            share["source"] += " (GTT: system RAM the GPU maps, inside memory.used)"
    elif integrated is False:
        topo = "discrete"
        used, total = rd("vram_used", int), rd("vram_total", int)
        share = gtt
        if share.get("source"):
            share["source"] += " (GTT: system RAM the GPU maps, inside memory.used)"
    else:
        topo = "unknown"
        used, total = rd("vram_used", int), rd("vram_total", int)
        share = gtt
    g = _gpu("amd", name, topo, utilization_pct=rd("util"), memory_used_bytes=used,
             memory_total_bytes=total, temperature_c=temp, shared_memory_used_bytes=share,
             temperatures={k: round(v, 1) for k, v in temps.items()} if len(temps) > 1 or zero else None)
    if zero:
        g["temperatures_unavailable"] = zero
    if integrated is None:
        g["topology_why"] = "an integrated-Radeon CPU and more than one AMD GPU: which one is integrated is not known"
    return g


def merge_amd(primary: List[Tuple[str, Dict]]) -> Tuple[Dict, Dict]:
    """[(source, readings)] in priority order -> (merged readings, field -> source)."""
    merged, src = {}, {}
    for source, r in primary:
        for k in ("util", "vram_used", "vram_total", "gtt_used"):
            if merged.get(k) is None and r.get(k) is not None:
                merged[k], src[k] = r[k], source
        if not merged.get("temps") and r.get("temps"):
            merged["temps"], src["temps"] = r["temps"], source
    return merged, src


def _cpu_has_radeon(model: Optional[str]) -> bool:
    return bool(model and "radeon" in model.lower())


def sense_gpus(plat: Dict, cpu_model: Optional[str] = None) -> Tuple[List[Dict], Optional[str]]:
    """Every GPU this body has, each with its vendor, topology and readings; or ([], why)."""
    if plat["kind"] == "macos":
        return _sense_apple()
    gpus: List[Dict] = []
    notes: List[str] = []
    jetson = plat["kind"] == "jetson"

    # NVIDIA, through its own tool (discrete cards, WSL, and Thor-class Jetsons)
    smi_rows: List[Dict] = []
    smi = which("nvidia-smi", plat)
    if smi:
        o, why = _run([smi, f"--query-gpu={NVSMI_FIELDS}", "--format=csv,noheader,nounits"])
        smi_rows = parse_nvidia_smi(o or "")
        if not smi_rows:
            notes.append(why or "nvidia-smi answered with no GPU rows")
    apps = None
    if smi and smi_rows and jetson:
        o, _ = _run([smi, "--query-compute-apps=gpu_bus_id,used_memory", "--format=csv,noheader,nounits"])
        apps = parse_nvidia_smi_apps(o or "")

    if jetson:
        gpus.append(_sense_jetson(plat, smi_rows[0] if smi_rows else None, apps))
    else:
        for row in smi_rows:
            gpus.append(nvidia_from_smi(row, None, unified=False))

    cards = [] if jetson else _drm_cards()
    seen = {r["bus"] for r in smi_rows}
    amd_cards = [c for c in cards if c["vendor"] == "amd"]
    for c in cards:
        if c["vendor"] == "nvidia" and c["bus"] not in seen:
            why = notes[0] if notes else "nvidia-smi not found"
            gpus.append(_gpu("nvidia", f"NVIDIA GPU at {c['bus']}", "discrete",
                             utilization_pct=gap(why), memory_used_bytes=gap(why),
                             memory_total_bytes=gap(why), temperature_c=gap(why)))
        elif c["vendor"] == "intel":
            gi = gap("Intel iGPU: no unprivileged busy counter (intel_gpu_top needs root)")
            gpus.append(_gpu("intel", f"Intel integrated GPU at {c['bus']}", "unified",
                             utilization_pct=gi, memory_used_bytes=gap(UNIFIED_NO_POOL),
                             memory_total_bytes=gap(UNIFIED_NO_POOL),
                             temperature_c=gap("no iGPU temperature sensor in sysfs"),
                             shared_memory_used_bytes=gap("not exposed without root")))
    if amd_cards:
        gpus.extend(_sense_amd(amd_cards, cpu_model, plat))

    if gpus:
        return gpus, None
    if plat["kind"] == "wsl2" and os.path.exists("/dev/dxg"):
        return [], ("a GPU is paravirtualized into WSL (/dev/dxg) but no vendor tool answered: "
                    + (notes[0] if notes else "nvidia-smi not found")
                    + "; AMD and Intel GPUs expose no sysfs inside the WSL guest")
    if notes:
        return [], notes[0]
    return [], "no GPU found (no nvidia-smi, no DRM card in /sys/class/drm)"


def _sense_amd(cards: List[Dict], cpu_model: Optional[str], plat: Dict) -> List[Dict]:
    tool_rows: List[Tuple[str, List[Dict]]] = []
    for tool, argv, parse in (
            ("amd-smi", ["metric", "--json"], parse_amd_smi),
            ("rocm-smi", ["--showuse", "--showmemuse", "--showtemp", "--showmeminfo", "vram", "--json"],
             parse_rocm_smi)):
        p = which(tool, plat)
        if p:
            o, _ = _run([p] + argv, timeout=10)
            rows = parse(o or "")
            if rows:
                tool_rows.append((tool, rows))
    radeon_cpu = _cpu_has_radeon(cpu_model)
    out = []
    for c in cards:
        layers = []
        # a tool's row is matched to a card only when there is exactly one AMD card: amd-smi and
        # rocm-smi number GPUs their own way, and a wrong match would put one GPU's numbers on another
        if len(cards) == 1:
            for tool, rows in tool_rows:
                layers.append((tool, rows[0]))
        layers.append((f"amdgpu sysfs {c['card']}", amd_sysfs(c["dev"])))
        merged, src = merge_amd(layers)
        if radeon_cpu:
            integrated = True if len(cards) == 1 else None
        else:
            integrated = False
        name = (_read(c["dev"] + "/product_name") or "").strip() or f"AMD GPU at {c['bus']}"
        out.append(amd_gpu(c, merged, src, integrated, name))
    return out


def _jetson_gpu_load() -> Optional[Tuple[float, str]]:
    """nvgpu's load file, per-mille. Its path moved between L4T releases; it is the kernel's
    own ABI, so look where the driver has put it rather than in one configured place."""
    for pat in ("/sys/devices/gpu.0/load", "/sys/devices/platform/gpu.0/load",
                "/sys/devices/platform/*.gpu/load", "/sys/devices/platform/bus@0/*.gpu/load"):
        for f in sorted(glob.glob(pat)):
            v = _num(_read(f))
            if v is not None:
                return v / 10.0, f
    return None


def _tegrastats_line(timeout: float = 3.0) -> Tuple[Optional[str], str]:
    p = shutil.which("tegrastats")
    if not p:
        return None, "tegrastats not found"
    try:
        proc = subprocess.Popen([p, "--interval", "200"], stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, text=True)
    except Exception as e:
        return None, f"tegrastats failed: {type(e).__name__}"
    try:
        import select
        r, _, _ = select.select([proc.stdout], [], [], timeout)
        return (proc.stdout.readline() if r else None), ("" if r else "tegrastats gave no line in time")
    finally:
        proc.kill()
        try:
            proc.wait(timeout=2)
        except Exception:
            pass


def _sense_jetson(plat: Dict, smi_row: Optional[Dict], apps) -> Dict:
    name = plat.get("detail") or "Jetson GPU"
    load = _jetson_gpu_load()
    zones = _thermal_zones()
    gz = [(t, c) for t, c in zones if t.lower().startswith("gpu")]
    teg = None
    if (not load and not (smi_row and smi_row["util"] is not None)) or not gz:
        line, why = _tegrastats_line()
        teg = parse_tegrastats(line) if line else {"why": why}
    if load:
        util = ok(round(load[0], 1), load[1])
    elif smi_row and smi_row["util"] is not None:
        util = ok(smi_row["util"], "nvidia-smi")
    elif teg and "gpu_util" in teg:
        util = ok(teg["gpu_util"], "tegrastats GR3D_FREQ")
    else:
        util = gap("no nvgpu load file, nvidia-smi utilization or tegrastats GR3D_FREQ"
                   + (f" ({teg.get('why')})" if teg and teg.get("why") else ""))
    if gz:
        temp = ok(round(gz[0][1], 1), f"thermal_zone {gz[0][0]}")
    elif smi_row and smi_row["temp"] is not None:
        temp = ok(smi_row["temp"], "nvidia-smi")
    elif teg and "gpu" in (teg.get("temps") or {}):
        temp = ok(teg["temps"]["gpu"], "tegrastats gpu@")
    else:
        temp = gap("no GPU thermal zone, nvidia-smi temperature or tegrastats gpu@")
    if smi_row and apps is not None and smi_row["bus"] in apps:
        share = ok(int(apps[smi_row["bus"]] * (1 << 20)), "nvidia-smi compute-apps used_memory")
    else:
        share = gap("the GPU's share of the unified pool needs root (nvmap debugfs)")
    return _gpu("nvidia", (smi_row or {}).get("name") or name, "unified", utilization_pct=util,
                memory_used_bytes=gap(UNIFIED_NO_POOL), memory_total_bytes=gap(UNIFIED_NO_POOL),
                temperature_c=temp, shared_memory_used_bytes=share)


def _sense_apple() -> Tuple[List[Dict], Optional[str]]:
    o, why = _run(["ioreg", "-r", "-d", "1", "-w", "0", "-c", "IOAccelerator"])
    if not o:
        return [], f"ioreg: {why}"
    d = parse_ioreg_accel(o)
    if not d:
        return [], "ioreg answered without an IOAccelerator"
    return [_gpu("apple", d.get("name") or "Apple GPU", "unified",
                 utilization_pct=ok(d["util"], "ioreg PerformanceStatistics (instantaneous)") if "util" in d
                 else gap("ioreg has no Device Utilization %"),
                 memory_used_bytes=gap(UNIFIED_NO_POOL), memory_total_bytes=gap(UNIFIED_NO_POOL),
                 temperature_c=gap("macOS exposes GPU temperature only to root (powermetrics)"),
                 shared_memory_used_bytes=ok(d["in_use_bytes"], "ioreg In use system memory")
                 if "in_use_bytes" in d else gap("ioreg has no In use system memory"))], None


HOST_ONLY = "a GPU on the Windows host (Win32_VideoController), not measurable from inside the WSL guest"


def _vendor_of_name(name: str) -> str:
    n = name.lower()
    return ("nvidia" if "nvidia" in n else "amd" if ("amd" in n or "radeon" in n)
            else "intel" if "intel" in n else "unknown")


def merge_host_gpus(gpus: List[Dict], host: Dict) -> List[Dict]:
    """The guest's sensed GPUs, plus every Windows host adapter the guest did not sense, named and
    unmeasured. A host adapter is the same GPU as a sensed one when the names match."""
    out = list(gpus)
    sensed = {str(g.get("name", "")).strip().lower() for g in gpus}
    for a in (host or {}).get("gpus") or []:
        name = str(a.get("name") or "").strip()
        if not name or name.lower() in sensed or "basic display" in name.lower():
            continue
        vendor = _vendor_of_name(name)
        topo = "unified" if vendor == "intel" else "unknown"
        g = _gpu(vendor, name, topo, utilization_pct=gap(HOST_ONLY), memory_used_bytes=gap(HOST_ONLY),
                 memory_total_bytes=gap(HOST_ONLY), temperature_c=gap(HOST_ONLY),
                 shared_memory_used_bytes=gap(HOST_ONLY))
        g["seen_by"] = "windows host"
        if topo == "unknown":
            g["topology_why"] = "Windows names the adapter; whether it is discrete or integrated is not measured"
        out.append(g)
    return out


def topology_of(gpus: List[Dict], plat: Dict) -> Tuple[str, str]:
    kinds = sorted({g["topology"] for g in gpus})
    if not gpus:
        return "unknown", "no GPU sensed"
    if len(kinds) == 1:
        k = kinds[0]
        why = {"discrete": "every sensed GPU has its own VRAM pool",
               "unified": "the GPU and CPU share one memory pool",
               "unified_carveout": "an integrated GPU with a VRAM carve-out reserved from system RAM",
               "unknown": "the GPU's topology could not be determined"}[k]
        return k, why
    return "mixed", "GPUs of different topologies: " + ", ".join(
        f"{g['vendor']} {g['topology']}" for g in gpus)


# ---- disks ----------------------------------------------------------------------------------

def _mount_of(path: str) -> Optional[str]:
    """The mount point holding `path`, from /proc/self/mountinfo: works when `path` itself is
    not traversable by this user (Ollama's models dir is often 0750 ollama).

    The path is RESOLVED first (legion, 2026-10-07: its models dir is a symlink onto another
    disk, and the unresolved path matched "/"). realpath resolves every component this user can
    see; a link inside a directory it cannot traverse stays unresolved, which sense_disks says.
    Off Linux (no mountinfo), the nearest ancestor that is a mount point."""
    path = os.path.realpath(path)
    if not sys.platform.startswith("linux"):
        p = path
        while p and not os.path.ismount(p):
            parent = os.path.dirname(p)
            if parent == p:
                break
            p = parent
        return p or None
    best = None
    for line in (_read("/proc/self/mountinfo") or "").splitlines():
        f = line.split()
        if len(f) < 5:
            continue
        mp = f[4].replace("\\040", " ")
        if (path == mp or path.startswith(mp.rstrip("/") + "/")) and (best is None or len(mp) > len(best)):
            best = mp
    return best


def models_dir() -> Tuple[Optional[str], str]:
    """Where Ollama keeps models: OLLAMA_MODELS, else Ollama's default under the service user's
    home, else under this user's home. (path, how it was found) or (None, why not)."""
    v = os.getenv("OLLAMA_MODELS")
    if v:
        return v, "OLLAMA_MODELS"
    try:
        import pwd
        h = pwd.getpwnam("ollama").pw_dir
        return os.path.join(h, ".ollama", "models"), "ollama service user's home"
    except Exception:
        pass
    h = os.path.join(os.path.expanduser("~"), ".ollama", "models")
    if os.path.isdir(h):
        return h, "this user's ollama home"
    return None, "OLLAMA_MODELS unset and no ollama models directory found"


def sense_disks(targets: List[Tuple[str, str]]) -> Tuple[List[Dict], List[Dict]]:
    """statvfs for each (label, path); paths on one filesystem are one disk with several labels."""
    disks: Dict[str, Dict] = {}
    gaps = []
    for label, path in targets:
        probe = path
        via = ""
        if not os.access(path, os.F_OK):
            mp = _mount_of(path) if sys.platform.startswith("linux") else None
            if not mp:
                gaps.append({"label": label, "path": path, "unavailable": "path not visible to this user"})
                continue
            probe, via = mp, (f" (measured at its mount {mp}: the path is not readable by this user, "
                              "so a symlink inside it could lead elsewhere unseen)")
        try:
            st = os.statvfs(probe)
            dev = str(os.stat(probe).st_dev)
        except Exception as e:
            gaps.append({"label": label, "path": path, "unavailable": f"statvfs failed: {type(e).__name__}"})
            continue
        if dev in disks:
            disks[dev]["labels"].append(label)
            continue
        total, free = st.f_blocks * st.f_frsize, st.f_bavail * st.f_frsize
        used = total - st.f_bfree * st.f_frsize
        real = os.path.realpath(path)
        disks[dev] = {"labels": [label], "path": path, **({"resolved": real} if real != os.path.abspath(path) else {}),
                      "mount": _mount_of(probe),
                      "total_bytes": ok(total, "statvfs" + via), "free_bytes": ok(free, "statvfs" + via),
                      "used_pct": ok(round(100.0 * used / (used + free), 1) if used + free else None, "statvfs" + via)}
    return list(disks.values()), gaps


# --------------------------------------------------------------------------------------------
# the snapshot and its one rendering
# --------------------------------------------------------------------------------------------

def sample(disks: Optional[List[Tuple[str, str]]] = None, cpu_window: float = CPU_WINDOW_S,
           wsl_host: bool = True, carried_host: Optional[Dict] = None) -> Dict:
    """One snapshot. `carried_host`: a previous `wsl_host` block (with its own sampled_at) to show
    when this sample does not re-ask Windows; the daemon passes it so the line stays complete."""
    t0 = time.time()
    plat = detect_platform()
    cpu = sense_cpu(plat, cpu_window)
    gpus, gpu_why = sense_gpus(plat, cpu.get("model"))
    topo, topo_why = topology_of(gpus, plat)
    unified_pool = topo in ("unified", "unified_carveout") or plat["kind"] in ("jetson", "macos")
    mem = sense_memory(plat, unified_pool)
    targets = list(disks or [])
    if not any(l == "models" for l, _ in targets):
        md, how = models_dir()
        if md:
            targets.append(("models", md))
    dlist, dgaps = sense_disks(targets)
    if not any(l == "models" for l, _ in targets):
        dgaps.append({"label": "models", "unavailable": models_dir()[1]})
    snap = {"schema": SCHEMA, "sampled_at": round(t0, 3), "host": socket.gethostname(),
            "platform": plat, "memory_topology": topo, "memory_topology_why": topo_why,
            "gpus": gpus, "cpu": cpu, "memory": mem, "disks": dlist}
    if gpu_why:
        snap["gpu_unavailable"] = gpu_why
    if dgaps:
        snap["disks_unavailable"] = dgaps
    if plat["kind"] == "wsl2" and wsl_host:
        snap["wsl_host"] = sense_wsl_host()
    elif plat["kind"] == "wsl2" and isinstance(carried_host, dict) and carried_host.get("sampled_at"):
        snap["wsl_host"] = dict(carried_host, carried=True)
    elif plat["kind"] != "wsl2":
        snap["wsl_host"] = {"unavailable": "not a WSL guest: `memory` is this machine's own single view"}
    if plat["kind"] == "wsl2" and (snap.get("wsl_host") or {}).get("gpus"):
        snap["gpus"] = merge_host_gpus(gpus, snap["wsl_host"])
        snap["memory_topology"], snap["memory_topology_why"] = topology_of(snap["gpus"], plat)
        if snap["gpus"] and "gpu_unavailable" in snap:
            snap["gpu_unavailable_in_guest"] = snap.pop("gpu_unavailable")
    snap["sample_ms"] = round((time.time() - t0) * 1000.0, 1)
    snap["cpu_window_ms"] = round(cpu_window * 1000.0)
    snap["line"] = summary_line(snap)
    return snap


def _gib(b) -> str:
    return f"{b / GIB:.1f}"


def _gpu_part(g: Dict, multi: bool) -> str:
    vendor = {"nvidia": "NVIDIA", "amd": "AMD", "intel": "Intel", "apple": "Apple"}.get(g["vendor"], g["vendor"])
    head = f"{vendor} GPU" if multi else "GPU"
    bits = []
    u = val(g.get("utilization_pct"))
    if u is not None:
        bits.append(f"{u:.0f}%")
    used, total = val(g.get("memory_used_bytes")), val(g.get("memory_total_bytes"))
    if used is not None and total is not None:
        bits.append(("carve-out " if g["topology"] == "unified_carveout" else "VRAM ") + f"{_gib(used)}/{_gib(total)} GiB")
    sh = val(g.get("shared_memory_used_bytes"))
    if sh is not None and g["topology"] != "discrete":
        bits.append(f"{_gib(sh)} GiB of shared RAM")
    t = val(g.get("temperature_c"))
    if t is not None:
        bits.append(f"{t:.0f}°C")
    if not bits:
        if g.get("seen_by") == "windows host":
            return f"{head}: on the Windows host, not measurable from WSL"
        return f"{head}: no readings"
    return head + " " + " · ".join(bits)


def _host_part(h: Dict) -> str:
    """The Windows host, headroom first: what the machine has left, and how much the VM holds."""
    ht, hu, ha = val(h.get("memory_total_bytes")), val(h.get("memory_used_bytes")), val(h.get("memory_available_bytes"))
    if ht is None or hu is None:
        why = (h.get("memory_total_bytes") or {}).get("unavailable") or "not sampled yet"
        return f"Windows host memory: {why}"
    if ha is None:      # a block from before the headroom fields: show what it measured
        return f"host {_gib(hu)}/{_gib(ht)} GiB"
    bits = [f"{_gib(ha)} free"]
    vm = val(h.get("wsl_vm_working_set_bytes"))
    bits.append(f"WSL VM holds {_gib(vm)}" if vm is not None else "WSL VM footprint not visible")
    out = f"host {_gib(hu)}/{_gib(ht)} GiB ({'; '.join(bits)})"
    lh = h.get("low_headroom") or {}
    if lh.get("value") is True:
        out += f" · low headroom ({lh.get('threshold', '')})"
    return out


def summary_line(s: Dict) -> str:
    """The one rendering. The being reads it, the dashboard shows it; both from the same snapshot,
    so they cannot disagree. Concise: readings first, gaps named briefly at the end."""
    parts, missing = [], []
    gpus = s.get("gpus") or []
    if gpus:
        shown = sorted(gpus, key=lambda g: val(g.get("utilization_pct")) is None)   # measured first, stable
        parts.append("; ".join(_gpu_part(g, len(gpus) > 1) for g in shown))
        for g in gpus:
            if val(g.get("temperature_c")) is None and len(gpus) == 1:
                missing.append("GPU temp: " + g["temperature_c"].get("unavailable", "unavailable"))
    else:
        parts.append("GPU: none sensed")
        missing.append("GPU: " + str(s.get("gpu_unavailable") or "unknown"))
    cpu, mem = s.get("cpu") or {}, s.get("memory") or {}
    cb = []
    u = val(cpu.get("utilization_pct"))
    cb.append(f"CPU {u:.0f}%" if u is not None else "CPU ?%")
    t = val(cpu.get("temperature_c"))
    if t is not None:
        cb.append(f"{t:.0f}°C")
    else:
        missing.append("CPU temp: " + (cpu.get("temperature_c") or {}).get("unavailable", "unavailable"))
    used, total = val(mem.get("used_bytes")), val(mem.get("total_bytes"))
    wsl = (s.get("platform") or {}).get("kind") == "wsl2"
    if used is not None and total is not None:
        anon, cache = val(mem.get("anon_bytes")), val(mem.get("cache_bytes"))
        if wsl and anon is not None and cache is not None:
            # the guest's cache is held on the host by the VM: show it beside what is in use
            ram = f"RAM {_gib(anon)} used + {_gib(cache)} cache / {_gib(total)} GiB (WSL cap)"
        else:
            ram = f"RAM {_gib(used)}/{_gib(total)} GiB"
            if mem.get("pool") == "unified":
                ram += " (one pool, GPU included)"
            elif wsl:
                ram += " (WSL cap)"
        sw = val(mem.get("swap_used_bytes"))
        if sw and round(sw / GIB, 1) > 0:      # shown when it prints as more than 0.0 GiB
            ram += f" (+{_gib(sw)} GiB swap)"
        cb.append(ram)
    else:
        missing.append("RAM: " + (mem.get("used_bytes") or {}).get("unavailable", "unavailable"))
    if wsl:
        cb.append(_host_part(s.get("wsl_host") or {}))
    parts.append(" · ".join(cb))
    dk = []
    for d in s.get("disks") or []:
        p, f = val(d.get("used_pct")), val(d.get("free_bytes"))
        if p is not None and f is not None:
            dk.append(f"disk{'' if len(s['disks']) == 1 else ' ' + '+'.join(d['labels'])} {p:.0f}% ({f / GIB:.0f} GiB free)")
    parts.append(", ".join(dk) if dk else "disk: not measured")
    parts.append(f"memory: {s.get('memory_topology', 'unknown')}")
    line = " | ".join(parts)
    if missing:
        line += " | unavailable: " + "; ".join(missing)
    return line


def being_line(snap: Optional[Dict], now: Optional[float] = None, why_missing: str = "") -> str:
    """The line in the being's body block, with the reading's age so staleness is visible."""
    if not snap or not snap.get("line"):
        return f"- Your machine body is not sensed this beat: {why_missing or 'no snapshot'}."
    now = time.time() if now is None else now
    age = max(0, int(now - float(snap.get("sampled_at") or 0)))
    when = f"{age} s ago" if age < 120 else f"{age // 60} min ago"
    stale = " (stale: the sampler has not refreshed)" if age > 120 else ""
    return f"- Your machine body, sampled {when}{stale}: {snap['line']}"


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="read-only snapshot of this machine's body (GPU, CPU, memory, disk)")
    ap.add_argument("--json", action="store_true", help="print the snapshot JSON only")
    ap.add_argument("--disk", action="append", default=[], metavar="LABEL=PATH",
                    help="a filesystem to report (repeatable); default: this checkout as 'sage'")
    ap.add_argument("--cpu-window", type=float, default=CPU_WINDOW_S)
    ap.add_argument("--no-wsl-host", action="store_true", help="skip the Windows host memory query (~0.5 s)")
    ap.add_argument("--wsl-host-from", default=None, help=argparse.SUPPRESS)   # the daemon's carried block
    a = ap.parse_args(argv)
    carried = None
    if a.wsl_host_from:
        try:
            carried = json.loads(a.wsl_host_from)
        except ValueError:
            carried = None
    disks = []
    for d in a.disk:
        label, _, path = d.partition("=")
        disks.append((label, path) if path else ("disk", label))
    if not disks:
        disks = [("sage", os.getcwd())]
    snap = sample(disks, a.cpu_window, wsl_host=not a.no_wsl_host, carried_host=carried)
    if a.json:
        print(json.dumps(snap))
    else:
        print(being_line(snap))
        print(json.dumps(snap, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
