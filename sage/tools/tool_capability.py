"""
Tool Capability Detection — runtime detection of model tool-calling tier.

Follows the SleepCapability pattern: probe the environment at startup,
classify into tiers, cache results.

Tiers:
    T1 (native_tools): Model supports Ollama /api/chat with tools parameter.
        Tool calls come back as structured JSON — no parsing needed.
    T2 (grammar_tools): Model responds to prompt-injected tool schemas.
        Outputs structured text (<tool_call>, ```json, etc.) that can be parsed.
    T3 (intent_tools): Heuristic detection only (always available).
        Scans natural language for tool intent patterns.

Detection strategy:
    1. Query Ollama /api/show for model metadata (template, parameters)
    2. Check model family against known-good list
    3. Optionally send probe prompt with tool definitions, classify response
    4. Cache result to instance directory (tool_capability.json)
    5. Re-probe on model change
"""

import json
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional


# Known model families and their expected best tier
_MODEL_TIERS: Dict[str, str] = {
    # T1: Native tool calling via /api/chat
    'llama3': 'T1',
    'llama3.1': 'T1',
    'llama3.2': 'T1',
    'llama3.3': 'T1',
    'qwen2.5': 'T1',
    'qwen2': 'T1',
    'qwen3': 'T1',
    'qwen3.5': 'T1',  # measured 2026-09-07: /api/chat returns structured tool_calls
    'mistral': 'T1',
    'mixtral': 'T1',
    'command-r': 'T1',

    # T2: Grammar-guided (structured output capable)
    'gemma4': 'T1',  # measured 2026-09-07: native tool_calls, incl. multi-turn
    'gemma3': 'T2',
    'gemma2': 'T2',
    'phi4': 'T2',
    'phi3': 'T2',
    'deepseek-r1': 'T2',
    'deepseek-coder': 'T2',

    # T3: Heuristic only
    'tinyllama': 'T3',
    'phi2': 'T3',
    'gemma': 'T3',  # gemma 1.x
}


