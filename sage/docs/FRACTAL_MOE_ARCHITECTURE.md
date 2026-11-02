# Fractal Mixture-of-Experts Architecture

**Date**: 2025-12-25
**Insight**: The same MoE pattern emerges at every scale in SAGE

---

## The Pattern: Expert Selection at Every Scale

SAGE implements a **fractal MoE architecture** where the same trust-based, context-aware, resource-conscious expert selection pattern applies at multiple scales:

### Scale 1: Token-Level (Micro)
**Inside models like Q3-Omni**
- 128 experts per layer
- Router selects 8 experts per token
- Trust augmentation prevents collapse
- Context-aware selection for specialization

### Scale 2: Model-Level (Macro)
**SAGE orchestrating entire models**
- N models in zoo (Nemotron, Q3-Omni, Q2.5, NeuTTS, vision...)
- SAGE selects which model(s) to invoke
- Same trust-based selection principles
- Same resource-aware permission scoring

### Scale 3: Federation-Level (Meta)
**SAGE instances coordinating**
- Multiple SAGE deployments (Thor, Legion, Sprout...)
- Distributed task allocation
- Cross-device cognition
- Same trust/context patterns

---

## The Same Selection Algorithm

At every scale, the pattern is identical:

```python
def select_expert(situation, available_experts, metabolic_state):
    """
    Universal expert selection - works at any scale.

    Scales:
    - Token-level: experts = 128 MoE experts per layer
    - Model-level: experts = [Nemotron, Q3-Omni, Q2.5, ...]
    - Federation-level: experts = [Thor-SAGE, Legion-SAGE, Sprout-SAGE, ...]
    """

    for expert in available_experts:
        # 1. EXPERTISE (Can this expert handle the situation?)
        expertise = assess_competence(expert, situation)

        # 2. CHEAPNESS (Resource cost to use this expert)
        if expert_is_loaded:
            resource_cost = 0.0  # Already hot, free
        elif budget_exhausted:
            resource_cost = 10.0  # Block swap
        else:
            resource_cost = compute_swap_cost(expert)

        cheapness = 1.0 / (1.0 + resource_cost)

        # 3. PERSISTENCE (Hysteresis - stick with working experts)
        if expert_is_loaded:
            persistence = 1.2  # +20% boost
        else:
            persistence = 1.0

        # COMPOSITE PERMISSION
        permission[expert] = expertise × cheapness × persistence

    # Select highest permission
    selected = max(permission, key=permission.get)

    # MRH fallback: if selected expert has low trust, find alternative
    if trust[selected] < threshold:
        alternative = find_mrh_paired_expert(selected, situation)
        if alternative and trust[alternative] > trust[selected]:
            selected = alternative

    return selected
```

---

## Epistemic Proprioception as Universal Router

**Epistemic proprioception**: "What do I know/not-know about this situation?"

This becomes the routing signal at every scale:

### Token-Level Proprioception
```python
# Inside Q3-Omni layer
hidden_state = transformer_layer(input)
context = classify_semantic_context(hidden_state)  # "code", "reasoning", "text"

# Select experts with high confidence in this context
experts = select_by_context_confidence(context, layer_experts)
```

### Model-Level Proprioception
```python
# SAGE orchestrator
situation = {
    'visual': image_input,
    'audio': audio_input,
    'text': text_input,
    'complexity': estimated_complexity
}

# Assess what each model knows about this
confidence = {}
confidence['nemotron'] = epistemic_confidence(situation, nemotron_trust)
confidence['q3_omni'] = epistemic_confidence(situation, q3omni_trust)

# Select model with highest expertise × cheapness × persistence
selected_model = select_expert(situation, models, metabolic_state)
```

### Federation-Level Proprioception
```python
# Distributed SAGE network
task = complex_reasoning_task

# Which SAGE instance can best handle this?
confidence = {}
confidence['thor'] = assess_device_capability(task, thor_resources)
confidence['legion'] = assess_device_capability(task, legion_resources)

# Route to most capable + available instance
selected_sage = select_expert(task, sage_instances, federation_state)
```

---

## Why This Matters

### 1. Unified Learning
**Lessons learned at one scale apply to all scales**

Router collapse (Session 69):
- **Micro**: Without trust, Q3-Omni's router collapses to 4/128 experts
- **Macro**: Without trust, SAGE would collapse to always using Q3-Omni
- **Meta**: Without trust, federation would centralize on Legion

