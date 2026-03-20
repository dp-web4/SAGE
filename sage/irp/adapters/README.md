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

## Evolving Configs from Raising Sessions

Raising sessions are the primary discovery mechanism for model quirks. When the tutor (Claude) or dream consolidation observes adapter-relevant behavior, it should be encoded back into the config.

### What to Watch For

| Symptom | Likely config field | Example |
|---------|-------------------|---------|
| Model echoes its own name before responding | `echo_prefixes` | TinyLlama outputs "CBP: Hello" instead of "Hello" |
| Model generates other speakers' turns | `bilateral_prone` | 0.8B Qwen writes "Claude: ..." after its own response |
| Model ignores tool XML / calls tools wrong | `supports_tool_calls`, `tier`, `notes` | Model wraps tool calls in markdown fences |
| Model loses coherence past N turns | `max_context_turns` | Quality degrades after 4 turns at 1.1B |
| Model produces structured output reliably | `tier` upgrade (T3→T2→T1) | Gemma3 reliably produces XML tool calls |
| Model has thinking/reasoning mode | `thinking_supported` | Qwen3.5 27B uses `<think>` blocks |

### How to Update

1. **Observe** — raising session or dream consolidation flags the behavior
2. **Reproduce** — confirm the quirk is consistent (not a one-off)
3. **Edit the JSON config** — add/change the relevant field
4. **No code changes needed** — `clean_response()` and `capabilities` read from the config
5. **Test** — run the adapter self-test: `python3 -m sage.irp.adapters.model_adapter`

### Adding New Config Fields

If a quirk doesn't fit existing fields:

1. Add the field to `model_capabilities.py` (ModelCapabilities dataclass)
2. Add handling to `clean_response()` or the relevant method in `model_adapter.py`
3. Set the default in `model_configs/default.json` (conservative — off/false)
4. Set the model-specific value in the relevant family config

Example: if raising discovers that a model wraps tool calls in markdown fences:
```json
// model_configs/newmodel.json
{
    "strip_markdown_fences": true,
    "notes": "Wraps tool XML in ```xml blocks — strip before parsing"
}
```

### Dream Consolidation Integration

Dream consolidation reviews each session transcript. When it detects adapter-relevant patterns, it should note them in the raising log:

```
[Dream] Adapter note: TinyLlama echoed sender name in 4/6 turns — echo_prefixes working.
[Dream] Adapter note: New pattern — model generated [System]: tag not in bilateral_speakers list.
```

These notes are human-reviewed. If a pattern is consistent across multiple sessions, update the config.

### Size-Dependent Behavior

The same model family often behaves differently at different parameter counts. Use instance-level `adapter_overrides` rather than changing the family config:

- **0.8B Qwen**: bilateral-prone, short context, T3 tools → instance override `bilateral_prone: true`
- **27B Qwen**: clean output, long context, T1 tools → instance override `bilateral_prone: false`

The family config should reflect the most common behavior. Instance overrides handle the exceptions.

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