@dataclass
class ToolCapability:
    """Runtime tool capability for a SAGE instance's model."""
    native_tools: bool = False    # T1: Ollama /api/chat with tools param
    grammar_tools: bool = False   # T2: Model responds to tool prompt templates
    intent_tools: bool = True     # T3: Heuristic parsing (always available)

    grammar_id: str = 'intent_heuristic'  # Which grammar adapter to use
    tier: str = 'T3'                       # Best available tier

    # Detection metadata
    model_name: str = ''
    model_family: str = ''
    detected_at: str = ''
    probe_result: Optional[str] = None

    @classmethod
    def detect(
        cls,
        model_name: str,
        ollama_host: str = 'http://localhost:11434',
        instance_dir: Optional[Path] = None,
        force_probe: bool = False,
    ) -> 'ToolCapability':
        """
        Detect tool capabilities for a model.

        Strategy:
            1. Check cache in instance_dir
            2. If cache miss or force_probe: query Ollama /api/show
            3. Match model family against known tiers
            4. Optionally probe with tool definitions
            5. Cache result

        Args:
            model_name: Ollama model identifier (e.g. 'gemma3:12b')
            ollama_host: Ollama API endpoint
            instance_dir: Instance directory for caching
            force_probe: Skip cache, re-detect

        Returns:
            ToolCapability with detected tier and grammar adapter
        """
        # 1. Check cache
        if instance_dir and not force_probe:
            cached = cls._load_cache(instance_dir, model_name)
            if cached:
                return cached

        cap = cls(model_name=model_name)

        # 2. Extract model family from name
        cap.model_family = _extract_family(model_name)

        # 3a. AUTHORITATIVE FIRST: ollama publishes a per-model `capabilities` array on
        # /api/show. If it lists "tools", the model natively renders the tools parameter
        # and the tier is T1 — no table lookup can be more correct than the runtime's own
        # answer. The hand-maintained _MODEL_TIERS below had drifted in BOTH directions
        # on this box (measured 2026-09-07): gemma4 was absent entirely and defaulted to
        # T3 while natively emitting structured tool_calls, and qwen3.5 was pinned T2 by
        # a comment ("Ollama template lacks {{.Tools}}") that is no longer true. Note the
        # old template-sniff is also unreliable now — gemma4, gemma3 and qwen3.5 ALL
        # report `.Tools` absent from the template while two of them do native calls.
        # A table of families is a snapshot; capabilities is the live fact.
        caps = []
        try:
            caps = (_query_model_info(model_name, ollama_host) or {}).get("capabilities") or []
        except Exception:
            caps = []
        if "tools" in caps:
            cap.native_tools = True
            cap.grammar_tools = True
            cap.tier = "T1"
            cap.grammar_id = "native_ollama"
            cap.detection_method = "ollama_capabilities"
            cls._save_cache(instance_dir, cap) if instance_dir else None
            return cap

        # 3b. Fall back to the family table for runtimes that do not publish capabilities.
        known_tier = _MODEL_TIERS.get(cap.model_family, None)

        if known_tier == 'T1':
            cap.native_tools = True
            cap.grammar_tools = True
            cap.tier = 'T1'
            cap.grammar_id = 'native_ollama'
        elif known_tier == 'T2':
            cap.grammar_tools = True
            cap.tier = 'T2'
            # Use json_block for qwen3.5 (xml tags cause empty responses)
            cap.grammar_id = 'json_block' if cap.model_family == 'qwen3.5' else 'xml_tags'
        else:
            # Default to T3 for unknown models
            cap.tier = 'T3'
            cap.grammar_id = 'intent_heuristic'

        # 4. Query Ollama /api/show for additional info
        model_info = _query_model_info(model_name, ollama_host)
        if model_info:
            template = model_info.get('template', '')
            # If model template contains tool-related tokens, upgrade to T1/T2
            if '{{.Tools}}' in template or '<tools>' in template.lower():
                cap.native_tools = True
                cap.grammar_tools = True
                cap.tier = 'T1'
                cap.grammar_id = 'native_ollama'
                cap.probe_result = 'template_has_tools'
            elif '{{.System}}' in template and known_tier is None:
                # Has system prompt support, likely handles structured output
                cap.grammar_tools = True
                if cap.tier == 'T3':
                    cap.tier = 'T2'
                    cap.grammar_id = 'xml_tags'
                    cap.probe_result = 'has_system_prompt'

        # 5. Set timestamp and cache
        from datetime import datetime
        cap.detected_at = datetime.now().isoformat()

        if instance_dir:
            cls._save_cache(instance_dir, cap)

        return cap

    @classmethod
    def _load_cache(cls, instance_dir: Path, model_name: str) -> Optional['ToolCapability']:
        """Load cached capability from instance directory."""
        cache_path = instance_dir / 'tool_capability.json'
        if not cache_path.exists():
            return None

        try:
            with open(cache_path) as f:
                data = json.load(f)

            # Cache invalidation: different model
            if data.get('model_name') != model_name:
                return None

            return cls(
                native_tools=data.get('native_tools', False),
                grammar_tools=data.get('grammar_tools', False),
                intent_tools=data.get('intent_tools', True),
                grammar_id=data.get('grammar_id', 'intent_heuristic'),
                tier=data.get('tier', 'T3'),
                model_name=data.get('model_name', ''),
                model_family=data.get('model_family', ''),
                detected_at=data.get('detected_at', ''),
                probe_result=data.get('probe_result'),
            )
        except (json.JSONDecodeError, KeyError):
            return None

    @classmethod
    def _save_cache(cls, instance_dir: Path, cap: 'ToolCapability'):
        """Save capability to instance directory cache."""
        instance_dir.mkdir(parents=True, exist_ok=True)
        cache_path = instance_dir / 'tool_capability.json'
        with open(cache_path, 'w') as f:
            json.dump(cap.to_dict(), f, indent=2)

    @property
    def best_tier(self) -> str:
        """Return the best available tier string."""
        return self.tier

    def to_dict(self) -> Dict[str, Any]:
        return {
            'native_tools': self.native_tools,
            'grammar_tools': self.grammar_tools,
            'intent_tools': self.intent_tools,
            'grammar_id': self.grammar_id,
            'tier': self.tier,
            'model_name': self.model_name,
            'model_family': self.model_family,
            'detected_at': self.detected_at,
            'probe_result': self.probe_result,
        }

    def __repr__(self) -> str:
        return (f"ToolCapability(tier={self.tier}, grammar={self.grammar_id}, "
                f"model={self.model_name})")


def _extract_family(model_name: str) -> str:
    """
    Extract model family from Ollama model name.

    'gemma3:12b' → 'gemma3'
    'llama3.2:3b-instruct' → 'llama3.2'
    'qwen2.5:14b' → 'qwen2.5'
    """
    base = model_name.split(':')[0]
    # Remove trailing size suffix if it's just digits (e.g. 'phi4-mini' stays 'phi4-mini')
    # but 'gemma3' stays 'gemma3'
    return base.rstrip('-').rstrip('_')


def _query_model_info(model_name: str, ollama_host: str) -> Optional[Dict[str, Any]]:
    """Query Ollama /api/show for model metadata."""
    try:
        payload = json.dumps({'name': model_name}).encode('utf-8')
        req = urllib.request.Request(
            f'{ollama_host}/api/show',
            data=payload,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


# ============================================================================
# CLI entry point
# ============================================================================

if __name__ == '__main__':
    import sys

    model = sys.argv[1] if len(sys.argv) > 1 else 'gemma3:12b'
    host = sys.argv[2] if len(sys.argv) > 2 else 'http://localhost:11434'

    print(f"Detecting tool capability for {model} @ {host}")
    print("=" * 50)

    cap = ToolCapability.detect(model, host)
    print(f"  Tier:         {cap.tier}")
    print(f"  Grammar:      {cap.grammar_id}")
    print(f"  Native tools: {cap.native_tools}")
    print(f"  Grammar tools:{cap.grammar_tools}")
    print(f"  Intent tools: {cap.intent_tools}")
    print(f"  Model family: {cap.model_family}")
    print(f"  Probe result: {cap.probe_result}")
    print()
    print(f"Full: {cap}")
