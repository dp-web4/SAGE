"""Proprioception: the being senses its machine body, with honest gaps (dp, 2026-10-06).

What these pin, against recorded fixtures (fixtures/proprioception/provenance.json says which are
VERIFIED captures and which are FORMAT-based):
  * every reading is {value, source} or {value: None, unavailable}; nothing is synthesized;
  * discrete: VRAM and RAM are separate pools;
  * unified (Jetson, Apple, Intel iGPU): ONE pool, the GPU carries no VRAM numbers, never RAM + VRAM;
  * AMD APU (unified_carveout): the carve-out and GTT are shares, never added to RAM;
  * WSL: no CPU temperature, said so; guest cap and Windows host labelled separately;
  * the being's line is short, carries its age, and is the same `line` the dashboard shows;
  * GET /body is read (never sampled) by the beat, and its failures become a named gap;
  * instance.json "proprioception": false turns the line off; it is on by default.
"""
import http.server
import json
import os
import socketserver
import sys
import threading
import time
import types
from pathlib import Path

import pytest

from sage.gateway import proprioception as P

FIX = Path(__file__).parent / "fixtures" / "proprioception"
LINUX = {"os": "linux", "kind": "linux", "detail": "6.8.0"}
WSL = {"os": "linux", "kind": "wsl2", "detail": "6.18.33.2-microsoft-standard-WSL2"}
JETSON = {"os": "linux", "kind": "jetson", "detail": "NVIDIA Jetson Orin Nano Engineering Reference Developer Kit Super"}
MAC = {"os": "macos", "kind": "macos", "detail": "macOS 15.3 arm64"}


def fx(name):
    return (FIX / name).read_text()


