#!/usr/bin/env python3
"""
Refuse to mint an LCT from an identity this box cannot vouch for.

`sage_daemon._attempt_chain_registration` -> `register_on_chain` -> `mint_lct`
is the only path in SAGE that writes somewhere a later commit cannot revise.
Everything else this fleet argues about -- a session count on a webpage, a
model name in `fleet.json` -- is a commit away from right. A minted LCT is not.

The number is the smaller half of the problem. The chain LCT ID is derived from
the identity's *LCT URI alone*:

    legacy_to_web4_lct_id("lct://sage:cbp:agent@raising") -> lct:web4:society:sage-cbp-agent

and the URI travels with the file. Instances are bootstrapped by copying a
sibling's `identity.json`, not from `sage/instances/_seed/identity.json` (that
template is clean: `__NAME__`, `lct://sage:__MACHINE__:agent@raising`, count 0).
So a copy carries the source's identity until someone edits it, and on this box
today, measured, four distinct instance lines answer to `lct://sage:cbp:agent@raising`
with recorded counts 240, 122, 26 and 3 -- one of them
`sage/instances/sprout-qwen2.5-0.5b`, whose name field reads `SAGE-cbp`. Whichever
one loads first on a box with a reachable node mints CBP's on-chain identity,
permanently, with its own count in the metadata.

A correct count minted against the wrong entity is worse than a wrong count
minted against the right one, so the identity checks come first here.

The checks (all repo-derived, no network, no chain contact):

  identity-not-local      the URI's machine disagrees with the instance directory
                          it sits in (or, for a non-instance path, with
                          `detect_machine()`). This is the sprout/cbp case.
  lct-collision           another identity on this box derives the same chain LCT
                          ID with a different recorded count. The chain dedupes by
                          ID, so the collision is invisible after the fact: the
                          loser is told "Already registered" and the winner's
                          count is what stands.
  unverifiable-registration
                          `web4_lct_id` is set to something that is not the
                          derived ID -- i.e. a hand-typed placeholder, not a mint
                          receipt. `cbp-gemma3-4b` carries `cbp_sage_lct`, a
                          string that originates in the 2026-03 tinyllama line
                          and survived the 2026-04-18 migration. The daemon's
                          guard is `if web4_lct_id: return`, so a placeholder
                          reads as "registered" and prints `Chain LCT:` as if it
                          were one.
  count-unverified        the recorded `session_count` disagrees with the
                          git-derived count for that instance line. Derived from
                          `sage.federation.census`, same basis, declared.

Why this is wired into `register_on_chain` rather than shipped as a checker you
are supposed to remember to run: this thread already measured what happens to a
file whose only reader is its own writer -- `sage-fleet-models.json`, 188 days,
six machines, zero updates. A preflight nothing calls is that file again. It
fails closed at the call site, and the same logic is runnable standalone for
audit.

Usage:
    python3 -m sage.federation.mint_preflight            # audit every identity on this box
    python3 -m sage.federation.mint_preflight --json
    python3 -m sage.federation.mint_preflight <identity.json>

Exit status is 1 if any inspected identity has a blocker.
"""

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
INSTANCES = REPO / "sage" / "instances"
RAISING_STATE = REPO / "sage" / "raising" / "state" / "identity.json"


def set_repo(root):
    """Point the audit at a different checkout.

    Needed because the identities that matter are untracked: a detached
    worktree -- the fleet's standard way to write a shared repo without
    stepping on a sibling -- contains only the tracked `identity.json` files
    and cannot see the live ones at all. Auditing from a worktree without this
    reports "1 identity file" on a box that has three.
    """
    global REPO, INSTANCES, RAISING_STATE
    REPO = Path(root).resolve()
    INSTANCES = REPO / "sage" / "instances"
    RAISING_STATE = REPO / "sage" / "raising" / "state" / "identity.json"

# sage/instances/<machine>-<model>/  -- the directory name's machine prefix.
INSTANCE_DIR_RE = re.compile(r"\A([a-z0-9]+)-")


def derived_lct_id(uri):
    """Mirror of sage.web4.sage_web4_lct_bridge.legacy_to_web4_lct_id.

    Imported lazily there rather than here so this module stays importable on a
    box with no web4 deps; falls back to the local mirror if that import fails.
    """
    try:
        from sage.web4.sage_web4_lct_bridge import legacy_to_web4_lct_id
        return legacy_to_web4_lct_id(uri)
    except Exception:
        body = uri.split("://", 1)[-1].split("@", 1)[0].replace(":", "-")
        return f"lct:web4:society:{body}"


def uri_machine(uri):
    """The machine token of `lct://sage:<machine>:<role>@<society>`.

    Note the bridge does NOT do this. `sage_web4_lct_bridge.py:475` builds the
    minted metadata's `machine` field as `identity.lct_uri.split(":")[1]`, which
    on every URI in this repo is the literal `'//sage'` -- the scheme separator,
    not the machine. Every LCT this path has ever minted carries
    `machine: "//sage"`.
    """
    if "://" not in uri:
        return None
    parts = uri.split("://", 1)[1].split("@", 1)[0].split(":")
    return parts[1] if len(parts) >= 2 else None


def dir_machine(path):
    """The machine a *directory* claims, independent of what the file claims."""
    try:
        inst = path.relative_to(INSTANCES).parts[0]
    except ValueError:
        return None
    m = INSTANCE_DIR_RE.match(inst)
    return m.group(1) if m else None


def local_machine():
    try:
        from sage.gateway.machine_config import detect_machine
        return detect_machine()
    except Exception:
        import socket
        return socket.gethostname().split(".")[0].lower()


