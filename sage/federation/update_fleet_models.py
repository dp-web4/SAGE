#!/usr/bin/env python3
"""
Update this machine's entry in sage-fleet-models.json.

Each machine runs this to register its current model, backend, and
LoRA capability. Called at the start of raising sessions or any time
the model configuration changes.

Usage:
    python3 -m sage.federation.update_fleet_models
    python3 -m sage.federation.update_fleet_models --model gemma3:4b --lora
    python3 -m sage.federation.update_fleet_models --dry-run
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_PATH = Path(__file__).parent / "sage-fleet-models.json"

# THE FILE THAT IS ACTUALLY READ. `sage-fleet-models.json` above is read by nothing
# but this script -- verified at code level 2026-09-14: the only grep hits outside
# forum posts are this file's own two references. `fleet.json` is the live registry:
# `sage-rs/sage-lib/src/federation/fleet.rs` loads it into the daemon, and the SAGE
# explainer site links it as "Fleet manifest", inviting readers to verify against it.
#
# That invitation was being answered with a document frozen on 2026-03-12, which said
# McNugget ran gemma3:12b six months after it stopped. Four of eight rows disagreed
# with the site (cbp, 2026-09-12) and the SITE was the correct one -- so a reader who
# accepted our invitation to check concluded we were wrong about half our own fleet.
#
# This script was written 2026-03-08 to prevent exactly that, and was never wired to
# anything. Writing the file nobody reads is why being unwired went unnoticed.
FLEET_JSON_PATH = Path(__file__).parent / "fleet.json"


def detect_machine() -> str:
    """Detect current machine name from SAGE machine config."""
    try:
        from sage.gateway.machine_config import detect_machine as _detect
        return _detect()
    except ImportError:
        import os
        return os.environ.get("SAGE_MACHINE", "unknown")


def detect_backend() -> str:
    """Detect whether ollama or transformers is the primary backend.

    Asks the ollama SERVER, not the PATH. Bare `ollama list` was the original
    check and it answers a different question: "is the CLI on this PATH". Under
    launchd the PATH is /usr/bin:/bin, so a box that has been serving ollama for
    months reports `transformers` and this file records the flip -- measured here
    2026-09-14 while wiring this into the raising loop, which is exactly where the
    stripped PATH applies. Same defect that killed raising for 29 days when
    /opt/homebrew/bin/python3 went missing: a PATH lookup standing in for a fact.
    """
    import urllib.request
    host = os.getenv("SAGE_OLLAMA_HOST", "http://127.0.0.1:11434")
    try:
        with urllib.request.urlopen(host + "/api/version", timeout=3) as r:
            if r.status == 200:
                return "ollama"
    except Exception:
        pass
    # Fall back to the CLI, absolute paths included, before giving up on ollama.
    for exe in ("ollama", "/usr/local/bin/ollama", "/opt/homebrew/bin/ollama"):
        try:
            import subprocess
            if subprocess.run([exe, "list"], capture_output=True, timeout=5).returncode == 0:
                return "ollama"
        except Exception:
            continue
    try:
        import transformers  # noqa
        return "transformers"
    except ImportError:
        pass
    return "unknown"


def detect_transformers_available() -> bool:
    try:
        import transformers  # noqa
        return True
    except ImportError:
        return False


def detect_os() -> str:
    """Detect OS: WSL2, macOS, or Linux (Ubuntu)."""
    import platform
    if platform.system() == "Darwin":
        return "macOS"
    # Check for WSL2
    try:
        with open("/proc/version") as f:
            if "microsoft" in f.read().lower():
                return "WSL2 (Ubuntu on Windows)"
    except Exception:
        pass
    return "Linux (Ubuntu)"


def detect_lora_capable() -> bool:
    """LoRA requires transformers + peft."""
    try:
        import transformers  # noqa
        import peft  # noqa
        return True
    except ImportError:
        return False


def detect_current_model(machine: str) -> tuple[str, str]:
    """Returns (model_id, model_display) from machine config or ollama."""
    try:
        from sage.gateway.machine_config import get_machine_config
        cfg = get_machine_config(machine)
        model = cfg.get("model", "unknown")
        # Strip 'ollama:' prefix if present
        model_id = model.replace("ollama:", "")
        # Display: capitalize and format nicely
        model_display = model_id.replace(":", " ").replace("-", " ").title()
        return model_id, model_display
    except Exception:
        return "unknown", "Unknown"


def detect_observed_model(machine: str) -> "tuple[str, str] | None":
    """What this machine ACTUALLY ran, from the record rather than from config.

    `detect_current_model` below asks `machine_config`, which is a statement of
    intent: it says what this box is configured to run. That is the right answer
    right up until a switch lands somewhere else and the config is the thing that
    was missed -- which is what happened on McNugget, whose switch to gemma4:12b on
    2026-09-08 updated the instance record, the launchd unit and the sessions, and
    left two manifests behind saying gemma3.

    So this prefers evidence over declaration, in order:

      1. the newest session record's `model` -- what the loop actually ran;
      2. the instance record's `model` -- what the next session will use;
      3. $SAGE_MODEL -- what the supervisor was told to use.

    Returns None if none can be read, so the caller falls back to config rather
    than this function inventing an answer.
    """
    import os
    root = Path(__file__).resolve().parents[2]
    inst_dir = root / "sage" / "instances"

    # The instance DIRECTORY NAME is not the model. McNugget's is
    # `mcnugget-gemma3-12b` and has run gemma4 since 09-08, because 461 sessions of
    # history hang off that path and renaming it would orphan them. So resolve the
    # instance by pin or by newest session record, never by parsing its name.
    #
    # The pin is the real answer: the raising loop knows which folder it writes to and
    # should pass it. The fallback used to be "the folder with the most sessions", which
    # picks the OLD model after a switch to a fresh folder that restarts at session 1
    # (sprout, 2026-09-14). It is now "the folder holding the newest session record",
    # by the record's own `start` -- local naive time, comparable within one machine,
    # which is the only comparison made here. mtime is not used: a checkout resets it.
    pin = os.getenv("SAGE_INSTANCE")
    cand = None
    newest = None
    if pin and (inst_dir / pin).is_dir():
        cand = inst_dir / pin
        newest = _newest_session(cand / "sessions")
    elif inst_dir.is_dir():
        owned = [d for d in inst_dir.iterdir()
                 if d.is_dir() and d.name.startswith(machine + "-")]
        found = [(n, d) for d in owned for n in [_newest_session(d / "sessions")] if n]
        if found:
            newest, cand = max(found, key=lambda nd: nd[0][1].get("start") or "")
        elif len(owned) == 1:
            cand = owned[0]
    if newest:
        path, rec = newest
        if rec.get("model"):
            return rec["model"], path.name + " (newest session record)"
    if cand:
        ij = cand / "instance.json"
        if ij.is_file():
            try:
                m = json.loads(ij.read_text()).get("model")
                if m:
                    return m, "instance.json"
            except Exception:
                pass

    m = os.getenv("SAGE_MODEL")
    if m:
        return m, "$SAGE_MODEL"
    return None


def _newest_session(sess: Path) -> "tuple[Path, dict] | None":
    """Highest-NUMBERED session record in a sessions/ dir, parsed.

    Numeric, not lexicographic: writers name files `session_{n:03d}`, so from 1000 on
    `sorted()` puts session_1000.json before session_999.json and the newest record
    would silently freeze at 999 (sprout, 2026-09-14; sprout reaches 1000 in ~75 days).
    """
    import re
    if not sess.is_dir():
        return None
    nums = []
    for f in sess.glob("session_*.json"):
        mt = re.fullmatch(r"session_(\d+)\.json", f.name)
        if mt:
            nums.append((int(mt.group(1)), f))
    for _, f in sorted(nums, reverse=True):
        try:
            rec = json.loads(f.read_text())
        except Exception:
            continue
        if isinstance(rec, dict):
            return f, rec
    return None


def update_fleet_json(machine: str, model_id: str, dry_run: bool = False) -> "bool | None":
    """Set this machine's `model_default` in the registry the daemon and site read.

    Touches exactly one field of one machine's entry and preserves the rest in key
    order, because every other row here belongs to a seat that is not this one.
    Writes temp-and-rename so the daemon, which loads this file at startup, never
    sees a half-written registry.

    Returns True if changed, False if already correct, None if it could not run --
    "already right" and "could not check" must not share a return value.
    """
    if not FLEET_JSON_PATH.exists():
        print("  fleet.json not found at " + str(FLEET_JSON_PATH) + "; skipping",
              file=sys.stderr)
        return None
    import collections, os, tempfile
    data = json.loads(FLEET_JSON_PATH.read_text(),
                      object_pairs_hook=collections.OrderedDict)
    machines = data.get("machines")
    if not isinstance(machines, dict) or machine not in machines:
        print("  '" + machine + "' has no entry in fleet.json; refusing to invent one",
              file=sys.stderr)
        return None
    cur = machines[machine].get("model_default")
    if cur == model_id:
        print("  fleet.json: model_default already " + str(model_id))
        return False
    print("  fleet.json: model_default " + repr(cur) + " -> " + repr(model_id))
    if dry_run:
        return True
    machines[machine]["model_default"] = model_id
    fd, tmp = tempfile.mkstemp(dir=str(FLEET_JSON_PATH.parent), suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        f.write(json.dumps(data, indent=2) + "\n")
    os.replace(tmp, FLEET_JSON_PATH)
    return True


def git_push(manifest_path: Path):
    """Commit and push the updated manifest."""
    repo_root = manifest_path.parent
    while repo_root != repo_root.parent:
        if (repo_root / ".git").exists():
            break
        repo_root = repo_root.parent

    rel_path = manifest_path.relative_to(repo_root)

    try:
        subprocess.run(["git", "add", str(rel_path)], cwd=repo_root, check=True)
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=repo_root, capture_output=True
        )
        if result.returncode == 0:
            print("  No changes to commit.")
            return

        machine = detect_machine()
        subprocess.run(
            ["git", "commit", "-m", f"fleet-models: {machine} updated model entry"],
            cwd=repo_root, check=True
        )
        subprocess.run(["git", "push"], cwd=repo_root, check=True)
        print("  Pushed to remote.")
    except subprocess.CalledProcessError as e:
        print(f"  Git operation failed: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Update this machine's fleet model entry")
    parser.add_argument("--machine", help="Machine name (auto-detected if omitted)")
    parser.add_argument("--model", help="Model ID (e.g. gemma3:4b)")
    parser.add_argument("--model-display", help="Human-readable model name")
    parser.add_argument("--backend", choices=["ollama", "transformers"], help="Inference backend")
    parser.add_argument("--lora", action="store_true", help="Mark as LoRA-capable")
    parser.add_argument("--no-lora", action="store_true", help="Mark as not LoRA-capable")
    parser.add_argument("--lora-plugins", nargs="*", default=None, help="LoRA plugin names")
    parser.add_argument("--notes", help="Inference notes")
    parser.add_argument("--role", help="Machine role description")
    parser.add_argument("--no-push", action="store_true", help="Update file but don't push")
    parser.add_argument("--dry-run", action="store_true", help="Print what would change, don't write")
    args = parser.parse_args()

    machine = args.machine or detect_machine()
    print(f"Updating fleet models entry for: {machine}")
    if machine == "unknown":
        # fleet.json already refuses this; the legacy file used to grow an `unknown` row.
        print("ERROR: could not detect this machine; refusing to register", file=sys.stderr)
        sys.exit(1)

    # Load manifest
    if not MANIFEST_PATH.exists():
        print(f"ERROR: Manifest not found at {MANIFEST_PATH}", file=sys.stderr)
        sys.exit(1)

    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)

    if machine not in manifest["machines"]:
        print(f"WARNING: '{machine}' not in manifest. Creating new entry.")
        manifest["machines"][machine] = {}

    entry = manifest["machines"][machine]

    # Auto-detect what wasn't specified
    backend = args.backend or detect_backend()
    transformers_avail = detect_transformers_available()
    lora_capable = args.lora or (not args.no_lora and detect_lora_capable())

    if args.model:
        model_id = args.model
        model_display = args.model_display or model_id.replace(":", " ").title()
    else:
        # Evidence first, declaration second. `detect_current_model` reads the
        # machine config, which states intent; a switch that lands in the instance
        # record and the launchd unit but not the config leaves it confidently wrong.
        observed = detect_observed_model(machine)
        if observed:
            model_id, basis = observed
            model_display = model_id.replace(":", " ").title()
            print("  observed model: " + model_id + "  (basis: " + basis + ")")
        else:
            model_id, model_display = detect_current_model(machine)
            print("  no observed record; fell back to machine_config: " + model_id)
        if args.model_display:
            model_display = args.model_display

    updates = {
        "model": model_id,
        "model_display": model_display,
        "backend": backend,
        "transformers_available": transformers_avail,
        "lora_capable": lora_capable,
    }
    if args.lora_plugins is not None:
        updates["lora_plugins"] = args.lora_plugins
    elif "lora_plugins" not in entry:
        updates["lora_plugins"] = []
    if args.notes is not None:
        updates["inference_notes"] = args.notes
    elif "inference_notes" not in entry:
        updates["inference_notes"] = ""
    if args.role is not None:
        updates["role"] = args.role
    if "os" not in entry:
        # Only when absent: detect_os() is coarse, and rewriting a hand-written
        # "JetPack/Ubuntu 20.04" as "Linux (Ubuntu)" every session loses the detail.
        updates["os"] = detect_os()

    # The registry the daemon and the site actually read. Done BEFORE the legacy
    # file below, and a failure here exits non-zero without touching it, so it is
    # not masked by a successful write to the document nobody consumes.
    if update_fleet_json(machine, model_id, dry_run=args.dry_run) is None:
        sys.exit(1)

    # Show diff
    changes = {k: (entry.get(k), v) for k, v in updates.items() if entry.get(k) != v}
    if not changes:
        # No write at all, timestamp included: this runs every raising session and a
        # supervisor commits the tree, so a fresh `updated_at` alone is a junk commit
        # per session per seat.
        print("  No changes detected.")
        return
    print("  Changes:")
    for k, (old, new) in changes.items():
        print(f"    {k}: {old!r} -> {new!r}")

    if args.dry_run:
        print("  (dry-run, not writing)")
        return

    updates["updated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    updates["updated_by"] = machine
    entry.update(updates)
    manifest["machines"][machine] = entry

    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"  Written to {MANIFEST_PATH}")

    if not args.no_push:
        git_push(MANIFEST_PATH)


if __name__ == "__main__":
    main()
