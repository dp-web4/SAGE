"""
Instance directory resolver for SAGE.

Single source of truth for finding instance directories. Every script and
the daemon should use InstancePaths to locate state files.

Resolution order:
    1. SAGE_INSTANCE env var (absolute path or slug name)
    2. SAGE_MACHINE + SAGE_MODEL → compute slug
    3. detect_machine() + default model from config → compute slug
    4. Fail with helpful message
"""

import os
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, List


# Instance root: sage/instances/
INSTANCES_ROOT = Path(__file__).parent


def model_to_slug(model: str) -> str:
    """Convert a model identifier to a filesystem-safe slug.

    Examples:
        'ollama:tinyllama:latest' → 'tinyllama-latest'
        'ollama:gemma3:12b'      → 'gemma3-12b'
        'ollama:qwen2:0.5b'      → 'qwen2-0.5b'
        'qwen2.5-0.5b'           → 'qwen2.5-0.5b'
        '/path/to/qwen2.5-14b/base-instruct' → 'qwen2.5-14b'
    """
    s = model
    # Strip ollama: prefix
    if s.startswith('ollama:'):
        s = s[len('ollama:'):]
    # If it's a filesystem path, extract the model name component
    if '/' in s:
        # Look for a recognizable model-size segment like 'qwen2.5-14b'
        parts = s.split('/')
        for part in parts:
            if any(size in part for size in ['0.5b', '1b', '3b', '4b', '7b', '12b', '14b', '30b', '70b']):
                s = part
                break
        else:
            # Fallback: use the last meaningful directory component
            s = parts[-1] if parts[-1] else parts[-2]
    # Replace colons with dashes for filesystem safety
    s = s.replace(':', '-')
    # Replace underscores with dashes for consistency
    s = s.replace('_', '-')
    return s.lower()


def make_slug(machine: str, model: str) -> str:
    """Compute instance slug from machine name and model identifier."""
    return f"{machine.lower()}-{model_to_slug(model)}"


# Default models per machine (mirrors machine_config.py)
_DEFAULT_MODELS = {
    'thor': 'qwen3.5:27b',
    'sprout': 'qwen3.8-distill:2b',  # 2026-08-28: upgraded frontal lobe (empero Qwen3.8-2B-Distill, reasoning+tools). Same being — identity/memory carried from sprout-qwen3.5-0.8b (retained for rollback).
    'legion': 'gemma3:12b',
    'mcnugget': 'gemma3:12b',
    'nomad': 'gemma3:4b',
    'cbp': 'qwen3.8-distill:4b',  # 2026-09-12: upgraded frontal lobe (empero Qwen3.8-4B-Distill, reasoning+tools). Same being — identity/memory carried from cbp-gemma3-4b (retained for rollback).
}