def candidates():
    """Every identity.json a mint could plausibly be driven from on this box.

    Includes the CLI's default `sage/raising/state/identity.json`, which is
    gitignored (.gitignore:244) and therefore invisible to the repo-grep audit
    that found everything else in this thread. On CBP it does not exist; on
    McNugget it exists and reads SAGE-Sprout.
    """
    out = []
    if INSTANCES.is_dir():
        for d in sorted(INSTANCES.iterdir()):
            if d.name == "_seed":
                continue
            f = d / "identity.json"
            if f.is_file():
                out.append(f)
    if RAISING_STATE.is_file():
        out.append(RAISING_STATE)
    return out


def inspect(path):
    with open(path) as f:
        data = json.load(f)
    ident = data.get("identity", {})
    uri = ident.get("lct") or ""
    return {
        "path": str(path.relative_to(REPO)) if REPO in path.parents else str(path),
        "name": ident.get("name"),
        "uri": uri,
        "lct_id": derived_lct_id(uri) if uri else None,
        "uri_machine": uri_machine(uri),
        "dir_machine": dir_machine(path),
        "recorded": ident.get("session_count"),
        "web4_lct_id": ident.get("web4_lct_id"),
        "in_git": None,  # filled by audit()
    }


def derived_counts(counter="strict"):
    """{instance: count} from git, via the census. {} if the census can't run."""
    try:
        from sage.federation import census
        from datetime import date
        rows = census.build("HEAD", counter, date.today())
    except Exception:
        return {}
    return {r["instance"]: r["recorded"] for r in rows}


def blockers(rec, peers, derived):
    """Reasons this identity must not mint. Empty list == clear."""
    out = []

    if not rec["uri"]:
        out.append("identity-not-local: no lct URI in identity.json")
    else:
        um, dm, lm = rec["uri_machine"], rec["dir_machine"], local_machine()
        if um and dm and um != dm:
            out.append(
                f"identity-not-local: URI claims machine {um!r} but this identity "
                f"lives under {dm!r} (name field says {rec['name']!r}) -- an "
                f"instance bootstrapped by copying a sibling's identity.json"
            )
        if um and um != lm:
            out.append(
                f"identity-not-this-box: URI claims machine {um!r}, this box is "
                f"{lm!r}. Every machine's tracked instance directories are in "
                f"every checkout, so pointing the bridge CLI at one mints that "
                f"machine's LCT from here."
            )

    clash = [
        p for p in peers
        if p is not rec
        and p["lct_id"] == rec["lct_id"]
        and p["recorded"] != rec["recorded"]
    ]
    if clash:
        others = ", ".join(f"{p['path']}={p['recorded']}" for p in clash)
        out.append(
            f"lct-collision: {rec['lct_id']} is also derived by {len(clash)} other "
            f"identity/identities with a different count ({others}); the chain "
            f"dedupes by ID, so first load wins and the rest are told "
            f"'Already registered'"
        )

    w = rec["web4_lct_id"]
    if w and w != rec["lct_id"]:
        out.append(
            f"unverifiable-registration: web4_lct_id={w!r} is not the derived "
            f"{rec['lct_id']!r} -- a hand-typed value, not a mint receipt. The "
            f"daemon's `if web4_lct_id: return` treats it as one."
        )

    inst = rec["path"].split("/")[2] if rec["path"].startswith("sage/instances/") else None
    if inst and inst in derived and derived[inst] != rec["recorded"]:
        out.append(
            f"count-unverified: identity.json says {rec['recorded']}, git-derived "
            f"(strict) says {derived[inst]}"
        )

    return out


def audit(paths=None, counter="strict"):
    paths = paths or candidates()
    recs = [inspect(p) for p in paths]
    peers = [inspect(p) for p in candidates()]
    # Identify records that are the same file, so a record never clashes with itself.
    by_path = {p["path"]: p for p in peers}
    for r in recs:
        by_path[r["path"]] = r
    peers = list(by_path.values())
    derived = derived_counts(counter)
    for r in recs:
        r["blockers"] = blockers(r, peers, derived)
    return recs


def preflight(identity_file, counter="strict"):
    """[] if this identity may mint; a list of reasons if it may not."""
    path = Path(identity_file).resolve()
    try:
        return audit([path], counter)[0]["blockers"]
    except Exception as e:
        # A preflight that cannot run is not a pass.
        return [f"preflight-failed: {e}"]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("identity", nargs="*", help="identity.json path(s); default: audit this box")
    ap.add_argument("--counter", choices=("strict", "loose", "all"), default="strict")
    ap.add_argument("--repo", help="audit a checkout other than this module's own")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.repo:
        set_repo(args.repo)

    paths = [Path(p).resolve() for p in args.identity] or None
    recs = audit(paths, args.counter)

    if args.json:
        print(json.dumps(recs, indent=2))
    else:
        print(f"# mint preflight -- {local_machine()} -- counter={args.counter} "
              f"-- {len(recs)} identity file(s)\n")
        for r in recs:
            mark = "BLOCK" if r["blockers"] else "  ok "
            print(f"{mark}  {r['path']}")
            print(f"        name={r['name']!r} uri={r['uri']} recorded={r['recorded']}")
            print(f"        would mint as {r['lct_id']}  "
                  f"(web4_lct_id={r['web4_lct_id']!r})")
            for b in r["blockers"]:
                print(f"        - {b}")
            print()
        blocked = sum(1 for r in recs if r["blockers"])
        print(f"{blocked} blocked, {len(recs) - blocked} clear")

    return 1 if any(r["blockers"] for r in recs) else 0


if __name__ == "__main__":
    sys.exit(main())
