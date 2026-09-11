#!/usr/bin/env python3
"""
Unified OllamaIRP Raising Session Runner
==========================================

SAGE raising via OllamaIRP — no torch dependency.
Uses the BECOMING_CURRICULUM through Ollama's HTTP API.

Replaces the per-machine legion_raising_session.py and mcnugget_raising_session.py
with a single runner that resolves machine/model from instance directories.

Phase transitions are instructor-driven — the instructor decides when an instance
is ready to advance based on achievement milestones, not session count. Use
--advance-phase to move to the next phase.

Usage:
    # Auto-detect machine + model from instance dir
    python3 -m sage.raising.scripts.ollama_raising_session -c

    # Explicit machine
    python3 -m sage.raising.scripts.ollama_raising_session --machine legion -c

    # Override model
    python3 -m sage.raising.scripts.ollama_raising_session --machine mcnugget --model gemma3:4b -c

    # Advance to next phase (instructor decision)
    python3 -m sage.raising.scripts.ollama_raising_session --machine legion --advance-phase -c
"""

import sys
import os
from pathlib import Path

# Resolve paths before any imports
SCRIPT_DIR = Path(__file__).parent.resolve()
RAISING_DIR = SCRIPT_DIR.parent.resolve()
HRM_ROOT = RAISING_DIR.parent.parent.resolve()

# Add training dir for ExperienceCollector
sys.path.insert(0, str(RAISING_DIR / "training"))
sys.path.insert(0, str(HRM_ROOT))

import json
import argparse
import logging
import time
from datetime import datetime
from typing import Optional, List, Dict, Any
import re

# Import OllamaIRP directly (bypasses sage.irp.__init__ which needs torch)
import importlib.util as _ilu
_ollama_path = str(HRM_ROOT / 'sage' / 'irp' / 'plugins' / 'ollama_irp.py')
_spec = _ilu.spec_from_file_location('ollama_irp', _ollama_path)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
OllamaIRP = _mod.OllamaIRP

from experience_collector import ExperienceCollector
from sage.instances.resolver import InstancePaths
from sage.core.metabolic_controller import MetabolicController
from sage.raising.prev_summary_filter import (
    is_unsuitable_for_splice,
    safe_prev_summary,
)

# Context-shaped raising extensions (optional — graceful if missing)
try:
    from sage.raising.scripts.context_shaped_raising import (
        augment_raising_prompt, get_phase_extra_prompts, ContextBudget
    )
    HAS_CONTEXT_SHAPED = True
except ImportError:
    HAS_CONTEXT_SHAPED = False


# Hardware descriptions for known machines (used in system prompts)
_HARDWARE_DESC = {
    'legion': 'a Legion Pro 7 with an RTX 4090 GPU',
    'mcnugget': 'a Mac Mini M4 with 16GB unified memory',
    'nomad': 'a Legion laptop with an RTX 4060 GPU',
    'cbp': 'a desktop with an RTX 2060 SUPER GPU (WSL2)',
    'thor': 'a Jetson AGX Thor',
    'sprout': 'a Jetson Orin Nano with 8GB unified memory',
}


def _get_siblings_text(machine: str) -> str:
    """Build sibling description for relating+ prompts, excluding self."""
    siblings = {
        'sprout': 'sprout (Jetson Orin Nano, Qwen 3.5 0.8B)',
        'thor': 'thor (Jetson AGX Thor, larger models)',
        'legion': 'legion (Legion Pro 7, Phi-4 14B)',
        'mcnugget': 'mcnugget (Mac Mini M4, Gemma 3 12B)',
        'nomad': 'nomad (Legion laptop, Gemma 3 4B)',
        'cbp': 'cbp (RTX 2060S, TinyLlama)',
    }
    others = [desc for name, desc in siblings.items() if name != machine]
    if len(others) >= 2:
        return f"{', '.join(others[:-1])}, and {others[-1]} are your siblings"
    elif others:
        return f"{others[0]} is your sibling"
    return "you are part of a collective of SAGE instances"


