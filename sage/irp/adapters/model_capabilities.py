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
    max_context_tokens: int = 4096            # Approximate context window
    max_context_turns: int = 6               # Recommended history turns
    thinking_supported: bool = False          # Qwen 3.5 /think mode?
    tier: str = 'T3'                          # T1/T2/T3 tool capability
    stop_sequences: List[str] = field(default_factory=list)
    echo_prefixes: List[str] = field(default_factory=lambda: [
        '[{self_name}]:', '{self_name}:', '[SAGE]:', 'SAGE:',
    ])
    bilateral_speakers: List[str] = field(default_factory=lambda: [
        'Claude', 'System', 'User', 'Human',
    ])
    notes: str = ''


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
