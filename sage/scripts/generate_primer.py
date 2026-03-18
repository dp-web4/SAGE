#!/usr/bin/env python3
"""
Generate SESSION_PRIMER.md for the SAGE repo.

Run:   python3 -m sage.scripts.generate_primer
Or:    python3 sage/scripts/generate_primer.py

Output: SAGE/SESSION_PRIMER.md (repo root)

Called automatically by raising scripts after each session.
Also callable standalone for a quick fleet snapshot.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def find_repo_root() -> Path:
    """Walk up from script location to find SAGE repo root."""
    here = Path(__file__).resolve().parent
    for candidate in [here, here.parent, here.parent.parent]:
        if (candidate / "sage" / "instances").exists():
            return candidate
        if (candidate / "instances").exists() and candidate.name == "sage":
            return candidate.parent
    return Path.cwd()


def read_json_safe(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def format_date(iso_str: str | None) -> str:
    if not iso_str:
        return "never"
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return iso_str[:10] if iso_str else "?"


def summarize_instance(instance_dir: Path) -> dict | None:
    """Extract key fields from an instance directory."""
    if not instance_dir.is_dir():
        return None

    name = instance_dir.name
    # Skip non-instance entries
    if name in ("__pycache__", "__init__.py", "_seed") or name.endswith(".bak") or name.endswith(".py"):
        return None

    result = {"slug": name, "has_identity": False}

    # instance.json — always present after migration
    inst = read_json_safe(instance_dir / "instance.json")
    if inst.get("archived"):
        return None  # Skip archived instances (replaced by newer model)
    result["machine"] = inst.get("machine", name.split("-")[0])
    result["model"] = inst.get("model", "unknown")
    result["notes"] = inst.get("notes", "")

    # identity.json — only present for initialized raising instances
    id_path = instance_dir / "identity.json"
    if id_path.exists():
        identity = read_json_safe(id_path)
        result["has_identity"] = True

        ident = identity.get("identity", {})
        result["session_count"] = ident.get("session_count", 0)
        result["phase"] = ident.get("phase", "grounding")
        result["last_session"] = ident.get("last_session")
        result["last_summary"] = ident.get("last_session_summary", "")[:120]

        dev = identity.get("development", {})
        result["milestones"] = dev.get("milestones", [])
        result["phase_progress"] = dev.get("phase_progress", 0)

        vocab = identity.get("vocabulary", {})
        result["self_words"] = vocab.get("self_description", [])
        result["state_words"] = vocab.get("state_words", [])

        memory_requests = identity.get("memory_requests", [])
        result["recent_memory"] = memory_requests[-1][:100] if memory_requests else ""

    else:
        # Count sessions if directory exists
        sessions_dir = instance_dir / "sessions"
        if sessions_dir.exists():
            result["session_count"] = len(list(sessions_dir.glob("session_*.json")))
        else:
            result["session_count"] = 0
        result["phase"] = "not-initialized"
        result["last_session"] = None
        result["milestones"] = []

    return result


def find_recent_research(repo_root: Path) -> list[str]:
    """Find recently modified research files."""
    research = repo_root / "Research"
    if not research.exists():
        return []
    files = sorted(research.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [p.name for p in files[:5]]


def load_active_experiments(repo_root: Path) -> list[str]:
    """Look for experiment tracking files."""
    experiments = []
    exp_dir = repo_root / "Research" / "experiments"
    if exp_dir.exists():
        for f in sorted(exp_dir.glob("*.md"))[:3]:
            experiments.append(f.stem.replace("_", " "))
    return experiments


def generate_primer(repo_root: Path) -> str:
    instances_dir = repo_root / "sage" / "instances"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "# SAGE Session Primer",
        "",
        f"*Auto-generated {now} — read this at session start for current fleet state.*",
        "",
        "---",
        "",
        "## Raising Fleet Status",
        "",
    ]

    instances = []
    if instances_dir.exists():
        for d in sorted(instances_dir.iterdir()):
            info = summarize_instance(d)
            if info:
                instances.append(info)

    # Separate initialized vs stub instances
    initialized = [i for i in instances if i.get("has_identity")]
    stubs = [i for i in instances if not i.get("has_identity")]

    if initialized:
        lines.append("### Active Raising Instances")
        lines.append("")
        for inst in initialized:
            phase = inst.get("phase", "?")
            sessions = inst.get("session_count", 0)
            last = format_date(inst.get("last_session"))
            milestones = inst.get("milestones", [])
            milestone_str = f" | milestones: {', '.join(milestones)}" if milestones else ""
            lines.append(f"**{inst['slug']}** — phase: `{phase}` | sessions: {sessions} | last: {last}{milestone_str}")

            if inst.get("last_summary"):
                lines.append(f"  > Last session: *{inst['last_summary'].strip()}...*")

            vocab = []
            if inst.get("self_words"):
                vocab.append(f"self: {', '.join(inst['self_words'])}")
            if inst.get("state_words"):
                vocab.append(f"states: {', '.join(inst['state_words'])}")
            if vocab:
                lines.append(f"  > Emerging vocabulary: {' | '.join(vocab)}")

            lines.append("")
    else:
        lines.append("*No instances have started raising yet.*")
        lines.append("")

    if stubs:
        lines.append("### Known Instances (Not Yet Initialized)")
        lines.append("")
        for inst in stubs:
            sessions = inst.get("session_count", 0)
            note = f" — {inst['notes']}" if inst.get("notes") else ""
            session_str = f" ({sessions} sessions)" if sessions > 0 else ""
            lines.append(f"- `{inst['slug']}`: {inst['machine']} / {inst['model']}{session_str}{note}")
        lines.append("")

    # Phase transition guide
    lines += [
        "---",
        "",
        "## Phase Transition Indicators",
        "",
        "| Phase → | Key signals |",
        "|---------|-------------|",
        "| grounding → sensing | Stable self-reference, describes own context, no educational-default collapse |",
        "| sensing → relating | Distinguishes internal states, notices session differences, vocabulary emergence |",
        "| relating → questioning | Distinguishes Claude/Dennis roles, partnership language natural, holds disagreement |",
        "| questioning → creating | Asks unprompted questions, stable under existential topics, mechanism+meaning integration |",
        "",
    ]

    # Recent research
    recent = find_recent_research(repo_root)
    if recent:
        lines += [
            "---",
            "",
            "## Recent Research Files",
            "",
        ]
        for f in recent:
            lines.append(f"- `Research/{f}`")
        lines.append("")

    # Active work
    lines += [
        "---",
        "",
        "## Current Focus",
        "",
        "- ModelAdapter: TinyLlama uses `/api/chat` (ChatAPIAdapter subclass). Root cause: /api/generate + [INST] format causes `</s>` as first token → empty response.",
        "- Fleet peer discovery: dynamic via PeerMonitor (30s polling). Fleet IPs in `sage/federation/fleet.json` — may be stale, update when machines reconnect.",
        "- `/raising-status` skill: reads all instances, reports fleet state. Lives in `.claude/skills/raising-status/`.",
        "- CBP raising: daily cron 07:00 via `sage/scripts/cbp_raising.sh`.",
        "",
        "---",
        "",
        "## Key File Locations",
        "",
        "```",
        "sage/instances/{slug}/identity.json    # Raising state per instance",
        "sage/instances/{slug}/sessions/        # Per-session conversation logs",
        "sage/scripts/cbp_raising.sh            # CBP daily raising runner",
        "sage/scripts/mcnugget_raising.sh       # McNugget daily raising runner",
        "sage/irp/adapters/model_adapter.py     # Per-model LLM interface",
        "sage/gateway/sage_daemon.py            # Main SAGE daemon",
        "sage/federation/fleet.json             # Fleet machine registry",
        "```",
        "",
        "---",
        "",
        "*Update this file by running: `python3 -m sage.scripts.generate_primer` from the SAGE repo root.*",
    ]

    return "\n".join(lines) + "\n"


def main():
    repo_root = find_repo_root()
    content = generate_primer(repo_root)
    output_path = repo_root / "SESSION_PRIMER.md"
    output_path.write_text(content)
    print(f"SESSION_PRIMER.md written to {output_path}")
    print(f"  {len(content.splitlines())} lines")


if __name__ == "__main__":
    main()