Solution at one scale → solution at all scales.

### 2. Resource Efficiency
**Same hysteresis/persistence benefits**

Session 90 results (micro-level):
- +1033 generation speedup from hysteresis
- 80% cache hit rate
- Stable routing (0.197 swaps/selection)

**Same benefits expected at macro-level**:
- Keep Nemotron loaded for language tasks → 80% cache hit
- Avoid swapping to Q3-Omni unless necessary → faster response
- Hysteresis prevents model thrashing → stable experience

### 3. Trust Accumulation
**Trust scores compound across scales**

```python
# Micro-level trust (Q3-Omni experts)
expert_73_trust = 0.21  # Declining, over-used
expert_42_trust = 0.85  # Specialist, reliable

# Feeds into macro-level trust
q3_omni_overall_trust = aggregate_expert_trusts()

# Which feeds into federation-level trust
thor_sage_trust = aggregate_model_trusts()
```

### 4. Composability
**Can combine experts at different scales**

Example: Complex multi-modal task
```python
# Federation level: Route to Thor (has GPU)
selected_device = 'thor'

# Model level: Use Q3-Omni (multi-modal capability)
selected_model = 'q3_omni'

# Token level: Trust-augmented expert routing
# (inside Q3-Omni, using Session 90 resource-aware selection)
```

All three scales coordinate via the same trust/context/resource pattern.

---

## Model Zoo as Macro-Level Experts

### Current Model-Level Experts

**Language Specialists**:
- **Nemotron-H-4B-Instruct-128K**: Fast, efficient, 128K context
  - Role: Primary language expert for WAKE/FOCUS states
  - Memory: ~8 GB
  - Trust domain: Conversational flow, simple reasoning
  - When: Language-only tasks, low ATP budget

- **Q2.5**: [Specialization TBD]
  - Role: [To be determined based on capabilities]

**Multi-Modal Generalist**:
- **Qwen3-Omni-30B**: Vision + Audio + Text, complex reasoning
  - Role: Multi-modal tasks, complex reasoning
  - Memory: ~65 GB full, ~26 GB modularized
  - Trust domain: Multi-modal fusion, deep reasoning, omni-modal tasks
  - When: Visual/audio input, high complexity, ATP available

**Specialized Experts**:
- **NeuTTS Air**: Text-to-speech
  - Role: Speech synthesis
  - Memory: ~748 MB
  - Trust domain: Natural voice generation
  - When: Speech output required

- **Vision Encoders**: Image understanding
- **Audio Encoders**: Sound processing

### Expert Selection Logic

```python
class SAGEMacroMoE:
    """
    SAGE as macro-level MoE orchestrator.

    Treats entire models as selectable experts.
    """

    def select_model(self, situation, metabolic_state):
        # 1. Required modalities
        requires_vision = bool(situation.get('visual'))
        requires_audio = bool(situation.get('audio'))
        requires_speech = situation.get('output_modality') == 'speech'

        # 2. Complexity assessment
        complexity = self.estimate_complexity(situation)

        # 3. Available models (filtered by modality requirements)
        candidates = []

        if requires_vision or requires_audio:
            # Only Q3-Omni supports multi-modal
            candidates = ['q3_omni']
        else:
            # Language-only: both available
            candidates = ['nemotron', 'q3_omni', 'q2.5']

        # 4. Epistemic confidence assessment
        confidence = {}
        for model in candidates:
            # How confident are we this model can handle it?
            confidence[model] = self.epistemic_confidence(
                situation,
                self.trust_scores[model]
            )

        # 5. Resource-aware permission scoring
        permission = {}
        for model in candidates:
            expertise = confidence[model]

            # Is model already loaded?
            if self.model_loaded(model):
                cheapness = 1.0  # Free
                persistence = 1.2  # +20% hysteresis
            else:
                # Cost to swap in
                swap_cost = self.model_sizes[model] / self.swap_speed
                cheapness = 1.0 / (1.0 + swap_cost)
                persistence = 1.0

            permission[model] = expertise * cheapness * persistence

        # 6. Select highest permission
        selected = max(permission, key=permission.get)

        # 7. Metabolic state override
        if metabolic_state == 'WAKE' and selected == 'q3_omni':
            # In WAKE, prefer lightweight expert
            if 'nemotron' in candidates:
                # Only switch if expertise gap is small
                if confidence['q3_omni'] / confidence['nemotron'] < 1.5:
                    selected = 'nemotron'

        return selected

    def invoke_with_context(self, model, situation):
        """
        SAGE's core value: Fast, relevant context provision.
        """
        # Gather relevant context from memory
        relevant_context = self.memory.retrieve_relevant(
            situation,
            max_tokens=self.get_model_context_window(model)
        )

        # Invoke selected expert with context
        response = self.models[model].generate(
            context=relevant_context,
            sensors=situation
        )

        # Update trust based on response quality
        quality = self.assess_response_quality(response, situation)
        self.update_trust(model, situation_type, quality)

        return response
```