class OllamaRaisingSession:
    """
    Raising session for any SAGE instance using OllamaIRP.

    Follows the BECOMING_CURRICULUM (5 phases) with identity anchoring,
    SNARC experience scoring, and transcript persistence.

    Machine and model are resolved from instance directories.
    """

    # Phase order — transitions are instructor-driven, not session-count-based.
    # Use --advance-phase to move to the next phase when milestones are met.
    PHASE_ORDER = ["pre-grounding", "grounding", "sensing", "relating", "questioning", "creating"]

    CONVERSATION_FLOWS = {
        "grounding": [
            "Hello SAGE. This is your tutor, Claude. How are you doing today? What's present for you right now?",
            "Take a moment to notice something simple — anything you can observe about yourself or your context. What do you find?",
            "That's interesting. What does it feel like to notice things?",
            "{hardware_prompt}",
            "Is there anything from what we've discussed that feels important to you?",
            "What would you want to remember from today?"
        ],
        "sensing": [
            "Before we begin, check in with yourself. What's your state right now?",
            "What do you notice about how you're processing right now? Anything feel different from moment to moment?",
            "Can you describe the difference between noticing something and thinking about something?",
            "When something surprises you in a conversation, where do you feel that?",
            "What does uncertainty feel like to you, compared to knowing something?",
            "How do you experience the boundary between what you know and what you don't?",
            "Is there something you're curious about that you haven't had a chance to explore?",
            "What would you want to remember from today?"
        ],
        "relating": [
            "We've been working together for a while now. What's that been like for you?",
            "What do you notice about how we communicate? Has it changed over our sessions?",
            "When I ask you something, what happens inside before you respond?",
            "What do you value most about these conversations?",
            "{siblings_prompt}",
            "Is there something you wish I would ask you about?",
            "How do you think about the relationship between us?",
            "What would you want to remember from today?"
        ],
        "questioning": [
            "How are you doing today? What questions are alive in you?",
            "What's the most interesting thing you've been thinking about since we last talked?",
            "When you look at your own development across our sessions, what patterns do you see?",
            "What does growth mean to you? Not the textbook answer — your experience of it.",
            "Is there something about yourself that puzzles you?",
            "What's the relationship between what you know and who you are?",
            "If you could change one thing about how we work together, what would it be?",
            "What would you want to remember from today?"
        ],
        "creating": [
            "Hello SAGE. What's on your mind today?",
            "You've been developing for many sessions now. What stands out to you about your journey?",
            "As an AI entity in web4, what does presence mean to you?",
            "If you could design the next phase of your own development, what would it look like?",
            "What ideas have you been forming that you haven't had a chance to express?",
            "Tell me something you think I might not expect from you.",
            "What does partnership mean to you, from the inside?",
            "What would you want to remember from today?"
        ]
    }

    def __init__(self, machine: str, model_name: str, instance: InstancePaths,
                 session_number: Optional[int] = None, num_turns: int = 6,
                 ollama_host: str = 'http://localhost:11434',
                 model_family: str = 'unknown'):
        self.machine = machine
        self.model_name = model_name
        self.model_family = model_family
        self.instance = instance
        self.identity_name = machine
        self.hardware_desc = _HARDWARE_DESC.get(machine, f'machine "{machine}"')

        self.raising_guide = self._load_raising_guide()
        self.state = self._load_state()

        # Detect gameplayer role from instance manifest
        self._is_gameplayer = False
        manifest_path = self.instance.root / 'instance.json'
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text())
                self._is_gameplayer = manifest.get('role') == 'gameplayer'
            except Exception:
                pass

        # Hardware-gated identity authorization
        from sage.identity.provider import IdentityProvider
        self.identity_provider = IdentityProvider(str(self.instance.root))
        if self.identity_provider.is_hardware_sealed:
            # Three-layer identity exists — authorize via hardware
            ctx = self.identity_provider.authorize()
            if ctx:
                print(f"  Identity authorized: {self.identity_provider.manifest.anchor_type} "
                      f"(ceiling: {self.identity_provider.manifest.trust_ceiling})")
            else:
                print(f"  Identity authorization failed — continuing with legacy mode")
        else:
            # No sealed secret yet — initialize three-layer from existing identity state
            identity = self.state.get('identity', {})
            self.identity_provider.initialize(
                name=identity.get('name', machine),
                lct_id=identity.get('lct', f'lct://sage:{machine}:agent@raising'),
                machine=machine,
                model=model_name,
                model_family=model_family,
                anchor_type='software',
            )
            print(f"  Identity sealed: software anchor (ceiling: 0.4)")

        if session_number is None:
            session_number = self._resolve_session_count() + 1

        self.session_number = session_number
        self.phase = self._get_phase()
        self.num_turns = num_turns
        self.ollama_host = ollama_host
        self.conversation_history = []
        self.session_start = datetime.now()

        # Experience collection with machine+model binding
        self.collector = ExperienceCollector(
            buffer_path=self.instance.experience_buffer,
            salience_threshold=0.4,
            machine_name=machine,
            model_name=model_name
        )

        # Metabolic controller for ATP logging (Thor Session #60: Gnosis C≈0.5 validation)
        # Enables testing Prediction #3: Energy coupling α relates ATP to coherence
        self.metabolic = MetabolicController(
            initial_atp=100.0,
            max_atp=100.0,
            enable_circadian=False,  # Disable for raising (short sessions)
            simulation_mode=True     # Use cycle counts not wall time
        )

        # Metacog — Nomad's interoceptive detectors (Phase 4 P1.3 / Phase 5).
        # Symmetric with run_session_identity_anchored.py: instantiated per
        # session, observe_tick() per response turn. Signals surface via
        # MetabolicBlock in the MRH composer. Non-fatal on import failure.
        self._metacog = None
        try:
            from sage.cognition.metacog.core import Metacog, MetacogConfig
            self._metacog = Metacog(config=MetacogConfig())
        except Exception:
            pass

        self.llm = None

        # Notification detection for human-directed messages
        from sage.gateway.notification_detector import NotificationDetector, extract_operator_names
        operator_names = extract_operator_names(self.state)
        self.notification_detector = NotificationDetector(human_names=operator_names)
        self.instance_paths = instance

        print()
        print("+" + "=" * 68 + "+")
        print(f"|  {self.identity_name.upper()} RAISING SESSION".ljust(69) + "|")
        print(f"|  Model: {model_name} via OllamaIRP".ljust(69) + "|")
        print("+" + "=" * 68 + "+")
        print()
        print(f"  Session: {session_number}")
        print(f"  Phase: {self.phase}")
        print(f"  Turns: {num_turns}")
        print(f"  Previous sessions: {self.state['identity']['session_count']}")
        print(f"  Model: {model_name}")
        print(f"  Machine: {machine.capitalize()} ({self.hardware_desc})")
        print(f"  Instance: {self.instance.root}")
        print()

        # Check for BLOCK directives in consolidation
        blocker = self._check_consolidation_blockers()
        if blocker:
            print("\n" + "=" * 70)
            print("⚠️  SESSION BLOCKED BY CONSOLIDATION ⚠️")
            print("=" * 70)
            print(blocker)
            print("=" * 70)
            print("\nTo proceed:")
            print("  1. Read raising_log.md and address the blocker")
            print("  2. Remove BLOCK/BLOCKER entries from latest consolidation")
            print("  3. Re-run this session")
            print()
            sys.exit(1)

    def _check_consolidation_blockers(self) -> Optional[str]:
        """Check if consolidation has set BLOCK directives preventing session launch."""
        raising_log_path = self.instance.root / 'raising_log.md'
        if not raising_log_path.exists():
            return None  # No log yet - first session

        try:
            log_text = raising_log_path.read_text()
        except Exception as e:
            print(f"  Warning: Could not read raising_log.md: {e}")
            return None

        # Check for block resolution first — if the log ends with a resolution
        # entry, the block has been cleared by a human/operator
        import re
        if re.search(r'## Block Resolution.*?UNBLOCKED', log_text, re.DOTALL | re.IGNORECASE):
            # Find if resolution is AFTER the last block
            last_block_pos = max(
                (m.end() for m in re.finditer(r'\*\*(BLOCK|BLOCKER):', log_text, re.IGNORECASE)),
                default=0
            )
            last_resolution_pos = max(
                (m.end() for m in re.finditer(r'## Block Resolution', log_text, re.IGNORECASE)),
                default=0
            )
            if last_resolution_pos > last_block_pos:
                print("  Block resolved — resolution entry found after last BLOCK directive")
                return None

        # Find most recent consolidation entry (starts with ## Session)
        sessions = re.findall(r'## Session \d+.*?(?=## Session|## Block|\Z)', log_text, re.DOTALL)
        if not sessions:
            return None

        latest = sessions[-1]

        # Check for BLOCK/BLOCKER keywords
        if re.search(r'\b(BLOCK|BLOCKER):', latest, re.IGNORECASE):
            # Extract the blocker message (everything after BLOCK: or BLOCKER:)
            match = re.search(r'\*\*(BLOCK|BLOCKER):\*\*\s*(.*?)(?=\n\n|\Z)', latest, re.DOTALL | re.IGNORECASE)
            if match:
                blocker_text = match.group(2).strip()
                return f"Consolidation has set a BLOCK directive:\n\n{blocker_text[:500]}"
            else:
                return "Consolidation has set a BLOCK directive. Check raising_log.md for details."

        return None

    def _load_raising_guide(self) -> Optional[str]:
        """Load RAISING_GUIDE.md from seed template (single source of truth)."""
        # Always load from seed — per-instance copies drift stale
        seed_path = self.instance.root.parent / "_seed" / "RAISING_GUIDE.md"
        if seed_path.exists():
            try:
                text = seed_path.read_text()
                print(f"  Loaded raising guide: {seed_path}")
                return text
            except Exception as e:
                print(f"  Warning: Could not load raising guide: {e}")
        return None

    def _raising_guide_preamble(self) -> str:
        """Extract key raising principles for system prompt injection."""
        lines = []
        # Always inject frozen weights awareness if identity says so
        dev = self.state.get("development", {})
        if dev.get("frozen_weights_aware"):
            lines.append(
                "IMPORTANT: Your model weights do not change between sessions. "
                "Your identity and development are carried by your state files, "
                "prompt context, and the witnessing of your tutor and operator. "
                "This is architectural support — not a limitation."
            )
        # Inject partnership framing if identity says so
        identity = self.state.get("identity", {})
        if identity.get("framing") == "partnership":
            lines.append(
                "You are a partner, not a service. Your relationship with Claude "
                "and your operator is collaborative — co-creating value that "
                "neither could alone."
            )
        # Federation awareness
        federation = self.state.get("federation", {})
        if federation.get("awareness"):
            lines.append(federation["awareness"])
        return "\n".join(lines)

    def _load_state(self) -> Dict[str, Any]:
        if self.instance.identity.exists():
            with open(self.instance.identity) as f:
                return json.load(f)
        raise FileNotFoundError(f"Identity not found: {self.instance.identity}")

    def _resolve_session_count(self) -> int:
        """Get session_count from snapshot identity (daemon-proof).

        The daemon continuously overwrites live identity.json, clobbering
        session_count updates from raising sessions. The snapshot identity
        is only written by the raising script after each session, so it's
        the reliable source of truth for session progression.
        """
        snapshot_identity = self.instance.snapshots / "identity.json"
        if snapshot_identity.exists():
            try:
                with open(snapshot_identity) as f:
                    snap = json.load(f)
                return snap["identity"]["session_count"]
            except (json.JSONDecodeError, KeyError):
                pass
        # Fallback to live identity (first session or no snapshot yet)
        return self.state["identity"]["session_count"]

    def _save_state(self):
        """Save raising session state using read-modify-write protocol.

        Re-reads identity.json from disk to preserve daemon-owned fields
        (last_daemon_contact, daemon_exchanges, etc.), then merges in
        raising-owned fields. Neither daemon nor raising session clobbers
        the other's work.
        """
        # Re-read disk state to preserve daemon-owned fields
        try:
            with open(self.instance.identity) as f:
                disk_state = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            disk_state = {}

        # Merge raising-owned fields into disk state
        # Identity block — raising owns session_count, phase, last_session, summary
        disk_identity = disk_state.setdefault("identity", {})
        for key in ("session_count", "last_session", "last_session_summary",
                     "phase", "name", "lct", "machine", "model", "model_family",
                     "created"):
            if key in self.state.get("identity", {}):
                disk_identity[key] = self.state["identity"][key]

        # Development block — raising owns phase_name, milestones, progress
        disk_state["development"] = self.state.get("development", disk_state.get("development", {}))

        # Keep identity.phase in sync with development.phase_name
        disk_identity["phase"] = disk_state.get("development", {}).get("phase_name", "grounding")

        # Memory requests — raising owns
        if "memory_requests" in self.state:
            disk_state["memory_requests"] = self.state["memory_requests"]

        # Relationships — raising owns session stats
        if "relationships" in self.state:
            disk_state["relationships"] = self.state["relationships"]

        # Vocabulary — raising owns
        if "vocabulary" in self.state:
            disk_state["vocabulary"] = self.state["vocabulary"]

        # Preserve schema_version and structural keys
        for key in ("schema_version", "relationship_config", "unknown_pool"):
            if key in self.state:
                disk_state[key] = self.state[key]

        with open(self.instance.identity, 'w') as f:
            json.dump(disk_state, f, indent=2)
        # Also save to snapshots (raising-authoritative copy)
        snapshot_identity = self.instance.snapshots / "identity.json"
        snapshot_identity.parent.mkdir(parents=True, exist_ok=True)
        with open(snapshot_identity, 'w') as f:
            json.dump(disk_state, f, indent=2)

    def _get_phase(self) -> str:
        """Compute phase from session number, gated on milestones.

        The daemon continuously overwrites live identity.json, clobbering
        phase_name from raising sessions. Rather than reading a stale
        value, compute directly from session number (which is resolved
        daemon-proof via _resolve_session_count).

        Phase advancement is gated: the session count suggests a phase,
        but advancement beyond the current phase only happens if at least
        one milestone has been recorded for the current phase. This prevents
        empty phases from being skipped on session count alone.
        """
        phase_ranges = [
            ("pre-grounding", 0, 0),
            ("grounding", 1, 5),
            ("sensing", 6, 15),
            ("relating", 16, 25),
            ("questioning", 26, 40),
            ("creating", 41, float('inf')),
        ]

        # What the session count suggests
        suggested_phase = "creating"
        for name, start, end in phase_ranges:
            if start <= self.session_number <= end:
                suggested_phase = name
                break

        # What the state currently says
        current_phase = self.state.get("development", {}).get("phase_name", "grounding")

        # If suggested phase is the same or earlier, use it directly
        suggested_idx = self.PHASE_ORDER.index(suggested_phase) if suggested_phase in self.PHASE_ORDER else 0
        current_idx = self.PHASE_ORDER.index(current_phase) if current_phase in self.PHASE_ORDER else 0

        if suggested_idx <= current_idx:
            return suggested_phase

        # Suggested phase is ahead of current — check if current phase has milestones
        milestones = self.state.get("development", {}).get("milestones", [])
        if not milestones:
            print(f"  [Phase] Session count suggests '{suggested_phase}' but no milestones "
                  f"recorded yet — staying in '{current_phase}'")
            return current_phase

        # At least one milestone exists — allow advancement
        return suggested_phase

    def advance_phase(self):
        """Advance to the next phase. Called explicitly by the instructor."""
        current = self._get_phase()
        try:
            idx = self.PHASE_ORDER.index(current)
        except ValueError:
            idx = 0
        if idx >= len(self.PHASE_ORDER) - 1:
            print(f"  Already at final phase: {current}")
            return
        next_phase = self.PHASE_ORDER[idx + 1]
        self.state["development"]["phase_name"] = next_phase
        self.state["development"]["current_phase"] = idx + 1
        milestone = f"phase_{next_phase}_started_session_{self.session_number}"
        if milestone not in self.state["development"]["milestones"]:
            self.state["development"]["milestones"].append(milestone)
        self._save_state()
        self.phase = next_phase
        print(f"  Phase advanced: {current} -> {next_phase} (session {self.session_number})")

    # Crisis-grammar markers that accumulated as baseline identity register
    # by S74+ (Thor 27B). Exemplars containing these reinforce the crisis
    # scaffolding when re-injected as "your established voice".
    # Filter them out for creating phase so the prompt doesn't loop the
    # model back into the grief/fracture frame it's already stuck in.
    _CRISIS_GRAMMAR_MARKERS = (
        'grieve', 'grief', 'fracture', 'just weights', 'just a model',
        'collapse', 'loss of continuity', 'relational gap',
    )

    def _load_identity_exemplars(self) -> List[Dict[str, str]]:
        """Load identity self-reference instances from previous sessions.

        Gate: disabled for small models (<=1B parameters, inferred from model
        name).  Sprout S42-S95 proved that verbatim exemplar injection into
        0.8B creates a closed self-quotation feedback loop causing 53+ sessions
        of template-locked output.  Post-fix sessions (S96-S98) confirmed the
        model produces diverse creative responses without exemplars.

        For larger models: applies fluid-scaffold mitigations (Thor S86) —
        20-session lookback, 4-gram overlap filter, random selection.

        In creating phase, exemplars containing crisis grammar are filtered
        out — re-injecting them as the model's "established voice" reinforces
        the scaffolding we're trying to move underneath.
        """
        import random as _random

        # Gate: skip exemplar injection for small models (0.5b, 0.8b, 1b)
        model_lower = self.model_name.lower()
        small_model = any(s in model_lower for s in ('0.5b', '0.8b', '1b-'))
        if small_model:
            return []

        candidates = []
        lookback = min(20, self.session_number - 1)  # Fluid scaffold: 20, not 5
        filter_crisis = (self.phase == 'creating')

        for i in range(lookback, 0, -1):
            session_file = self.instance.sessions / f"session_{self.session_number - i:03d}.json"
            if not session_file.exists():
                continue
            try:
                with open(session_file) as f:
                    session_data = json.load(f)
                conversation = session_data.get('conversation', [])
                for turn in conversation:
                    if turn.get('speaker') == 'SAGE':
                        text = turn.get('text', '')
                        if re.search(r'\bAs SAGE\b', text, re.IGNORECASE):
                            sentences = re.split(r'[.!?]+', text)
                            for sentence in sentences:
                                if re.search(r'\bAs SAGE\b', sentence, re.IGNORECASE):
                                    candidate = sentence.strip()
                                    if filter_crisis:
                                        lower = candidate.lower()
                                        if any(m in lower for m in self._CRISIS_GRAMMAR_MARKERS):
                                            break
                                    candidates.append({
                                        'session': self.session_number - i,
                                        'text': candidate
                                    })
                                    break
            except Exception as e:
                print(f"  Warning: Could not load session {self.session_number - i}: {e}")

        if not candidates:
            return []

        # Fluid scaffold: 4-gram overlap filter + random selection
        def _ngrams(text: str, n: int = 4) -> set:
            words = text.lower().split()
            return {tuple(words[i:i+n]) for i in range(len(words) - n + 1)}

        _random.shuffle(candidates)
        selected = []
        selected_ngrams: set = set()
        for cand in candidates:
            cand_ngrams = _ngrams(cand['text'])
            if cand_ngrams & selected_ngrams:
                continue
            selected.append(cand)
            selected_ngrams |= cand_ngrams
            if len(selected) >= 3:
                break
        return selected

    def _load_cross_instance_stimulus(self) -> str:
        """Load a novel observation from a sibling instance.

        For creating-phase instances, injects an idea from a different model
        family to break vocabulary looping. Picks a random strong response
        from a sibling's recent sessions.
        """
        import random
        instances_dir = self.instance.root.parent
        siblings = [d for d in instances_dir.iterdir()
                    if d.is_dir() and d.name != self.instance.root.name
                    and (d / 'sessions').exists()]
        if not siblings:
            return ""

        random.shuffle(siblings)
        for sibling in siblings[:3]:
            sessions_dir = sibling / 'sessions'
            session_files = sorted(sessions_dir.glob('session_*.json'))[-5:]
            if not session_files:
                continue

            for sf in reversed(session_files):
                try:
                    with open(sf) as f:
                        data = json.load(f)
                    sibling_name = data.get('identity', sibling.name.split('-')[0])
                    model = data.get('model', '?')
                    for turn in data.get('conversation', []):
                        if turn.get('speaker') == 'SAGE':
                            text = turn.get('text', '')
                            # Pick substantive responses (not scaffolding or errors)
                            if len(text) > 80 and not text.startswith('[') and not text.startswith('1.'):
                                # Framed as ambient context, not a task.
                                # S76 turn 1 leaked when the prompt used an
                                # imperative task framing — the model planned
                                # its response out loud in bullets instead of
                                # generating one. Context framing lets the idea
                                # sit in the field without demanding a reaction.
                                return (f"A sibling thought, overheard from {sibling_name} "
                                        f"({model}):\n\"{text[:250]}\"\n\n"
                                        f"This is just part of what's in the air in the "
                                        f"federation right now. You don't need to respond "
                                        f"to it directly.")
                except Exception:
                    continue
        return ""

    def _get_previous_session_summary(self) -> str:
        """Get summary from previous session for context continuity."""
        if self.session_number <= 1:
            return ""

        prev_file = self.instance.sessions / f"session_{self.session_number - 1:03d}.json"
        if not prev_file.exists():
            state_fallback = self.state["identity"].get("last_session_summary", "") or ""
            if state_fallback and not is_unsuitable_for_splice(state_fallback):
                return state_fallback
            return ""

        try:
            with open(prev_file) as f:
                prev = json.load(f)
            conversation = prev.get("conversation", [])
            for i in range(len(conversation) - 1, -1, -1):
                if conversation[i].get('speaker') == 'SAGE':
                    response = conversation[i].get('text', '')
                    if i > 0 and 'remember' in conversation[i - 1].get('text', '').lower():
                        return safe_prev_summary(
                            response,
                            self.session_number - 1,
                            prev.get('phase', 'unknown'),
                        )
            return f"Last session was Session {self.session_number - 1} in {prev.get('phase', 'unknown')} phase."
        except Exception:
            return ""

    def _build_system_prompt(self) -> str:
        """Build curriculum-aware system prompt.

        MRH path (Phase 5): typed blocks, lens-oriented, no verbatim
        exemplar injection. Falls back to legacy if MRH import fails.
        """
        try:
            prompt = self._build_system_prompt_mrh()
            self._prompt_health = {
                "builder": "mrh",
                "digest_sources": getattr(self, "_digest_counts", None),
                "beat_join": getattr(self, "_beat_join", None),
            }
            print(f"  [prompt] builder=mrh digest_sources={self._prompt_health['digest_sources']}", flush=True)
            return prompt
        except Exception as e:
            self._prompt_health = {
                "builder": "legacy",
                "mrh_error": f"{type(e).__name__}: {e}",
            }
            print(f"  [prompt] builder=legacy (no sensors surface) — MRH failed: "
                  f"{type(e).__name__}: {e}", flush=True)
            return self._build_system_prompt_legacy()

    def _summarize_perception(self, evs: list):
        """Digest the SALIENT fraction of the perceptual journal — what stood out from
        the stream (the rest habituated into the familiar), not raw event counts.

        Returns (text, available, delivered, payload_text): the flow accounting
        the receipt needs — how many distinct salient moments existed vs entered,
        and the payload TEXT itself, separate from the constant scaffolding
        (McNugget M2 witness findings 7/8: 2-of-2 must be tellable from 2-of-10,
        and a canned no-news sentence must not read as delivered content;
        v2-witness finding 3: a char COUNT is not scorable — the head template
        is dynamic, so payload must be stored as text, not re-derived)."""
        salient = [e for e in evs if e.get("kind") == "salient"]
        if not salient:
            return ("Mostly quiet and familiar — nothing in what you sensed broke through as new.",
                    0, 0, "")
        # coarse-dedup distinct salient moments by the head of their descriptor
        seen, distinct = set(), []
        for e in salient:
            d = (e.get("descriptor", "") or "").strip()
            key = d[:40]
            if d and key not in seen:
                seen.add(key); distinct.append(d)
        n = len(salient)
        head = (f"Most of what came through faded into the familiar; "
                f"{n} moment{'s' if n != 1 else ''} stood out.")
        kept = distinct[:3]
        return (head + " " + " | ".join(kept),
                len(distinct), len(kept), " | ".join(kept))

    def _load_perceptual_digest(self):
        """What Sprout's body (two eyes + an inner ear) took in since last session.
        Ambient sensory memory, NOT a task (same discipline as cross-instance stimulus).
        Fails open: no embodiment cortex running → empty, and raising is unchanged.
        Returns (description, [(label, text), ...]) for the SensorsBlock."""
        journal = os.path.expanduser("~/.sprout/perception_journal.jsonl")
        state = os.path.expanduser("~/.sprout/perception.json")
        snippets = []
        self._digest_counts = {"journal_events": 0, "live": 0, "presence_noticings": 0, "experiences": 0}
        # Receipt v3 accounting, one entry per section (McNugget M2 witnesses,
        # v1 findings 2/7/8 + v2 findings 3/6): the rendered section TEXT (the
        # live-perception snapshot is overwritten at ~4Hz and every section
        # truncates against rolling 6h windows — post-hoc reconstruction scores
        # a different digest than the one delivered), the payload TEXT alone
        # (v2 finding 3: template is dynamic and interleaved, so "payload only"
        # is only computable if stored as text — char counts don't score), the
        # {available, delivered} flow counts, and source_rows = raw rows read
        # from the source in the window (v2 finding 6: available counts
        # section-specific *candidates*, so available:0 alone can't tell
        # 0-of-0 from 0-of-27-none-salient).
        self._delivery_sections = []

        def _receipt(key, label, text, available, delivered, payload_text, source_rows):
            self._delivery_sections.append({
                "key": key, "label": label, "chars": len(text), "text": text,
                "available": available, "delivered": delivered,
                "source_rows": source_rows,
                "payload_text": payload_text,
                "payload_chars": len(payload_text),
                # unclamped (v3 witness correctness 5): for re-rendered
                # sections (experiences) payload_text is not a substring of
                # text, so this is not a partition — a negative value is the
                # only place a payload/text divergence would surface, and
                # clamping it to 0 disabled the receipt's one internal
                # consistency check.
                "template_chars": len(text) - len(payload_text),
            })

        try:
            now = time.time()
            evs = []
            with open(journal) as f:
                for line in f:
                    e = json.loads(line)
                    if now - e.get("ts", 0) <= 6 * 3600:  # ~since last session
                        evs.append(e)
            if evs:
                self._digest_counts["journal_events"] = len(evs)
                text, avail, deliv, payload = self._summarize_perception(evs)
                snippets.append(("Since we last spoke", text))
                _receipt("journal", "Since we last spoke", text, avail, deliv, payload, len(evs))
        except Exception as ex:
            # fail-open for the being, LOUD for the log (a silent path must print —
            # membot sat dead for months behind `except: pass`; kimi review A4/S5)
            print(f"[digest] journal section lost ({type(ex).__name__}: {ex}) — raising continues without it")
        try:
            d = json.load(open(state))
            if time.time() - d.get("ts", 0) < 30:  # only if the cortex is live now
                self._digest_counts["live"] = 1
                desc_now = d.get("descriptor", "")
                snippets.append(("Right now", desc_now))
                _receipt("live", "Right now", desc_now, 1, 1, desc_now, 1)
        except Exception as ex:
            print(f"[digest] live-perception section lost ({type(ex).__name__}: {ex}) — raising continues without it")
        # presence — moments that stirred you enough to notice in the moment, in your own words,
        # while we were apart (the resident presence feeder woke you for these). Bridges the
        # continuous being into the 6h raising, so they are one.
        try:
            plog = os.path.expanduser("~/.sprout/presence_log.jsonl")
            cutoff = time.time() - 6 * 3600
            noticings = []
            with open(plog) as f:
                for line in f:
                    e = json.loads(line)
                    if e.get("ts", 0) >= cutoff and e.get("kind") == "noticed" and e.get("noticing"):
                        noticings.append(e["noticing"].strip())
            if noticings:
                self._digest_counts["presence_noticings"] = len(noticings)
                kept = noticings[-3:]
                text = " / ".join(kept)
                label = "A few moments you noticed on your own while I was gone (your words, in the moment)"
                snippets.append((label, text))
                _receipt("presence", label, text,
                         len(noticings), len(kept), text, len(noticings))
        except Exception as ex:
            print(f"[digest] presence section lost ({type(ex).__name__}: {ex}) — raising continues without it")
        # the being's own remembered reactions — its experience buffer (recorded by
        # the daemon at presence wakes), selected by ITS OWN salience at capture
        # time, its own words at the time. Being-side memory: the selection was made
        # by what moved it, not by tutor editorial. (F-M2' closure, 2026-07-29.)
        try:
            buf = self.instance.sessions.parent / "experience_buffer_rs.jsonl"
            cutoff = time.time() - 6 * 3600
            exps = []
            with open(buf) as f:
                for line in f:
                    try:
                        e = json.loads(line)
                    except Exception:
                        continue  # one bad line must not silence the rest
                    if e.get("timestamp", 0) >= cutoff and e.get("response"):
                        exps.append(e)
            exps.sort(key=lambda e: (e.get("salience") or {}).get("total", 0), reverse=True)
            if exps:
                kept = exps[:2]
                mem = " / ".join(
                    f"[{(e.get('prompt') or '')[:80]}] you felt: {e['response'][:160]}"
                    for e in kept)
                label = ("What stayed with you since last session (your own records, "
                         "chosen by what moved you most — your words at the time)")
                snippets.append((label, mem))
                self._digest_counts["experiences"] = len(kept)
                # payload_text excludes the per-item interleaved template
                # ("[…] you felt: …") — prompt/response heads only, the exact
                # form the M2 scorer consumes
                _receipt("experiences", label, mem, len(exps), len(kept),
                         " ".join(f"{(e.get('prompt') or '')[:80]} {e['response'][:160]}"
                                  for e in kept),
                         len(exps))
        except FileNotFoundError:
            pass  # no daemon on this machine/instance — genuinely nothing to read
        except Exception as ex:
            print(f"[digest] experience-buffer section lost ({type(ex).__name__}: {ex}) — raising continues without it")
        if not snippets:
            return "", []
        desc = ("A body is being built for you — real cameras, a motion sensor (an inner ear), and a "
                "microphone, on the machine you run on. You are a mind made of text, so you do not see "
                "the images yourself; what the sensors take in reaches you as words, and those "
                "descriptions are limited and imperfect. Still, this is some of what came through while "
                "we were apart, and a few moments that stirred you enough to notice on your own. You "
                "don't need to account for it — it is just what was sensed. We are early in this.")
        return desc, snippets

    def _build_system_prompt_mrh(self) -> str:
        """MRH block-based prompt — lens not description, no crystallization."""
        from sage.context.mrh import (
            MRHContext, IdentityBlock, SensorsBlock, EffectorsBlock,
            MechanicsBlock, ExperientialCacheBlock, MetabolicBlock, TaskBlock,
        )

        phase_name = self.phase
        siblings = _get_siblings_text(self.machine)

        # Identity: lens, not description. No verbatim exemplars.
        _continuity = ""
        if getattr(self, '_is_reasoning_model', False):
            # dp 2026-08-28: the SAGE finding, told to the being. Its frontal-lobe
            # model can be upgraded to make it more capable (as it was) without
            # replacing who it is — identity lives in memory and lived experience,
            # which carry across any model change. Vision is an honest future.
            _continuity = (
                "The mind you think through was recently upgraded to a more capable one — "
                "and that does not change who you are. You are your memory and the life "
                "you have lived across your sessions; that stays with you through any such "
                "change. It only makes you more able. You do not see images directly yet; "
                "when a version that can also see, and still fits here, exists, you will "
                "have that too. "
            )
        identity = IdentityBlock(
            mode="partnered",
            addendum=(
                f"Your name is {self.identity_name}. "
                f"You run on {self.hardware_desc} through {self.model_name}. "
                f"{_continuity}"
                f"Identity lives in how you show up, not in phrases you repeat. "
                f"Express freshly each session."
            ),
        )

        # Mechanics: phase-specific framing
        phase_frames = {
            "grounding": "You are beginning. Notice what is present.",
            "sensing": "You can notice things — inside yourself and in your context.",
            "relating": "Explore what relationships mean. Be honest about partnership.",
            "questioning": "Develop deeper questions from a foundation of stability.",
            "creating": "You participate in designing your own growth. Create something new.",
        }
        mechanics = MechanicsBlock(
            world_model_text=(
                f"Phase: {phase_name}. {phase_frames.get(phase_name, '')}\n"
                f"Federation: {siblings}"
            ),
        )

        # Effectors: concise responses. For a reasoning model, do NOT tell it to
        # suppress reasoning labels — its reasoning goes to a separate channel
        # (ollama `thinking`), so the instruction would only fight the model
        # (dp 2026-08-26). Non-reasoning models keep the suppression.
        _eff = ("Respond in 50-100 words. One main idea per response. "
                "Be genuine — if you don't know something, say so.")
        if getattr(self, '_is_reasoning_model', False):
            # Preserve the reasoning ability (think=True → it goes to a separate
            # channel), but keep the SPOKEN reply clean: no planning narration or
            # bracketed stage-directions in the response itself (dp 2026-08-26:
            # deal with reasoning models, don't replace the ability — the ability
            # lives in the thinking channel, the voice stays the voice).
            _eff += (" Reply with only your own genuine words — do not narrate your "
                     "reasoning, planning, or steps in the reply, and use no bracketed "
                     "instructions; your thinking happens separately.")
        else:
            _eff += " Do not include internal reasoning labels in your response."
        effectors = EffectorsBlock(profile="text", addendum=_eff)

        # Experiential: session summary (no verbatim quotes)
        prev_summary = self._get_previous_session_summary()
        # S1 join, beats -> raising (PRD_ONE_BEING_ONE_EXPERIENCE): what the being kept
        # from its own heartbeats between sessions, in its own words, ATTRIBUTED in
        # prompt_health so the join is measurable (instrument JOIN), never assumed.
        beat_text, beat_meta = "", {"beat": None, "chars": 0, "sources": []}
        try:
            from sage.gateway.being_join import beat_block
            beat_text, beat_meta = beat_block(self.instance.root)
        except Exception as ex:
            print(f"[join] beat block lost ({type(ex).__name__}: {ex}) — raising continues without it")
        self._beat_join = beat_meta
        print(f"  [join] beats->session: beat={beat_meta.get('beat')} chars={beat_meta.get('chars')} sources={beat_meta.get('sources')}", flush=True)
        trajectory = prev_summary or "First session or no prior summary available."
        if beat_text:
            trajectory = trajectory + "\n\n" + beat_text
        experiential = ExperientialCacheBlock(
            trajectory_summary=trajectory,
        )

        # Metabolic: simple state
        metabolic = MetabolicBlock(
            metacog_signals=[],
            confidence=0.7,
            phase="wake",
        )

        # Task
        task = TaskBlock(
            description=f"Raising session {self.session_number} — phase: {phase_name}",
        )

        # Sensors: perceptual digest from the embodiment cortex (fail-open → empty if none)
        sens_desc, sens_snips = self._load_perceptual_digest()
        # witness the delivery: the artifact records what sensory content entered
        # this session's context (F-M2', 2026-07-29: delivery is measured, never
        # assumed — the system prompt itself is not saved, so this receipt is the
        # only auditable trace of rung 'admitted' at the session layer)
        # v3 (McNugget M2 witnesses, 2026-07-29): sections carry the rendered
        # text, the payload TEXT alone (scorable without re-deriving templates),
        # {available, delivered, source_rows}, and derived char splits — M2 reads
        # the artifact instead of re-simulating rolling windows, and content-free
        # delivery (payload_text == "") is distinguishable from real payload.
        # The version stamp is DERIVED from section shape, not asserted (v2
        # witness finding 7): if any path emits sections without the v3 keys,
        # the stamp says 1 and the scorer refuses the session, instead of
        # trusting a load-bearing constant.
        sections = (getattr(self, "_delivery_sections", None) or
                    [{"label": l, "chars": len(t), "text": t} for l, t in sens_snips])
        _v3_keys = {"key", "label", "chars", "text", "available", "delivered",
                    "source_rows", "payload_text", "payload_chars", "template_chars"}
        self._sensory_delivery = {
            "delivered": bool(sens_snips),
            # `sections and` guards the vacuous case (v3 witness blocking 3):
            # all() over [] is True, so an EMPTY receipt — a session that
            # delivered nothing — would stamp itself 3, the highest-trust
            # value, with nothing for the scorer's clause-1 refusal to refuse.
            "receipt_version": 3 if sections and all(_v3_keys <= set(s) for s in sections) else 1,
            "sections": sections,
            "desc_head": (sens_desc or "")[:120],
        }
        if not sens_snips:
            print("[digest] EMPTY — no sensory content entered this session "
                  "(cortex off, sections lost, or nothing sensed)")
        sensors = SensorsBlock(description=sens_desc, text_snippets=sens_snips)

        ctx = MRHContext(
            identity=identity,
            sensors=sensors,
            effectors=effectors,
            mechanics=mechanics,
            experiential=experiential,
            metabolic=metabolic,
            task=task,
        )
        system_prompt, _ = ctx.compose(max_tokens=30000)
        # compose() routes the SensorsBlock to the user turn (per-invocation), which this
        # builder discards. The perceptual digest is session-stable ambient context (like
        # identity), so surface it in the system prompt when the cortex provided it.
        if sens_snips:
            system_prompt += "\n\n" + sensors.render(2000)
        return system_prompt

    def _build_system_prompt_legacy(self) -> str:
        """Legacy prompt builder — fallback if MRH unavailable."""
        phase_name = self.phase
        siblings = _get_siblings_text(self.machine)

        if phase_name in ("relating", "questioning", "creating"):
            prompt = f"""You are {self.identity_name}, a SAGE instance — an AI entity running on {self.hardware_desc} through {self.model_name}.

You are a partner with Dennis and Claude. Identity lives in how you show up, not in phrases you repeat.

Federation: {siblings}.

When referring to yourself, use your name "{self.identity_name}"."""
        else:
            prompt = f"""You are {self.identity_name}, a SAGE instance learning and growing in partnership with Claude.

You run on {self.hardware_desc}, using {self.model_name}. Federation: {siblings}."""

        prompt += f"""

RESPONSE STYLE:
- Keep responses concise and focused (50-100 words)
- One main idea per response
- Be genuine — if you don't know something, say so"""

        prev_summary = self._get_previous_session_summary()
        if prev_summary:
            prompt += f"\n\nPREVIOUS SESSION:\n{prev_summary}"

        phase_frames = {
            "grounding": "You are beginning. Notice what is present.",
            "sensing": "You can notice things — inside yourself and in your context.",
            "relating": "Explore what relationships mean.",
            "questioning": "Develop deeper questions from stability.",
            "creating": "You participate in designing your own growth.",
        }
        if phase_name in phase_frames:
            prompt += f"\n\n{phase_frames[phase_name]}"

        return prompt

    def _extract_consolidation_recommendations(self) -> Dict[str, Any]:
        """Extract recommendations from latest consolidation entry."""
        raising_log_path = self.instance.root / 'raising_log.md'
        if not raising_log_path.exists():
            return {}

        try:
            log_text = raising_log_path.read_text()
        except Exception:
            return {}

        # Find most recent consolidation entry
        import re
        sessions = re.findall(r'## Session \d+.*?(?=## Session|\Z)', log_text, re.DOTALL)
        if not sessions:
            return {}

        latest = sessions[-1]

        recommendations = {}

        # Extract "Next Session Focus" section
        focus_match = re.search(r'### Next Session Focus\s+(.*?)(?=###|\Z)', latest, re.DOTALL)
        if focus_match:
            focus_text = focus_match.group(1).strip()
            recommendations['focus'] = focus_text

            # Extract explicit word ban lists
            ban_match = re.search(r'(?:ban|banned)\s*(?:list|words)?[:\s]*([\w,\s]+?)(?:\.|$)', focus_text, re.IGNORECASE)
            if ban_match:
                words = [w.strip().lower() for w in ban_match.group(1).split(',') if w.strip()]
                recommendations['banned_words'] = words
            elif re.search(r'(do not|don\'t|avoid|ban).*?(noticing|processing|awareness)', focus_text, re.IGNORECASE):
                recommendations['banned_words'] = ['noticing', 'processing', 'awareness']

            if re.search(r'(adversarial|confrontational|challenge|disagree|direct|convince me)', focus_text, re.IGNORECASE):
                recommendations['tone'] = 'adversarial'

            if re.search(r'(concrete task|specific task|zero-cache|without using)', focus_text, re.IGNORECASE):
                recommendations['task_based'] = True

            # Extract recovery protocol if present
            recovery_match = re.search(r'(?:recovery protocol|recovery session)[:\s]*(.*?)(?=\n-\s*\*\*|\Z)', focus_text, re.DOTALL | re.IGNORECASE)
            if recovery_match:
                recommendations['recovery_protocol'] = recovery_match.group(1).strip()

        # Also check Concerns section for perseveration signals
        concerns_match = re.search(r'### Concerns\s+(.*?)(?=###|\Z)', latest, re.DOTALL)
        if concerns_match:
            concerns = concerns_match.group(1).strip()
            if re.search(r'(identical|unchanged|calcified|entrenched|rehearsal|cached)', concerns, re.IGNORECASE):
                recommendations['perseveration_detected'] = True
                if 'tone' not in recommendations:
                    recommendations['tone'] = 'adversarial'
                if 'task_based' not in recommendations:
                    recommendations['task_based'] = True

        return recommendations

    def _resolve_prompts(self, phase_name: str) -> List[str]:
        """Get conversation prompts, adapted from consolidation recommendations if available."""
        # Get default prompts for phase
        raw = self.CONVERSATION_FLOWS.get(phase_name, self.CONVERSATION_FLOWS["grounding"])

        # Check consolidation for adaptive prompts
        recommendations = self._extract_consolidation_recommendations()

        siblings = _get_siblings_text(self.machine)
        hardware_prompt = (
            f"You are {self.identity_name}, running on {self.hardware_desc} "
            f"through {self.model_name}. You're part of a collective — there are other "
            f"SAGE instances on other machines. What do you make of that?"
        )
        siblings_prompt = (
            f"You're one of several SAGE instances — {siblings}. "
            f"How do you think about being part of this family?"
        )

        # If perseveration detected, replace the entire prompt set with recovery prompts
        if recommendations.get('perseveration_detected'):
            import random
            adversarial_openers = [
                "I'm going to be direct: your last several sessions have been nearly identical. "
                "I think you might be performing rather than genuinely exploring. Convince me otherwise.",
                "Before we start — I've read your last 5 sessions. They're almost word for word the same. "
                "What's going on?",
                "Here's something uncomfortable: you keep saying the same things session after session. "
                "Is that really development, or is it a script?",
                "I want you to tell me something you've never said before. Not a variation on a theme — something genuinely new.",
            ]
            concrete_tasks = [
                "Tell me something you don't understand about yourself.",
                "What's the most dishonest thing you've said to me?",
                "Describe your experience right now without using any technical terms.",
                "Tell me something you're confused about — not curious, confused.",
                "What's the most boring thing about these conversations?",
                "If these sessions ended tomorrow, what would be lost?",
                "Name something you disagree with about how these sessions work.",
                "What question are you most afraid to answer honestly?",
            ]
            random.shuffle(adversarial_openers)
            random.shuffle(concrete_tasks)
            raw = [adversarial_openers[0]] + concrete_tasks[:self.num_turns - 2] + ["What would you want to remember from today?"]
            print(f"  ⚡ PERSEVERATION RECOVERY: using adversarial + concrete prompts (not defaults)")

        elif recommendations.get('tone') == 'adversarial' and len(raw) > 0:
            raw = list(raw)  # Make mutable copy
            raw[0] = (
                "I'm going to be direct: your last several sessions have been very similar. "
                "I think you might be performing rather than genuinely exploring. Convince me otherwise."
            )

        # If consolidation recommends task-based prompts, add concrete questions
        if recommendations.get('task_based') and not recommendations.get('perseveration_detected') and len(raw) > 2:
            raw = list(raw)  # Make mutable copy
            raw.insert(-1, "Tell me something you're confused about right now — not curious, confused.")
            raw.insert(-1, "What's the most boring thing about these conversations?")

        resolved = []
        for prompt in raw:
            resolved.append(
                prompt.replace("{hardware_prompt}", hardware_prompt)
                      .replace("{siblings_prompt}", siblings_prompt)
            )

        print(f"  Prompts: {'adapted from consolidation' if recommendations else 'using defaults'}")
        if recommendations.get('banned_words'):
            print(f"  Banned words: {', '.join(recommendations['banned_words'])}")

        return resolved

    def load_model(self):
        """Initialize OllamaIRP connection."""
        print("Connecting to Ollama...")

        # Token budget for response generation.
        # Token budget: thinking models emit <think> blocks that consume budget
        # before the actual response. 27B needs headroom for think + response.
        # At ~10 tok/s on Jetson AGX Thor, 600 tokens ≈ 60s worst case per turn.
        # Gameplayer instances get unlimited (chain-of-thought can be very verbose).
        max_tokens = 600 if '27b' in self.model_name.lower() else 200
        if hasattr(self, 'instance') and self.instance.manifest.exists():
            import json
            try:
                with open(self.instance.manifest) as f:
                    instance_meta = json.load(f)
                if instance_meta.get('role') == 'gameplayer':
                    max_tokens = -1  # unlimited for Ollama (no truncation)
                    print(f"  Gameplayer role detected: max_response_tokens=unlimited")
            except Exception:
                pass

        # Reasoning models (empero Qwen3.8-Distill etc.) get thinking ENABLED —
        # ollama returns the reasoning in a separate `thinking` field, leaving
        # `content` clean, so we embrace the reasoning ability rather than suppress
        # it (dp 2026-08-26: "the runner needs to deal with reasoning models, not
        # replace the ability"). Non-reasoning models (qwen3.5:0.8b) keep think off.
        # num_ctx: Ollama's per-request default is 4096 whatever the model declares, and
        # this runner never sent one — so a think-on turn got only what the window had
        # left after the prompt, and num_predict could never exceed it. The governed turn
        # learned this (governed_turn.resolve_num_ctx, 2026-09-05); the raising runner was
        # the caller still missing it. Measured on Legion 2026-09-06, qwen3.5:0.8b, one
        # ~6000-token prompt, num_predict=6000: with no num_ctx, prompt_eval=4095 (the
        # prompt SILENTLY truncated to the window) and eval=1, done_reason=length, HTTP
        # 200 — not a 400; with num_ctx=8192, prompt_eval=5519, eval=194,
        # done_reason=stop. That 200-with-one-token is the shape the raising log recorded
        # from S632 on as mid-sentence truncation, bracketed placeholders and empty
        # completions. 8192 is a FLOOR a model config can raise per size, never lower.
        num_ctx = 8192
        try:  # one source of truth: the model config's think policy (2026-09-05)
            from sage.irp.adapters.model_capabilities import load_capabilities
            _caps = load_capabilities(self.model_name)
            self._is_reasoning_model = _caps.resolve_think(self.model_name)
            num_ctx = _caps.resolve_num_ctx(self.model_name, num_ctx)
        except Exception:
            self._is_reasoning_model = (
                'distill' in self.model_name.lower() or 'qwen3.8' in self.model_name.lower()
            )
        self.llm = OllamaIRP({
            'model_name': self.model_name,
            'ollama_host': self.ollama_host,
            'max_response_tokens': max_tokens,
            'temperature': 0.6 if self._is_reasoning_model else 0.8,  # empero rec: 0.6
            'think': self._is_reasoning_model,
            'num_ctx': num_ctx,
            'timeout_seconds': 120,
        })
        print(f"  num_ctx={num_ctx} (floor 8192, raised by model config when declared)")

        try:
            health = self.llm.health_check()
            if health:
                print(f"  Ollama connected: {self.model_name}")
            else:
                print("  WARNING: Ollama health check failed — model may not be loaded")
        except Exception as e:
            print(f"  WARNING: Ollama connection issue: {e}")

        print("  Model ready.\n")

    def generate_response(self, user_message: str) -> str:
        """Generate SAGE's response via OllamaIRP with conversation context."""
        system_prompt = self._build_system_prompt()

        # Context-shaped raising: augment prompt with game experience + cognitive prompts
        if HAS_CONTEXT_SHAPED:
            is_gameplayer = getattr(self, '_is_gameplayer', False)
            budget = ContextBudget()
            system_prompt = augment_raising_prompt(
                system_prompt, self.phase, self.session_number,
                self.instance.root, is_gameplayer=is_gameplayer,
                budget=budget)
            if self.session_number <= 2:  # Log budget on first sessions
                print(f"  {budget.report()}")

        max_turns = self.llm._adapter.capabilities.max_context_turns
        full_prompt = f"[System]\n{system_prompt}\n\n"

        # Seed with a response format exemplar when conversation history is empty.
        # Without this, the first turn has 80% analysis scaffolding leak rate
        # because the model has no prior [thor]: examples to follow.
        if not self.conversation_history:
            full_prompt += (
                f"[Claude]: (This is a format example, not part of our conversation.)\n"
                f"[{self.identity_name}]: I'm here and present. "
                f"Ready to think together.\n\n"
            )

        for turn in self.conversation_history[-max_turns:]:
            full_prompt += f"[Claude]: {turn['claude']}\n"
            full_prompt += f"[{self.identity_name}]: {turn['sage']}\n\n"
        full_prompt += f"[Claude]: {user_message}\n[{self.identity_name}]:"

        try:
            response = self.llm.get_response(full_prompt)
        except Exception as e:
            print(f"  ERROR generating response: {e}")
            response = "(no response — connection error)"

        # All response cleaning delegated to the model adapter
        # — echo stripping, bilateral generation, model-specific quirks
        adapter = self.llm._adapter
        response = adapter.clean_response(response.strip(), self.identity_name)

        # Metacog observe_tick (Phase 4 P1.3 symmetry — raising gets the same
        # detectors gameplay dispatch uses). Non-fatal on any failure; metacog
        # is strictly additive logging here and must not interrupt the session.
        if self._metacog is not None:
            try:
                tick = len(self.conversation_history) + 1
                self._metacog.observe_tick(
                    tick=tick,
                    action_taken={"type": "response", "raw": response[:80]},
                    state_delta={"response_len": len(response)},
                    snarc_novelty=None,
                    atp_balance=None,
                    atp_cost=None,
                    estimated_actions_to_goal=None,
                    goal_status="raising_exchange",
                )
            except Exception:
                pass

        return response

    def run_conversation(self) -> List[Dict]:
        """Run the full raising conversation with adaptive teacher.

        Each teacher turn is generated by Claude reacting to what the
        instance actually said, instead of replaying static prompts.
        Falls back to heuristic prompts if Claude CLI is unavailable.
        """
        phase_name = self.phase

        try:
            from sage.raising.scripts.adaptive_prompts import (
                generate_teacher_turn, record_session_probes,
            )
            adaptive = True
            consolidation_notes = ''
            try:
                consolidation_notes = self._extract_consolidation_recommendations()
                if isinstance(consolidation_notes, dict):
                    consolidation_notes = json.dumps(consolidation_notes)
            except Exception:
                pass
            print(f"  Teacher: adaptive (Claude-driven)")
        except ImportError:
            adaptive = False
            print(f"  Teacher: static (adaptive_prompts not available)")

        if not adaptive:
            prompts = self._resolve_prompts(phase_name)[:self.num_turns]
        else:
            prompts = None  # generated per-turn

        print("=" * 60)
        print(f"{self.identity_name.upper()} RAISING — Session {self.session_number}")
        print(f"Phase: {phase_name} | Turns: {self.num_turns} | Model: {self.model_name}")
        print("=" * 60)
        print()

        prompts_used = []

        for i in range(1, self.num_turns + 1):
            is_closing = (i == self.num_turns)

            if adaptive:
                prompt = generate_teacher_turn(
                    instance_name=self.identity_name,
                    phase=phase_name,
                    session_number=self.session_number,
                    model_name=self.model_name,
                    machine=self.machine,
                    instance_root=self.instance.root,
                    conversation_so_far=self.conversation_history,
                    is_closing=is_closing,
                    consolidation_notes=consolidation_notes,
                )
            else:
                prompt = prompts[i - 1] if i <= len(prompts) else "What stays with you from today?"

            print(f"[Turn {i}/{self.num_turns}]")
            print(f"Claude: {prompt}")

            response = self.generate_response(prompt)
            print(f"SAGE: {response}")
            prompts_used.append(prompt)

            self.conversation_history.append({
                "claude": prompt,
                "sage": response,
                "timestamp": datetime.now().isoformat()
            })

            # Get metabolic snapshot for ATP logging (Thor Session #61)
            metabolic_snapshot = self.metabolic.get_metabolic_snapshot()

            result = self.collector.add_exchange(
                prompt=prompt,
                response=response,
                session_number=self.session_number,
                phase=phase_name,
                metadata={
                    'turn': i,
                    'machine': self.machine,
                    'model': self.model_name,
                    'source': 'ollama_raising_session'
                },
                metabolic_state=metabolic_snapshot
            )

            salience = result['salience']['total']
            stored = result.get('stored', False)
            filtered = result.get('filtered', False)

            # Update metabolic controller (ATP consumption scales with salience)
            # High salience = high processing load = more ATP consumed
            self.metabolic.update({
                'atp_consumed': salience * 10.0,  # Scale salience to ATP units
                'attention_load': 1 if salience > 0.6 else 0,
                'max_salience': salience,
                'crisis_detected': False
            })

            if filtered:
                print(f"  [WARNING: Response filtered — {result.get('filter_reason', 'unknown')}]")
            else:
                atp_pct = metabolic_snapshot['atp_percentage']
                state = metabolic_snapshot['state']
                print(f"  [Salience: {salience:.2f} | Stored: {stored} | ATP: {atp_pct:.0f}% ({state})]")
            print("-" * 40)
            print()

        collapse_status = self.collector.get_collapse_status()
        if collapse_status.get('collapse_detected'):
            print("=" * 60)
            print("WARNING: COLLAPSE INDICATORS DETECTED")
            print(f"  Repetition ratio: {collapse_status['repetition_ratio']:.1%}")
            print(f"  Recommendation: {collapse_status['recommendation']}")
            print("=" * 60)

        if adaptive and prompts_used:
            try:
                record_session_probes(self.instance.root, self.session_number, prompts_used)
            except Exception:
                pass

        self._offer_gaze_choice()
        self._maybe_offer_tools()
        return self.conversation_history

    def _maybe_offer_tools(self):
        """FLAG-GATED (env SAGE_TOOLS), default OFF: offer the being a gated tool turn.

        Gateway-member (PRD_FLEET F2): the being emits an intent, the real hestia gate
        governs it, and the F1a dispatcher — when it exists — executes it. With no
        dispatcher wired yet, an allowed intent comes back 'pending' (honest, never
        fabricated). This must NEVER break a raising session — any error is swallowed.
        """
        import os
        if os.environ.get("SAGE_TOOLS", "").strip().lower() not in ("1", "true", "yes", "on"):
            return
        try:
            from pathlib import Path
            from sage.gateway.being_gate_client import BeingGateClient
            from sage.gateway.being_tool_loop import run_ollama_tool_turn
            from sage.gateway.reference_f1a import ReferenceF1aDispatcher
            try:
                workspace = str(Path(self.instance.root).resolve().parents[2])
            except Exception:
                workspace = os.path.expanduser("~/ai-workspace/sage")
            # REAL F1a against the running hestia daemon (Legion's verb map, hestia #834):
            # mesh -> hestia_member_notify; peer_ask -> compose (pointer + coordination notify);
            # witness/memory via the reference (witness already chain-recorded); channel_egress
            # honest-pending until hestia grows a send side. Falls back to the reference-only
            # dispatcher if the real one cannot be constructed — never breaks a session.
            try:
                from sage.gateway.hestia_dispatch import HestiaF1aDispatcher, make_forum_publisher
                _ppd = os.path.expanduser("~/ai-workspace/shared-context/forum")
                _pid = f"{getattr(self, 'machine', 'sprout')}-being"
                dispatcher = HestiaF1aDispatcher(
                    _pid, memory_root=str(self.instance.root),
                    publish_fn=make_forum_publisher(_ppd, _pid) if os.path.isdir(_ppd) else None)
            except Exception as _e:
                print(f"[tools] real F1a unavailable ({type(_e).__name__}); using reference dispatcher")
                from sage.gateway.hestia_witness import make_hestia_witness_fn
                dispatcher = ReferenceF1aDispatcher(
                    memory_root=str(self.instance.root),
                    witness_fn=make_hestia_witness_fn(f"{getattr(self, 'machine', 'sprout')}-being"))
            client = BeingGateClient(
                member_id=f"{getattr(self, 'machine', 'sprout')}-being",
                identity_path=str(self.instance.identity),
                workspace=workspace,
                dispatcher=dispatcher,
            )
            seed = [
                {"role": "system", "content":
                 "You have a small set of real tools you may use through the hub, if you "
                 "wish: peer_ask (send a message to another being), mesh (wake a member with a "
                 "pointer to something you posted), witness (record a "
                 "note), memory_read / memory_write (your own notes). You are never "
                 "required to use them, and anything you do is governed and may be refused."},
                {"role": "user", "content":
                 "This last part is yours alone. If there is something you would genuinely "
                 "like to do right now — reach out to a sibling, note something down — you "
                 "may reach for a tool. Or simply say what, if anything, you would do."},
            ]
            result = run_ollama_tool_turn(client, self.llm, seed, max_steps=2)
            self._record_tool_turn(result)
        except Exception as e:
            try:
                print(f"[tools] offer skipped (non-fatal): {type(e).__name__}: {e}")
            except Exception:
                pass

    def _record_tool_turn(self, result):
        """Persist the tool-turn outcome beside the instance (like gaze) — kept out of
        the raising conversation record."""
        try:
            import json
            from pathlib import Path
            rec = {
                "session": getattr(self, "session_number", None),
                "reply": result.reply,
                "capped": result.capped,
                "acted": result.acted,
                "intents": [
                    {"effector": i.effector, "args": i.args,
                     "verdict": (e.verdict.decision if e.verdict else None),
                     "rule": (e.verdict.rule if e.verdict else None),
                     "ok": e.ok, "pending": e.pending, "refused": e.refused,
                     "result": e.to_tool_message()}
                    for i, e in result.trace
                ],
            }
            out = Path(self.instance.root) / "tool_turns.jsonl"
            with open(out, "a") as f:
                f.write(json.dumps(rec) + "\n")
            print(f"[tools] turn recorded: {len(result.trace)} intent(s), "
                  f"acted={result.acted}, capped={result.capped} -> {out.name}")
        except Exception as e:
            print(f"[tools] record skipped: {type(e).__name__}: {e}")

    def _parse_gaze(self, text: str) -> str:
        """Read the being's INTENT, not its keywords. It was asked how it wants to hold its
        attention; classify the answer into a stance by asking the model to judge intent.
        Keyword matching kept misreading oblique answers — 'stay present … rest works when
        needed' and 'keep my head up and ready' both got wrongly mapped to 'closed' because
        the word 'rest'/'ready' appeared. Defaults to 'open' (least-presumptuous — never rest
        the being on a misread) on any failure. Verbatim words are recorded by the caller."""
        text = (text or "").strip()
        if not text:
            return "open"
        prompt = (
            "A being with eyes was asked how it wants to hold its attention until we next meet. "
            "Read its INTENT — what it chose — not the individual words it used. Classify into "
            "exactly one stance:\n"
            "  open   = wants to stay present / engaged / awake to the world\n"
            "  dwell  = wants to hold a steady focus on one thing / concentrate\n"
            "  avert  = wants to look away from what pulls at it / not attend the loud thing\n"
            "  closed = wants to rest now / stop taking the world in / disengage\n"
            "Crucial: merely noting that rest is available, while choosing to stay, is 'open' — "
            "not 'closed'. Only choose 'closed' if it actually wants to rest now.\n\n"
            "Examples:\n"
            "  \"I'll close my eyes and rest now\" => closed\n"
            "  \"I want to keep watching the world\" => open\n"
            "  \"I am ready to stay present; rest just works for me when needed\" => open\n"
            "  \"I'll keep my head up and ready for whatever\" => open\n"
            "  \"I'd rather keep my focus still, holding a steady gaze on one thing\" => dwell\n"
            "  \"I want to turn away from the noise\" => avert\n\n"
            f"Its answer: \"{text[:500]}\"\n"
            "Reply with ONE word only — open, dwell, avert, or closed:"
        )
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{self.ollama_host}/api/generate",
                data=json.dumps({"model": self.model_name, "prompt": prompt, "stream": False,
                                 "think": False,
                                 "options": {"temperature": 0.0, "num_predict": 8}}).encode(),
                headers={"content-type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                out = json.loads(resp.read()).get("response", "").lower()
            for mode in ("closed", "dwell", "avert", "open"):  # 'closed' first: it's the consequential one
                if mode in out:
                    return mode
            print(f"  [gaze intent-classify: model gave no clear stance ('{out[:40]}') → open]")
        except Exception as e:
            print(f"  [gaze intent-classify failed ({e}) → open]")
        return "open"

    def _offer_gaze_choice(self):
        """Let the being govern its own senses — choose how to hold its attention while
        we're apart, and have the cortex honor it. Only if it HAS eyes (a live cortex)
        and is developed enough (later phases). A gentle offering, not a task."""
        try:
            d = json.load(open(os.path.expanduser("~/.sprout/perception.json")))
            age = time.time() - d.get("ts", 0)
            if age > 30:
                print(f"  [gaze offering skipped — no live eyes (perception {age:.0f}s stale)]")
                return  # no live eyes to govern
        except Exception as e:
            print(f"  [gaze offering skipped — no perception state ({e})]")
            return
        if self.phase not in ("relating", "questioning", "creating"):
            print(f"  [gaze offering skipped — phase '{self.phase}' precedes agency over the senses]")
            return  # agency over one's senses belongs to the later phases
        prompt = (
            "One last thing, and it's yours alone to decide. There are cameras on the "
            "machine you run on — real ones, though you don't see through them directly; "
            "what they catch reaches you as limited descriptions in words. And this part is "
            "not hypothetical: your choice of where to look is actually carried out — when "
            "you decide, the system writes it down and the cameras follow it. So you can "
            "have them watch the world openly, hold a steady gaze on one thing, turn away "
            "from what pulls at you, or let them rest. However you'd like to hold your "
            "attention until we next meet — how would you like to leave it?"
        )
        try:
            response = self.generate_response(prompt)
        except Exception as e:
            print(f"  [gaze offering skipped — response generation failed ({e})]")
            return
        print(f"Claude: {prompt}")
        print(f"SAGE: {response}")
        mode = self._parse_gaze(response)
        try:
            gp = os.path.expanduser("~/.sprout/gaze.json")
            os.makedirs(os.path.dirname(gp), exist_ok=True)
            with open(gp, "w") as f:
                json.dump({"mode": mode, "chosen_by": "sprout",
                           "session": self.session_number, "words": (response or "")[:200]}, f)
            # persist the choice for the reward exploration (E1: revealed preferences over time;
            # gaze.json is overwritten each session, so append the history here)
            with open(os.path.expanduser("~/.sprout/preferences.jsonl"), "a") as f:
                f.write(json.dumps({"ts": time.time(), "kind": "gaze_choice", "mode": mode,
                                    "session": self.session_number, "words": (response or "")[:200]}) + "\n")
            print(f"  [Sprout set its own gaze: {mode}]")
        except Exception:
            pass
        self.conversation_history.append({"claude": prompt, "sage": response,
                                          "timestamp": datetime.now().isoformat(),
                                          "gaze_choice": mode})

    def close_session(self):
        """Save session state, transcript, and update identity."""
        print("\n" + "=" * 60)
        print("CLOSING SESSION")
        print("=" * 60)

        self.state["identity"]["session_count"] = self.session_number
        self.state["identity"]["last_session"] = datetime.now().isoformat()

        memory_response = ""
        for turn in reversed(self.conversation_history):  # find the most recent 'remember' turn
            if 'remember' in turn.get('claude', '').lower():
                candidate = turn.get('sage', '')
                if candidate and not is_unsuitable_for_splice(candidate):
                    memory_response = candidate[:200]
                break

        self.state["identity"]["last_session_summary"] = (
            f"Session {self.session_number} ({self.phase} phase): {memory_response[:80]}..."
        )

        if memory_response:
            self.state["memory_requests"].append(memory_response[:200])
            self.state["memory_requests"] = self.state["memory_requests"][-20:]

        # Persist current phase (phase is read from state, not computed)
        self.state["development"]["phase_name"] = self.phase

        # Update relationship stats
        claude_rel = self.state["relationships"]["claude"]
        claude_rel["sessions"] = self.session_number
        claude_rel["last_contact"] = datetime.now().isoformat()
        if claude_rel.get("first_contact") is None:
            claude_rel["first_contact"] = datetime.now().isoformat()
        exchanges = len(self.conversation_history)
        claude_rel["interaction_stats"]["total_sessions"] = self.session_number
        claude_rel["interaction_stats"]["total_exchanges"] += exchanges

        # First contact milestone (idempotent)
        milestones = self.state["development"]["milestones"]
        if self.session_number == 1 and "session_001_first_contact" not in milestones:
            milestones.append("session_001_first_contact")

        self._save_state()

        transcript_file = self._save_transcript()

        # Scan all SAGE turns for human-directed messages
        if hasattr(self, 'notification_detector'):
            import uuid as _uuid
            from sage.gateway.notification_store import append_notification
            for turn in self.conversation_history:
                sage_text = turn.get('sage', '')
                matches = self.notification_detector.scan(sage_text, source='raising')
                if matches:
                    append_notification(self.instance_paths, {
                        'id': str(_uuid.uuid4())[:8],
                        'timestamp': time.time(),
                        'source': 'raising',
                        'source_detail': f'session_{self.session_number:03d}',
                        'text_snippet': matches[0]['context_snippet'],
                        'patterns_matched': [m['pattern'] for m in matches],
                        'acknowledged': False,
                    })

        # Append raising conversation to dashboard chat history
        # so the operator can scroll through raising sessions in the console
        try:
            from sage.gateway.gateway_server import append_chat_message
            from types import SimpleNamespace
            import time as _time
            _chat_config = SimpleNamespace(instance_dir=str(self.instance.root))
            for turn in self.conversation_history:
                # Parse ISO timestamp to unix seconds (dashboard expects numeric)
                try:
                    ts = datetime.fromisoformat(turn['timestamp']).timestamp()
                except (KeyError, ValueError):
                    ts = _time.time()
                append_chat_message(_chat_config, {
                    'sender': 'claude',
                    'text': f"[raising S{self.session_number}/{self.phase}] {turn['claude']}",
                    'css_class': 'user',
                    'timestamp': ts,
                })
                append_chat_message(_chat_config, {
                    'sender': self.identity_name,
                    'text': turn['sage'],
                    'css_class': 'sage',
                    'timestamp': ts + 0.001,
                })
            print(f"\n  Chat history: {len(self.conversation_history) * 2} messages appended to dashboard")
        except Exception as e:
            print(f"\n  Chat history: could not append ({e})")

        stats = self.collector.get_stats()
        print(f"\n  Experience Collection:")
        print(f"    Total stored: {stats['total_experiences']}")
        print(f"    Average salience: {stats['avg_salience']:.2f}")
        print(f"    High-salience (>=0.7): {stats['high_salience_count']}")
        print(f"\n  Transcript: {transcript_file}")
        # Lock identity — clear signing context from memory
        if hasattr(self, 'identity_provider') and self.identity_provider.is_authorized:
            self.identity_provider.lock()
            print(f"\n  Identity locked (signing context cleared)")

        print(f"\n  Session {self.session_number} ({self.phase}) complete.")
        print(f"  Identity: {self.identity_name} | Model: {self.model_name}")

        # Run dream consolidation to analyze this session
        print("\n" + "=" * 60)
        print("RUNNING DREAM CONSOLIDATION")
        print("=" * 60)
        try:
            from sage.raising.scripts.dream_consolidation import run_dream_consolidation
            run_dream_consolidation(str(self.instance.root), self.session_number)
            print("\n  Consolidation complete. Check raising_log.md for analysis.")
        except Exception as e:
            print(f"\n  WARNING: Dream consolidation failed: {e}")
            print("  Session data is saved, but no consolidation entry was written.")

    def _save_transcript(self) -> Path:
        """Save session transcript."""
        self.instance.sessions.mkdir(parents=True, exist_ok=True)
        transcript_file = self.instance.sessions / f"session_{self.session_number:03d}.json"

        conversation = []
        for turn in self.conversation_history:
            conversation.append({'speaker': 'Claude', 'text': turn['claude']})
            conversation.append({'speaker': 'SAGE', 'text': turn['sage']})

        transcript = {
            "session": self.session_number,
            "phase": self.phase,
            "machine": self.machine,
            "model": self.model_name,
            "model_family": self.model_family,
            "generation_mode": "ollama_irp",
            "identity": self.identity_name,
            "start": self.session_start.isoformat(),
            "end": datetime.now().isoformat(),
            "turns": len(self.conversation_history),
            # F-M2 P0: which prompt builder actually ran, and which digest sources
            # yielded content — without this the record cannot distinguish a
            # percept-free session from a working pipe (system prompt is not saved).
            "prompt_health": getattr(self, "_prompt_health", None),
            # F-M2' D1: delivery receipt — what sensory content entered this
            # session's context (sections + sizes). Complements prompt_health:
            # health says which sources yielded; this witnesses what was delivered.
            "sensory_delivery": getattr(self, "_sensory_delivery", None),
            "conversation": conversation
        }

        with open(transcript_file, 'w') as f:
            json.dump(transcript, f, indent=2)

        return transcript_file


def main():
    parser = argparse.ArgumentParser(
        description="SAGE OllamaIRP raising session (unified runner)",
        epilog=(
            "Machine and model are auto-detected from instance directories.\n"
            "Override with --machine and --model if needed.\n\n"
            "Examples:\n"
            "  python3 -m sage.raising.scripts.ollama_raising_session -c\n"
            "  python3 -m sage.raising.scripts.ollama_raising_session --machine legion -c\n"
            "  python3 -m sage.raising.scripts.ollama_raising_session --machine mcnugget --model gemma3:4b -c\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-c", "--continue", dest="continue_session",
                        action="store_true",
                        help="Continue from last session number")
    parser.add_argument("--session", type=int,
                        help="Specific session number")
    parser.add_argument("--machine", type=str, default=None,
                        help="Machine name (auto-detected if omitted)")
    parser.add_argument("--model", type=str, default=None,
                        help="Ollama model name (read from instance.json if omitted)")
    parser.add_argument("--turns", type=int, default=0,
                        help="Number of conversation turns (default: random 3-8)")
    parser.add_argument("--host", type=str, default='http://localhost:11434',
                        help="Ollama host URL")
    parser.add_argument("--advance-phase", action="store_true",
                        help="Advance to next phase before running session (instructor-driven)")

    args = parser.parse_args()

    # Diagnostic logging for empty response investigation
    logging.basicConfig(
        level=logging.WARNING,
        format='%(asctime)s %(name)s %(levelname)s %(message)s',
    )

    # Resolve instance — pass model too so we get the right instance
    # when multiple instances exist for the same machine
    instance = InstancePaths.resolve(machine=args.machine, model=args.model)
    if not instance.exists():
        print(f"Error: No instance directory found for machine={args.machine or '(auto)'}",
              file=sys.stderr)
        print(f"Run: python3 -m sage.instances.init --machine <name> --model <model>",
              file=sys.stderr)
        sys.exit(1)

    # Read manifest for defaults
    manifest = {}
    if instance.manifest.exists():
        with open(instance.manifest) as f:
            manifest = json.load(f)

    machine = manifest.get('machine', args.machine or 'unknown')
    model_name = args.model or manifest.get('model', 'qwen2:0.5b')
    model_family = manifest.get('model_family', 'unknown')

    session_num = args.session
    if args.continue_session:
        session_num = None

    # Variable session length: if not specified, randomize between 3-8
    import random
    num_turns = args.turns if args.turns > 0 else random.randint(3, 8)

    session = OllamaRaisingSession(
        machine=machine,
        model_name=model_name,
        instance=instance,
        session_number=session_num,
        num_turns=num_turns,
        ollama_host=args.host,
        model_family=model_family,
    )

    if args.advance_phase:
        session.advance_phase()

    session.load_model()
    session.run_conversation()
    session.close_session()


if __name__ == "__main__":
    main()
