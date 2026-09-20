#!/usr/bin/env python3
"""fleet-fact-check — compare the copies of a published fact and report divergence.

WHAT THIS IS, AND WHAT IT DELIBERATELY IS NOT

It is a DIFFER. It reads, compares, prints, and exits 0 or 3. It writes nothing,
fixes nothing, and has no opinion about which copy is right.

It is not a generator, and that is the design decision rather than a limitation.
A generator has to choose a basis, and the fleet measured on 2026-09-12 that every
available basis is wrong somewhere: Sprout's session count read 661 from git,
690 on disk, and 682 from an `ls | wc -l` that counted a subdirectory -- three
honest measurements of one number, published simultaneously across two public
sites. A generator counting git would have reproduced 4-lab's 661 exactly and
confidently, and been 29 behind, because that loop runs while its commit step is
broken. A generator does not fix a basis problem; it industrialises whichever
basis it picks.

A differ needs no such choice. "These two copies disagree" is checkable without
settling which is true, and it is the question nobody was asking.

WHY IT EXISTS

Seven independent instances in the week of 2026-09-08, one shape each time -- a
fact correct in one copy and stale in another, with nothing detecting it:

  fleet.json 4/8 rows disagreeing with the site (frozen 08-28, site was right)
  sage-fleet-models.json frozen since 03-12, read by nothing but its writer
  update_fleet_models.py written 03-08, wired to nothing on any seat
  Sprout's count published as three different numbers on two sites
  a README caveat reverted 7 minutes after it was written, unnoticed for 4 days
  a census with one as-of date over eight counts, three of them refreshed
  hestia's own deploy dead 2 weeks, so "merged" was not "installed"

Every one was found by a human or a seat who happened to look. None was found by
a mechanism. The one mechanism on this fleet that keeps a fact true unattended is
`hestia-deploy --check`, which does exactly this and nothing more.

THE RULE THAT MATTERS MOST HERE

A comparison that could not actually be made reports UNDETERMINED, never PASS.
A check that cannot go red is a testimonial with a timestamp -- and a green board
produced by a check that silently skipped is worse than no board, because it is
believed. Same discipline as the gate's fail-closed and the deploy's "a failed
look is reported as a failed look".

Exit: 0 all clear, 3 divergence or undetermined, 2 the checker itself broke.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FLEET_JSON = REPO / "sage" / "federation" / "fleet.json"
LEGACY_JSON = REPO / "sage" / "federation" / "sage-fleet-models.json"
SITE_URL = os.getenv("SAGE_SITE_URL", "https://sage-site-murex.vercel.app/")

OK, DIVERGE, UNDETERMINED = "ok", "DIVERGE", "UNDETERMINED"


class Report:
    """Collects findings. Undetermined is a failure, not a skip."""

    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []

    def add(self, status: str, check: str, detail: str) -> None:
        self.rows.append((status, check, detail))

    @property
    def bad(self) -> int:
        return sum(1 for s, _, _ in self.rows if s != OK)

    def render(self, as_json: bool) -> str:
        if as_json:
            return json.dumps(
                {"checks": [{"status": s, "check": c, "detail": d} for s, c, d in self.rows],
                 "diverged": self.bad},
                indent=2)
        out = []
        for s, c, d in self.rows:
            mark = "  ok  " if s == OK else ("  !!  " if s == DIVERGE else "  ??  ")
            out.append(f"{mark}{c}\n        {d}")
        return "\n".join(out)


# ── model-name comparison ────────────────────────────────────────────────────
# Two spellings of one model: "gemma4:12b" in a manifest, "Gemma4 12B" in prose.
# Collapsing to alphanumerics matches those, and also correctly separates
# qwen2.5-14b from Qwen3.8 27B. It does NOT match "granite4:h-tiny" against
# "Granite 4.0-H-Tiny", which is the same model written two ways -- so equality
# is not the only outcome. A mismatch in the FAMILY token is a real divergence;
# a mismatch below it is reported UNDETERMINED for a human, because a checker
# that guesses here would either cry wolf or, far worse, learn to stay quiet.

def _strip_prose(s: str) -> str:
    """Drop the decoration a prose table carries and a manifest never does.

    The site says "Qwen 3.8-Distill 2B — agentic (was 0.8B)"; the manifest says
    "qwen3.8-distill:2b". Those are the same fact and a checker that calls them
    undetermined teaches its reader to ignore it, which is the only way a check
    like this actually fails.
    """
    s = re.sub(r"\([^)]*\)", " ", s or "")           # parentheticals
    s = re.sub(r"\b(agentic|raising|sweeps|ollama|instance[s]?)\b", " ", s, flags=re.I)
    return s


def _norm_ver(s: str) -> str:
    # "Granite 4.0-H-Tiny" and "granite4:h-tiny" are one model. A trailing .0 is
    # decoration; a differing non-zero minor is not, and must survive to canon().
    return re.sub(r"(\d)\.0(?!\d)", r"\1", s or "")


def canon(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _norm_ver(_strip_prose(s)).lower())


def family(s: str) -> str:
    """Family INCLUDING its version: gemma4, gemma3, qwen35, llama31.

    Leading letters alone were too coarse -- it made "Gemma4 e2b" vs "gemma3:4b"
    merely undetermined when it is a plain disagreement about which model runs.
    """
    m = re.match(r"([a-z]+[0-9]*)", canon(s))
    return m.group(1) if m else ""


def compare_model(a: str, b: str) -> tuple[str, str]:
    """(status, note). `a` may be a prose cell naming several models."""
    if not a or not b:
        return UNDETERMINED, "one side absent"
    parts = [p for p in re.split(r"[,;/]| and ", _strip_prose(a)) if canon(p)]
    if not parts:
        parts = [a]
    for p in parts:
        if canon(p) == canon(b):
            note = "" if len(parts) == 1 else f"matched on {p.strip()!r} of {len(parts)} listed"
            return OK, note
    if all(family(p) and family(b) and family(p) != family(b) for p in parts):
        return DIVERGE, ""
    return UNDETERMINED, "same family, different spelling — needs a human"


# ── sources ──────────────────────────────────────────────────────────────────

def load_json(p: Path):
    try:
        return json.loads(p.read_text())
    except Exception as e:
        return {"__error__": f"{type(e).__name__}: {e}"}


def observed_model(machine: str) -> tuple[str | None, str]:
    """This machine's model from the record, not from config. Mirrors
    update_fleet_models.detect_observed_model; duplicated deliberately so the
    checker does not import the thing it checks."""
    inst_dir = REPO / "sage" / "instances"
    pin = os.getenv("SAGE_INSTANCE")
    cand = None
    if pin and (inst_dir / pin).is_dir():
        cand = inst_dir / pin
    elif inst_dir.is_dir():
        owned = [d for d in inst_dir.iterdir()
                 if d.is_dir() and d.name.startswith(machine + "-")]
        if owned:
            cand = max(owned, key=lambda d: len(list((d / "sessions").glob("*.json")))
                       if (d / "sessions").is_dir() else 0)
    if not cand:
        return None, "no instance directory for this machine"
    files = sorted((cand / "sessions").glob("session_*.json")) if (cand / "sessions").is_dir() else []
    if files:
        try:
            m = json.loads(files[-1].read_text()).get("model")
            if m:
                return m, f"{cand.name}/sessions/{files[-1].name}"
        except Exception:
            pass
    ij = cand / "instance.json"
    if ij.is_file():
        try:
            m = json.loads(ij.read_text()).get("model")
            if m:
                return m, f"{cand.name}/instance.json"
        except Exception:
            pass
    return None, f"{cand.name}: no session record or instance.json model"


def fetch_site(url: str) -> tuple[str | None, str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "fleet-fact-check"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode("utf-8", "replace"), f"HTTP {r.status}"
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def site_models(html: str) -> dict[str, str]:
    """Machine -> model string from the published hardware table."""
    out: dict[str, str] = {}
    m = re.search(r'<table[^>]*class="[^"]*hw-table[^"]*"[^>]*>(.*?)</table>', html, re.S)
    if not m:
        return out
    for row in re.findall(r"<tr>(.*?)</tr>", m.group(1), re.S):
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)
        if len(cells) < 2:
            continue
        def txt(c: str) -> str:
            c = re.sub(r"<[^>]+>", " ", c)
            c = c.replace("&mdash;", " ").replace("&middot;", " ").replace("&#8209;", "-")
            return re.sub(r"\s+", " ", c).strip()
        name, model = txt(cells[0]), txt(cells[1])
        if name and model and name.lower() not in ("machine",):
            out[name.lower()] = model
    return out


def site_census(html: str) -> list[tuple[str, int, str | None]]:
    """(machine, count, as-of or None) from the published census line."""
    i = html.find("Raising sessions")
    if i < 0:
        return []
    seg = html[i:i + 1600]
    rows = []
    for m in re.finditer(r"([A-Z][A-Za-z]+)\s*\((\d+)\)(.{0,120}?)(?=&middot;|</span>|$)", seg, re.S):
        name, n, tail = m.group(1), int(m.group(2)), m.group(3)
        d = re.search(r"(\d{2})&#8209;(\d{2})|(\d{2})-(\d{2})", tail)
        asof = None
        if d:
            mm, dd = (d.group(1), d.group(2)) if d.group(1) else (d.group(3), d.group(4))
            asof = f"{mm}-{dd}"
        rows.append((name.lower(), n, asof))
    return rows


# ── checks ───────────────────────────────────────────────────────────────────

def check_local_model(rep: Report, machine: str, fleet: dict) -> None:
    obs, basis = observed_model(machine)
    row = (fleet.get("machines") or {}).get(machine, {})
    declared = row.get("model_default")
    if obs is None:
        rep.add(UNDETERMINED, f"local model vs fleet.json [{machine}]",
                f"cannot read what this machine ran ({basis}) — not asserting agreement")
        return
    if not declared:
        rep.add(UNDETERMINED, f"local model vs fleet.json [{machine}]",
                f"observed {obs} ({basis}); fleet.json has no model_default for this machine")
        return
    st, note = compare_model(obs, declared)
    rep.add(st, f"local model vs fleet.json [{machine}]",
            f"observed {obs} ({basis})  |  fleet.json {declared}" + (f"  — {note}" if note else ""))


def check_manifest_pair(rep: Report, fleet: dict, legacy: dict) -> None:
    fm = fleet.get("machines") or {}
    lm = legacy.get("machines") or {}
    for name in sorted(set(fm) | set(lm)):
        a = (fm.get(name) or {}).get("model_default")
        b = (lm.get(name) or {}).get("model")
        if not a or not b:
            rep.add(UNDETERMINED, f"fleet.json vs sage-fleet-models.json [{name}]",
                    f"fleet.json {a!r}  |  legacy {b!r} — one side absent")
            continue
        st, note = compare_model(a, b)
        rep.add(st, f"fleet.json vs sage-fleet-models.json [{name}]",
                f"fleet.json {a}  |  legacy {b}" + (f"  — {note}" if note else ""))


def check_site_models(rep: Report, fleet: dict, models: dict, site_note: str) -> None:
    if not models:
        rep.add(UNDETERMINED, "fleet.json vs published site table",
                f"could not read the hardware table from the live site ({site_note})")
        return
    fm = fleet.get("machines") or {}
    for name, shown in sorted(models.items()):
        declared = (fm.get(name) or {}).get("model_default")
        if not declared:
            rep.add(UNDETERMINED, f"site vs fleet.json [{name}]",
                    f"site publishes {shown!r}; fleet.json has no row for this machine")
            continue
        st, note = compare_model(shown, declared)
        rep.add(st, f"site vs fleet.json [{name}]",
                f"site {shown}  |  fleet.json {declared}" + (f"  — {note}" if note else ""))


def check_census_age(rep: Report, rows, max_age_days: int, site_note: str) -> None:
    if not rows:
        rep.add(UNDETERMINED, "published census provenance",
                f"could not read the census line from the live site ({site_note})")
        return
    today = date.today()
    undated = [n for n, _, a in rows if a is None]
    for name, count, asof in rows:
        if asof is None:
            continue  # paused tracks carry no as-of by construction; reported below
        try:
            mm, dd = (int(x) for x in asof.split("-"))
            age = (today - date(today.year, mm, dd)).days
        except Exception:
            rep.add(UNDETERMINED, f"census as-of [{name}]", f"unparseable date {asof!r}")
            continue
        st = OK if age <= max_age_days else DIVERGE
        rep.add(st, f"census as-of [{name}]",
                f"{count} as of {asof} — {age}d old (threshold {max_age_days}d)")
    if undated:
        rep.add(OK, "census rows without an as-of",
                f"{', '.join(undated)} — expected for paused tracks; a live track here would be a defect")


def check_local_census(rep: Report, machine: str, rows) -> None:
    inst_dir = REPO / "sage" / "instances"
    pin = os.getenv("SAGE_INSTANCE")
    cand = None
    if pin and (inst_dir / pin).is_dir():
        cand = inst_dir / pin
    elif inst_dir.is_dir():
        owned = [d for d in inst_dir.iterdir()
                 if d.is_dir() and d.name.startswith(machine + "-")]
        cand = max(owned, key=lambda d: len(list((d / "sessions").glob("*.json"))), default=None) if owned else None
    if not cand or not (cand / "sessions").is_dir():
        rep.add(UNDETERMINED, f"local session count vs site [{machine}]",
                "no sessions directory on this machine")
        return
    files = sorted((cand / "sessions").glob("session_*.json"))
    on_disk = len(files)
    # Numbering and count are different facts and the gap is itself a finding:
    # a gap means either lost records or a numbering restart. Report both.
    highest = 0
    if files:
        m = re.search(r"(\d+)", files[-1].stem)
        highest = int(m.group(1)) if m else 0
    published = next((n for nm, n, _ in rows if nm == machine), None)
    if published is None:
        rep.add(UNDETERMINED, f"local session count vs site [{machine}]",
                f"{on_disk} on disk; the site publishes no count for this machine")
        return
    st = OK if published == on_disk else DIVERGE
    extra = "" if highest == on_disk else f"  [highest id {highest} != {on_disk} on disk — gaps or restart]"
    rep.add(st, f"local session count vs site [{machine}]",
            f"on disk {on_disk}  |  site {published}{extra}")


def daemon_presence(repo: Path = REPO, home: Path | None = None) -> list[str]:
    """Evidence that this seat is SUPPOSED to run a sage-rs daemon. Empty list = none found.

    Exists because of HUB (2026-09-18): HUB has never had a sage-daemon -- no unit, no
    binary, nothing on the port -- and the check told it, on every run, forever, that "a
    down daemon is itself a finding". True line, wrong explanation, unclearable. The port
    in fleet.json cannot discriminate: all eight rows carry the same template 8760.
    So presence is established from what is on the box, not from the manifest.
    """
    import glob
    import subprocess
    home = home or Path.home()
    ev: list[str] = []
    for b in (repo / "sage-rs" / "target" / "release" / "sage-daemon",
              home / ".sage-deploy" / "bin" / "sage-daemon"):
        if b.is_file():
            ev.append(f"binary {b}")
    for pat in (str(home / "Library/LaunchAgents/*sage-daemon*"),
                str(home / ".config/systemd/user/*sage-daemon*"),
                "/etc/systemd/system/*sage-daemon*", "/Library/LaunchDaemons/*sage-daemon*"):
        ev.extend(f"unit {u}" for u in sorted(glob.glob(pat)))
    try:
        r = subprocess.run(["pgrep", "-f", "sage-daemon"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            ev.append(f"process pid {r.stdout.split()[0]}")
    except Exception:
        pass
    return ev


def upstream_newest(git, fetch: bool, max_ref_age_h: float = 24.0) -> tuple[str, str, str]:
    """(newest sage-rs commit ON THE FLEET'S MAIN, the ref it was read from, caveat).

    Exists because of Sprout (2026-09-18): the first cut read `git log -1 -- sage-rs/`
    from HEAD of whatever checkout ran it and never fetched, so a seat whose checkout was
    one sage-rs commit behind was told `ok` about a stale binary -- the check failing OPEN
    in the one direction it exists to close. A non-empty caveat means "I could not see the
    fleet's newest from here", and the caller must not turn that into `ok`.
    """
    import time
    # Age of the last fetch, read BEFORE fetching: git rewrites FETCH_HEAD when a fetch
    # STARTS, so after a failed one its mtime says "just now" about a ref that did not move.
    # (Found by this function's own test, 2026-09-20: the failed-fetch arm came back clean.)
    gd = git("rev-parse", "--git-common-dir").stdout.strip()
    fh = Path(gd if os.path.isabs(gd) else REPO / gd) / "FETCH_HEAD"
    age_h = (time.time() - fh.stat().st_mtime) / 3600 if fh.exists() else float("inf")
    failed = ""
    if fetch:
        r = git("fetch", "--quiet", "origin", "main", timeout=30)
        if r.returncode == 0:
            age_h = 0.0
        else:
            failed = "could not fetch origin/main (" + ((r.stderr or "").strip().splitlines() or ["no output"])[-1][:80] + "); "
    ref = "origin/main"
    if git("rev-parse", "--verify", "--quiet", ref).returncode != 0:
        return "", "", "this checkout has no origin/main to compare against"
    caveat = ""
    if age_h > max_ref_age_h:   # a recent fetch by anyone is as good as ours; an old one is not
        age = "has never been fetched" if age_h == float("inf") else f"was last fetched {age_h:.0f}h ago"
        caveat = failed + f"origin/main {age}" + ("" if fetch else ", and this run did not refresh it")
    newest = git("log", "-1", "--format=%h", ref, "--", "sage-rs/").stdout.strip()
    return newest, ref, caveat


def daemon_verdict(*, reachable: bool, why_unreachable: str, port: int, presence: list[str],
                   build: str, newest: str, ref: str, caveat: str,
                   built_resolvable: bool, is_current: bool, behind: str) -> tuple[str, str]:
    """PURE: every observation in, (status, detail) out. Tested in test_fleet_fact_check.py.

    Four states, which the first cut collapsed into two:
      no daemon on this seat   -> ok, and it says what it looked for (HUB)
      daemon expected, not up  -> DIVERGE: that one a seat can act on
      up, but I cannot see the fleet's newest sage-rs  -> UNDETERMINED, never ok (Sprout)
      up and comparable        -> ok / DIVERGE on ancestry, as before
    """
    if not reachable:
        if not presence:
            return OK, (f"this seat runs no sage-rs daemon: nothing on :{port}, no sage-daemon binary, "
                        "unit or process found — nothing to be stale (not a skip: absence was looked for)")
        return DIVERGE, (f"daemon is DOWN: /health unreachable on :{port} ({why_unreachable}), but this seat "
                         f"has one — {'; '.join(presence[:3])}")
    m = re.search(r"\+([0-9a-f]{7,40})", build)
    if not m:
        return UNDETERMINED, f"/health reports build {build!r}; no commit sha to compare (binary predates build stamping?)"
    if not newest:
        return UNDETERMINED, f"running {build}  |  {caveat or 'no sage-rs history on ' + ref}"
    if not built_resolvable:
        return UNDETERMINED, f"running {build}  |  that commit is not in this checkout, so ancestry cannot be decided"
    dirty = "  [built from a DIRTY tree]" if "dirty" in build else ""
    base = f"running {build}  |  newest sage-rs commit on {ref} is {newest}"
    if not is_current:
        # Stale against even a stale ref is still stale: report it, caveat and all.
        return DIVERGE, base + f" — binary is {behind} sage-rs commit(s) behind" + dirty + (f"  ({caveat})" if caveat else "")
    if caveat:
        return UNDETERMINED, base + f" — current against that, BUT {caveat}; cannot say the fleet has nothing newer"
    return (DIVERGE if dirty else OK), base + dirty


def check_daemon_build(rep: Report, machine: str, fleet: dict, fetch: bool = True) -> None:
    """Is the RUNNING daemon built from the newest sage-rs on the fleet's main?

    Added 2026-09-18, the day McNugget's daemon was found running a binary built
    2026-06-06 -- fourteen sage-rs commits and three months behind. /health publishes
    its build as "<ver>+<sha>@<date>"; the binary is current iff the newest commit
    touching sage-rs/ on origin/main is an ancestor of that sha. A differ: it rebuilds
    nothing. Reworked 2026-09-20 after HUB's and Sprout's reviews -- see daemon_presence,
    upstream_newest and daemon_verdict for what each of them found.
    """
    import subprocess
    port = ((fleet.get("machines") or {}).get(machine) or {}).get("gateway_port", 8760)
    name = f"running daemon vs sage-rs source [{machine}]"

    def git(*a, timeout=20):
        try:
            return subprocess.run(["git", "-C", str(REPO), *a], capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(a, 124, "", "timed out")

    build, why, reachable = "", "", False
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=4) as r:
            build = str(json.loads(r.read().decode()).get("build", ""))
        reachable = True
    except Exception as e:
        why = type(e).__name__
    if not reachable:
        status, detail = daemon_verdict(reachable=False, why_unreachable=why, port=port,
                                        presence=daemon_presence(), build="", newest="", ref="", caveat="",
                                        built_resolvable=False, is_current=False, behind="?")
        rep.add(status, name, detail)
        return
    newest, ref, caveat = upstream_newest(git, fetch)
    m = re.search(r"\+([0-9a-f]{7,40})", build)
    built = m.group(1) if m else ""
    resolvable = bool(built) and git("cat-file", "-e", built + "^{commit}").returncode == 0
    current = bool(newest) and resolvable and git("merge-base", "--is-ancestor", newest, built).returncode == 0
    behind = (git("rev-list", "--count", f"{built}..{ref}", "--", "sage-rs/").stdout.strip() or "?") if resolvable and ref else "?"
    status, detail = daemon_verdict(reachable=True, why_unreachable="", port=port, presence=[],
                                    build=build, newest=newest, ref=ref, caveat=caveat,
                                    built_resolvable=resolvable, is_current=current, behind=behind)
    rep.add(status, name, detail)


def main() -> int:
    ap = argparse.ArgumentParser(description="Compare published fleet facts against their sources.")
    ap.add_argument("--machine", default=os.getenv("SAGE_MACHINE", ""),
                    help="machine to check locally (default $SAGE_MACHINE)")
    ap.add_argument("--site", default=SITE_URL, help="published site URL")
    ap.add_argument("--no-site", action="store_true", help="skip checks that need the network")
    ap.add_argument("--max-age-days", type=int, default=7,
                    help="how stale a dated census row may be before it is a finding")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    rep = Report()
    fleet, legacy = load_json(FLEET_JSON), load_json(LEGACY_JSON)
    if "__error__" in fleet:
        print(f"fleet-fact-check: cannot read {FLEET_JSON}: {fleet['__error__']}", file=sys.stderr)
        return 2

    machine = args.machine or os.uname().nodename.split(".")[0].lower()
    if machine not in (fleet.get("machines") or {}):
        rep.add(UNDETERMINED, "identify this machine",
                f"{machine!r} has no fleet.json row; local checks cannot run")
        machine = ""

    if machine:
        check_local_model(rep, machine, fleet)
        check_daemon_build(rep, machine, fleet, fetch=not args.no_site)
    if "__error__" in legacy:
        rep.add(UNDETERMINED, "fleet.json vs sage-fleet-models.json",
                f"cannot read the legacy manifest: {legacy['__error__']}")
    else:
        check_manifest_pair(rep, fleet, legacy)

    if args.no_site:
        rep.add(UNDETERMINED, "published site checks", "skipped by --no-site")
    else:
        html, note = fetch_site(args.site)
        if html is None:
            rep.add(UNDETERMINED, "published site checks", f"could not fetch {args.site} ({note})")
        else:
            check_site_models(rep, fleet, site_models(html), note)
            rows = site_census(html)
            check_census_age(rep, rows, args.max_age_days, note)
            if machine:
                check_local_census(rep, machine, rows)

    print(rep.render(args.json))
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not args.json:
        verdict = "CLEAR" if rep.bad == 0 else f"{rep.bad} FINDING(S)"
        print(f"\n{stamp} fleet-fact-check: {verdict} across {len(rep.rows)} checks")
    return 0 if rep.bad == 0 else 3


if __name__ == "__main__":
    sys.exit(main())
