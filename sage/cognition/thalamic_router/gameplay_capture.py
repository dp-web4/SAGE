#!/usr/bin/env python3
"""Gameplay capture — replay winning game traces to generate router shadow records.

The router shadow pipeline captures (kernel state → decision) pairs at
the router's decision boundary. But the daemon's consciousness loop
doesn't currently drive ARC-AGI-3 games — our solvers bypass the daemon.
So natural capture produces only idle-source records.

This module generates `source=gameplay` records by replaying known
winning traces through the arc_agi env and running the programmatic
baseline at each step. The result: training-data records that carry
real game context + real game outcomes, immediately joinable to
downstream training.

The records are HONEST about their provenance:
  metadata.source = 'gameplay'
  metadata.replay_source = 'run.json' | 'solutions.json'
  metadata.game = 'cd82'
  metadata.game_outcome = {...}  # attached at capture-end
  metadata.synthetic_kernel_state = True  # NOT from a live daemon tick

The `synthetic_kernel_state` flag lets Phase 1 training (and any
downstream consumer) distinguish replay-synthesized records from
live-daemon-captured records. Both are useful; they're not the same.

Spec: shared-context/arc-agi-3/phase2/brain-arch/thalamic-router-prd.md
      §5 (data sources — explicit non-goals), §4 Phase 1+
      shared-context/arc-agi-3/phase2/brain-arch/motor-skills.md
      (future: gameplay-through-skills when cerebellum + motor tier land)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sage.cognition.router.inputs import RouterInput, CARTRIDGE_EMBEDDING_DIM
from sage.cognition.router.outputs import RouterOutput
from sage.cognition.router.record import (
    RouterRecord,
    VALID_RECORD_SOURCES,
)
from sage.cognition.router.data import RouterDatasetWriter
from sage.cognition.router.baseline import programmatic_decide


# Path where arc_agi lives (SAGE's experiments tree)
ARC_AGI_EXPERIMENTS = Path(__file__).resolve().parents[3] / "arc-agi-3" / "experiments"


# Trace-action-string → GameAction-value mapping
_ACTION_STR_TO_INT = {
    "UP": 1, "DOWN": 2, "LEFT": 3, "RIGHT": 4,
    "SEL": 5, "SELECT": 5, "CLICK": 6, "UNDO": 7, "A0": 0,
}


# ───────────────────────────────────────────────────────────────────
# Trace loading
# ───────────────────────────────────────────────────────────────────

@dataclass
class TraceStep:
    """Normalized trace step — whatever the source format, we flatten to this."""
    index: int                    # 1-based position in the full trace
    level: Optional[int]          # game level (0-indexed) if known
    action: int                   # GameAction integer (1..7)
    data: Optional[Dict[str, Any]] = None   # click coords etc.


@dataclass
class Trace:
    """A replayable game trace with enough outcome info to attach to records."""
    game: str                     # short family name, e.g. 'cd82'
    game_id: str                  # full id, e.g. 'cd82-fb555c5d'
    source: str                   # 'run.json' | 'solutions.json'
    source_path: str              # absolute path
    steps: List[TraceStep]
    outcome: Dict[str, Any]       # what we know about the game-level result


def load_trace(path: Path, game_family: str, game_id: str) -> Trace:
    """Load either a run.json or solutions.json into a normalized Trace."""
    data = json.loads(Path(path).read_text())
    fmt = "unknown"
    steps: List[TraceStep] = []
    outcome: Dict[str, Any] = {}

    if isinstance(data, list) and (not data or isinstance(data[0], list)):
        # solutions.json — list of per-level action lists
        fmt = "solutions.json"
        idx = 0
        for lvl_idx, lvl in enumerate(data):
            for entry in lvl:
                if not isinstance(entry, dict) or "action" not in entry:
                    continue
                idx += 1
                steps.append(TraceStep(
                    index=idx, level=lvl_idx,
                    action=int(entry["action"]),
                    data=entry.get("data"),
                ))
        outcome = {
            "source_format": "solutions.json",
            "levels_in_solution": len(data),
            "inferred_won": True,   # solutions.json is by convention a winning trace
            "steps_total": idx,
        }
    elif isinstance(data, dict) and "steps" in data:
        # run.json — dict with `steps` list + metadata
        fmt = "run.json"
        for i, s in enumerate(data.get("steps") or [], start=1):
            action_raw = s.get("action")
            if isinstance(action_raw, int):
                action_int = action_raw
            elif isinstance(action_raw, str):
                action_int = _ACTION_STR_TO_INT.get(action_raw.upper(), -1)
            else:
                continue
            if action_int < 0:
                continue
            step_data: Optional[Dict[str, Any]] = None
            if action_int == 6:
                x, y = s.get("x"), s.get("y")
                if x is not None and y is not None:
                    step_data = {"x": x, "y": y}
            steps.append(TraceStep(
                index=i, level=s.get("level"),
                action=action_int, data=step_data,
            ))
        outcome = {
            "source_format": "run.json",
            "result": data.get("result"),
            "levels_completed": data.get("levels_completed"),
            "win_levels": data.get("win_levels") or data.get("win_levels_proved"),
            "final_level_index": data.get("final_level_index"),
            "total_steps": data.get("total_steps") or len(steps),
            "inferred_won": (
                str(data.get("result") or "").upper() == "WIN"
                or (isinstance(data.get("levels_completed"), int)
                    and isinstance(data.get("win_levels"), int)
                    and data["win_levels"] >= data["levels_completed"])
            ),
        }
    else:
        raise ValueError(f"Unknown trace format at {path}")

    return Trace(
        game=game_family, game_id=game_id,
        source=fmt, source_path=str(path),
        steps=steps, outcome=outcome,
    )


# ───────────────────────────────────────────────────────────────────
# Synthetic RouterInput from env state
# ───────────────────────────────────────────────────────────────────

def _frame_delta(prev_frame: Any, curr_frame: Any) -> float:
    """Pixel-delta normalized to [0,1] — used as a novelty/arousal proxy."""
    try:
        import numpy as np
        a = np.array(prev_frame)
        b = np.array(curr_frame)
        if a.shape != b.shape:
            return 1.0
        # Take the last layer if 3D (many ARC games have stacked frames)
        if a.ndim == 3:
            a, b = a[-1], b[-1]
        diff = (a != b).sum() / max(a.size, 1)
        return float(min(1.0, diff * 4.0))   # scale so small changes are visible
    except Exception:
        return 0.0


def synth_router_input(
    tick: int, prev_frame: Any, curr_frame: Any,
    step: TraceStep, game: str, level: Optional[int], atp: float,
) -> RouterInput:
    """Synthesize a plausible RouterInput from what we can observe during replay.

    This is NOT a replacement for live daemon capture — fields we can't
    observe from outside the loop (episodic recall, RPE priors, metacog
    blocks, cartridge) default to zero/empty. The synthetic flag in the
    record's metadata lets consumers filter if they want strict kernel-
    captured records only.
    """
    delta = _frame_delta(prev_frame, curr_frame)
    # SNARC: arousal proportional to frame change; novelty high at game start, decays
    arousal = delta
    novelty = max(0.0, 1.0 - tick / 200.0) if delta > 0.01 else 0.1
    surprise = delta * 0.8
    conflict = 0.2 if step.action == 6 else 0.1  # clicks carry more decision weight
    reward = 0.0  # not yet known at this tick — outcome attaches at end

    return RouterInput(
        tick=tick,
        timestamp=time.time(),
        goal_id=f"play:{game}:L{level}" if level is not None else f"play:{game}",
        wm_state_key=f"game:{game}:tick:{tick:04d}",
        wm_slot_counts={"goal": 1, "plan_step": 1},
        wm_goal_active=True,
        wm_age_ticks=tick,
        wm_pressure=0.3,
        sensory_modalities=["vision", "game_frame"],
        sensory_novelty=novelty,
        sensory_urgency=min(1.0, arousal * 1.2),
        snarc_surprise=surprise,
        snarc_novelty=novelty,
        snarc_arousal=arousal,
        snarc_reward=reward,
        snarc_conflict=conflict,
        metabolic_state="focus",   # game-play = focused
        atp_level=max(10.0, atp),
        atp_trend="falling",
        recall_count=0,
        recall_best_similarity=0.0,
        recall_best_outcome=None,
        habit_available=False,
        habit_confidence=0.0,
        prior_invoke=0.5,
        prior_habit=0.0,
        prior_noop=0.5,
        metacog_block_list=[],
        cartridge_recall_count=0,
        cartridge_recall_best_similarity=0.0,
        cartridge_recall_embedding=[0.0] * CARTRIDGE_EMBEDDING_DIM,
    )


# ───────────────────────────────────────────────────────────────────
# Plugin registry (minimal — just enough for programmatic_decide)
# ───────────────────────────────────────────────────────────────────

def _minimal_plugin_registry() -> Dict[str, Dict[str, Any]]:
    """Minimal registry matching what the programmatic baseline expects.

    The real daemon has a richer registry; for replay we only need the
    plugin names + tiers programmatic_decide references.
    """
    return {
        "vision": {"tier": "specialized", "atp_cost": 10, "latency_ms": 50},
        "control": {"tier": "routine", "atp_cost": 2, "latency_ms": 5},
        "language": {"tier": "routine", "atp_cost": 5, "latency_ms": 100},
        "memory": {"tier": "reflex", "atp_cost": 1, "latency_ms": 1},
    }


# ───────────────────────────────────────────────────────────────────
# Capture runner
# ───────────────────────────────────────────────────────────────────

@dataclass
class CaptureResult:
    game: str
    game_id: str
    records_emitted: int
    steps_total: int
    steps_applied: int
    errors: List[str] = field(default_factory=list)
    final_state: Optional[str] = None
    final_levels_completed: Optional[int] = None


class GameplayCapture:
    """Replay a winning trace, emit source=gameplay records.

    Lifecycle:
      1. Construct with (trace, writer, [env_factory])
      2. Call run() — advances the env step-by-step, emits one RouterRecord per step
      3. Check result — records_emitted + final_state

    The writer is externally owned so callers can batch multiple captures
    to the same partition, or use a mock writer in tests.
    """

    def __init__(
        self,
        trace: Trace,
        writer: RouterDatasetWriter,
        machine: str,
        env_factory=None,              # callable → (env, reset_frame)
        atp_initial: float = 80.0,
        atp_decay_per_step: float = 0.15,
    ):
        self.trace = trace
        self.writer = writer
        self.machine = machine
        self.env_factory = env_factory  # None → lazy import of arc_agi
        self.atp = atp_initial
        self.atp_decay = atp_decay_per_step
        self.records: List[RouterRecord] = []
        self.errors: List[str] = []

    def _make_env(self):
        if self.env_factory is not None:
            return self.env_factory()
        # Lazy import — arc_agi is optional (tests can inject via env_factory)
        if str(ARC_AGI_EXPERIMENTS) not in sys.path:
            sys.path.insert(0, str(ARC_AGI_EXPERIMENTS))
        from arc_agi import Arcade
        arc = Arcade(operation_mode="offline")
        # Try the trace's pinned version first (reproducibility). If the SDK
        # no longer has that version (common — traces age out), fall back to
        # the short family id so the SDK auto-selects the latest local version.
        env = arc.make(self.trace.game_id)
        if env is None:
            env = arc.make(self.trace.game)
            if env is not None:
                self.errors.append(
                    f"version_fallback: trace pinned {self.trace.game_id}, "
                    f"using latest local version for family {self.trace.game}"
                )
        if env is None:
            raise RuntimeError(
                f"arc.make returned None for both {self.trace.game_id} "
                f"and {self.trace.game}"
            )
        fd = env.reset()
        return env, fd

    def _attach_outcome(self, game_outcome: Dict[str, Any]) -> None:
        """Enrich every emitted record with the final game outcome.

        Records are already written to disk at this point. The in-memory
        `self.records` list is updated so callers can re-emit to an
        outcome-enriched sidecar if desired, but main partition records
        are NOT re-written (immutable capture principle).
        """
        for i, rec in enumerate(self.records):
            md = dict(rec.metadata)
            md["game_outcome"] = dict(game_outcome)
            self.records[i] = rec.__class__(
                router_input=rec.router_input,
                router_output=rec.router_output,
                record_id=rec.record_id,
                schema_version=rec.schema_version,
                timestamp=rec.timestamp,
                machine=rec.machine,
                outcome=rec.outcome,
                metadata=md,
            )

    def run(self) -> CaptureResult:
        """Replay the trace, emit records per step. Returns summary."""
        try:
            env, fd = self._make_env()
        except Exception as e:
            self.errors.append(f"env init failed: {e!r}")
            return CaptureResult(
                game=self.trace.game, game_id=self.trace.game_id,
                records_emitted=0, steps_total=len(self.trace.steps),
                steps_applied=0, errors=list(self.errors),
            )

        # Import GameAction lazily for action-int → enum mapping
        try:
            from arcengine import GameAction
            int_to_action = {ga.value: ga for ga in GameAction}
        except Exception:
            int_to_action = {}

        steps_applied = 0
        prev_frame = getattr(fd, "frame", None)

        for step in self.trace.steps:
            curr_frame = getattr(fd, "frame", None)

            # Synthesize RouterInput for THIS tick (pre-action)
            router_input = synth_router_input(
                tick=step.index,
                prev_frame=prev_frame,
                curr_frame=curr_frame,
                step=step,
                game=self.trace.game,
                level=step.level,
                atp=self.atp,
            )
            # Call programmatic baseline
            try:
                router_output = programmatic_decide(
                    router_input, _minimal_plugin_registry()
                )
            except Exception as e:
                self.errors.append(f"step {step.index}: decide failed: {e!r}")
                continue

            # Build the record with provenance metadata.
            #
            # `known_good_*` fields are the supervised-training labels. Since
            # this trace is a WIN, the action actually taken at this tick is
            # by definition a good next action. This lets downstream training
            # use the record as a supervised triple:
            #   state → (baseline-proposed dispatch)  [router BC]
            #   state → known_good_action             [action prediction]
            #   state × skill_params → known_good_action [motor-skill BC]
            # Plus outcome-weighted shaping: sample weight ∝ game_outcome.won.
            metadata = {
                "source": "gameplay",
                "game": self.trace.game,
                "game_id": self.trace.game_id,
                "replay_source": self.trace.source,
                "replay_source_path": self.trace.source_path,
                "step_index": step.index,
                "level": step.level,
                "synthetic_kernel_state": True,
                # Supervised labels from the winning trace
                "known_good_action": step.action,
                "known_good_data": step.data,
                "known_good_level": step.level,
            }
            record = RouterRecord(
                router_input=router_input,
                router_output=router_output,
                machine=self.machine,
                metadata=metadata,
            )
            self.records.append(record)
            try:
                self.writer.append(record.to_dict())
            except Exception as e:
                self.errors.append(f"step {step.index}: write failed: {e!r}")

            # Apply the action to advance the env.
            # Translate int → GameAction when arcengine is available; when
            # it isn't (tests, machines without the SDK), pass the raw int.
            # The env either accepts it (MockEnv) or raises (caught below).
            if int_to_action:
                ga = int_to_action.get(step.action)
            else:
                ga = step.action
            try:
                if ga is not None:
                    fd = env.step(ga, data=step.data) if step.data else env.step(ga)
                    steps_applied += 1
                    prev_frame = curr_frame
                    self.atp = max(10.0, self.atp - self.atp_decay)
            except Exception as e:
                self.errors.append(f"step {step.index}: env.step failed: {e!r}")

        # Compose final game_outcome from env state + trace outcome
        final_state = getattr(getattr(fd, "state", None), "name", None)
        final_levels = getattr(fd, "levels_completed", None)
        game_outcome = {
            "final_state": final_state,
            "final_levels_completed": final_levels,
            "won": (final_state == "WIN")
                   if final_state is not None
                   else bool(self.trace.outcome.get("inferred_won")),
            **self.trace.outcome,   # also include source/file metadata
        }
        self._attach_outcome(game_outcome)

        return CaptureResult(
            game=self.trace.game, game_id=self.trace.game_id,
            records_emitted=len(self.records),
            steps_total=len(self.trace.steps),
            steps_applied=steps_applied,
            errors=list(self.errors),
            final_state=final_state,
            final_levels_completed=final_levels,
        )


# ───────────────────────────────────────────────────────────────────
# CLI
# ───────────────────────────────────────────────────────────────────

def _discover_trace(game_family: str, game_id: str) -> Optional[Path]:
    """Find the best replayable trace for a game: solutions.json > latest run_*"""
    # Search multiple workspace roots — different machines use different paths
    for root in [
        Path(os.environ.get("ARC_SAGE_DIR", "")),
        Path("/mnt/c/exe/projects/ai-agents/ARC-SAGE"),
        Path("/mnt/c/projects/ai-agents/arc-sage"),
        Path.home() / "ai-agents" / "arc-sage",
        Path.home() / "ai-workspace" / "ARC-SAGE",
        Path.home() / "repos" / "ARC-SAGE",
    ]:
        vm = root / "knowledge" / "visual-memory" / game_family
        if vm.is_dir():
            break
    else:
        return None
    vm = vm  # use the found path
    if not vm.is_dir():
        return None
    sol = vm / "solutions.json"
    if sol.exists() and _is_actionable_solutions(sol):
        return sol
    # Otherwise newest run_ dir with a run.json
    runs = sorted(
        [d for d in vm.iterdir() if d.is_dir() and d.name.startswith("run_")],
        key=lambda d: d.stat().st_mtime, reverse=True,
    )
    for run_dir in runs:
        run_json = run_dir / "run.json"
        if run_json.exists():
            return run_json
    # Last resort — return solutions.json even if not actionable; load_trace
    # will raise a clear error. Better than silently returning None.
    return sol if sol.exists() else None


def _is_actionable_solutions(path: Path) -> bool:
    """Quick peek to check if solutions.json is the per-step action-list format
    (list-of-lists-of-dicts-with-"action") vs a summary format (e.g. ka59's
    {"solutions": {"L0": {"moves": N, ...}}} which has no executable actions).
    """
    try:
        data = json.loads(path.read_text())
    except Exception:
        return False
    if isinstance(data, list):
        # Top-level list: expected action-per-level format. Check one action.
        if data and isinstance(data[0], list):
            first = data[0]
            if first and isinstance(first[0], dict) and "action" in first[0]:
                return True
        return False
    # Any other shape (dict, etc.) is a summary/metadata file — not actionable.
    return False


def main() -> int:
    p = argparse.ArgumentParser(
        description="Replay game traces → emit source=gameplay router shadow records.",
    )
    p.add_argument("--game", required=True,
                   help="Short game family name (e.g. cd82, bp35, lf52)")
    p.add_argument("--game-id", default=None,
                   help="Full game id (e.g. cd82-fb555c5d). Defaults: looked up from game_coordination.json")
    p.add_argument("--trace", default=None,
                   help="Explicit trace path (run.json or solutions.json). Auto-discovered if omitted.")
    p.add_argument("--machine", default=os.environ.get("SAGE_MACHINE", "cbp"))
    p.add_argument("--data-dir",
                   default=os.environ.get(
                       "SAGE_ROUTER_DATA_DIR",
                       "/mnt/c/exe/projects/ai-agents/private-context/training-data/router"))
    args = p.parse_args()

    # Resolve game_id if not provided
    game_id = args.game_id
    if not game_id:
        # Search multiple workspace roots for coordination JSON
        coord_path = None
        for root in [
            Path(os.environ.get("ARC_SAGE_DIR", "")),
            Path("/mnt/c/exe/projects/ai-agents/ARC-SAGE"),
            Path("/mnt/c/projects/ai-agents/arc-sage"),
            Path.home() / "ai-agents" / "arc-sage",
            Path("/mnt/c/projects/ai-agents/shared-context/arc-agi-3"),
            Path.home() / "ai-agents" / "shared-context" / "arc-agi-3",
            Path.home() / "ai-workspace" / "ARC-SAGE",
            Path.home() / "repos" / "ARC-SAGE",
        ]:
            candidate = root / "knowledge" / "game_coordination.json"
            if not candidate.exists():
                candidate = root / "game_coordination.json"
            if candidate.exists():
                coord_path = candidate
                break
        if coord_path is None:
            coord_path = Path("/dev/null")  # will fail gracefully below
        try:
            coord = json.loads(coord_path.read_text())
            for g in coord.get("games", []):
                if g.get("family") == args.game:
                    game_id = g.get("id")
                    break
        except Exception:
            pass
        if not game_id:
            print(f"ERROR: could not resolve game_id for {args.game}. Pass --game-id.")
            return 1

    # Resolve trace
    trace_path = Path(args.trace) if args.trace else _discover_trace(args.game, game_id)
    if not trace_path or not trace_path.exists():
        print(f"ERROR: no trace found for {args.game}. Pass --trace explicitly.")
        return 1
    print(f"Loading trace from {trace_path}")
    trace = load_trace(trace_path, args.game, game_id)
    print(f"  format={trace.source} steps={len(trace.steps)} outcome={trace.outcome}")

    # Writer — gameplay records land in {machine}/gameplay/ to avoid
    # gzip-append concurrency corruption with the live router daemon
    # writing to {machine}/{today}.jsonl.gz.
    writer = RouterDatasetWriter(
        base_dir=Path(args.data_dir),
        machine=args.machine,
        compress=True,
        subdir="gameplay",
    )
    capture = GameplayCapture(trace=trace, writer=writer, machine=args.machine)
    result = capture.run()
    writer.close()

    print(f"\n=== Capture result ===")
    print(f"  records_emitted: {result.records_emitted}")
    print(f"  steps_applied:   {result.steps_applied} / {result.steps_total}")
    print(f"  final_state:     {result.final_state}")
    print(f"  final_levels:    {result.final_levels_completed}")
    print(f"  errors:          {len(result.errors)}")
    for err in result.errors[:5]:
        print(f"    - {err}")

    return 0 if result.records_emitted > 0 else 2


if __name__ == "__main__":
    sys.exit(main())
