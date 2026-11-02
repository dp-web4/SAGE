"""
Model capabilities — declarative configuration per model family.

Each model family has a capabilities profile loaded from JSON config.
Instance-level overrides can adjust for specific model sizes.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from pathlib import Path
import json


@dataclass
class ModelCapabilities:
    """Declarative capabilities for a model family/size."""
    family: str = 'unknown'
    api_mode: str = 'chat'                   # 'chat' or 'generate'
    bilateral_prone: bool = False             # Generates both sides of conversation?
    supports_tool_calls: bool = False         # Native Ollama tool calling?
    # Does the chat template render the tool schemas only when the LAST message is a user turn?
    # Ollama's llama3.1 template does, so a prompt ending in a tool result counts thousands of
    # tokens fewer than the same list ending in a user turn (being_tool_loop._tail_kind).
    tools_on_last_user_only: bool = False
    max_context_tokens: int = 4096            # Approximate context window
    max_context_turns: int = 6               # Recommended history turns
    thinking_supported: bool = False          # Qwen 3.5 /think mode?
    # Policy, not capability: should a caller that does not say run this model with
    # thinking on? None = fall back to thinking_supported. Per-size override via
    # variants[size]['think_default'] (qwen3.5:0.8b on a Jetson: supported, off by
    # default since 2026-03; the empero distills: on, they act only when thinking).
    think_default: Optional[bool] = None
    tier: str = 'T3'                          # T1/T2/T3 tool capability
    stop_sequences: List[str] = field(default_factory=list)
    echo_prefixes: List[str] = field(default_factory=lambda: [
        '[{self_name}]:', '{self_name}:', '[SAGE]:', 'SAGE:',
    ])
    bilateral_speakers: List[str] = field(default_factory=lambda: [
        'Claude', 'System', 'User', 'Human',
    ])
    strip_think_tags: bool = False            # Strip <think>...</think> blocks (Qwen 3.5)?
    num_predict: Optional[int] = None         # Family-wide num_predict fallback (thinking budget + response)
    # Chars per token for the tool loop's step-1 PREFLIGHT estimate (being_tool_loop.PREFLIGHT_CPT,
    # 2.9, was calibrated on a Qwen-tokenized being and over-counts a denser tokenizer badly: on
    # llama3.1 it refused every explore for 2.5 days, SAGE #582). Declare it per family from a
    # MEASURED ratio, set BELOW every measured value so the estimate still errs high. None = 2.9.
    preflight_chars_per_token: Optional[float] = None
    timeout_seconds: Optional[int] = None     # HTTP wall-clock timeout floor (think+response envelope)
    # Per-size overrides. Requirements differ dramatically by size AND by
    # think/no-think state, so a single family value is wrong. Keyed by the
    # size token in the model name (e.g. "0.8b", "27b"). Each entry may carry
    # "num_predict" (no-think) and "num_predict_think" (think-on). Editing one
    # size's entry can never change another size's resolution.
    variants: Dict[str, Dict] = field(default_factory=dict)
    notes: str = ''

    def resolve_num_predict(self, model_name: str, think: bool,
                            caller_budget: Optional[int] = None) -> Optional[int]:
        """Resolve num_predict for the full (family, size, think) tuple.

        Why this exists: qwen3.5:27b emits <think> content and needs a ~16384
        envelope even with think disabled, while qwen3.5:0.8b targets short
        responses and would only run away (and overflow context on long prompts)
        with that budget. Per-size `variants` carry a no-think value and an
        optional think-on value; resolution is independent per size, so tuning
        one model can never break another. Falls back to the family-wide
        num_predict, then to the caller's budget. caller_budget == -1 means the
        caller explicitly wants unlimited (e.g. gameplayer) and is honored.
        """
        if caller_budget == -1:
            return -1
        variant = self.variant_for(model_name)
        if variant:
            if think and variant.get('num_predict_think') is not None:
                return variant['num_predict_think']
            if variant.get('num_predict') is not None:
                return variant['num_predict']
        if self.num_predict is not None:
            return self.num_predict
        return caller_budget

    def resolve_think(self, model_name: str) -> bool:
        """Whether this model runs with thinking on when the caller does not say.
        variants[size].think_default, then the family think_default, then
        thinking_supported. dp, 2026-09-05: "generally we want the beings to think";
        the exceptions are declared here per size, not hard-coded in callers."""
        declared = self.declared_think(model_name)
        if declared is not None:
            return declared
        return bool(self.thinking_supported)

    def declared_think(self, model_name: str) -> Optional[bool]:
        """The think_default a config states for this model (its size's, else its family's); None
        when neither says. None is what lets the server's own capability list decide
        (ollama_irp.ollama_can_think): dp, 2026-10-30, "we should be [thinking], whenever that's
        an option"."""
        variant = self.variant_for(model_name) or {}
        if variant.get('think_default') is not None:
            return bool(variant['think_default'])
        if self.think_default is not None:
            return bool(self.think_default)
        return None

    def variant_for(self, model_name: str) -> Optional[Dict]:
        """The declared variant for a model's tag: the exact tag, else the longest declared tag that is
        a dash-separated PREFIX of it ("4b-q4-vision" -> "4b"), else None.

        Why the fallback (Sprout 2026-10-12): the being moved to `qwen3.8-distill:4b-q4-vision`, a
        local tag for the 4B with its vision projector. The exact lookup missed the declared `4b`
        variant, so num_ctx fell back to the 8192 floor and 36 of 37 beats were refused by Ollama
        ("request (11594 tokens) exceeds the available context size (8192 tokens)") for 13 hours.
        A suffix after the size names a build of that size; it must not drop the size's limits."""
        size = model_name.split(':', 1)[1].lower().strip() if ':' in model_name else ''
        if size in self.variants:
            return self.variants[size]
        best = None
        for k in self.variants:
            if size.startswith(str(k).lower() + "-") and (best is None or len(k) > len(best)):
                best = k
        return self.variants[best] if best is not None else None

    def resolve_num_ctx(self, model_name: str, caller_floor: int) -> int:
        """The context window a caller should send as options.num_ctx: the larger of the
        caller's floor and variants[size].num_ctx when declared. Never lowers the floor.

        Why per size: the governed harness sends 8192 because Ollama's default (4096)
        was too small for a heartbeat prompt (Sprout, 2B). But 8192 also OVERRIDES the
        Modelfile of a model that declared more: qwen38-heretic:q3km (27B, Modelfile
        num_ctx 16384) at 8192 with thinking on spent every token of room left after a
        ~5000-token prompt in its think block (prompt_eval + eval == 8192 on every empty
        turn, Legion beat 46, 2026-09-05) and never acted; at 16384 the same prompt
        gave 6 + 3 native calls and no empty turn. The retry budget cannot fix this:
        num_predict is capped by what the window has left."""
        variant = self.variant_for(model_name) or {}
        declared = variant.get('num_ctx')
        if declared is None:
            return caller_floor
        return max(int(caller_floor), int(declared))


