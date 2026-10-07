#!/usr/bin/env python3
"""llm_dispatch — the router's invoke head meets an actual LLM.

At each game step:
  1. NN observes state, runs v4 adapter → (decision, play_action, hint_ranking)
  2. If decision == "play" → env.step(play_action, center-click if CLICK)
  3. If decision == "invoke" → render prev + curr frames as PNG, build a
     context+hint prompt, POST to a local vision LLM (Ollama by default),
     parse the response for ACTION=<n> [X=<x> Y=<y>], env.step that

This is the first time the invoke head's output actually gets consumed by
an LLM. The LLM sees the frames, considers the NN's hint, and either
confirms or overrides. Its response is logged for later analysis.

Backend: Ollama HTTP API at localhost:11434 by default, configurable via
SAGE_LLM_MODEL and SAGE_LLM_BASE_URL env vars. Default model
llama3.2-vision:11b — US-origin, vision-capable, fits in 8GB VRAM.

Spec: shared-context/arc-agi-3/phase2/brain-arch/phase-2-world-model-embedding-sprint.md
      (this is the Phase-3 follow-on: router + LLM consuming its hint)
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import sys
import time
from collections import deque
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn.functional as F

from sage.cognition.router.data import RouterDatasetWriter
from sage.cognition.router.record import RouterRecord
from sage.cognition.router.outputs import RouterOutput
from sage.cognition.thalamic_router.frame_router import (
    FrameRouter, FrameRouterConfig, load_frame_router,
    onehot_frame, build_scalar_vector,
    N_ACTIONS, ACTION_NAMES, FRAME_H, FRAME_W, N_COLORS, RECENT_ACTIONS_K,
)
from sage.cognition.thalamic_router.gameplay_capture import (
    load_trace, _discover_trace, ARC_AGI_EXPERIMENTS,
)

# Three-party conversation components (Nomad B1 + Thor B2, optional imports
# — dispatch falls back gracefully when either is unavailable)
try:
    from sage.cognition.metacog.core import Metacog, MetacogConfig
    _METACOG_AVAILABLE = True
except ImportError:
    Metacog = None  # type: ignore
    MetacogConfig = None  # type: ignore
    _METACOG_AVAILABLE = False

try:
    from sage.cognition.episodic.index import EpisodicIndex
    from sage.cognition.episodic.gameplay_recall import (
        recall_gameplay, format_recall_for_prompt, GameStateCue,
    )
    _EPISODIC_AVAILABLE = True
except ImportError:
    EpisodicIndex = None  # type: ignore
    _EPISODIC_AVAILABLE = False

# Grounded reasoning metrics (Phase 4 B6) — always available, no external deps
from sage.cognition.thalamic_router.grounded_metrics import (
    compute_grounded_metrics, aggregate_grounded_metrics,
)

# MRH context architecture (Phase 5) — structured block-based context assembly
try:
    from sage.context.mrh import (
        MRHContext,
        IdentityBlock, SensorsBlock, EffectorsBlock,
        MechanicsBlock, ExperientialCacheBlock,
        MetabolicBlock, TaskBlock,
    )
    from sage.context.mrh.base import ImageAttachment
    from sage.context.mrh.experiential import TrajectoryEntry as MRHTrajectoryEntry, EpisodicMatch as MRHEpisodicMatch
    from sage.context.mrh.metabolic import MetacogSignalSummary
    _MRH_AVAILABLE = True
except ImportError:
    _MRH_AVAILABLE = False


# Multi-turn conversation default — env SAGE_DISPATCH_MULTITURN=0 to fall
# back to legacy stateless single-call mode for debugging.
_MULTITURN_DEFAULT = os.environ.get("SAGE_DISPATCH_MULTITURN", "1") not in ("0", "false", "False")

# Memory trimming thresholds (B5). Keep last N turn pairs verbatim; older
# turns get dropped and replaced by a trajectory-derived summary preamble
# in the next user turn. Sprout consensus: NEVER quote the LLM back to
# itself in summaries — use trajectory data only.
MAX_CONVERSATION_TURNS = 20      # 10 user + 10 assistant pairs
KEEP_VERBATIM_TURNS = 10         # 5 user + 5 assistant pairs

# Episodic index — lazily loaded once per process. Path configurable via
# env SAGE_EPISODIC_DB. Missing DB → no episodic recall, dispatch continues.
_EPISODIC_INDEX_CACHE: Any = None


def _resolve_workspace_root() -> Optional[Path]:
    """Find the workspace root (the dir containing both SAGE and private-context).

    Matches the pattern used by _resolve_gameplay_system_prompt_path.
    Returns None if no workspace is detectable.
    """
    for candidate in [
        Path(os.environ.get("SAGE_WORKSPACE", "")),
        Path("/mnt/c/exe/projects/ai-agents"),
        Path.home() / "ai-workspace",
        Path.home() / "repos",
    ]:
        if (candidate / "private-context").exists() and (candidate / "SAGE").exists():
            return candidate
    return None


def _resolve_router_data_dir() -> Path:
    """Find the router training-data dir for the current machine.

    Resolution order:
      1. SAGE_ROUTER_DATA_DIR env var (absolute)
      2. <workspace>/private-context/training-data/router
      3. Fallback: CWD-relative (will likely fail gracefully when used)
    """
    env_path = os.environ.get("SAGE_ROUTER_DATA_DIR")
    if env_path:
        return Path(env_path)
    root = _resolve_workspace_root()
    if root is not None:
        return root / "private-context" / "training-data" / "router"
    # Last-resort fallback; caller will likely see errors on write.
    return Path("./training-data/router")


def _load_episodic_index() -> Any:
    """Lazy-load the episodic index. Returns None if DB missing or import fails."""
    global _EPISODIC_INDEX_CACHE
    if _EPISODIC_INDEX_CACHE is not None:
        return _EPISODIC_INDEX_CACHE if _EPISODIC_INDEX_CACHE != "missing" else None
    if not _EPISODIC_AVAILABLE:
        _EPISODIC_INDEX_CACHE = "missing"
        return None
    db_path_env = os.environ.get("SAGE_EPISODIC_DB")
    candidates: List[Optional[Path]] = [
        Path(db_path_env) if db_path_env else None,
    ]
    root = _resolve_workspace_root()
    if root is not None:
        candidates.append(root / "private-context" / "training-data" / "episodic" / "thor_episodes.db")
    for p in candidates:
        if p and p.exists():
            try:
                _EPISODIC_INDEX_CACHE = EpisodicIndex(db_path=str(p))
                return _EPISODIC_INDEX_CACHE
            except Exception:
                continue
    _EPISODIC_INDEX_CACHE = "missing"
    return None


# Default thresholds for the dispatch decision
INVOKE_THRESHOLD = 0.5
PLAY_CONFIDENCE_THRESHOLD = 0.55
PLAY_MARGIN_THRESHOLD = 0.05
STUCK_WINDOW = 5
STUCK_FRAME_EPS = 1e-3
PROGRESS_STALL_WINDOW = 30

# Canonical ARC-AGI-3 palette for rendering frames to PNG for the vision LLM.
# 16 distinct colors indexed 0-15.
_PALETTE_RGB = [
    (0, 0, 0),          # 0 black
    (0, 116, 217),      # 1 blue
    (255, 65, 54),      # 2 red
    (46, 204, 64),      # 3 green
    (255, 220, 0),      # 4 yellow
    (170, 170, 170),    # 5 grey
    (240, 18, 190),     # 6 magenta
    (255, 133, 27),     # 7 orange
    (127, 219, 255),    # 8 cyan
    (139, 69, 19),      # 9 brown
    (128, 0, 128),      # 10 purple
    (0, 128, 128),      # 11 teal
    (255, 192, 203),    # 12 pink
    (0, 255, 0),        # 13 lime
    (100, 100, 100),    # 14 dark grey
    (255, 255, 255),    # 15 white
]


def _frame_int_from_onehot(oh: np.ndarray) -> np.ndarray:
    """Inverse of onehot_frame — recover the integer grid (H, W)."""
    return oh.argmax(axis=0).astype(np.int32)


def _frame_to_rgb(frame_oh_or_raw: Any) -> np.ndarray:
    arr = np.asarray(frame_oh_or_raw)
    if arr.ndim == 3 and arr.shape[0] == N_COLORS:
        grid = _frame_int_from_onehot(arr.astype(np.float32))
    elif arr.ndim == 3:
        grid = arr[-1].astype(np.int32)
    elif arr.ndim == 2:
        grid = arr.astype(np.int32)
    else:
        grid = np.zeros((FRAME_H, FRAME_W), dtype=np.int32)
    h, w = grid.shape
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    for i, (r, g, b) in enumerate(_PALETTE_RGB):
        mask = (grid == i)
        rgb[mask] = (r, g, b)
    return rgb


def _upscale(rgb: np.ndarray, scale: int) -> np.ndarray:
    if scale <= 1:
        return rgb
    return np.repeat(np.repeat(rgb, scale, axis=0), scale, axis=1)


def render_frame_png(frame_oh_or_raw: Any, scale: int = 4) -> bytes:
    """Render a single frame to PNG bytes (one-hot or raw int grid)."""
    rgb = _upscale(_frame_to_rgb(frame_oh_or_raw), scale)
    try:
        from PIL import Image
        img = Image.fromarray(rgb)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        header = f"P6\n{rgb.shape[1]} {rgb.shape[0]}\n255\n".encode()
        return header + rgb.tobytes()


def render_frame_pair_png(
    prev_frame: Any, curr_frame: Any, scale: int = 4, gap: int = 8,
) -> bytes:
    """Stitch prev and curr into one side-by-side PNG with a black gap between
    them. Many vision LLMs only accept one image per turn; this gets both
    frames to the model in a single attachment.

    Layout: [ PREV frame | gap | CURR frame ]
    """
    prev_rgb = _upscale(_frame_to_rgb(prev_frame), scale)
    curr_rgb = _upscale(_frame_to_rgb(curr_frame), scale)
    h = max(prev_rgb.shape[0], curr_rgb.shape[0])
    # Pad shorter to match height
    def _pad(rgb, target_h):
        if rgb.shape[0] == target_h:
            return rgb
        pad = np.zeros((target_h - rgb.shape[0], rgb.shape[1], 3), dtype=np.uint8)
        return np.vstack([rgb, pad])
    prev_rgb = _pad(prev_rgb, h)
    curr_rgb = _pad(curr_rgb, h)
    # Black gap column + simple label strip on top with text would be nice but
    # PIL text rendering adds a dep we don't strictly need. The gap itself
    # plus the prompt's explicit "LEFT=PREV RIGHT=CURR" is enough.
    gap_col = np.zeros((h, gap, 3), dtype=np.uint8)
    stitched = np.hstack([prev_rgb, gap_col, curr_rgb])
    try:
        from PIL import Image
        img = Image.fromarray(stitched)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        header = f"P6\n{stitched.shape[1]} {stitched.shape[0]}\n255\n".encode()
        return header + stitched.tobytes()


# ───────────────────────────────────────────────────────────────────
# LLM client — Ollama HTTP API
# ───────────────────────────────────────────────────────────────────

class LLMClient:
    """Abstract interface for dispatched-LLM clients.

    Supports both single-call (stateless) and multi-turn (conversation) modes:

      - Single-call: chat(prompt, images_png=[...]) — legacy shape, full context
        re-assembled each call. history defaults to None.

      - Multi-turn: chat(user_message, history=[...], system_prompt="...",
        images_png=[...]) — system prompt injected once (cached in adapter
        context), history carries prior (user, assistant) turns, each call
        appends one new user turn.

    The three-party gameplay conversation uses the multi-turn mode: the
    dispatcher holds conversation_history per game session, the system
    prompt is the canonical fleet gameplay prompt + game-specific session
    init (world model + mechanics cluster + cartridge + level hint), and
    each invocation appends a new CNN narration user turn.

    Implementations should gracefully fall back to single-call behavior
    when history is None.
    """
    model: str

    def chat(
        self,
        prompt: str,
        images_png: Optional[List[bytes]] = None,
        max_tokens: int = 300,
        history: Optional[List[Dict[str, str]]] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Send a prompt (or user message + history) and return the response.

        history: if provided, a list of {"role": "user"|"assistant", "content": str}
                 dicts from prior invocations in this session.
        system_prompt: if provided, used as the system role message (only
                       meaningful in multi-turn mode).
        """
        raise NotImplementedError