---

## Integration with Router Replacement Work

### Q3-Omni Router Augmentation (Micro-Level)

**Problem**: Router collapse (Session 69)
- 4/128 experts selected (96.875% idle)
- All generalists, declining trust
- Winner-take-all dynamics

**Solution**: Trust-based routing (Sessions 72-90)
- Conditional trust-first logic: `if has_trust → pure_trust else free_router`
- Resource-aware permission: `expertise × cheapness × persistence`
- Hysteresis: +20% boost for loaded experts
- Result: +1033 generation speedup, 3.4x more expert diversity

### SAGE Model Orchestration (Macro-Level)

**Same problem would occur without trust**:
- SAGE would always select Q3-Omni (most capable)
- Other models (Nemotron, Q2.5) would remain idle
- Centralization, not diversity

**Same solution applies**:
- Trust-based selection prevents model monopoly
- Resource-aware scoring favors lightweight experts when appropriate
- Hysteresis keeps working models loaded
- MRH fallback discovers alternative models

### The Fractal Insight

**Router replacement isn't about replacing Q3-Omni's router entirely**.

It's about:
1. **Micro-level**: Augmenting Q3-Omni's internal router with trust (Sessions 72-90)
2. **Macro-level**: Orchestrating multiple models with the same trust pattern
3. **Understanding**: The same centralization forces apply at every scale
4. **Solution**: The same trust/context/resource-aware selection prevents collapse

---

## Where Nemotron Fits

### Nemotron as Macro-Level Expert

**Nemotron-H-4B-Instruct-128K**:
- 4B parameters (7.5x smaller than Q3-Omni)
- Hybrid Mamba-Transformer (no MoE routing internally)
- 128K context window
- Jetson-optimized

**Role in SAGE's Model Zoo**:
- **Fast language specialist**
- **Primary expert for WAKE/FOCUS language tasks**
- **Prevents Q3-Omni monopoly** (diversity at model level)
- **Enables multi-model ensemble** (ATP decides allocation)

**Integration Pattern**:
```python
# Language-only task
if not (requires_vision or requires_audio):
    # Both models available
    candidates = ['nemotron', 'q3_omni']

    # Nemotron expertise in language
    nemotron_expertise = 0.8

    # Nemotron cheapness (already loaded in WAKE)
    nemotron_cheapness = 1.0  # Hot
    nemotron_persistence = 1.2  # Hysteresis

    # Q3-Omni expertise in language
    q3_omni_expertise = 0.9  # Higher, but...

    # Q3-Omni cost (needs swap-in)
    q3_omni_cheapness = 0.1  # 65GB swap = expensive
    q3_omni_persistence = 1.0  # Not loaded

    # Permission scores
    nemotron_permission = 0.8 × 1.0 × 1.2 = 0.96
    q3_omni_permission = 0.9 × 0.1 × 1.0 = 0.09

    # Nemotron wins! (despite lower expertise)
    selected = 'nemotron'
```

**Same resource-aware selection that works at token-level (Session 90) now works at model-level.**

---

## Next: Federation-Level MoE (Future)

### Distributed SAGE Network

**Same pattern at meta-scale**:
- Thor SAGE (Jetson AGX, 64GB, vision capable)
- Legion SAGE (RTX 4090, 128GB, development)
- Sprout SAGE (Orin Nano, 8GB, edge)