# Config directory
_CONFIG_DIR = Path(__file__).parent / 'model_configs'

# Cache loaded configs
_config_cache: Dict[str, ModelCapabilities] = {}


def load_capabilities(model_name: str, overrides: Optional[Dict] = None) -> ModelCapabilities:
    """Load capabilities for a model, with optional instance-level overrides.

    Resolution order:
    1. Extract family from model name (e.g., 'tinyllama:latest' -> 'tinyllama')
    2. Look for model_configs/{family}.json
    3. If not found, try alias matching across all configs
    4. Fall back to default.json
    5. Apply overrides if provided
    """
    family = _extract_family(model_name)

    # Check cache (without overrides — overrides are per-call)
    if family in _config_cache and overrides is None:
        return _config_cache[family]

    # Try direct family match
    config_path = _CONFIG_DIR / f'{family}.json'
    if config_path.exists():
        caps = _load_from_json(config_path)
    else:
        # Try alias matching
        caps = _try_aliases(family)
        if caps is None:
            # Fall back to default
            default_path = _CONFIG_DIR / 'default.json'
            if default_path.exists():
                caps = _load_from_json(default_path)
            else:
                caps = ModelCapabilities(family=family)

    # Apply instance-level overrides
    if overrides:
        caps = _apply_overrides(caps, overrides)
    else:
        # Cache only un-overridden configs
        _config_cache[family] = caps

    return caps


def _extract_family(model_name: str) -> str:
    """Extract family name from model string.
    'tinyllama:latest' -> 'tinyllama'
    'qwen2.5:0.5b' -> 'qwen2.5'
    'phi4:14b' -> 'phi4'
    """
    return model_name.split(':')[0].lower().strip()


def _load_from_json(path: Path) -> ModelCapabilities:
    """Load capabilities from a JSON config file."""
    with open(path) as f:
        data = json.load(f)
    # Remove non-dataclass fields
    aliases = data.pop('aliases', [])
    return ModelCapabilities(**{k: v for k, v in data.items()
                               if k in ModelCapabilities.__dataclass_fields__})


def _try_aliases(family: str) -> Optional[ModelCapabilities]:
    """Search all config files for a matching alias."""
    if not _CONFIG_DIR.exists():
        return None
    for config_file in _CONFIG_DIR.glob('*.json'):
        try:
            with open(config_file) as f:
                data = json.load(f)
            aliases = data.get('aliases', [])
            if family in [a.lower() for a in aliases]:
                return _load_from_json(config_file)
        except (json.JSONDecodeError, KeyError):
            continue
    return None


def _apply_overrides(caps: ModelCapabilities, overrides: Dict) -> ModelCapabilities:
    """Apply instance-level overrides to capabilities."""
    # Create a copy with overrides applied
    from dataclasses import asdict
    merged = asdict(caps)
    merged.update(overrides)
    return ModelCapabilities(**{k: v for k, v in merged.items()
                                if k in ModelCapabilities.__dataclass_fields__})
