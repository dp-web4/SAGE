# ModelAdapter — Dictionary Entity for Model Interactions

The ModelAdapter is the authoritative translation layer through which ALL interactions with a specific model pass. Think of it as a Web4 dictionary entity: you don't talk to the model directly, you talk through its adapter.

## Why

Without the adapter, model-specific behavior was scattered:
- The raising session had its own bilateral generation filter
- The consciousness loop had its own echo stripping
- Each caller built prompts differently
- When a model quirk was discovered, it had to be fixed in multiple places

Now every model quirk is encoded once in a JSON config file, and every caller benefits.

## What the Adapter Handles

| Concern | Method | Driven by |
|---------|--------|-----------|
| Prompt formatting | `format_payload()` | Adapter subclass (ChatAPI vs Generate) |
| API endpoint selection | `format_payload()` | Model family |
| Response extraction | `extract_response()` | Endpoint type |
| Echo stripping | `clean_response()` | `echo_prefixes` in config |
| Bilateral generation | `clean_response()` | `bilateral_prone` in config |
| Context windowing | `capabilities.max_context_turns` | Config |
| Tool support | `capabilities.supports_tool_calls` | Config |

## Adding a New Model

Create a JSON file in `model_configs/`:

```json
{
    "family": "newmodel",
    "aliases": ["nm", "newmodel-v2"],
    "api_mode": "chat",
    "bilateral_prone": false,
    "supports_tool_calls": false,
    "max_context_tokens": 4096,
    "max_context_turns": 6,
    "thinking_supported": false,
    "tier": "T3",
    "stop_sequences": [],
    "echo_prefixes": ["{self_name}:"],
    "bilateral_speakers": ["Claude", "System", "User", "Human"],
    "notes": "Description of model behavior and quirks."
}
```

That's it. No code changes needed unless the model requires a fundamentally different API interaction pattern.

## Instance-Level Overrides

The same model family can behave differently at different sizes. Instance configs can override adapter behavior:

```json
// sage/instances/sprout-qwen3.5-0.8b/instance.json
{
    "model": "qwen3.5:0.8b",
    "adapter_overrides": {
        "bilateral_prone": true,
        "max_context_turns": 3
    }
}
```

```json
// sage/instances/thor-qwen3.5-27b/instance.json
{
    "model": "qwen3.5:27b",
    "adapter_overrides": {
        "bilateral_prone": false,
        "max_context_turns": 12,
        "thinking_supported": true
    }
}
```

## Current Model Configs

| Config | Family | Bilateral | Turns | Tier | Notes |
|--------|--------|-----------|-------|------|-------|
| `tinyllama.json` | TinyLlama | Yes | 4 | T3 | Bilateral-prone, uses /api/chat |
| `qwen2.5.json` | Qwen 2.5 | Yes | 4 | T3 | 0.5B bilateral-prone, 7B/14B not |
| `qwen3.5.json` | Qwen 3.5 | Yes | 4 | T3 | 0.8B bilateral-prone, thinking mode available |
| `gemma3.json` | Gemma 3 | No | 8 | T2 | Clean tool calls, good instruction following |
| `phi4.json` | Phi 4 | No | 10 | T1 | Native tool calling, strong reasoning |
| `default.json` | Fallback | No | 6 | T3 | Conservative defaults for unknown models |

## Usage

```python
from sage.irp.adapters.model_adapter import get_adapter

# Basic usage
adapter = get_adapter('tinyllama:latest')
caps = adapter.capabilities
print(caps.bilateral_prone)  # True
print(caps.max_context_turns)  # 4

# Response cleaning — all model-specific cleanup in one call
raw = "CBP: Hello\n[Claude]: next turn"
clean = adapter.clean_response(raw, 'CBP')  # "Hello"

# With instance overrides
adapter = get_adapter('qwen3.5:0.8b', overrides={'bilateral_prone': True})
```

## Files

```
sage/irp/adapters/
    model_adapter.py          # Base class + subclasses + get_adapter()
    model_capabilities.py     # ModelCapabilities dataclass + JSON loading
    model_configs/            # Per-family JSON configs
        tinyllama.json
        qwen2.5.json
        qwen3.5.json
        gemma3.json
        phi4.json
        default.json
```