def readings(obj, path=""):
    """Every reading dict in a snapshot, with its path."""
    if isinstance(obj, dict):
        if "value" in obj and ("source" in obj or "unavailable" in obj):
            yield path, obj
            return
        for k, v in obj.items():
            yield from readings(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from readings(v, f"{path}[{i}]")


# ---- parsers against recorded output --------------------------------------------------------

def test_cbp_nvidia_smi_real_capture():
    rows = P.parse_nvidia_smi(fx("cbp_nvidia_smi.csv"))
    assert len(rows) == 1
    r = rows[0]
    assert r["name"] == "NVIDIA GeForce RTX 2060 SUPER" and r["bus"] == "01:00.0"
    assert r["total_mib"] == 8192 and r["used_mib"] is not None and r["temp"] is not None


def test_na_fields_are_none_never_zero():
    rows = P.parse_nvidia_smi(fx("two_gpu_nvidia_smi.csv"))
    assert [r["index"] for r in rows] == [0, 1]
    g = P.nvidia_from_smi(rows[1], None, unified=False)
    assert g["utilization_pct"]["value"] is None and "not available" in g["utilization_pct"]["unavailable"]
    assert g["temperature_c"]["value"] is None
    assert g["memory_used_bytes"]["value"] == 512 * (1 << 20)


def test_meminfo_and_proc_stat_real_capture():
    mi = P.parse_meminfo(fx("cbp_meminfo.txt"))
    assert mi["MemTotal"] > 20 * (1 << 30) and 0 < mi["MemAvailable"] <= mi["MemTotal"]
    a, b = P.parse_proc_stat(fx("cbp_proc_stat_a.txt")), P.parse_proc_stat(fx("cbp_proc_stat_b.txt"))
    u = P.cpu_util_from(a, b)
    assert u is not None and 0.0 <= u <= 100.0
    assert P.cpu_util_from(a, a) is None, "no elapsed jiffies is no reading, not 0%"


def test_tegrastats_orin_line():
    d = P.parse_tegrastats(fx("orin_tegrastats.txt"))
    assert d["ram_used_mib"] == 3156 and d["ram_total_mib"] == 7620
    assert d["gpu_util"] == 12
    assert d["temps"]["gpu"] == pytest.approx(47.687) and d["temps"]["cpu"] == pytest.approx(48.5)


def test_tegrastats_without_a_gpu_field_reports_no_gpu_util():
    d = P.parse_tegrastats(fx("thor_tegrastats.txt"))
    assert "gpu_util" not in d, "an absent field must stay absent, not become 0"
    assert d["ram_total_mib"] == 125772 and d["temps"]["cpu"] == pytest.approx(44.093)


def test_macos_vm_stat_and_ioreg():
    vm = P.parse_vm_stat(fx("macos_vm_stat.txt"))
    assert vm["page_size"] == 16384 and vm["anonymous_pages"] == 341218
    used = P.macos_used_bytes(vm)
    assert used == (341218 - 10421 + 150732 + 251233) * 16384
    io = P.parse_ioreg_accel(fx("macos_ioreg_accel.txt"))
    assert io == {"name": "Apple M4", "util": 9.0, "in_use_bytes": 1362182144}
    assert P.macos_used_bytes({"page_size": 16384}) is None


def test_rocm_smi_and_both_amd_smi_shapes():
    r = P.parse_rocm_smi(fx("rocm_smi.json"))[0]
    assert r["util"] == 3 and r["vram_total"] == 8573157376 and r["temps"]["edge"] == 41.0
    for f in ("amd_smi_metric.json", "amd_smi_metric_gpu_data.json"):
        a = P.parse_amd_smi(fx(f))[0]
        assert a["util"] == 4 and a["vram_used"] == 410 * (1 << 20) and a["vram_total"] == 8176 * (1 << 20)
        assert a["temps"]["edge"] == 42 and a["temps"]["junction"] == 44
    assert P.parse_amd_smi("not json") == [] and P.parse_rocm_smi("") == []


def test_amd_sources_merge_in_priority_order():
    merged, src = P.merge_amd([("amd-smi", {"util": 4, "vram_used": None, "temps": {}}),
                               ("rocm-smi", {"util": 3, "vram_used": 100, "temps": {"edge": 41}}),
                               ("amdgpu sysfs card0", {"util": 9, "vram_used": 200, "gtt_used": 7, "temps": {"edge": 40}})])
    assert (merged["util"], src["util"]) == (4, "amd-smi")
    assert (merged["vram_used"], src["vram_used"]) == (100, "rocm-smi")
    assert (merged["gtt_used"], src["gtt_used"]) == (7, "amdgpu sysfs card0")
    assert src["temps"] == "rocm-smi"


# ---- memory: the guest's cache and the host's headroom (dp: "always razor thin") ----------

def test_guest_breakdown_from_a_large_cache_meminfo(monkeypatch):
    text = fx("cbp_meminfo_large_cache.txt")
    mi = P.parse_meminfo(text)
    monkeypatch.setattr(P, "_read", lambda path: text if path == "/proc/meminfo" else None)
    m = P.sense_memory(WSL, unified=False)
    assert m["anon_bytes"] == {"value": mi["AnonPages"], "source": "/proc/meminfo AnonPages"}
    assert m["cache_bytes"]["value"] == mi["Cached"] + mi["Buffers"]
    assert m["available_bytes"]["value"] == mi["MemAvailable"]
    assert m["cache_bytes"]["value"] > 3 * m["anon_bytes"]["value"], "the fixture is the large-cache case"
    s = _snap(WSL, [], mem=m)
    line = P.summary_line(s)
    assert f"RAM {mi['AnonPages'] / P.GIB:.1f} used + {(mi['Cached'] + mi['Buffers']) / P.GIB:.1f} cache / " in line
    assert "(WSL cap)" in line


def test_host_block_from_the_real_windows_answer():
    h = P.parse_win_host(fx("cbp_win_host.json"), now=1.0)
    d = json.loads(fx("cbp_win_host.json"))
    assert h["memory_total_bytes"]["value"] == d["total_kib"] * 1024
    assert h["memory_available_bytes"]["value"] == d["free_kib"] * 1024
    assert h["memory_used_bytes"]["value"] == (d["total_kib"] - d["free_kib"]) * 1024
    assert h["committed_bytes"]["value"] == (d["commit_limit_kib"] - d["commit_free_kib"]) * 1024
    assert h["wsl_vm_working_set_bytes"] == {"value": d["vm"][0]["WorkingSet64"], "source": "Get-Process vmmemWSL WorkingSet64"}
    assert h["low_headroom"]["controls"].startswith("nothing") and "10%" in h["low_headroom"]["threshold"]
    part = P._host_part(h)
    gib = lambda b: f"{b / P.GIB:.1f}"
    assert part == (f"host {gib((d['total_kib'] - d['free_kib']) * 1024)}/{gib(d['total_kib'] * 1024)} GiB "
                    f"({gib(d['free_kib'] * 1024)} free; WSL VM holds {gib(d['vm'][0]['WorkingSet64'])})")


def test_an_invisible_vmmem_is_named_not_guessed():
    h = P.parse_win_host(fx("win_host_no_vmmem.json"), now=1.0)
    assert h["wsl_vm_working_set_bytes"]["value"] is None
    assert "no vmmem/vmmemWSL process visible" in h["wsl_vm_working_set_bytes"]["unavailable"]
    assert "WSL VM footprint not visible" in P._host_part(h)


def test_low_headroom_is_a_stated_marker_only():
    ans = json.dumps({"total_kib": 32 << 20, "free_kib": 2 << 20, "commit_limit_kib": 1, "commit_free_kib": 0,
                      "vm": {"Name": "vmmemWSL", "WorkingSet64": 20 << 30, "PrivateMemorySize64": 22 << 30}})
    h = P.parse_win_host(ans, now=1.0)
    assert h["low_headroom"]["value"] is True
    assert P._host_part(h) == "host 30.0/32.0 GiB (2.0 free; WSL VM holds 20.0) · low headroom (available < 10% of host physical)"
    assert P.parse_win_host("garbage", 1.0)["memory_total_bytes"]["value"] is None


def test_the_host_view_exists_only_on_wsl(monkeypatch):
    monkeypatch.setattr(P, "detect_platform", lambda: dict(LINUX))
    s = P.sample([("here", str(FIX))], cpu_window=0.05, wsl_host=True)
    assert "not a WSL guest" in s["wsl_host"]["unavailable"]
    assert "host " not in s["line"].split("| disk")[0].split("RAM")[-1]


def test_macos_has_no_breakdown_and_says_why(monkeypatch):
    out = {"sysctl": fx("macos_sysctl_hw_memsize.txt"), "vm_stat": fx("macos_vm_stat.txt")}
    monkeypatch.setattr(P, "_run", lambda argv, timeout=5.0: (out[argv[0]], ""))
    m = P.sense_memory(MAC, unified=True)
    assert m["cache_bytes"]["value"] is None and "macOS" in m["cache_bytes"]["unavailable"]


# ---- topology: no double count --------------------------------------------------------------

def _no_tools(monkeypatch):
    monkeypatch.setattr(P, "which", lambda tool, plat=None: None)


def test_jetson_unified_is_one_pool_and_never_ram_plus_vram(monkeypatch):
    _no_tools(monkeypatch)
    monkeypatch.setattr(P, "_jetson_gpu_load", lambda: None)
    monkeypatch.setattr(P, "_thermal_zones", lambda: [("cpu-thermal", 48.5)])
    monkeypatch.setattr(P, "_tegrastats_line", lambda timeout=3.0: (fx("orin_tegrastats.txt"), ""))
    gpus, why = P.sense_gpus(JETSON)
    assert why is None and len(gpus) == 1
    g = gpus[0]
    assert g["topology"] == "unified"
    assert g["memory_used_bytes"]["value"] is None and g["memory_total_bytes"]["value"] is None
    assert "no separate pool" in g["memory_used_bytes"]["unavailable"]
    assert (g["utilization_pct"]["value"], g["utilization_pct"]["source"]) == (12, "tegrastats GR3D_FREQ")
    assert g["temperature_c"]["source"] == "tegrastats gpu@"
    mi = P.parse_meminfo(fx("cbp_meminfo.txt"))   # any meminfo: the pool is whatever MemTotal says
    snap = _snap(JETSON, gpus, mem=_mem("unified", mi))
    line = P.summary_line(snap)
    assert "VRAM" not in line and "one pool, GPU included" in line and "memory: unified" in line
    assert line.count(f"/{mi['MemTotal'] / P.GIB:.1f} GiB") == 1, "the pool appears once"


def test_thor_nvidia_smi_na_memory_on_unified_with_compute_app_share():
    row = P.parse_nvidia_smi(fx("thor_nvidia_smi.csv"))[0]
    apps = P.parse_nvidia_smi_apps(fx("thor_nvidia_smi_apps.csv"))
    g = P.nvidia_from_smi(row, apps, unified=True)
    assert g["memory_used_bytes"]["value"] is None and g["memory_total_bytes"]["value"] is None
    assert g["shared_memory_used_bytes"]["value"] == 17234 * (1 << 20)
    assert g["utilization_pct"]["value"] == 3 and g["temperature_c"]["value"] == 45


def test_apple_unified_gpu_share_from_ioreg(monkeypatch):
    monkeypatch.setattr(P, "_run", lambda argv, timeout=5.0: (fx("macos_ioreg_accel.txt"), ""))
    gpus, why = P.sense_gpus(MAC)
    g = gpus[0]
    assert g["vendor"] == "apple" and g["topology"] == "unified"
    assert g["shared_memory_used_bytes"]["value"] == 1362182144
    assert g["memory_total_bytes"]["value"] is None
    assert "root" in g["temperature_c"]["unavailable"]


def _amd_card(root: Path, n: int, vendor="0x1002", busy="7", vram_used=str(512 << 20), vram_total=str(8 << 30),
              gtt="12582912", temps=(("edge", "41000"), ("junction", "43000"))):
    pci = root / "pci" / f"0000:0{n + 3}:00.0"
    pci.mkdir(parents=True)
    (pci / "vendor").write_text(vendor + "\n")
    if vendor == "0x1002":
        (pci / "gpu_busy_percent").write_text(busy)
        (pci / "mem_info_vram_used").write_text(vram_used)
        (pci / "mem_info_vram_total").write_text(vram_total)
        (pci / "mem_info_gtt_used").write_text(gtt)
        hw = pci / "hwmon" / "hwmon3"
        hw.mkdir(parents=True)
        for i, (label, mc) in enumerate(temps, 1):
            (hw / f"temp{i}_input").write_text(mc)
            (hw / f"temp{i}_label").write_text(label)
    card = root / "drm" / f"card{n}"
    card.mkdir(parents=True)
    (card / "device").symlink_to(pci)
    (root / "drm" / f"card{n}-HDMI-A-1").mkdir()       # a connector, not a GPU


def test_discrete_radeon_from_sysfs_alone(monkeypatch, tmp_path):
    _no_tools(monkeypatch)
    _amd_card(tmp_path, 0)
    monkeypatch.setattr(P, "DRM_GLOB", str(tmp_path / "drm" / "card[0-9]*"))
    gpus, why = P.sense_gpus(LINUX, "11th Gen Intel(R) Core(TM) i7-11700 @ 2.50GHz")
    assert len(gpus) == 1, "the connector is not a second GPU"
    g = gpus[0]
    assert (g["vendor"], g["topology"]) == ("amd", "discrete")
    assert g["utilization_pct"] == {"value": 7.0, "source": "amdgpu sysfs card0"}
    assert g["memory_total_bytes"]["value"] == 8 << 30
    assert g["temperature_c"]["value"] == 41.0 and g["temperatures"]["junction"] == 43.0
    assert "GTT" in g["shared_memory_used_bytes"]["source"]


def test_amd_apu_is_unified_carveout_and_not_added_to_ram(monkeypatch, tmp_path):
    _no_tools(monkeypatch)
    _amd_card(tmp_path, 0, vram_total=str(2 << 30))
    monkeypatch.setattr(P, "DRM_GLOB", str(tmp_path / "drm" / "card[0-9]*"))
    gpus, _ = P.sense_gpus(LINUX, "AMD Ryzen 3 7320U with Radeon Graphics")
    g = gpus[0]
    assert g["topology"] == "unified_carveout"
    assert "carve-out" in g["memory_total_bytes"]["source"]
    snap = _snap(LINUX, gpus, mem=_mem("unified", {"MemTotal": 14 << 30, "MemAvailable": 10 << 30}))
    assert snap["memory_topology"] == "unified_carveout"
    line = P.summary_line(snap)
    assert "carve-out 0.5/2.0 GiB" in line and "RAM 4.0/14.0 GiB" in line
    assert "16.0" not in line, "carve-out must not be added to the OS-visible RAM"


def test_two_amd_gpus_with_an_apu_cpu_say_which_is_unknown(monkeypatch, tmp_path):
    _no_tools(monkeypatch)
    _amd_card(tmp_path, 0)
    _amd_card(tmp_path, 1)
    monkeypatch.setattr(P, "DRM_GLOB", str(tmp_path / "drm" / "card[0-9]*"))
    gpus, _ = P.sense_gpus(LINUX, "AMD Ryzen AI Max+ 395 w/ Radeon 8060S")
    assert [g["topology"] for g in gpus] == ["unknown", "unknown"]
    assert "not known" in gpus[0]["topology_why"]


def test_amd_plus_intel_igpu_is_mixed_and_every_gpu_is_listed(monkeypatch, tmp_path):
    _no_tools(monkeypatch)
    _amd_card(tmp_path, 0)
    _amd_card(tmp_path, 1, vendor="0x8086")
    monkeypatch.setattr(P, "DRM_GLOB", str(tmp_path / "drm" / "card[0-9]*"))
    gpus, _ = P.sense_gpus(LINUX, "11th Gen Intel(R) Core(TM) i7-11700 @ 2.50GHz")
    assert sorted(g["vendor"] for g in gpus) == ["amd", "intel"]
    intel = [g for g in gpus if g["vendor"] == "intel"][0]
    assert intel["topology"] == "unified" and intel["utilization_pct"]["value"] is None
    topo, why = P.topology_of(gpus, LINUX)
    assert topo == "mixed" and "amd discrete" in why and "intel unified" in why
    line = P.summary_line(_snap(LINUX, gpus))
    assert "AMD GPU 7%" in line and "Intel GPU: no readings" in line


def test_nvidia_card_without_a_working_nvidia_smi_is_named_not_dropped(monkeypatch, tmp_path):
    _no_tools(monkeypatch)
    _amd_card(tmp_path, 0, vendor="0x10de")
    monkeypatch.setattr(P, "DRM_GLOB", str(tmp_path / "drm" / "card[0-9]*"))
    gpus, _ = P.sense_gpus(LINUX, "Intel")
    assert gpus[0]["vendor"] == "nvidia" and "nvidia-smi not found" in gpus[0]["utilization_pct"]["unavailable"]


# ---- WSL ------------------------------------------------------------------------------------

def test_wsl_has_no_cpu_temperature_and_says_so():
    t = P.cpu_temp(WSL, zones=[], hwmon=None)
    assert t == {"value": None, "unavailable": "not exposed inside WSL"}


def test_wsl_gpu_with_no_vendor_tool_names_dxg_and_the_amd_gap(monkeypatch):
    _no_tools(monkeypatch)
    monkeypatch.setattr(P, "_drm_cards", lambda: [])
    real = os.path.exists
    monkeypatch.setattr(P.os.path, "exists", lambda p: True if p == "/dev/dxg" else real(p))
    gpus, why = P.sense_gpus(WSL, "Intel")
    assert gpus == [] and "/dev/dxg" in why and "AMD and Intel GPUs expose no sysfs inside the WSL guest" in why
    line = P.summary_line(_snap(WSL, gpus, gpu_why=why))
    assert "GPU: none sensed" in line and "memory: unknown" in line


def test_x86_cpu_temp_from_thermal_zone_or_hwmon_never_acpitz():
    assert P.cpu_temp(LINUX, zones=[("acpitz", 27.8), ("x86_pkg_temp", 52.0)], hwmon=None)["value"] == 52.0
    assert P.cpu_temp(LINUX, zones=[("acpitz", 27.8)], hwmon=(61.0, "hwmon coretemp Package id 0")) == \
        {"value": 61.0, "source": "hwmon coretemp Package id 0"}
    assert P.cpu_temp(LINUX, zones=[("acpitz", 27.8)], hwmon=False)["value"] is None


def test_macos_cpu_uses_psutil_when_present_and_says_when_it_is_not(monkeypatch):
    monkeypatch.setattr(P, "_run", lambda argv, timeout=5.0: ("Apple M4\n", ""))
    fake = types.ModuleType("psutil")
    fake.cpu_percent = lambda interval=None: 23.4
    monkeypatch.setitem(sys.modules, "psutil", fake)
    c = P.sense_cpu(MAC, 0.01)
    assert c["utilization_pct"] == {"value": 23.4, "source": "psutil over 0.01 s"}
    assert c["model"] == "Apple M4" and c["temperature_c"]["value"] is None
    monkeypatch.setitem(sys.modules, "psutil", None)      # import psutil -> ImportError
    c = P.sense_cpu(MAC, 0.01)
    assert c["utilization_pct"]["value"] is None and "psutil is not installed" in c["utilization_pct"]["unavailable"]


def test_macos_memory_from_sysctl_and_vm_stat(monkeypatch):
    out = {"sysctl": fx("macos_sysctl_hw_memsize.txt"), "vm_stat": fx("macos_vm_stat.txt")}
    monkeypatch.setattr(P, "_run", lambda argv, timeout=5.0: (out[argv[0]], ""))
    m = P.sense_memory(MAC, unified=True)
    assert m["pool"] == "unified" and m["total_bytes"]["value"] == 17179869184
    assert m["used_bytes"]["value"] == P.macos_used_bytes(P.parse_vm_stat(fx("macos_vm_stat.txt")))


# ---- disks ----------------------------------------------------------------------------------

def test_paths_on_one_filesystem_are_one_disk_with_both_labels(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    disks, gaps = P.sense_disks([("instance", str(tmp_path / "a")), ("models", str(tmp_path / "b"))])
    assert len(disks) == 1 and disks[0]["labels"] == ["instance", "models"] and not gaps
    assert 0 <= disks[0]["used_pct"]["value"] <= 100


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="mountinfo is Linux")
def test_an_unreadable_path_is_measured_at_its_mount_and_says_so(tmp_path):
    missing = str(tmp_path / "no" / "such" / "models")
    disks, gaps = P.sense_disks([("models", missing)])
    assert not gaps and "measured at its mount" in disks[0]["free_bytes"]["source"]


# ---- the snapshot, the line, the budget -----------------------------------------------------

def _mem(pool, mi):
    return {"pool": pool, "scope": "machine",
            "total_bytes": P.ok(mi["MemTotal"], "/proc/meminfo"),
            "used_bytes": P.ok(mi["MemTotal"] - mi["MemAvailable"], "/proc/meminfo")}


def _snap(plat, gpus, mem=None, gpu_why=None):
    topo, why = P.topology_of(gpus, plat)
    s = {"schema": P.SCHEMA, "sampled_at": time.time(), "platform": plat, "memory_topology": topo,
         "memory_topology_why": why, "gpus": gpus,
         "cpu": {"utilization_pct": P.ok(5.0, "t"), "temperature_c": P.gap("none here")},
         "memory": mem or _mem("system", {"MemTotal": 32 << 30, "MemAvailable": 20 << 30}), "disks": []}
    if gpu_why:
        s["gpu_unavailable"] = gpu_why
    return s


def test_cbp_real_snapshot_schema_and_honesty():
    s = json.loads(fx("cbp_snapshot.json"))
    for k in ("schema", "sampled_at", "sample_ms", "platform", "memory_topology", "gpus", "cpu",
              "memory", "disks", "line"):
        assert k in s, k
    assert s["schema"] == "sage.body/1" and s["platform"]["kind"] == "wsl2"
    assert s["memory_topology"] == "discrete" and s["gpus"][0]["topology"] == "discrete"
    assert s["memory"]["scope"].startswith("wsl guest") and "wsl_host" in s
    for path, r in readings(s):
        if r["value"] is None:
            assert r.get("unavailable"), f"{path}: a missing value must say why"
        else:
            assert r.get("source"), f"{path}: a value must say where it came from"
    assert s["cpu"]["temperature_c"]["unavailable"] == "not exposed inside WSL"
    assert P.summary_line(s) == s["line"], "the line is a pure function of the snapshot"


def test_live_sample_on_this_machine_is_well_formed():
    """The real path, read-only: no daemon, no writes, no GPU work (a query, not a load)."""
    s = P.sample([("here", str(FIX))], cpu_window=0.05, wsl_host=False)
    assert s["schema"] == P.SCHEMA and s["memory_topology"] in ("discrete", "unified", "unified_carveout", "mixed", "unknown")
    for path, r in readings(s):
        assert (r["value"] is None) == ("unavailable" in r), path
    assert s["line"] and len(s["line"]) < 400


def test_the_line_stays_short_even_when_everything_is_missing():
    gpus = [P._gpu(v, "x", "unknown") for v in ("nvidia", "amd", "intel")]
    s = _snap(LINUX, gpus)
    s["cpu"] = {"utilization_pct": P.gap("x" * 30), "temperature_c": P.gap("no CPU sensor in /sys/class/thermal or hwmon")}
    s["memory"] = {"used_bytes": P.gap("/proc/meminfo unreadable"), "total_bytes": P.gap("x")}
    line = P.being_line(dict(s, line=P.summary_line(s)))
    assert len(line) < 500, len(line)
    # a 2B being at an 8k window (the smallest the fleet runs) has ~16k chars of prompt room
    from sage.gateway.heartbeat import window_budget_chars
    assert len(line) < 0.04 * window_budget_chars(8192, 2048)


def test_cbp_line_is_concise():
    line = P.being_line(json.loads(fx("cbp_snapshot.json")), now=json.loads(fx("cbp_snapshot.json"))["sampled_at"] + 4)
    assert line.startswith("- Your machine body, sampled 4 s ago: GPU ")
    assert len(line) < 320, len(line)   # 274 with the guest cache and the host headroom (2026-10-06)


def test_a_stale_snapshot_says_so_and_a_missing_one_says_why():
    s = json.loads(fx("cbp_snapshot.json"))
    assert "stale" in P.being_line(s, now=s["sampled_at"] + 600) and "10 min ago" in P.being_line(s, now=s["sampled_at"] + 600)
    assert P.being_line(None, why_missing="the daemon did not answer /body (URLError)") == \
        "- Your machine body is not sensed this beat: the daemon did not answer /body (URLError)."


# ---- the beat reads GET /body; opt-out ------------------------------------------------------

class _Body(http.server.BaseHTTPRequestHandler):
    reply = (200, {})

    def do_GET(self):
        code, body = self.reply
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


@pytest.fixture
def fake_daemon(monkeypatch):
    srv = socketserver.TCPServer(("127.0.0.1", 0), _Body)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    from sage.gateway import body
    monkeypatch.setattr(body, "DAEMON_BODY", f"http://127.0.0.1:{srv.server_address[1]}/body")
    yield _Body
    srv.shutdown()
    srv.server_close()


def test_machine_body_reads_the_endpoint(fake_daemon):
    from sage.gateway import body
    snap = json.loads(fx("cbp_snapshot.json"))
    fake_daemon.reply = (200, snap)
    assert body.machine_body()["snapshot"]["line"] == snap["line"]
    fake_daemon.reply = (503, {"unavailable": "no body snapshot yet: the first sample has not finished"})
    assert body.machine_body() == {"snapshot": None, "why": "no body snapshot yet: the first sample has not finished"}
    fake_daemon.reply = (404, {})
    assert "does not serve /body yet" in body.machine_body()["why"]


def test_machine_body_with_no_daemon_is_a_named_gap(monkeypatch):
    from sage.gateway import body
    monkeypatch.setattr(body, "DAEMON_BODY", "http://127.0.0.1:9/body")
    r = body.machine_body(timeout=0.5)
    assert r["snapshot"] is None and "did not answer /body" in r["why"]


def test_the_body_block_carries_the_line_and_the_opt_out_removes_it():
    from sage.gateway import body
    snap = json.loads(fx("cbp_snapshot.json"))
    cur = {"perception": {}, "metabolism": {"live": True}, "gaze": {}, "inventory": {},
           "machine": {"snapshot": snap}}
    on = body.render(cur, None)
    assert snap["line"] in on and on.splitlines()[1].startswith("- Your machine body, sampled")
    assert snap["line"] not in body.render(cur, None, proprioception=False)
    assert "machine body" not in body.render({k: v for k, v in cur.items() if k != "machine"}, None)


def test_proprioception_is_on_by_default_and_off_only_for_false():
    from sage.gateway.heartbeat import proprioception_for
    assert proprioception_for(None) is True and proprioception_for({}) is True
    assert proprioception_for({"proprioception": "off"}) is True, "only an explicit false turns it off"
    assert proprioception_for({"proprioception": False}) is False


def test_standalone_cli_json(tmp_path):
    import subprocess
    root = Path(__file__).resolve().parents[3]
    p = subprocess.run([sys.executable, "-m", "sage.gateway.proprioception", "--json", "--no-wsl-host",
                        "--cpu-window", "0.05", "--disk", f"t={tmp_path}"],
                       capture_output=True, text=True, cwd=root, timeout=60)
    assert p.returncode == 0, p.stderr
    s = json.loads(p.stdout)
    assert s["schema"] == P.SCHEMA and s["disks"][0]["labels"][0] == "t"
    assert list(tmp_path.iterdir()) == [], "the sampler writes nothing"