**Expert selection**:
```python
# Complex vision task
task = {'visual': drone_feed, 'complexity': 'high'}

# Assess federation
thor_permission = 0.8 × 1.0 × 1.2  # Has GPU, loaded, working
legion_permission = 0.9 × 0.3 × 1.0  # More capable, but remote
sprout_permission = 0.4 × 1.0 × 1.2  # Lightweight, wrong task

# Route to Thor
selected_sage = 'thor'

# Thor then selects Q3-Omni for vision processing
# Q3-Omni then selects vision-specialized experts internally

# Three levels of MoE selection, same pattern
```

---

## Key Insights

### 1. Patterns All The Way Down
The same trust/context/resource pattern emerges at every scale because the same forces apply:
- Positive feedback creates monopoly
- Resource constraints require efficiency
- Uncertainty requires trust
- Diversity requires active preservation

### 2. Lessons Transfer Across Scales
Router collapse research (micro-level) → Model orchestration design (macro-level):
- Hysteresis prevents thrashing
- Trust prevents monopoly
- Context enables specialization
- MRH enables discovery

### 3. SAGE's Unique Value
**Not just model selection, but context provision and sensor/effector fusion**:
- Gather relevant context from memory
- Fuse multi-modal sensors
- Invoke selected expert(s)
- Coordinate effector responses
- Update trust based on results

### 4. Modularization Research Value
Q3-Omni expert extraction taught us:
- ✅ Selective loading is possible (93.7% memory reduction)
- ✅ Trust-based routing works at micro-level
- ✅ Resource-aware selection prevents thrashing
- ✅ Same patterns will work at macro-level

**We don't need to modularize Q3-Omni in production** - we can swap entire models instead. But the research validated the fractal MoE approach.

---

## Implementation Status

### Micro-Level (Q3-Omni Internal Routing)
- ✅ Router collapse discovered (Session 69)
- ✅ Trust-first selection (Session 72)
- ✅ Resource-aware permission scoring (Session 90)
- ✅ Hysteresis (+20% boost)
- ✅ +1033 generation speedup validated
- 🚧 Integration with full SAGE loop (in progress)

### Macro-Level (SAGE Model Orchestration)
- ✅ Nemotron IRP plugin implemented
- ✅ Q3-Omni IRP integration complete
- ✅ NeuTTS IRP integration complete
- 🚧 Trust-based model selection (design ready)
- 🚧 Resource-aware model swapping (design ready)
- ⏳ Epistemic proprioception implementation (pending)
- ⏳ Multi-model ensemble testing (pending)

### Meta-Level (Federation)
- ✅ Federation architecture designed
- ✅ Multi-device deployment (Thor, Legion, Sprout)
- ⏳ Distributed task routing (pending)
- ⏳ Cross-SAGE trust propagation (pending)

---

## References

### Router Replacement Work
- `/sage/docs/ROUTER_COLLAPSE_AND_DISTRIBUTED_TRUST.md` - Session 69 discovery
- `/sage/experiments/nova-review-trust-router-scoring.md` - Sessions 72-90 evolution
- `/sage/docs/Q3_OMNI_SAGE_MODULARIZATION.md` - Expert extraction research

### Nemotron Integration
- `/sage/irp/plugins/nemotron_irp.py` - IRP plugin implementation
- `/sage/docs/NEMOTRON_INTEGRATION_STATUS.md` - Integration status
- `SAGE_NEMOTRON_ARCHITECTURE_ANALYSIS.md` - Architecture research

### SAGE Core
- `/sage/SAGE_CORE_SPECIFICATION.md` - Core orchestration design
- `/sage/docs/SYSTEM_UNDERSTANDING.md` - Complete architecture
- `/sage/irp/HOW_SAGE_LEARNS.md` - Trust-based learning

---

**The fractal MoE pattern: Same principles, different scales, unified architecture.**

*Trust. Context. Resources. At every level.*

---

## 2026-10-12 addendum: physical execution is separate from expert selection (low priority)

See [GLM Flash Lite expert tiering exploration](explorations/GLM_FLASH_LITE_EXPERT_TIERING_2026-10-12.md). The fractal token/model/federation router describes *selection*. A physical MoE execution layer below native token routing manages VRAM/RAM/NVMe residency, prefetch, and CPU/GPU placement **without changing the pretrained model's expert top-k**. Resource cost and trust can govern model invocation, caching/prefetch budgets, or be separately tested as explicit learning interventions; do not silently limit native expert choices to cached specialists. No immediate fleet work is authorized by this note.