class OllamaClient(LLMClient):
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.2-vision:11b",
        timeout: float = 60.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def chat(
        self, prompt: str, images_png: Optional[List[bytes]] = None,
        max_tokens: int = 300,
        history: Optional[List[Dict[str, str]]] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        """POST to /api/chat with optional image attachments.
        Returns the assistant's response text.

        Multi-turn mode (history + system_prompt provided): builds a messages
        array with system + history turns + new user turn. Images attach to
        the new user turn only.

        Single-call mode (history None): legacy behavior — one user message
        with full prompt.
        """
        import urllib.request, urllib.error

        messages: List[Dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history:
            for turn in history:
                messages.append({"role": turn["role"], "content": turn["content"]})

        new_user_msg: Dict[str, Any] = {"role": "user", "content": prompt}
        if images_png:
            new_user_msg["images"] = [
                base64.b64encode(b).decode("ascii") for b in images_png
            ]
        messages.append(new_user_msg)

        # Gemma4 produces empty responses with num_predict+temperature in options.
        # Use think: false (mandatory for gemma4 speed) and keep options minimal.
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": False,
        }
        # DO NOT send options — any options hash triggers an ollama model
        # reload that disables flash attention and drops GPU layers from
        # 49 to 13 on Apple Silicon. The 14s→40s regression was caused by
        # this. Let server defaults handle num_predict/temperature.
        # See: explorations/mcnugget-ollama-perf-diagnosis-2026-04-22/
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                body = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return f"ERROR: HTTP {e.code} — {e.read().decode('utf-8', 'ignore')[:200]}"
        except Exception as e:
            return f"ERROR: {type(e).__name__}: {e}"
        msg = body.get("message") or {}
        return str(msg.get("content", "") or "")


class ClaudeCLIClient(LLMClient):
    """Claude via the `claude` CLI with OAuth subscription auth.

    Uses the Max x20 subscription instead of the Anthropic API — no credit
    balance drain. Slightly more overhead than direct API (process spawn
    per call), but free under the subscription.

    Works by writing images to a temp dir, referencing them in the prompt,
    and letting Claude Code's Read tool load them during its turn.
    Uses --dangerously-skip-permissions + --add-dir to auto-approve reads
    of the temp directory.

    Default model: "sonnet" (current default-shortcut in Claude Code).
    For strategic use of stronger reasoning, pass "opus".
    """
    def __init__(
        self,
        model: str = "sonnet",
        timeout: float = 90.0,
        temp_dir: Optional[Path] = None,
        claude_bin: Optional[str] = None,
    ):
        import shutil, subprocess as _sp
        self.model = model
        self.timeout = timeout
        self._subprocess = _sp
        self._tempdir = Path(temp_dir) if temp_dir else Path("/tmp/sage_llm_dispatch")
        self._tempdir.mkdir(parents=True, exist_ok=True)
        self._bin = claude_bin or shutil.which("claude")
        if not self._bin:
            # Common install paths
            for candidate in [
                Path.home() / ".local" / "bin" / "claude",
                Path("/usr/local/bin/claude"),
                Path.home() / ".npm-global" / "bin" / "claude",
            ]:
                if candidate.exists():
                    self._bin = str(candidate); break
        if not self._bin:
            raise RuntimeError("claude CLI not found in PATH or common install locations")

    def chat(
        self, prompt: str, images_png: Optional[List[bytes]] = None,
        max_tokens: int = 300,
        history: Optional[List[Dict[str, str]]] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Invoke `claude --print`, attaching any images via temp files.
        Returns the assistant's response text.

        Multi-turn mode: serializes history as [System] / [User] / [Assistant]
        prose tags that Claude parses natively (same format as SAGE's
        ChatAPIAdapter prose mode). claude_cli subprocess is stateless per
        call, but Claude recognizes the tagged conversation and responds to
        the final user turn.

        Single-call mode: legacy — one prompt, no history framing.
        """
        # Write images to temp files; reference them in the prompt
        img_refs: List[str] = []
        written: List[Path] = []
        for i, img_bytes in enumerate(images_png or []):
            path = self._tempdir / f"frame_{int(time.time()*1000)}_{i}.png"
            try:
                path.write_bytes(img_bytes)
                written.append(path)
                img_refs.append(str(path))
            except Exception:
                continue

        img_preamble = ""
        if img_refs:
            img_preamble = (
                "Please use your Read tool to view the following image file(s):\n"
                + "\n".join(f"  {p}" for p in img_refs)
                + "\n\n"
            )

        if history is not None or system_prompt is not None:
            # Multi-turn: serialize as tagged conversation
            parts: List[str] = []
            if system_prompt:
                parts.append(f"[System]\n{system_prompt}\n")
            if history:
                for turn in history:
                    role = turn["role"]
                    tag = "User" if role == "user" else "Assistant"
                    parts.append(f"[{tag}]:\n{turn['content']}\n")
            parts.append(f"[User]:\n{img_preamble}{prompt}\n")
            parts.append("[Assistant]:")  # Claude fills this
            full_prompt = "\n".join(parts)
        else:
            # Single-call mode: legacy behavior
            full_prompt = img_preamble + prompt

        try:
            # Set a max token constraint via CLAUDE_CODE_SIMPLE-ish flags.
            # --bare is too minimal; use defaults but dangerously-skip-permissions
            # so the Read tool doesn't pause for approval.
            result = self._subprocess.run(
                [
                    self._bin, "--print",
                    "--model", self.model,
                    "--dangerously-skip-permissions",
                    "--add-dir", str(self._tempdir),
                ],
                input=full_prompt.encode("utf-8"),
                capture_output=True, timeout=self.timeout,
            )
            if result.returncode != 0:
                return f"ERROR: returncode={result.returncode}: {result.stderr.decode('utf-8','ignore')[:200]}"
            return result.stdout.decode("utf-8", errors="ignore").strip()
        except self._subprocess.TimeoutExpired:
            return "ERROR: TimeoutExpired"
        except Exception as e:
            return f"ERROR: {type(e).__name__}: {e}"
        finally:
            # Clean up temp files
            for p in written:
                try: p.unlink()
                except Exception: pass


class AnthropicClient(LLMClient):
    """Anthropic API backend via the official SDK. For the ceiling experiment:
    does claude-opus + our triage + world-model context actually play games?

    Requires ANTHROPIC_API_KEY env var. Default model claude-opus-4-7.
    """
    def __init__(
        self,
        model: str = "claude-opus-4-7",
        api_key: Optional[str] = None,
        timeout: float = 60.0,
        max_retries: int = 2,
    ):
        self.model = model
        self.timeout = timeout
        # Lazy import so Ollama-only users don't need the SDK
        try:
            import anthropic
        except ImportError as e:
            raise RuntimeError(
                "anthropic SDK not installed. pip install anthropic"
            ) from e
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY not set and not provided")
        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=key, max_retries=max_retries,
                                            timeout=timeout)

    def chat(
        self, prompt: str, images_png: Optional[List[bytes]] = None,
        max_tokens: int = 300,
        history: Optional[List[Dict[str, str]]] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Send the prompt (+ optional images) to Claude. Images accepted
        as a LIST (unlike Ollama's stitched-only approach). Returns text.

        Multi-turn mode: uses Anthropic's native messages array with system
        param and conversation turns. Caching applies naturally to the
        system message when identical across calls.
        """
        content_blocks: List[Dict[str, Any]] = []
        for img_bytes in (images_png or []):
            content_blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": base64.b64encode(img_bytes).decode("ascii"),
                },
            })
        content_blocks.append({"type": "text", "text": prompt})

        messages: List[Dict[str, Any]] = []
        if history:
            for turn in history:
                messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({"role": "user", "content": content_blocks})

        create_kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system_prompt:
            create_kwargs["system"] = system_prompt

        try:
            resp = self._client.messages.create(**create_kwargs)
        except self._anthropic.APIError as e:
            return f"ERROR: APIError: {e}"
        except Exception as e:
            return f"ERROR: {type(e).__name__}: {e}"
        # Response shape: resp.content is list of blocks, text in TextBlock
        parts: List[str] = []
        for block in resp.content:
            if getattr(block, "type", None) == "text":
                parts.append(block.text)
        return "".join(parts) or str(resp.content)[:500]


# ───────────────────────────────────────────────────────────────────
# Prompt + response parsing
# ───────────────────────────────────────────────────────────────────

# Fallback prompt used only if the fleet-canonical MD file is missing.
# Canonical source: shared-context/arc-agi-3/gameplay_system_prompt.md.
# Kept brief; the real prompt is ~200 lines and loaded from disk.
_FALLBACK_SYSTEM_PROMPT = """You are the deliberation tier of SAGE, a cognition kernel playing \
ARC-AGI-3 grid-based puzzle games. A small neural router has flagged this state as \
requiring deliberation. You see two images: the previous game frame and the current \
game frame. Cells are 16 colors. The grid is 64x64.

The neural network provides hints. Your job: pick the best next action to make \
progress toward winning the level."""