class InstancePaths:
    """All paths for a SAGE instance, computed from a single root directory."""

    def __init__(self, instance_dir: Path):
        self.root = Path(instance_dir)
        self.identity = self.root / "identity.json"
        self.experience_buffer = self.root / "experience_buffer.json"
        self.peer_trust = self.root / "peer_trust.json"
        self.peer_trust_rs = self.root / "peer_trust_rs.json"
        self.daemon_state = self.root / "daemon_state.json"
        self.chat_history = self.root / "chat_history.jsonl"
        self.latent_exploration_state = self.root / "latent_exploration_state.json"
        self.sessions = self.root / "sessions"
        self.training_sessions = self.root / "training" / "sessions"
        self.training_state = self.root / "training" / "state.json"
        self.notifications = self.root / "notifications.jsonl"
        self.checkpoints = self.root / "checkpoints"
        self.sleep_checkpoints = self.root / "checkpoints" / "sleep"
        self.dream_bundles = self.root / "dream_bundles"
        self.backups = self.root / "backups"
        self.manifest = self.root / "instance.json"

    @property
    def slug(self) -> str:
        return self.root.name

    def exists(self) -> bool:
        return self.root.is_dir() and self.manifest.exists()

    @property
    def snapshots(self) -> Path:
        return self.root / "snapshots"

    def ensure_dirs(self):
        """Create subdirectories if they don't exist."""
        self.sessions.mkdir(parents=True, exist_ok=True)
        self.training_sessions.mkdir(parents=True, exist_ok=True)
        self.backups.mkdir(parents=True, exist_ok=True)
        self.snapshots.mkdir(parents=True, exist_ok=True)

    def snapshot(self, max_snapshots: int = 10) -> Optional[Path]:
        """Snapshot live state files to a git-tracked snapshots/ directory.

        Copies identity.json, experience_buffer.json, peer_trust.json, and
        daemon_state.json into snapshots/ with a timestamp prefix. Old snapshots
        beyond max_snapshots are pruned.

        Returns the snapshot directory, or None if no state files exist.
        """
        state_files = [
            ("identity", self.identity),
            ("experience_buffer", self.experience_buffer),
            ("peer_trust", self.peer_trust),
            ("peer_trust_rs", self.peer_trust_rs),
            ("daemon_state", self.daemon_state),
            ("chat_history", self.chat_history),
        ]

        # Check if any state files exist
        existing = [(name, path) for name, path in state_files if path.exists()]
        if not existing:
            return None

        self.snapshots.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        for name, path in existing:
            try:
                if path.suffix == '.jsonl':
                    # JSONL: copy verbatim (line-delimited JSON)
                    dest = self.snapshots / f"{name}.jsonl"
                    shutil.copy2(path, dest)
                else:
                    # JSON: validate then pretty-print
                    with open(path) as f:
                        data = json.load(f)
                    dest = self.snapshots / f"{name}.json"
                    with open(dest, 'w') as f:
                        json.dump(data, f, indent=2)
            except (json.JSONDecodeError, IOError) as e:
                print(f"  WARN: Could not snapshot {path.name}: {e}")

        # Write snapshot metadata
        meta = {
            "timestamp": timestamp,
            "slug": self.slug,
            "files": [name for name, path in existing],
        }
        meta_path = self.snapshots / "latest.json"
        with open(meta_path, 'w') as f:
            json.dump(meta, f, indent=2)

        # Archive: keep timestamped copies for history (pruned to max_snapshots)
        archive_dir = self.snapshots / "archive"
        archive_dir.mkdir(exist_ok=True)
        for name, path in existing:
            if name == "identity":  # Only archive identity (others are too large)
                dest = archive_dir / f"{name}_{timestamp}.json"
                shutil.copy2(self.snapshots / f"{name}.json", dest)

        # Prune old archives
        archives = sorted(archive_dir.glob("identity_*.json"), reverse=True)
        for old in archives[max_snapshots:]:
            old.unlink()

        return self.snapshots

    @classmethod
    def resolve(cls, machine: Optional[str] = None, model: Optional[str] = None) -> 'InstancePaths':
        """Resolve instance directory from env vars or arguments.

        Resolution order:
            1. SAGE_INSTANCE env var (absolute path or slug)
            2. machine + model args (or SAGE_MACHINE + SAGE_MODEL env vars)
            3. detect_machine() + default model
            4. Fail with helpful message
        """
        # 1. SAGE_INSTANCE env var
        instance_env = os.environ.get('SAGE_INSTANCE')
        if instance_env:
            p = Path(instance_env)
            if p.is_absolute():
                return cls(p)
            # Treat as slug name
            return cls(INSTANCES_ROOT / instance_env)

        # 2. Explicit machine + model
        machine = machine or os.environ.get('SAGE_MACHINE')
        model = model or os.environ.get('SAGE_MODEL')

        # 3. Auto-detect machine
        if not machine:
            try:
                from sage.gateway.machine_config import detect_machine
                machine = detect_machine()
            except ImportError:
                pass

        if not machine or machine == 'unknown':
            raise RuntimeError(
                "Cannot resolve SAGE instance: no machine detected.\n"
                "Set SAGE_INSTANCE or SAGE_MACHINE environment variable, or run:\n"
                "  python3 -m sage.instances.init --machine <name> --model <model>"
            )

        # Resolve model from default if not given
        if not model:
            model = _DEFAULT_MODELS.get(machine)
        if not model:
            raise RuntimeError(
                f"Cannot resolve SAGE instance for machine '{machine}': no model specified.\n"
                "Set SAGE_MODEL environment variable or pass model= argument."
            )

        slug = make_slug(machine, model)
        instance_dir = INSTANCES_ROOT / slug

        # Fallback: if instance dir doesn't exist yet, return the path anyway
        # (caller can check .exists() and fall back to old paths during transition)
        return cls(instance_dir)

    @classmethod
    def list_instances(cls):
        """List all instance directories (excluding _seed)."""
        instances = []
        for d in sorted(INSTANCES_ROOT.iterdir()):
            if d.is_dir() and d.name != '_seed' and d.name != '__pycache__':
                paths = cls(d)
                if paths.manifest.exists():
                    instances.append(paths)
        return instances

    def __repr__(self):
        return f"InstancePaths({self.root})"