def _resolve_gameplay_system_prompt_path() -> Optional[Path]:
    """Find shared-context/arc-agi-3/gameplay_system_prompt.md across the
    common repo layouts used by the fleet. Returns None if not found."""
    candidates = [
        Path(os.environ.get("SHARED_CONTEXT_DIR", "")) / "arc-agi-3" / "gameplay_system_prompt.md",
        Path("/mnt/c/exe/projects/ai-agents/shared-context") / "arc-agi-3" / "gameplay_system_prompt.md",
        Path.home() / "ai-workspace" / "shared-context" / "arc-agi-3" / "gameplay_system_prompt.md",
        Path.home() / "repos" / "shared-context" / "arc-agi-3" / "gameplay_system_prompt.md",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _load_gameplay_system_prompt() -> str:
    """Load the fleet-canonical gameplay system prompt. Caches at module level
    so we read disk at most once per process."""
    global _SYSTEM_PROMPT_CACHE
    if _SYSTEM_PROMPT_CACHE is not None:
        return _SYSTEM_PROMPT_CACHE
    path = _resolve_gameplay_system_prompt_path()
    if path is not None:
        try:
            _SYSTEM_PROMPT_CACHE = path.read_text(encoding="utf-8").strip()
            return _SYSTEM_PROMPT_CACHE
        except Exception:
            pass
    _SYSTEM_PROMPT_CACHE = _FALLBACK_SYSTEM_PROMPT
    return _SYSTEM_PROMPT_CACHE


_SYSTEM_PROMPT_CACHE: Optional[str] = None


# Back-compat alias for existing callers (tests, build_prompt).
SYSTEM_PROMPT = _load_gameplay_system_prompt()


def _retrieve_game_context(game_family: str, max_entries: int = 3) -> str:
    """Retrieve game-specific context from the all-games membot cartridge.

    Uses nomic-embed-text to embed a query, then cosine similarity against
    the cartridge's pre-computed embeddings. Returns the top entries as text.
    """
    import requests as _req
    cart_path = Path(__file__).parent.parent.parent.parent / "shared-context" / "arc-agi-3" / "phase2" / "all-games.cart.npz"
    if not cart_path.exists():
        # Try other common locations
        for p in [
            Path(os.environ.get("ARC_SAGE_DIR", "")) / ".." / "shared-context" / "arc-agi-3" / "phase2" / "all-games.cart.npz",
            Path.home() / "ai-workspace" / "shared-context" / "arc-agi-3" / "phase2" / "all-games.cart.npz",
        ]:
            if p.exists():
                cart_path = p; break
    if not cart_path.exists():
        return ""

    try:
        cart = np.load(str(cart_path), allow_pickle=True)
        embeddings = cart['embeddings']
        snippets = cart['snippets']

        # Embed query
        resp = _req.post("http://localhost:11434/api/embeddings", json={
            "model": "nomic-embed-text",
            "prompt": f"{game_family} game mechanics strategy how to play",
        }, timeout=10)
        q_emb = np.array(resp.json()["embedding"], dtype=np.float32)

        # Cosine similarity
        norms = np.linalg.norm(embeddings, axis=1)
        q_norm = np.linalg.norm(q_emb)
        sims = (embeddings @ q_emb) / (norms * q_norm + 1e-8)

        top_idx = np.argsort(sims)[::-1][:max_entries]
        context_parts = []
        for i in top_idx:
            if sims[i] > 0.4:  # Only include relevant hits
                text = str(snippets[i])
                # Truncate each entry
                if len(text) > 400:
                    text = text[:400] + "..."
                context_parts.append(text)
        return "\n\n".join(context_parts)
    except Exception:
        return ""


# Cache retrieved context per game to avoid repeated embedding calls
_game_context_cache: Dict[str, str] = {}
# Cache world-model markdown summary per game (session-stable)
_world_model_cache: Dict[str, str] = {}
# Cache mechanics-encoder neighbors per game (loaded once per session from
# the adapter JSON at SAGE_MECHANICS_ADAPTER env var)
_mechanics_neighbors_cache: Optional[Dict[str, List[Tuple[str, float]]]] = None
# Cache per-level annotations: {game_family: {level_int: hint_string}}
_level_annotations_cache: Dict[str, Dict[int, str]] = {}


# Cache per-level click bboxes: {game: {level: {x_min, x_max, y_min, y_max, stride_x, stride_y}}}
_level_bbox_cache: Dict[str, Dict[int, Dict[str, int]]] = {}
# Rotation counter for NN's default click — advances through grid-aligned
# points in the bbox so we don't repeat the same coord (self-inverse in ft09).
# Key: (game_family, level). Value: counter integer.
_nn_click_rotation: Dict[Tuple[str, int], int] = {}


def _load_level_bboxes(game_family: str) -> Dict[int, Dict[str, int]]:
    """Load per-level click-region bbox + stride. Separate from
    _load_level_annotations which returns prose hints — this returns
    structured bbox + stride for coord rotation.
    """
    if game_family in _level_bbox_cache:
        return _level_bbox_cache[game_family]
    _level_bbox_cache[game_family] = {}
    for root in [
        Path(os.environ.get("SHARED_CONTEXT_DIR", "")),
        Path("/mnt/c/exe/projects/ai-agents/shared-context"),
        Path.home() / "ai-workspace" / "shared-context",
        Path.home() / "repos" / "shared-context",
    ]:
        path = root / "arc-agi-3" / "world-models" / f"{game_family}-levels.json"
        if path.exists():
            try:
                d = json.loads(path.read_text())
                levels = d.get("levels") or {}
                out: Dict[int, Dict[str, int]] = {}
                for lvl_str, entry in levels.items():
                    try:
                        lvl = int(lvl_str)
                    except ValueError:
                        continue
                    bbox = entry.get("click_region_bbox")
                    if bbox:
                        # Include stride info for rotation-over-grid
                        merged = dict(bbox)
                        if entry.get("coord_stride_x"):
                            merged["stride_x"] = int(entry["coord_stride_x"])
                        if entry.get("coord_stride_y"):
                            merged["stride_y"] = int(entry["coord_stride_y"])
                        out[lvl] = merged
                _level_bbox_cache[game_family] = out
                break
            except Exception:
                continue
    return _level_bbox_cache[game_family]


def _nn_click_coords(game_family: str, level: Optional[int]) -> Optional[Dict[str, int]]:
    """Return click coords for NN-driven CLICK actions.

    Strategy: if a level-hint bbox + stride is available, enumerate all
    grid-aligned points inside the bbox and rotate through them ONCE.
    Returns None once every grid point has been tried — signals to the
    harness to force-invoke so Claude can decide which to re-click
    (with awareness that the first cycle was toggle-heavy).

    Falls back to frame center (32, 32) when no level-hint available.
    Never returns None in the fallback path — center-click is always
    available, even if not useful.
    """
    lvl = level if level is not None else 0
    bboxes = _load_level_bboxes(game_family)
    bbox = bboxes.get(lvl)
    if not bbox:
        return {"x": 32, "y": 32}

    x_min, x_max = int(bbox["x_min"]), int(bbox["x_max"])
    y_min, y_max = int(bbox["y_min"]), int(bbox["y_max"])
    sx = int(bbox.get("stride_x") or max(1, (x_max - x_min)))
    sy = int(bbox.get("stride_y") or max(1, (y_max - y_min)))

    xs = list(range(x_min, x_max + 1, sx)) or [x_min]
    ys = list(range(y_min, y_max + 1, sy)) or [y_min]
    grid: List[Tuple[int, int]] = [(x, y) for y in ys for x in xs]

    key = (game_family, lvl)
    idx = _nn_click_rotation.get(key, 0)
    _nn_click_rotation[key] = idx + 1

    # One cycle only. Beyond that, rotation without strategy toggles
    # earlier clicks off (self-inverse games like ft09). Return None
    # to signal "exhausted grid, force invoke."
    if idx >= len(grid):
        return None

    x, y = grid[idx]
    return {"x": int(x), "y": int(y)}


def _load_level_annotations(game_family: str) -> Dict[int, str]:
    """Load per-level hints from world-models/{game}-levels.json.

    Only the `hint` field is extracted — the raw winning-action coords
    stay out of the prompt. The hint carries bbox + stride + action
    distribution + step count: information a player would learn from
    observation, not the solution itself.
    """
    if game_family in _level_annotations_cache:
        return _level_annotations_cache[game_family]
    _level_annotations_cache[game_family] = {}

    for root in [
        Path(os.environ.get("SHARED_CONTEXT_DIR", "")),
        Path("/mnt/c/exe/projects/ai-agents/shared-context"),
        Path.home() / "ai-workspace" / "shared-context",
        Path.home() / "repos" / "shared-context",
    ]:
        path = root / "arc-agi-3" / "world-models" / f"{game_family}-levels.json"
        if path.exists():
            try:
                d = json.loads(path.read_text())
                levels = d.get("levels") or {}
                out: Dict[int, str] = {}
                for lvl_str, entry in levels.items():
                    try:
                        lvl = int(lvl_str)
                    except ValueError:
                        continue
                    hint = entry.get("hint") or ""
                    if hint:
                        out[lvl] = hint
                _level_annotations_cache[game_family] = out
                break
            except Exception:
                continue
    return _level_annotations_cache[game_family]


def _load_mechanics_neighbors() -> Dict[str, List[Tuple[str, float]]]:
    """Load per-game nearest-neighbor map from the mechanics encoder adapter.
    Returns {} if no adapter available — feature degrades gracefully.
    """
    global _mechanics_neighbors_cache
    if _mechanics_neighbors_cache is not None:
        return _mechanics_neighbors_cache
    _mechanics_neighbors_cache = {}

    path_env = os.environ.get("SAGE_MECHANICS_ADAPTER", "")
    candidates: List[Path] = []
    if path_env:
        candidates.append(Path(path_env))
    # Default scan — find any cbp-mechanics-*.json in _adapters/
    for root in [
        Path(os.environ.get("SAGE_ROUTER_DATA_DIR", "")),
        Path("/mnt/c/exe/projects/ai-agents/private-context/training-data/router"),
        Path.home() / "ai-workspace" / "private-context" / "training-data" / "router",
    ]:
        ad = root / "_adapters"
        if ad.is_dir():
            candidates.extend(sorted(ad.glob("*mechanics*.json"), reverse=True))

    for path in candidates:
        if not path.exists():
            continue
        try:
            d = json.loads(path.read_text())
            nn = d.get("nearest_neighbors") or {}
            if nn:
                _mechanics_neighbors_cache = {
                    g: [(str(nbr), float(sim)) for nbr, sim in nns]
                    for g, nns in nn.items()
                }
                break
        except Exception:
            continue
    return _mechanics_neighbors_cache


def _load_world_model_summary(game_family: str, max_chars: int = 1500) -> str:
    """Load hand-authored world model for this game and extract the sections
    that inform live play: Objects, Rules, Win Condition, Strategy.

    These are the symbolic "source of truth" docs assembled over the 2-week
    understanding phase. Skips debugging/diagnostic sections (Known Failure
    Modes, historical notes) that aren't useful for deliberation.

    Searches multiple workspace roots for the `world-models/{game}.md` file.
    Returns empty string if not found — graceful degradation.
    """
    for root in [
        Path(os.environ.get("SHARED_CONTEXT_DIR", "")),
        Path("/mnt/c/exe/projects/ai-agents/shared-context"),
        Path("/mnt/c/projects/ai-agents/shared-context"),
        Path.home() / "ai-agents" / "shared-context",
        Path.home() / "ai-workspace" / "shared-context",
        Path.home() / "repos" / "shared-context",
    ]:
        wm_path = root / "arc-agi-3" / "world-models" / f"{game_family}.md"
        if wm_path.exists():
            break
    else:
        return ""

    try:
        text = wm_path.read_text()
    except Exception:
        return ""

    # Keep only the play-relevant sections. Order matters — Objects first so
    # the LLM knows the visual vocabulary, then Rules, then Win, then Strategy.
    wanted = ["## Objects", "## Rules", "## Win Condition", "## Strategy"]
    lines = text.splitlines()
    sections: Dict[str, List[str]] = {s: [] for s in wanted}
    current: Optional[str] = None
    for line in lines:
        if line.startswith("## "):
            current = line if line in wanted else None
        elif current is not None:
            sections[current].append(line)

    out_parts: List[str] = []
    for s in wanted:
        body = "\n".join(sections[s]).strip()
        if body:
            out_parts.append(f"{s}\n{body}")
    combined = "\n\n".join(out_parts)
    # Truncate at a section boundary if possible
    if len(combined) > max_chars:
        combined = combined[:max_chars] + "\n[...truncated]"
    return combined


def _detect_trajectory_patterns(window: List[Dict[str, Any]]) -> List[str]:
    """Scan a trajectory window and emit human-readable pattern flags.

    Helps the LLM see patterns without inferring them from raw numbers:
    stuck (low frame change repeatedly), level advance, frame revert,
    oscillation, and repeated-identical-action warnings.
    """
    flags: List[str] = []
    if not window:
        return flags

    # Stuck: 3+ consecutive low-delta steps at the end of the window
    low_delta_tail = 0
    for t in reversed(window):
        if t.get("frame_delta_pct", 0.0) < 2.0:
            low_delta_tail += 1
        else:
            break
    if low_delta_tail >= 3:
        flags.append(
            f"⚠️ STUCK: last {low_delta_tail} actions produced <2% frame change. "
            "Pick something categorically different — if CLICK, try a movement; "
            "if movement, try CLICK or the opposite direction."
        )

    # Level advance
    for t in window:
        if t.get("new_level") != t.get("level"):
            flags.append(
                f"✓ Level advanced at step {t.get('step')}. Mechanics may shift — "
                "re-read the world model for level-specific notes."
            )
            break

    # Frame revert: any step with ≥30% frame change after a stable sequence
    # often signals death, reset, or undo.
    for t in window[-5:]:
        if t.get("frame_delta_pct", 0.0) >= 30.0:
            flags.append(
                f"⚠️ LARGE FRAME CHANGE at step {t.get('step')} "
                f"({t.get('frame_delta_pct', 0):.0f}%) — possible reset, death, or undo. "
                "Verify your model of current state against the frame."
            )
            break

    # Repeated identical action with no effect
    if len(window) >= 3:
        last = window[-1]
        last_act = last.get("action")
        last_coords = last.get("coords")
        same_action_count = 0
        same_action_zero_delta = 0
        for t in reversed(window):
            if t.get("action") == last_act and t.get("coords") == last_coords:
                same_action_count += 1
                if t.get("frame_delta_pct", 0.0) < 2.0:
                    same_action_zero_delta += 1
            else:
                break
        if same_action_count >= 3 and same_action_zero_delta >= 3:
            act_name = ACTION_NAMES[last_act] if isinstance(last_act, int) and 0 <= last_act < len(ACTION_NAMES) else "?"
            coord_str = f"({last_coords['x']},{last_coords['y']})" if last_coords else ""
            flags.append(
                f"⚠️ PERSEVERATION: same action {act_name}{coord_str} repeated "
                f"{same_action_count}× with no effect. DO NOT emit it again. "
                "3 failures of the same approach = stop."
            )

    # Oscillation: alternating opposites in recent window
    OPPOSITES = {1: 2, 2: 1, 3: 4, 4: 3}  # UP/DOWN, LEFT/RIGHT
    if len(window) >= 4:
        recent_acts = [t.get("action") for t in window[-4:]]
        if (recent_acts[0] == recent_acts[2] and recent_acts[1] == recent_acts[3]
                and OPPOSITES.get(recent_acts[0]) == recent_acts[1]):
            flags.append(
                "⚠️ OSCILLATION: alternating opposite directions — you may be "
                "toggling a state without progress. Try a different action entirely."
            )

    return flags


# ───────────────────────────────────────────────────────────────────
# Three-party conversation composers (Phase 4 B4)
#
# build_session_system_prompt — the system message. Fleet-canonical prompt
# + game-specific session context. Sent once; cached by the model adapter.
#
# compose_cnn_narration — the CNN's user turn at invoke time. Combines
# trajectory + pattern flags + metacog signals (Nomad B1) + episodic recall
# (Thor B2) + habit_match (McNugget, placeholder None for now) + invoke
# reason + NN ranking. This is the "my read" the LLM sees.
# ───────────────────────────────────────────────────────────────────


def summarize_game_progress(
    trajectory: List[Dict[str, Any]],
    up_to_step: Optional[int] = None,
) -> str:
    """Deterministic game-progress summary from trajectory.

    Used by B5 memory trimming: when conversation history exceeds
    MAX_CONVERSATION_TURNS, the older turns get dropped and replaced by
    this summary as a preamble to the next user turn.

    Per Sprout: this summary uses ONLY trajectory data (actions, coords,
    deltas, level advances). It never quotes the LLM back to itself —
    that would re-seed crystallization.
    """
    if not trajectory:
        return "Prior context: (none — this is early in the game)."

    scope = trajectory if up_to_step is None else [t for t in trajectory if t["step"] <= up_to_step]
    if not scope:
        return "Prior context: (no earlier steps to summarize)."

    parts: List[str] = ["[Prior context — summary of earlier game progress]"]

    # Step count
    first_step = scope[0]["step"]
    last_step = scope[-1]["step"]
    parts.append(f"Steps {first_step}-{last_step} summarized below ({len(scope)} actions).")

    # Level progression
    level_changes: List[Tuple[int, int, int]] = []
    for t in scope:
        lvl = t.get("level")
        new_lvl = t.get("new_level", lvl)
        if lvl != new_lvl:
            level_changes.append((t["step"], lvl, new_lvl))
    if level_changes:
        changes_str = "; ".join(f"L{b}→L{a} at step {s}" for s, b, a in level_changes)
        parts.append(f"Level advances: {changes_str}.")
    else:
        parts.append("No level advance during this period.")

    # Action+coord bucket outcomes
    # Group by (action_name, coord_str) → (count, advance_count, avg_delta)
    bucket: Dict[str, Dict[str, Any]] = {}
    for t in scope:
        a = t.get("action", -1)
        name = ACTION_NAMES[a] if 0 <= a < len(ACTION_NAMES) else str(a)
        coords = t.get("coords")
        coord_str = f"({coords['x']},{coords['y']})" if coords else ""
        key = f"{name}{coord_str}"
        if key not in bucket:
            bucket[key] = {"count": 0, "advanced": 0, "total_delta": 0.0}
        bucket[key]["count"] += 1
        bucket[key]["total_delta"] += t.get("frame_delta_pct", 0.0)
        if t.get("new_level", t.get("level")) != t.get("level"):
            bucket[key]["advanced"] += 1

    # Report the most-used buckets + their outcomes
    sorted_buckets = sorted(bucket.items(), key=lambda kv: -kv[1]["count"])
    if sorted_buckets:
        top_lines = []
        for key, stats in sorted_buckets[:6]:
            count = stats["count"]
            avg_delta = stats["total_delta"] / count
            outcome = ""
            if stats["advanced"] > 0:
                outcome = f" [advanced {stats['advanced']}×]"
            elif avg_delta < 2.0:
                outcome = " [no effect]"
            elif avg_delta > 20.0:
                outcome = " [large change]"
            top_lines.append(f"  {key} ×{count} (avg {avg_delta:.0f}% change{outcome})")
        parts.append("Actions tried (most-used first):\n" + "\n".join(top_lines))

    return "\n".join(parts)


def trim_conversation_history(
    history: List[Dict[str, str]],
    trajectory: List[Dict[str, Any]],
    max_turns: int = MAX_CONVERSATION_TURNS,
    keep_verbatim: int = KEEP_VERBATIM_TURNS,
) -> Tuple[List[Dict[str, str]], Optional[str]]:
    """Return (trimmed_history, summary_preamble_or_None).

    If history is under max_turns, returns (history, None) — no trim needed.

    Otherwise returns (last-keep_verbatim turns, summary-preamble-text).
    The preamble should be prepended to the NEXT user turn so conversation
    alternation stays clean (no synthetic system messages injected mid-chat).
    """
    if len(history) <= max_turns:
        return history, None

    # Figure out the step range of turns being dropped.
    # Heuristic: each user turn narrates up to some step; trajectory is the
    # source of truth for what happened. We summarize up to the step
    # referenced by the LAST dropped user turn (approximate).
    dropped_count = len(history) - keep_verbatim
    # Roughly half of dropped are user turns; that's how many invocations got dropped
    # Dropped invocations cover steps up to some boundary. We'll cut trajectory
    # at: the step number we infer from the first kept user turn's content.
    first_kept = history[-keep_verbatim:]
    # Take the earliest retained user turn; its step number bounds the summary
    retained_user_steps: List[int] = []
    for turn in first_kept:
        if turn.get("role") == "user":
            # Extract "Step N" from the content's header line
            content = turn.get("content", "")
            import re as _re
            m = _re.search(r"Step\s+(\d+)", content)
            if m:
                retained_user_steps.append(int(m.group(1)))
    summary_cutoff = (min(retained_user_steps) - 1) if retained_user_steps else None

    summary = summarize_game_progress(trajectory, up_to_step=summary_cutoff)
    return first_kept, summary


# ───────────────────────────────────────────────────────────────────
# MRH-backed composer helpers (Phase 5 C)
#
# These populate an MRHContext from dispatcher state and render. The
# legacy functions below (build_session_system_prompt, compose_cnn_narration)
# are retained as thin wrappers for back-compat; they use the MRH path
# internally when available.
# ───────────────────────────────────────────────────────────────────


def _build_gameplay_identity_block(mode: str = "solo_gladiator") -> Any:
    """Build an IdentityBlock for gameplay (solo gladiator by default)."""
    if not _MRH_AVAILABLE:
        return None
    return IdentityBlock(mode=mode)


def _build_gameplay_effectors_block(level_annotation: Optional[str] = None) -> Any:
    """Build an EffectorsBlock for ARC-AGI-3 gameplay."""
    if not _MRH_AVAILABLE:
        return None
    return EffectorsBlock(
        kind_profile="game_actions",
        level_annotation=level_annotation,
    )


def _build_gameplay_mechanics_block(
    game_family: str, profile: Optional[str] = None,
) -> Any:
    """Build a MechanicsBlock with this game's world model + cluster.

    Handles the existing caches (world model + cartridge + mechanics
    neighbors) so the MRH path and the legacy path both use the same
    underlying data.
    """
    if not _MRH_AVAILABLE:
        return None
    # World model
    if game_family not in _world_model_cache:
        _world_model_cache[game_family] = _load_world_model_summary(game_family)
    world_model = _world_model_cache[game_family] or ""

    # Mechanics cluster (top neighbors)
    cluster_str = ""
    neighbors_map = _load_mechanics_neighbors()
    if game_family in neighbors_map:
        neighbors = neighbors_map[game_family][:3]
        if neighbors:
            cluster_str = ", ".join(f"{n} ({s:.2f})" for n, s in neighbors)

    return MechanicsBlock(
        world_model_text=world_model,
        mechanics_cluster=cluster_str,
        profile=profile,
        game_family=game_family,
    )


def _metacog_signals_to_summaries(signals: List[Dict[str, Any]]) -> List[Any]:
    """Convert raw metacog signal dicts (from Metacog.active_signals())
    into MetacogSignalSummary dataclasses for MetabolicBlock.

    Accepts either already-dict form (from signal.to_dict()) or the
    plain shape with name/severity/evidence/suggestion.
    """
    if not _MRH_AVAILABLE:
        return []
    out = []
    for s in signals or []:
        if not isinstance(s, dict):
            continue
        out.append(MetacogSignalSummary(
            signal=s.get("signal", s.get("name", "?")),
            severity=float(s.get("severity", 0.0)),
            evidence=s.get("evidence") or {},
            suggestion=s.get("suggestion", ""),
        ))
    return out


def build_gameplay_mrh_context(
    *,
    game: str, level: int, step_index: int,
    invoke_reasons: List[str],
    action_ranking: List[Tuple[int, float]],
    play_action_idx: int,
    play_confidence: float,
    trajectory: Optional[List[Dict[str, Any]]] = None,
    since_last_invoke: Optional[List[Dict[str, Any]]] = None,
    metacog_signals: Optional[List[Dict[str, Any]]] = None,
    episodic_matches_text: Optional[str] = None,
    habit_match: Optional[Dict[str, Any]] = None,
    level_hint: Optional[str] = None,
    level_changed: bool = False,
    stuck_duration: int = 0,
    actions_since_last_invoke: int = 0,
    atp_balance: Optional[float] = None,
    system_budget_tokens: int = 8000,
    user_budget_tokens: int = 4000,
    sensor_description: str = "",
    image_attachments: Optional[List[bytes]] = None,
) -> Any:
    """Build an MRHContext populated from dispatcher state.

    This is Phase 5 C's primary composer helper. The dispatcher calls it,
    then uses `ctx.compose()` to render the (system, user) pair, plus
    `collect_image_attachments(ctx)` to pull images for the LLM client.

    Returns an MRHContext, or None if the MRH package isn't available
    (fallback case — caller should use legacy composers).
    """
    if not _MRH_AVAILABLE:
        return None

    game_family = game.split("-")[0] if "-" in game else game

    # Mechanics profile swap — stuck-escape if stuck signal is active
    mech_profile = "stuck_escape" if stuck_duration >= 3 else None

    # Trajectory entries — MRH's format
    traj_entries: List[MRHTrajectoryEntry] = []
    if trajectory:
        for t in trajectory[-10:]:
            traj_entries.append(MRHTrajectoryEntry(
                step=int(t.get("step", 0)),
                action_name=(
                    ACTION_NAMES[t["action"]]
                    if isinstance(t.get("action"), int) and 0 <= t["action"] < len(ACTION_NAMES)
                    else str(t.get("action", "?"))
                ),
                coords=t.get("coords"),
                frame_delta_pct=float(t.get("frame_delta_pct", 0.0)),
                level_before=int(t.get("level", 0)),
                level_after=int(t.get("new_level", t.get("level", 0))),
            ))

    # Trajectory pattern flags (reusing existing detector)
    flags = _detect_trajectory_patterns(trajectory[-10:] if trajectory else [])

    # Episodic matches — wrap pre-formatted text
    episodic = []
    if episodic_matches_text:
        episodic.append(MRHEpisodicMatch(formatted_text=episodic_matches_text, similarity=0.0))

    # Conversation summary — level-transition banner goes here as a note
    conv_summary = ""
    if level_changed:
        conv_summary = f"[Level transition] → L{level}. Mechanics may shift; re-read the world model."

    # Identity addendum — include NN ranking/top pick context so the LLM
    # sees it alongside its role lens
    top5 = action_ranking[:5]
    top_str = ", ".join(f"{ACTION_NAMES[a]}({p:.2f})" for a, p in top5)
    top_name = ACTION_NAMES[play_action_idx] if 0 <= play_action_idx < len(ACTION_NAMES) else str(play_action_idx)
    # NN ranking lives in the user turn per convention — put on TaskBlock
    nn_ranking_text = f"CNN action ranking (top 5): {top_str}. Top pick: {top_name} (confidence {play_confidence:.2f})."

    # Swap recommendations — MetabolicBlock raises flags the composer collects
    swaps: List[str] = []
    if stuck_duration >= 5:
        swaps.append("mechanics:stuck_escape")

    # Image attachments (from dispatcher)
    attachments: List[Any] = []
    if image_attachments:
        for i, png in enumerate(image_attachments):
            attachments.append(ImageAttachment(
                png_bytes=png,
                label=("frame_pair" if i == 0 else f"image_{i}"),
            ))

    ctx = MRHContext(
        identity=_build_gameplay_identity_block(mode="solo_gladiator"),
        sensors=SensorsBlock(
            description=sensor_description or "Two game frames side by side: LEFT=previous, RIGHT=current.",
            image_attachments=attachments,
        ),
        # EffectorsBlock holds the STABLE action surface (kept system-side
        # per MRH split). Per-level hints go in TaskBlock (user-side)
        # because they change per-level — keeping system prompt stable
        # across level transitions improves conversation-cache stability.
        effectors=_build_gameplay_effectors_block(level_annotation=None),
        mechanics=_build_gameplay_mechanics_block(game_family, profile=mech_profile),
        experiential=ExperientialCacheBlock(
            recent_trajectory=traj_entries,
            pattern_flags=flags,
            episodic_matches=episodic,
            conversation_summary=conv_summary,
        ),
        metabolic=MetabolicBlock(
            metacog_signals=_metacog_signals_to_summaries(metacog_signals or []),
            metabolic_state="active",
            atp_balance=atp_balance,
            atp_trend="falling" if atp_balance is not None and atp_balance < 200 else "stable",
            confidence=play_confidence,
            stuck_duration=stuck_duration,
            actions_since_last_invoke=actions_since_last_invoke,
            swap_recommendations=swaps,
        ),
        task=TaskBlock(
            game_family=game_family,
            level=level,
            step_index=step_index,
            invoke_reasons=invoke_reasons,
            goal=f"Pick the best next action. {nn_ranking_text}",
            level_hint=level_hint or "",
        ),
        system_budget_tokens=system_budget_tokens,
        user_budget_tokens=user_budget_tokens,
    )
    return ctx


def build_session_system_prompt(game: str) -> str:
    """Extend the canonical fleet gameplay system prompt with game-specific
    session context. This is the system-role message for multi-turn mode.

    Session context includes: mechanics cluster (neighbor games), authoritative
    world model, cartridge snippets. Level hints are NOT here — they're per-turn
    since they change at level transitions.
    """
    base = _load_gameplay_system_prompt()
    game_family = game.split("-")[0] if "-" in game else game

    sections: List[str] = [base, ""]

    # Mechanics cluster
    neighbors_map = _load_mechanics_neighbors()
    if game_family in neighbors_map:
        neighbors = neighbors_map[game_family][:3]
        if neighbors:
            neigh_str = ", ".join(f"{n} ({s:.2f})" for n, s in neighbors)
            sections.append(
                "## Game-session context\n\n"
                f"=== Mechanics cluster (from learned encoder) ===\n"
                f"This game's dynamics signature is closest to: {neigh_str}\n"
                "Hypothesis: similar action-consequence patterns may apply.\n"
            )

    # World model
    if game_family not in _world_model_cache:
        _world_model_cache[game_family] = _load_world_model_summary(game_family)
    world_model = _world_model_cache[game_family]
    if world_model:
        sections.append(
            f"=== Game mechanics (authoritative) ===\n{world_model}\n"
        )

    # Cartridge snippets
    if game_family not in _game_context_cache:
        _game_context_cache[game_family] = _retrieve_game_context(game_family)
    game_context = _game_context_cache[game_family]
    if game_context:
        sections.append(
            f"=== Relevant reasoning snippets (from solved-games cartridge) ===\n"
            f"{game_context}\n"
        )

    return "\n".join(sections).strip()


def compose_cnn_narration(
    game: str,
    level: int,
    step_index: int,
    play_action_idx: int,
    play_confidence: float,
    action_ranking: List[Tuple[int, float]],
    invoke_reasons: List[str],
    trajectory: List[Dict[str, Any]],
    since_last_invoke: Optional[List[Dict[str, Any]]] = None,
    metacog_signals: Optional[List[Dict[str, Any]]] = None,
    episodic_matches_text: Optional[str] = None,
    habit_match: Optional[Dict[str, Any]] = None,
    level_hint: Optional[str] = None,
    level_changed: bool = False,
    llm_plan_prior: Optional[str] = None,
) -> str:
    """Compose the CNN's user-turn narration at invoke time.

    The CNN speaks in first-person as an instrument reporting observations
    to the LLM. Narration is factual, template-driven — interpretation is
    the LLM's job (Q1 consensus).

    Fields:
      - level_changed: if True, emit a LEVEL TRANSITION banner (Q5 carry+banner)
      - since_last_invoke: list of trajectory entries between previous
        invoke and now — lets the LLM see what the CNN did autonomously
        (Q8 inter-invocation narration)
      - metacog_signals: Nomad B1 shape [{signal, severity, evidence, suggestion}]
      - episodic_matches_text: Thor B2 format_recall_for_prompt output
      - habit_match: McNugget placeholder (None until wired)
      - level_hint: current level's solver-derived hint (re-injected each
        invoke in case level changed)
    """
    parts: List[str] = []

    if level_changed:
        parts.append(
            f"=== LEVEL TRANSITION → L{level} ===\n"
            "Previous strategy worked for the prior level. Re-read the world "
            "model for this level's mechanics before proceeding.\n"
        )

    # Opening header
    parts.append(
        f"Step {step_index}. Game: {game}. Level: {level}. "
        f"Invoke triggers: {', '.join(invoke_reasons) if invoke_reasons else 'manual'}."
    )

    # Inter-invoke narration — what the CNN did since last time you saw it
    if since_last_invoke:
        n = len(since_last_invoke)
        if n <= 3:
            # Short stretch — report verbatim
            lines = []
            for t in since_last_invoke:
                act_name = ACTION_NAMES[t["action"]] if 0 <= t.get("action", -1) < len(ACTION_NAMES) else "?"
                coords = t.get("coords")
                coord_str = f"({coords['x']},{coords['y']})" if coords else ""
                delta = t.get("frame_delta_pct", 0.0)
                lines.append(f"  step {t['step']}: {act_name}{coord_str} → {delta:.0f}% change")
            parts.append(f"Since your last turn I took {n} step(s):\n" + "\n".join(lines))
        else:
            # Long stretch — summary + last 3 verbatim (Q8 consensus)
            action_counts: Dict[str, int] = {}
            level_changes_seen: List[Tuple[int, int, int]] = []
            total_delta = 0.0
            for t in since_last_invoke:
                a = t.get("action", -1)
                if 0 <= a < len(ACTION_NAMES):
                    action_counts[ACTION_NAMES[a]] = action_counts.get(ACTION_NAMES[a], 0) + 1
                total_delta += t.get("frame_delta_pct", 0.0)
                if t.get("new_level", t.get("level")) != t.get("level"):
                    level_changes_seen.append((t["step"], t["level"], t["new_level"]))
            avg_delta = total_delta / n
            action_str = ", ".join(f"{k}×{v}" for k, v in sorted(action_counts.items(), key=lambda x: -x[1]))
            summary = f"Since your last turn I took {n} steps: {action_str} (avg {avg_delta:.0f}% frame change)"
            if level_changes_seen:
                for step, before, after in level_changes_seen:
                    summary += f"; level advanced L{before}→L{after} at step {step}"
            parts.append(summary + ".")

            # Last 3 verbatim for fine-grained detail
            recent3 = since_last_invoke[-3:]
            lines = []
            for t in recent3:
                act_name = ACTION_NAMES[t["action"]] if 0 <= t.get("action", -1) < len(ACTION_NAMES) else "?"
                coords = t.get("coords")
                coord_str = f"({coords['x']},{coords['y']})" if coords else ""
                delta = t.get("frame_delta_pct", 0.0)
                lines.append(f"  step {t['step']}: {act_name}{coord_str} → {delta:.0f}% change")
            parts.append("Most recent steps:\n" + "\n".join(lines))

    # Trajectory pattern flags (CBP's existing detector)
    window = trajectory[-10:] if trajectory else []
    flags = _detect_trajectory_patterns(window)
    if flags:
        parts.append("Trajectory pattern flags:\n" + "\n".join(f"  {f}" for f in flags))

    # Metacog signals (Nomad B1)
    if metacog_signals:
        meta_lines = []
        for sig in metacog_signals:
            name = sig.get("signal", "?")
            sev = sig.get("severity", 0.0)
            suggestion = sig.get("suggestion", "")
            evidence = sig.get("evidence") or {}
            evidence_str = ""
            if isinstance(evidence, dict) and evidence:
                # Compact one-line evidence summary
                kv = [f"{k}={v}" for k, v in list(evidence.items())[:3]]
                evidence_str = f" [{', '.join(kv)}]"
            line = f"  {name} (severity {sev:.1f}){evidence_str}"
            if suggestion:
                line += f" — {suggestion}"
            meta_lines.append(line)
        parts.append("Metacog signals (CNN self-report):\n" + "\n".join(meta_lines))

    # Habit match (McNugget placeholder — emit only when provided)
    if habit_match:
        habit_id = habit_match.get("habit_id", "?")
        conf = habit_match.get("confidence", 0.0)
        outcome = habit_match.get("past_outcome", "unknown")
        parts.append(
            f"Habit match: {habit_id} (confidence {conf:.2f}), "
            f"past outcome: {outcome}"
        )

    # Episodic recall (Thor B2)
    if episodic_matches_text:
        parts.append(f"Episodic recall:\n  {episodic_matches_text}")

    # Level hint (re-injected each invoke — solver-derived, per-level)
    if level_hint:
        parts.append(f"Level {level} hint (observed-from-solved):\n  {level_hint}")

    # Prior LLM plan, if one was emitted previously and still being followed
    if llm_plan_prior:
        parts.append(f"Your prior plan (in progress): {llm_plan_prior}")

    # NN ranking + top pick
    top5 = action_ranking[:5]
    top_str = ", ".join(f"{ACTION_NAMES[a]}({p:.2f})" for a, p in top5)
    top_name = ACTION_NAMES[play_action_idx] if 0 <= play_action_idx < len(ACTION_NAMES) else str(play_action_idx)
    parts.append(
        f"My action ranking (top 5): {top_str}.\n"
        f"My top pick: {top_name} (confidence {play_confidence:.2f})."
    )

    # Response format reminder — kept short since it's in the system prompt too
    parts.append(
        "Respond with ACTION=UP or DOWN or LEFT or RIGHT or SEL or CLICK"
        "[ X=<0-63> Y=<0-63> for CLICK] on the first line, "
        "then one sentence of rationale."
    )

    return "\n\n".join(parts)


def build_prompt(
    game: str, level: int, step_index: int,
    play_action_idx: int, play_confidence: float,
    action_ranking: List[Tuple[int, float]],
    recent_actions: List[int],
    invoke_reasons: List[str],
    recent_trajectory: Optional[List[Dict[str, Any]]] = None,
    frame_state_text: Optional[str] = None,
) -> str:
    """Compose the invoke-time LLM prompt.

    Keeps it tight ��� the LLM is on a budget, don't waste its context.
    Includes game-specific context from the membot cartridge when available.
    """
    top5 = action_ranking[:5]
    top_str = ", ".join(
        f"{ACTION_NAMES[a]}({p:.2f})" for a, p in top5
    )
    recent_names = " → ".join(
        ACTION_NAMES[a] if 0 <= a < len(ACTION_NAMES) else str(a)
        for a in recent_actions[-5:]
    ) or "(none yet)"

    # Trajectory context: recent steps' actions + effect magnitude + pattern flags.
    # Extended to last 10 (from 5) and annotated with patterns the LLM should notice.
    trajectory_block = ""
    if recent_trajectory:
        window = recent_trajectory[-10:]
        lines = []
        for t in window:
            act_name = ACTION_NAMES[t["action"]] if 0 <= t.get("action", -1) < len(ACTION_NAMES) else "?"
            coords = t.get("coords")
            coord_str = f"({coords['x']},{coords['y']})" if coords else ""
            delta = t.get("frame_delta_pct", 0.0)
            level_marker = f" L{t['level']}→L{t['new_level']}" if t.get("new_level") != t.get("level") else ""
            lines.append(
                f"  step {t['step']}: {act_name}{coord_str} → {delta:.0f}% frame change{level_marker}"
            )

        # Pattern detection — flag patterns the LLM should recognize without
        # having to infer them from the raw numbers.
        flags = _detect_trajectory_patterns(window)

        header = "Recent trajectory (last {} actions; have they been moving state?):".format(len(window))
        body = "\n".join(lines)
        flag_block = ""
        if flags:
            flag_block = "\n\nPattern flags:\n" + "\n".join(f"  {f}" for f in flags)
        trajectory_block = f"\n{header}\n{body}{flag_block}\n"

    game_family = game.split("-")[0] if "-" in game else game

    # Tier 1: hand-authored world-model markdown (authoritative mechanics,
    # loaded once per session). Highest-priority context.
    if game_family not in _world_model_cache:
        _world_model_cache[game_family] = _load_world_model_summary(game_family)
    world_model = _world_model_cache[game_family]

    # Tier 2: cartridge retrieval (situational examples, similarity-matched
    # to game name). Augments the world model with live-reasoning snippets.
    if game_family not in _game_context_cache:
        _game_context_cache[game_family] = _retrieve_game_context(game_family)
    game_context = _game_context_cache[game_family]

    # Tier 0: mechanics-encoder cluster — "this game is near X, Y, Z"
    mech_block = ""
    neighbors_map = _load_mechanics_neighbors()
    if game_family in neighbors_map:
        neighbors = neighbors_map[game_family][:3]
        if neighbors:
            neigh_str = ", ".join(f"{n} ({s:.2f})" for n, s in neighbors)
            mech_block = (
                f"\n=== Mechanics cluster (from learned encoder) ===\n"
                f"This game's dynamics signature is closest to: {neigh_str}\n"
                "Hypothesis: similar action-consequence patterns may apply.\n"
            )

    world_model_block = ""
    if world_model:
        world_model_block = f"""
=== Game mechanics (authoritative) ===
{world_model}

"""

    # Per-level annotation — derived from solver traces, hint-only (no
    # winning sequence revealed). Tells LLM bbox + stride + step count for
    # the current level.
    level_block = ""
    level_hints = _load_level_annotations(game_family)
    lvl_hint = level_hints.get(level or 0)
    if lvl_hint:
        level_block = f"""
=== Level {level} hint (observed-from-solved) ===
{lvl_hint}

"""
    context_block = ""
    if game_context:
        context_block = f"""
=== Relevant reasoning snippets (from solved-games cartridge) ===
{game_context}

"""

    return f"""{SYSTEM_PROMPT}

The image contains TWO frames side by side: LEFT is the PREVIOUS frame, \
RIGHT is the CURRENT frame (separated by a black gap). Compare them to \
understand what just changed.
{mech_block}{world_model_block}{level_block}{context_block}{f"=== Computed frame state ==={chr(10)}{frame_state_text}{chr(10)}{chr(10)}" if frame_state_text else ""}=== Current situation ===
Game: {game}  Level: {level}  Step: {step_index}
Invoke triggers: {', '.join(invoke_reasons) if invoke_reasons else 'manual'}
Recent actions: {recent_names}{trajectory_block}

NN's best-action ranking (top 5): {top_str}
NN's top pick: {ACTION_NAMES[play_action_idx]} (confidence {play_confidence:.2f})

Respond with exactly this format on the first line:
ACTION=UP or DOWN or LEFT or RIGHT or SEL or CLICK[ X=<0-63> Y=<0-63>]
<one-sentence rationale grounded in the game mechanics above>

If you choose CLICK, you MUST provide X and Y pixel coordinates on the 64×64 grid.
"""


# Natural-language action-name fallback: "I choose CLICK at (32, 12)",
# "my action is UP", etc. Looked up case-insensitively against ACTION_NAMES.
# Only used if ACTION=<n> format didn't match.
_NAMED_ACTION_RE = re.compile(
    r"\b(?:action[:\s]+is|i\s+(?:choose|pick|select)|let'?s\s+(?:do|go|try)|going\s+with)\s*"
    r"(?:the\s+)?(UP|DOWN|LEFT|RIGHT|SEL(?:ECT)?|CLICK)\b",
    re.IGNORECASE,
)
_NAKED_ACTION_RE = re.compile(
    r"\b(UP|DOWN|LEFT|RIGHT|SELECT|SEL|CLICK)\b", re.IGNORECASE,
)
_NAME_TO_IDX = {n: i for i, n in enumerate(ACTION_NAMES)}
_NAME_TO_IDX["SELECT"] = _NAME_TO_IDX["SEL"]


# ACTION=<n> or ACTION=<name> — required. Coords parsed independently
# (tolerates brackets, extra whitespace, commas, etc. that real LLMs produce).
_ACTION_RE = re.compile(r"ACTION\s*=\s*<?(\w+)>?", re.IGNORECASE)
_X_RE = re.compile(r"X\s*=\s*(-?\d+)", re.IGNORECASE)
_Y_RE = re.compile(r"Y\s*=\s*(-?\d+)", re.IGNORECASE)
# Parenthetical coords: "CLICK at (32, 12)" / "click cell (48, 36)"
_PAREN_COORD_RE = re.compile(r"\(\s*(-?\d+)\s*[,xX]\s*(-?\d+)\s*\)")
_ACTION_NAME_MAP = {
    "a0": 0, "up": 1, "down": 2, "left": 3, "right": 4, "sel": 5, "click": 6,
    "noop": 0, "select": 5,
}


def parse_llm_response(
    text: str, fallback_action: int, fallback_coords: Optional[Dict[str, int]] = None,
) -> Tuple[int, Optional[Dict[str, int]], str]:
    """Extract (action, coords_or_None, rationale) from the LLM's response.
    Falls back to the NN's hint if the response is malformed.
    """
    m = _ACTION_RE.search(text)
    action: int = -1
    if m:
        raw = m.group(1)
        try:
            action = int(raw)
        except ValueError:
            action = _ACTION_NAME_MAP.get(raw.lower(), -1)
    # Fallback 1: explicit "I choose X" or "action is X" natural-language
    if action < 0:
        nm = _NAMED_ACTION_RE.search(text)
        if nm:
            name = nm.group(1).upper()
            action = _NAME_TO_IDX.get(name, -1)
    # Fallback 2: naked action-name mention (first one wins)
    if action < 0:
        nm = _NAKED_ACTION_RE.search(text)
        if nm:
            name = nm.group(1).upper()
            action = _NAME_TO_IDX.get(name, -1)
    if action < 0:
        return fallback_action, fallback_coords, f"parse_failed: {text[:120]}"
    if not (0 <= action < N_ACTIONS):
        return fallback_action, fallback_coords, f"action_out_of_range: {action}"

    coords: Optional[Dict[str, int]] = None
    if action == 6:
        xm = _X_RE.search(text); ym = _Y_RE.search(text)
        if xm and ym:
            try:
                x = max(0, min(FRAME_W - 1, int(xm.group(1))))
                y = max(0, min(FRAME_H - 1, int(ym.group(1))))
                coords = {"x": x, "y": y}
            except Exception:
                coords = fallback_coords
        else:
            # Parenthetical fallback: "(32, 12)" or "(32x12)"
            pm = _PAREN_COORD_RE.search(text)
            if pm:
                try:
                    x = max(0, min(FRAME_W - 1, int(pm.group(1))))
                    y = max(0, min(FRAME_H - 1, int(pm.group(2))))
                    coords = {"x": x, "y": y}
                except Exception:
                    coords = fallback_coords
            else:
                coords = fallback_coords

    # Rationale — everything after the action line (first 200 chars)
    lines = text.strip().splitlines()
    rationale = ""
    for line in lines:
        if "ACTION" in line.upper():
            continue
        rationale = line.strip()
        if rationale:
            break
    return action, coords, rationale[:200]


# ───────────────────────────────────────────────────────────────────
# Dispatch decision — same structure as choose_dispatch in world_model.py,
# adapted for FrameRouter
# ───────────────────────────────────────────────────────────────────

@dataclass
class DispatchDecision:
    decision: str                         # "play" | "invoke"
    invoke_reasons: List[str]
    invoke_prob: float
    play_action: int
    play_confidence: float
    play_margin: float
    action_ranking: List[Tuple[int, float]]


def choose_dispatch(
    model: FrameRouter, cfg: FrameRouterConfig,
    prev_frame_oh: np.ndarray, curr_frame_oh: np.ndarray,
    scalar: np.ndarray, device: str = "cpu",
    invoke_threshold: float = INVOKE_THRESHOLD,
    play_confidence_threshold: float = PLAY_CONFIDENCE_THRESHOLD,
    play_margin_threshold: float = PLAY_MARGIN_THRESHOLD,
) -> DispatchDecision:
    model.eval()
    with torch.no_grad():
        prev = torch.from_numpy(prev_frame_oh).unsqueeze(0).to(device)
        curr = torch.from_numpy(curr_frame_oh).unsqueeze(0).to(device)
        sc = torch.from_numpy(scalar).unsqueeze(0).to(device)
        out = model(prev, curr, sc)
        action_probs = F.softmax(out["action_logits"], dim=-1)[0]
        invoke_prob = float(torch.sigmoid(out["invoke_logit"]).item())

    sorted_idx = torch.argsort(action_probs, descending=True)
    top_action = int(sorted_idx[0].item())
    top_conf = float(action_probs[top_action].item())
    second_conf = float(action_probs[int(sorted_idx[1].item())].item())
    margin = top_conf - second_conf
    ranking = [
        (int(i.item()), float(action_probs[i].item())) for i in sorted_idx
    ]

    reasons: List[str] = []
    if invoke_prob > invoke_threshold:
        reasons.append("novelty")
    if top_conf < play_confidence_threshold:
        reasons.append("low_confidence")
    if margin < play_margin_threshold:
        reasons.append("tight_margin")

    return DispatchDecision(
        decision="invoke" if reasons else "play",
        invoke_reasons=reasons, invoke_prob=invoke_prob,
        play_action=top_action, play_confidence=top_conf, play_margin=margin,
        action_ranking=ranking,
    )


# ───────────────────────────────────────────────────────────────────
# Harness
# ───────────────────────────────────────────────────────────────────

@dataclass
class LlmDispatchResult:
    game: str
    game_id: str
    n_steps: int
    max_steps: int
    final_state: Optional[str]
    final_levels: Optional[int]
    outcome: str
    solver_steps: Optional[int] = None
    action_counts: Dict[str, int] = field(default_factory=dict)
    invoke_count: int = 0
    llm_calls: int = 0
    llm_parse_failures: int = 0
    stuck_count: int = 0
    llm_responses: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    grounded_aggregates: Dict[str, Any] = field(default_factory=dict)


def _make_env(game_family: str, game_id: str):
    if str(ARC_AGI_EXPERIMENTS) not in sys.path:
        sys.path.insert(0, str(ARC_AGI_EXPERIMENTS))
    from arc_agi import Arcade
    arc = Arcade(operation_mode="offline")
    env = arc.make(game_id) or arc.make(game_family)
    if env is None:
        raise RuntimeError(f"arc.make None for {game_id}/{game_family}")
    fd = env.reset()
    return env, fd


def run_llm_dispatch(
    model: FrameRouter, cfg: FrameRouterConfig,
    game_family: str, game_id: str,
    writer: RouterDatasetWriter, machine: str,
    llm_client: LLMClient,
    max_steps: int, trace_steps: Optional[int] = None,
    device: str = "cpu", log_every_llm: bool = True,
    multiturn: Optional[bool] = None,
) -> LlmDispatchResult:
    """Run LLM dispatch against a game.

    multiturn: if True, uses three-party conversation (system prompt once,
               CNN narration per invoke, history carried across invocations).
               If False, uses legacy stateless build_prompt() one-shot mode.
               Default from SAGE_DISPATCH_MULTITURN env var (1=on, 0=off).
    """
    if multiturn is None:
        multiturn = _MULTITURN_DEFAULT
    errors: List[str] = []
    try:
        env, fd = _make_env(game_family, game_id)
    except Exception as e:
        return LlmDispatchResult(
            game=game_family, game_id=game_id, n_steps=0,
            max_steps=max_steps, final_state=None, final_levels=None,
            outcome="ENV_INIT_FAILED", errors=[f"env init: {e!r}"],
        )

    try:
        from arcengine import GameAction
        int_to_action = {ga.value: ga for ga in GameAction}
    except Exception:
        int_to_action = {}

    model = model.to(device)
    game_slugs = cfg.game_slugs
    game_idx = game_slugs.index(game_family) if game_family in game_slugs else 0

    action_counts: Dict[str, int] = {}
    invoke_count = 0
    llm_calls = 0
    llm_parse_failures = 0
    stuck_count = 0
    llm_responses: List[Dict[str, Any]] = []
    trajectory: List[Dict[str, Any]] = []   # last-K action/delta log for prompt
    grounded_per_invoke: List[Dict[str, Any]] = []   # B6 per-invoke metrics

    # Three-party conversation state (B4)
    conversation_history: List[Dict[str, str]] = []
    session_system_prompt: Optional[str] = None
    metacog: Any = None
    episodic_index: Any = None
    last_invoke_step_idx: int = 0
    last_invoke_level: int = 0
    # Metacog runs in ALL dispatch modes — it observes, doesn't control
    if _METACOG_AVAILABLE:
        try:
            metacog = Metacog(config=MetacogConfig())
        except Exception:
            metacog = None

    if multiturn:
        session_system_prompt = build_session_system_prompt(game_family)
        episodic_index = _load_episodic_index()

    # Zero-frame convention at game start
    zero_frame_oh = np.zeros((N_COLORS, FRAME_H, FRAME_W), dtype=np.float32)
    prev_frame_oh = zero_frame_oh
    prev_frame_raw = None
    last_action: int = 0
    recent: deque = deque([0] * RECENT_ACTIONS_K, maxlen=RECENT_ACTIONS_K)

    # Stuck tracking
    recent_action_win: deque = deque(maxlen=STUCK_WINDOW)
    recent_frame_win: deque = deque(maxlen=STUCK_WINDOW)
    steps_since_progress = 0
    last_levels = 0

    step_idx = 0
    outcome_terminal = {"WIN", "GAME_OVER"}

    _level_just_changed = False

    while step_idx < max_steps:
        curr_frame_raw = getattr(fd, "frame", None)
        curr_frame_oh = onehot_frame(curr_frame_raw) if curr_frame_raw is not None else zero_frame_oh
        curr_state = getattr(getattr(fd, "state", None), "name", None) or "RUNNING"
        curr_levels = getattr(fd, "levels_completed", 0) or 0

        # After a level transition, let the game settle. Some games show
        # transition animations or reset frames that don't represent
        # actionable state. Wait for the frame to stabilize.
        if _level_just_changed:
            _level_just_changed = False
            _settle_frame = curr_frame_raw
            for _ in range(5):  # up to 5 no-op frames to settle
                try:
                    _noop_fd = env.step(list(int_to_action.values())[0])
                    _noop_frame = getattr(_noop_fd, "frame", None)
                    _noop_state = getattr(getattr(_noop_fd, "state", None), "name", None)
                    if _noop_state in outcome_terminal:
                        fd = _noop_fd; break
                    fd = _noop_fd
                    # If frame stabilized (same as last), we've settled
                    if _noop_frame is not None and _settle_frame is not None:
                        if np.array_equal(np.asarray(_noop_frame), np.asarray(_settle_frame)):
                            break
                    _settle_frame = _noop_frame
                except Exception:
                    break
            # Re-read after settling
            curr_frame_raw = getattr(fd, "frame", None)
            curr_frame_oh = onehot_frame(curr_frame_raw) if curr_frame_raw is not None else zero_frame_oh
            curr_state = getattr(getattr(fd, "state", None), "name", None) or "RUNNING"
            curr_levels = getattr(fd, "levels_completed", 0) or 0

        level = curr_levels
        step_frac = min(1.0, (step_idx + 1) / max(1, trace_steps or 100))
        budget_remaining = max(0.0, 1.0 - step_frac)

        mech_vec = None
        if cfg.use_mech_embedding and hasattr(model, "mech_embedding_table"):
            mech_vec = model.mech_embedding_table[game_idx].detach().cpu().numpy().tolist()
        scalar = build_scalar_vector(
            game_idx=game_idx, n_games=cfg.n_games,
            level=level, n_levels=cfg.n_levels,
            step_frac=step_frac, budget_remaining=budget_remaining,
            last_action=last_action,
            recent_actions=list(recent),
            available_actions=[1] * N_ACTIONS,
            batch_state=[0.0, 0.0, 0.0],
            include_last_action=cfg.include_last_action,
            mech_embedding=mech_vec,
        )
        scalar_arr = np.array(scalar, dtype=np.float32)

        dispatch = choose_dispatch(
            model, cfg, prev_frame_oh, curr_frame_oh, scalar_arr, device=device,
        )

        # Harness-level stuck detection
        stuck_triggered = False
        if len(recent_action_win) == STUCK_WINDOW:
            same_actions = len(set(recent_action_win)) == 1
            frames_same = all(
                np.array_equal(recent_frame_win[0], recent_frame_win[i])
                for i in range(1, len(recent_frame_win))
            )
            if same_actions and frames_same:
                stuck_triggered = True
                stuck_count += 1
        if steps_since_progress >= PROGRESS_STALL_WINDOW:
            stuck_triggered = True
            stuck_count += 1
        if stuck_triggered and dispatch.decision != "invoke":
            dispatch.decision = "invoke"
            dispatch.invoke_reasons.append("stuck")

        # Metacog-driven invoke escalation: selective by signal type.
        # Some signals (perseveration, budget_anxiety) benefit from LLM help.
        # Others (exploration_starvation) are better handled by letting the
        # NN explore randomly — forcing invoke wastes budget on "try opposite"
        # suggestions that don't help with pathfinding.
        _ESCALATION_SIGNALS = {"perseveration", "budget_anxiety", "intention_amnesia"}
        if metacog is not None and dispatch.decision != "invoke":
            try:
                _mc_signals = metacog.active_signals()
                if _mc_signals:
                    _escalatable = [s for s in _mc_signals
                                    if (s.signal if hasattr(s, 'signal') else s.get('signal', '?'))
                                    in _ESCALATION_SIGNALS
                                    and (s.severity if hasattr(s, 'severity') else s.get('severity', 0)) >= 0.7]
                    if _escalatable:
                        dispatch.decision = "invoke"
                        sig_names = [s.signal if hasattr(s, 'signal') else s.get('signal', '?')
                                     for s in _escalatable]
                        dispatch.invoke_reasons.append(f"metacog:{','.join(sig_names)}")
            except Exception:
                pass

        # Resolve action
        llm_info: Optional[Dict[str, Any]] = None
        if dispatch.decision == "invoke":
            invoke_count += 1
            llm_calls += 1
            # Stitch prev+curr into one image (llama3.2-vision accepts 1 image)
            pair_png = render_frame_pair_png(prev_frame_oh, curr_frame_oh)

            if multiturn:
                # Three-party conversation mode (B4)
                # Build since_last_invoke slice (actions the CNN took autonomously
                # between this invoke and the previous one)
                since_last = [t for t in trajectory if t["step"] > last_invoke_step_idx]
                level_changed = level != last_invoke_level and last_invoke_step_idx > 0

                # Metacog signals (Nomad B1) — read currently-active signals
                # observe_tick() is called per-step below; here we just read
                metacog_signals_list: List[Dict[str, Any]] = []
                if metacog is not None:
                    try:
                        active = metacog.active_signals()
                        metacog_signals_list = [sig.to_dict() for sig in active]
                    except Exception:
                        metacog_signals_list = []

                # Episodic recall (Thor B2)
                episodic_text: Optional[str] = None
                if episodic_index is not None and curr_frame_raw is not None:
                    try:
                        cue = GameStateCue(
                            game_family=game_family, level=level,
                            frame=np.asarray(curr_frame_raw),
                            action_context=list(recent)[-5:],
                        )
                        matches = recall_gameplay(episodic_index, cue, k=3, min_similarity=0.25)
                        if matches:
                            episodic_text = format_recall_for_prompt(matches)
                    except Exception:
                        episodic_text = None

                # Level hint — re-inject each invoke since level can change
                level_hints = _load_level_annotations(game_family)
                level_hint = level_hints.get(level or 0)

                # Phase 5 C: use MRH composer when available, fall back to
                # legacy compose_cnn_narration. Env SAGE_USE_MRH=0 forces legacy.
                use_mrh = (
                    _MRH_AVAILABLE
                    and os.environ.get("SAGE_USE_MRH", "1") not in ("0", "false", "False")
                )
                if use_mrh:
                    ctx = build_gameplay_mrh_context(
                        game=game_family, level=level, step_index=step_idx + 1,
                        invoke_reasons=dispatch.invoke_reasons,
                        action_ranking=dispatch.action_ranking,
                        play_action_idx=dispatch.play_action,
                        play_confidence=dispatch.play_confidence,
                        trajectory=trajectory,
                        since_last_invoke=since_last if last_invoke_step_idx > 0 else None,
                        metacog_signals=metacog_signals_list,
                        episodic_matches_text=episodic_text,
                        habit_match=None,
                        level_hint=level_hint,
                        level_changed=level_changed,
                        stuck_duration=steps_since_progress,
                        actions_since_last_invoke=(step_idx + 1 - last_invoke_step_idx) if last_invoke_step_idx > 0 else (step_idx + 1),
                        atp_balance=float(max_steps - step_idx - 1),
                        image_attachments=[pair_png],
                    )
                    mrh_system, narration = ctx.compose()
                    # The canonical fleet gameplay prompt remains the stable
                    # system header; MRH's system half provides the structured
                    # game-specific context underneath.
                    mrh_session_system = session_system_prompt + "\n\n" + mrh_system
                else:
                    narration = compose_cnn_narration(
                        game=game_family, level=level, step_index=step_idx + 1,
                        play_action_idx=dispatch.play_action,
                        play_confidence=dispatch.play_confidence,
                        action_ranking=dispatch.action_ranking,
                        invoke_reasons=dispatch.invoke_reasons,
                        trajectory=trajectory,
                        since_last_invoke=since_last if last_invoke_step_idx > 0 else None,
                        metacog_signals=metacog_signals_list,
                        episodic_matches_text=episodic_text,
                        habit_match=None,  # McNugget placeholder
                        level_hint=level_hint,
                        level_changed=level_changed,
                    )
                    mrh_session_system = session_system_prompt

                # Memory trim (B5): if history exceeds threshold, drop older
                # turns and prepend a trajectory-derived summary to the new
                # user turn. Trajectory-only — Sprout consensus: never quote
                # the LLM back to itself.
                conversation_history, summary_preamble = trim_conversation_history(
                    conversation_history, trajectory,
                )
                if summary_preamble:
                    narration = summary_preamble + "\n\n" + narration

                t0 = time.time()
                response = llm_client.chat(
                    narration,
                    images_png=[pair_png],
                    history=conversation_history,
                    system_prompt=mrh_session_system,
                )
                llm_latency = time.time() - t0

                # Append this turn to history
                conversation_history.append({"role": "user", "content": narration})
                conversation_history.append({"role": "assistant", "content": response})
                last_invoke_step_idx = step_idx + 1
                last_invoke_level = level

                prompt_preview = narration[-300:]
            else:
                # Legacy single-call mode
                # Compute frame state for the LLM
                _fs_text = None
                try:
                    from sage.cognition.thalamic_router.frame_state import extract_state
                    _fs_text = extract_state(
                        curr_frame=curr_frame_raw,
                        prev_frame=prev_frame_raw,
                    )
                except Exception:
                    pass

                # Lookahead: predict what each action does (best-effort)
                _la_text = None
                try:
                    from sage.cognition.thalamic_router.lookahead import lookahead
                    # Directional actions always
                    _la_text, _la_elapsed = lookahead(env, fd, actions=[1, 2, 3, 4, 5])
                    # Click-coord probing when adapter suggests CLICK or
                    # when all directional actions are blocked
                    if dispatch.play_action == 6 or "no change" in (_la_text or "").lower().replace("trivial", "no change"):
                        _click_coords = [(x, y) for y in range(8, 56, 16) for x in range(8, 56, 16)]
                        _click_text, _ = lookahead(env, fd, actions=[], click_coords=_click_coords)
                        _active = [l for l in _click_text.split('\n')
                                   if 'CLICK' in l and 'no change' not in l and 'trivial' not in l and 'error' not in l]
                        if _active:
                            _la_text += "\n\nActive CLICK targets:\n" + "\n".join(_active)
                        else:
                            _la_text += "\n\nNo active CLICK targets found in grid probe."
                except Exception:
                    pass

                # Episodic recall: "have I been in this state before?"
                _ep_text = None
                try:
                    from sage.cognition.episodic.gameplay_recall import (
                        recall_gameplay, format_recall_for_prompt, GameStateCue,
                    )
                    from sage.cognition.episodic.index import EpisodicIndex
                    _ep_db = os.environ.get("SAGE_EPISODIC_DB",
                        os.path.expanduser("~/ai-workspace/private-context/training-data/episodic/gameplay_episodes.db"))
                    if os.path.exists(_ep_db):
                        if not hasattr(run_llm_dispatch, '_episodic_index'):
                            run_llm_dispatch._episodic_index = EpisodicIndex(db_path=_ep_db)
                        _cue = GameStateCue(
                            game_family=game_family,
                            level=level,
                            frame=curr_frame_raw,
                        )
                        _matches = recall_gameplay(run_llm_dispatch._episodic_index, _cue, k=3)
                        _ep_text = format_recall_for_prompt(_matches)
                except Exception:
                    pass

                # Membot: associative memory — "games like this..."
                _mb_text = None
                try:
                    import sys as _sys
                    _lib_path = os.path.join(
                        os.environ.get("SHARED_CONTEXT_DIR",
                            os.path.expanduser("~/ai-workspace/shared-context")),
                        "lib")
                    if _lib_path not in _sys.path:
                        _sys.path.insert(0, _lib_path)
                    from membot_vendored import Cart as _Cart
                    from membot_vendored.arcsage_query import stuck_hints
                    from membot_vendored.arcsage_games import bundle_for
                    _cart_path = os.path.join(
                        os.environ.get("SHARED_CONTEXT_DIR",
                            os.path.expanduser("~/ai-workspace/shared-context")),
                        "arc-agi-3/phase2/all-games-vendored.cart.npz")
                    if os.path.exists(_cart_path):
                        if not hasattr(run_llm_dispatch, '_membot_cart'):
                            run_llm_dispatch._membot_cart = _Cart.open(_cart_path)
                        # Embed current situation
                        import requests as _req
                        _stuck_prefix = "stuck on " if stuck_triggered else ""
                        _query = f"{_stuck_prefix}{game_family} level {level} game strategy"
                        _resp = _req.post("http://localhost:11434/api/embeddings",
                            json={"model": "nomic-embed-text", "prompt": _query}, timeout=5)
                        _q_emb = np.array(_resp.json()["embedding"], dtype=np.float32)
                        # Use stuck_hints for game+bundle-aware retrieval
                        _bundle = bundle_for(game_family)
                        _hits = stuck_hints(
                            run_llm_dispatch._membot_cart, _q_emb,
                            game=game_family,
                            game_bundle=_bundle if stuck_triggered else None,
                            k=3, only_successful=False,
                        )
                        if _hits:
                            _mb_lines = ["Relevant game knowledge (from fleet memory):"]
                            for _h in _hits:
                                _mb_lines.append(f"  {_h['text'][:200]}")
                            _mb_text = "\n".join(_mb_lines)
                except Exception:
                    pass

                # Metacog signals: what does the system know about its own state?
                _mc_text = None
                if metacog is not None:
                    try:
                        signals = metacog.active_signals()
                        if signals:
                            # Terse numerical format — don't give the model prose to parrot
                            _mc_parts = [f"{(s.signal if hasattr(s,'signal') else s.get('signal','?'))}:"
                                         f"{(s.severity if hasattr(s,'severity') else s.get('severity',0)):.1f}"
                                         for s in signals]
                            _mc_text = f"Metacog: {', '.join(_mc_parts)}"
                    except Exception:
                        pass

                # Combine all context signals
                _context_parts = [p for p in [_fs_text, _la_text, _ep_text, _mb_text, _mc_text] if p]
                _fs_text = "\n\n".join(_context_parts) if _context_parts else None
                prompt = build_prompt(
                    game=game_family, level=level, step_index=step_idx + 1,
                    play_action_idx=dispatch.play_action,
                    play_confidence=dispatch.play_confidence,
                    action_ranking=dispatch.action_ranking,
                    recent_actions=list(recent),
                    invoke_reasons=dispatch.invoke_reasons,
                    recent_trajectory=trajectory[-15:] if trajectory else None,
                    frame_state_text=_fs_text,
                )
                t0 = time.time()
                response = llm_client.chat(prompt, images_png=[pair_png])
                llm_latency = time.time() - t0
                prompt_preview = prompt[-300:]

            action, coords, rationale = parse_llm_response(
                response,
                fallback_action=dispatch.play_action,
                fallback_coords={"x": 32, "y": 32} if dispatch.play_action == 6 else None,
            )
            parse_ok = not rationale.startswith("parse_failed")

            # Retry on parse failure: ask for just the action number.
            # Cost: ~1-2 sec. Recovers ~50% of parse failures on small models.
            if not parse_ok:
                retry_prompt = (
                    "Your previous response could not be parsed. "
                    "Reply with ONLY the action on a single line, e.g.:\n"
                    "ACTION=UP\n"
                    "or\n"
                    "ACTION=CLICK X=32 Y=48\n"
                    "Available: UP, DOWN, LEFT, RIGHT, SEL, CLICK"
                )
                try:
                    retry_response = llm_client.chat(retry_prompt)
                    retry_action, retry_coords, retry_rationale = parse_llm_response(
                        retry_response,
                        fallback_action=dispatch.play_action,
                        fallback_coords={"x": 32, "y": 32} if dispatch.play_action == 6 else None,
                    )
                    if not retry_rationale.startswith("parse_failed"):
                        action, coords, rationale = retry_action, retry_coords, f"retry_ok: {retry_rationale}"
                        parse_ok = True
                        response = f"{response}\n[RETRY]: {retry_response}"
                except Exception:
                    pass  # retry failed — keep original parse failure

            if not parse_ok:
                llm_parse_failures += 1

            llm_info = {
                "prompt_preview": prompt_preview,
                "response": response[:500],
                "rationale": rationale,
                "action": action, "coords": coords,
                "latency_s": llm_latency,
                "parse_ok": parse_ok,
            }
            if log_every_llm:
                llm_responses.append(llm_info)
        else:
            action = dispatch.play_action
            coords = None
            if action == 6:
                # NN-driven CLICK: rotate through level-hint bbox grid once.
                # Returns None once the grid has cycled; fall back to center.
                # Not force-escalating to invoke — that's a tactical patch
                # for a strategic issue. The right fix is retraining with
                # the delta records so the action_head learns coord choice.
                coords = _nn_click_coords(game_family, level)
                if coords is None:
                    coords = {"x": 32, "y": 32}

        aname = ACTION_NAMES[action] if 0 <= action < N_ACTIONS else str(action)
        action_counts[aname] = action_counts.get(aname, 0) + 1

        # Advance env
        try:
            ga = int_to_action.get(action)
            if ga is None:
                errors.append(f"step {step_idx}: no enum for {action}")
                break
            new_fd = env.step(ga, data=coords) if coords else env.step(ga)
        except Exception as e:
            errors.append(f"step {step_idx}: env.step({aname}) failed: {e!r}")
            break

        new_state = getattr(getattr(new_fd, "state", None), "name", None) or "RUNNING"
        new_levels = getattr(new_fd, "levels_completed", 0) or 0

        # Compute frame-delta for trajectory log (post-action change)
        new_frame_raw = getattr(new_fd, "frame", None)
        if curr_frame_raw is not None and new_frame_raw is not None:
            try:
                a_arr = np.asarray(curr_frame_raw)
                b_arr = np.asarray(new_frame_raw)
                if a_arr.ndim == 3 and a_arr.shape[0] > 0:
                    a_arr = a_arr[-1]
                if b_arr.ndim == 3 and b_arr.shape[0] > 0:
                    b_arr = b_arr[-1]
                if a_arr.shape == b_arr.shape and a_arr.size > 0:
                    frame_delta_pct = 100.0 * float((a_arr != b_arr).mean())
                else:
                    frame_delta_pct = 100.0  # shape change
            except Exception:
                frame_delta_pct = 0.0
        else:
            frame_delta_pct = 0.0

        # Record this step in the trajectory for future prompt context
        trajectory.append({
            "step": step_idx + 1,
            "action": action,
            "coords": coords,
            "level": curr_levels,
            "new_level": new_levels,
            "frame_delta_pct": frame_delta_pct,
        })

        # Grounded reasoning metrics (B6) — computed after outcome is known
        # so mechanics_alignment can score prediction vs observation.
        if llm_info is not None and llm_info.get("rationale"):
            try:
                # World model text for vocabulary/entity grounding
                wm_text = _world_model_cache.get(
                    game_family,
                    _load_world_model_summary(game_family) or "",
                )
                _world_model_cache[game_family] = wm_text
                level_advanced = new_levels > curr_levels
                metrics = compute_grounded_metrics(
                    rationale=llm_info["rationale"],
                    world_model_text=wm_text or "",
                    observed_frame_delta_pct=frame_delta_pct,
                    level_advanced=level_advanced,
                )
                llm_info["grounded"] = metrics
                grounded_per_invoke.append(metrics)
            except Exception as e:
                errors.append(f"grounded metrics at step {step_idx}: {e!r}")

        # Metacog observe_tick (Nomad B1) — per step, not just per invoke.
        # Records what the CNN did + outcome; detectors fire if patterns emerge.
        if metacog is not None:
            try:
                action_name = ACTION_NAMES[action] if 0 <= action < N_ACTIONS else str(action)
                action_dict: Dict[str, Any] = {"type": action_name, "raw": int(action)}
                if coords:
                    action_dict["coords"] = coords
                snarc_novelty = min(1.0, frame_delta_pct / 50.0)  # crude approx
                metacog.observe_tick(
                    tick=step_idx + 1,
                    action_taken=action_dict,
                    state_delta={"frame_delta_pct": frame_delta_pct,
                                 "level_delta": new_levels - curr_levels},
                    snarc_novelty=snarc_novelty,
                    atp_balance=float(max_steps - step_idx - 1),
                    atp_cost=1.0,
                    estimated_actions_to_goal=None,
                    goal_status="active",
                )
            except Exception:
                pass   # metacog is additive; any failure shouldn't break dispatch

        # Level transition → reset metacog counters (Q5 consensus)
        if metacog is not None and new_levels > curr_levels:
            try:
                metacog.reset()
            except Exception:
                pass

        metadata = {
            "source": "sage_plays_self",
            "game": game_family, "game_id": game_id,
            "step_index": step_idx + 1, "synthetic_kernel_state": True,
            "sage_plays_self": {
                "decision": dispatch.decision,
                "invoke_reasons": dispatch.invoke_reasons,
                "invoke_prob": dispatch.invoke_prob,
                "play_action": dispatch.play_action,
                "play_confidence": dispatch.play_confidence,
                "action_ranking": dispatch.action_ranking[:5],
                "applied_action": action,
                "applied_coords": coords,
                "llm_invoked": llm_info is not None,
                "llm_action": llm_info["action"] if llm_info else None,
                "llm_rationale": llm_info["rationale"] if llm_info else None,
                "llm_latency_s": llm_info["latency_s"] if llm_info else None,
                "state_before": curr_state, "state_after": new_state,
                "levels_before": curr_levels, "levels_after": new_levels,
                "stuck_triggered": stuck_triggered,
                "planner": "llm_dispatch_v4",
            },
        }
        # Bypass RouterRecord — we don't have a full RouterInput to attach
        # for this stream. Write a minimal dict directly.
        rec_dict = {
            "record_id": f"llm_{machine}_{int(time.time()*1000):013d}_{step_idx:05d}",
            "schema_version": "v0.2.0",
            "timestamp": time.time(),
            "machine": machine,
            "router_input": {
                "tick": step_idx + 1, "game_family": game_family,
                "level": curr_levels, "step_index": step_idx + 1,
            },
            "router_output": {"action": "noop", "rationale_code": "llm_dispatch"},
            "outcome": None,
            "metadata": metadata,
        }
        try:
            writer.append(rec_dict)
        except Exception as e:
            errors.append(f"step {step_idx}: write failed: {e!r}")

        # Accumulate experience for batch write at game end (no per-step overhead)
        if not hasattr(run_llm_dispatch, '_experience_buffer'):
            run_llm_dispatch._experience_buffer = []
        _outcome = "progress" if frame_delta_pct > 3 else "stuck"
        if new_levels > curr_levels:
            _outcome = "win"
        elif new_state == "GAME_OVER":
            _outcome = "game_over"
        _aname = ACTION_NAMES[action] if 0 <= action < N_ACTIONS else str(action)
        run_llm_dispatch._experience_buffer.append({
            "game": game_family, "level": level, "step": step_idx,
            "action": _aname, "outcome": _outcome,
            "frame_delta": frame_delta_pct,
            "stuck_before": stuck_triggered,
            "rationale": (llm_info.get("rationale", "") if llm_info else "")[:100],
        })

        # Update state
        recent.append(action)
        last_action = int(action)
        recent_action_win.append(action)
        recent_frame_win.append(_frame_int_from_onehot(curr_frame_oh))
        if new_levels > last_levels:
            steps_since_progress = 0; last_levels = new_levels
            _level_just_changed = True
        else:
            steps_since_progress += 1

        fd = new_fd
        prev_frame_oh = curr_frame_oh
        prev_frame_raw = curr_frame_raw
        step_idx += 1

        if new_state in outcome_terminal:
            # GAME_OVER retrospective (B5): one final LLM turn asking for
            # failure analysis. ~10 tokens to emit, free R7 training signal.
            # Skipped on WIN (no failure to analyze) and when not in multiturn.
            if (multiturn and new_state == "GAME_OVER"
                    and conversation_history and llm_client is not None):
                try:
                    retro_prompt = (
                        f"The game just ended in GAME_OVER at step {step_idx} with "
                        f"{new_levels} levels cleared. One sentence only: what do you "
                        f"think went wrong, and what would you try differently next game?"
                    )
                    t0 = time.time()
                    retro_response = llm_client.chat(
                        retro_prompt,
                        history=conversation_history,
                        system_prompt=session_system_prompt,
                        max_tokens=120,
                    )
                    retro_latency = time.time() - t0
                    llm_responses.append({
                        "prompt_preview": retro_prompt,
                        "response": retro_response[:500],
                        "rationale": "retrospective",
                        "action": None, "coords": None,
                        "latency_s": retro_latency,
                        "parse_ok": True,
                        "kind": "retrospective",
                    })
                except Exception as e:
                    errors.append(f"retrospective failed: {e!r}")

            return LlmDispatchResult(
                game=game_family, game_id=game_id, n_steps=step_idx,
                max_steps=max_steps, final_state=new_state,
                final_levels=new_levels, outcome=new_state,
                solver_steps=trace_steps, action_counts=action_counts,
                invoke_count=invoke_count, llm_calls=llm_calls,
                llm_parse_failures=llm_parse_failures, stuck_count=stuck_count,
                llm_responses=llm_responses, errors=errors,
                grounded_aggregates=aggregate_grounded_metrics(grounded_per_invoke),
            )

    # Batch-write accumulated experience to membot cart
    try:
        _buf = getattr(run_llm_dispatch, '_experience_buffer', [])
        if _buf and hasattr(run_llm_dispatch, '_membot_cart'):
            import sys as _sys
            _lib_path = os.path.join(
                os.environ.get("SHARED_CONTEXT_DIR",
                    os.path.expanduser("~/ai-workspace/shared-context")),
                "lib")
            if _lib_path not in _sys.path:
                _sys.path.insert(0, _lib_path)
            from membot_vendored.arcsage_cart import append_turn as _append_turn
            import requests as _req
            # Only write interesting steps (wins, stuck moments, invoked steps)
            _interesting = [e for e in _buf if e["outcome"] in ("win", "game_over")
                           or e["stuck_before"] or e.get("rationale")]
            for e in _interesting[:50]:  # cap at 50 per game
                _body = f"{e['game']} L{e['level']} step {e['step']}: {e['action']} → {e['outcome']}"
                if e.get('rationale'):
                    _body += f". {e['rationale']}"
                try:
                    _resp = _req.post("http://localhost:11434/api/embeddings",
                        json={"model": "nomic-embed-text", "prompt": _body}, timeout=5)
                    _emb = np.array(_resp.json()["embedding"], dtype=np.float32)
                    _append_turn(
                        run_llm_dispatch._membot_cart, _emb,
                        game=e["game"], level=e["level"], step=e["step"],
                        machine=machine, action=e["action"], outcome=e["outcome"],
                        body=_body, stuck_before=e["stuck_before"],
                    )
                except Exception:
                    continue
            run_llm_dispatch._membot_cart.save()
        run_llm_dispatch._experience_buffer = []
    except Exception:
        pass

    final_state = getattr(getattr(fd, "state", None), "name", None) or "RUNNING"
    final_levels = getattr(fd, "levels_completed", 0) or 0
    return LlmDispatchResult(
        game=game_family, game_id=game_id, n_steps=step_idx,
        max_steps=max_steps, final_state=final_state,
        final_levels=final_levels, outcome="MAX_STEPS",
        solver_steps=trace_steps, action_counts=action_counts,
        invoke_count=invoke_count, llm_calls=llm_calls,
        llm_parse_failures=llm_parse_failures, stuck_count=stuck_count,
        llm_responses=llm_responses, errors=errors,
        grounded_aggregates=aggregate_grounded_metrics(grounded_per_invoke),
    )


# ───────────────────────────────────────────────────────────────────
# CLI
# ───────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--adapter", required=True, help="FrameRouter adapter base path.")
    p.add_argument("--game", required=True)
    p.add_argument("--game-id", default=None)
    p.add_argument("--machine", default=os.environ.get("SAGE_MACHINE", "unknown"))
    p.add_argument("--data-dir", default=None,
                   help="Router training-data dir. If unset, resolves via "
                        "SAGE_ROUTER_DATA_DIR env var, then "
                        "<workspace>/private-context/training-data/router. "
                        "Fleet-portable; no machine-specific hardcoding.")
    p.add_argument("--max-steps", type=int, default=None)
    p.add_argument("--llm-backend", default=os.environ.get("SAGE_LLM_BACKEND", "ollama"),
                   choices=["ollama", "anthropic", "claude_cli"],
                   help="LLM backend. "
                        "ollama = local Ollama HTTP API (free, local). "
                        "claude_cli = Claude via OAuth subscription subprocess (free under Max plan). "
                        "anthropic = Anthropic API via SDK (paid per-call; use strategically).")
    p.add_argument("--llm-model", default=os.environ.get("SAGE_LLM_MODEL", "llama3.2-vision:11b"),
                   help="Model name. For anthropic backend, claude-opus-4-7 recommended.")
    p.add_argument("--llm-url", default=os.environ.get("SAGE_LLM_BASE_URL", "http://localhost:11434"),
                   help="Ollama base URL (ignored for anthropic backend).")
    p.add_argument("--llm-timeout", type=float, default=60.0)
    p.add_argument("--json-out", default=None)
    args = p.parse_args()

    # Resolve game_id
    game_id = args.game_id
    if not game_id:
        for root in [Path(os.environ.get("ARC_SAGE_DIR", "")),
                     Path("/mnt/c/exe/projects/ai-agents/ARC-SAGE"),
                     Path.home() / "ai-workspace" / "ARC-SAGE",
                     Path.home() / "repos" / "ARC-SAGE"]:
            coord = root / "knowledge" / "game_coordination.json"
            if coord.exists():
                try:
                    for g in json.loads(coord.read_text()).get("games", []):
                        if g.get("family") == args.game:
                            game_id = g.get("id"); break
                except Exception:
                    pass
                if game_id: break
    if not game_id:
        print(f"ERROR: could not resolve game_id for {args.game}")
        return 1

    # Trace for step budget
    trace_steps = None
    try:
        tp = _discover_trace(args.game, game_id)
        if tp and tp.exists():
            tr = load_trace(tp, args.game, game_id)
            trace_steps = len(tr.steps)
    except Exception:
        pass
    max_steps = args.max_steps or (min(2 * trace_steps, 500) if trace_steps else 200)

    model, cfg = load_frame_router(Path(args.adapter))

    # Build LLM client based on backend
    if args.llm_backend == "anthropic":
        if args.llm_model == "llama3.2-vision:11b":
            args.llm_model = "claude-opus-4-7"
        try:
            llm: LLMClient = AnthropicClient(model=args.llm_model, timeout=args.llm_timeout)
        except RuntimeError as e:
            print(f"ERROR: {e}")
            return 1
        endpoint_desc = f"anthropic API ({args.llm_model})"
    elif args.llm_backend == "claude_cli":
        if args.llm_model == "llama3.2-vision:11b":
            args.llm_model = "sonnet"
        try:
            llm = ClaudeCLIClient(model=args.llm_model, timeout=args.llm_timeout)
        except RuntimeError as e:
            print(f"ERROR: {e}")
            return 1
        endpoint_desc = f"claude CLI via OAuth ({args.llm_model})"
    else:
        llm = OllamaClient(base_url=args.llm_url, model=args.llm_model,
                           timeout=args.llm_timeout)
        endpoint_desc = f"{args.llm_model} at {args.llm_url}"

    # Probe LLM availability
    probe = llm.chat("Reply with just OK.", max_tokens=10)
    if probe.startswith("ERROR"):
        print(f"LLM probe failed: {probe}")
        print(f"  endpoint: {endpoint_desc}")
        return 1
    print(f"LLM online: {endpoint_desc} (probe: {probe[:60]!r})")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    data_dir = Path(args.data_dir) if args.data_dir else _resolve_router_data_dir()
    writer = RouterDatasetWriter(
        base_dir=data_dir, machine=args.machine,
        compress=True, subdir="llm_dispatch",
    )
    try:
        result = run_llm_dispatch(
            model, cfg, args.game, game_id, writer, args.machine, llm,
            max_steps=max_steps, trace_steps=trace_steps, device=device,
        )
    finally:
        writer.close()

    print("=" * 60)
    print(f"llm_dispatch — {args.game} — {args.machine}")
    print(f"  LLM model: {args.llm_model}")
    print("=" * 60)
    print(f"  Solver ref : {trace_steps} steps")
    print(f"  SAGE took  : {result.n_steps} / {max_steps}")
    print(f"  Final      : {result.final_state}  levels={result.final_levels}")
    print(f"  Outcome    : {result.outcome}")
    print(f"  Actions    : {result.action_counts}")
    print(f"  Invokes    : {result.invoke_count}/{result.n_steps} "
          f"({100*result.invoke_count/max(result.n_steps,1):.1f}%)")
    print(f"  LLM calls  : {result.llm_calls}  (parse_fail={result.llm_parse_failures})")
    print(f"  Stuck hits : {result.stuck_count}")
    if result.llm_responses:
        print(f"\n  First LLM response:")
        r = result.llm_responses[0]
        print(f"    rationale: {r.get('rationale','')}")
        print(f"    action:    {r.get('action')}  coords: {r.get('coords')}")
        print(f"    latency:   {r.get('latency_s', 0):.2f}s")

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(asdict(result), f, indent=2)
        print(f"\nWrote: {args.json_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
