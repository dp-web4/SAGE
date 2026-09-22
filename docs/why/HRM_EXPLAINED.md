# SAGE: Situation-Aware Governance Engine

> **CURRENT-STATUS WARNING — historical architecture record.**  
> This explainer preserves the project's 2025 HRM/SAGE design framing. It is useful for provenance, but it is **not** the authoritative description of SAGE as of September 2026. For current assessment, start with [README.md](../../README.md), [SAGE Current Status](../../sage/docs/LATEST_STATUS.md), and claim-specific merged code / experiment evidence.
>
> **MRH terminology:** MRH means **Markov Relevancy Horizon**. The section below titled "Dynamic MRH Navigation" describes a *fractal, multi-resolution approach* to moving between levels of abstraction; "multi-resolution" is not an expansion of the MRH acronym. Current operational framing: [MRH as a Relevance Contract](../../forum/insights/mrh-relevance-contract.md).

## An Exploratory Architecture for Living Intelligence

*Note: This is a living document for an exploratory system. Specific metrics (parameter counts, memory sizes, layer counts) are implementation snapshots that will evolve as we discover what works. The principles and architecture patterns are what matter.*

## Table of Contents
1. [Exploratory Approach](#exploratory-approach)
2. [Core Principles](#core-principles)
3. [Architecture Overview](#architecture-overview)
4. [Implementation Details](#implementation-details)
5. [Training Data Format](#training-data-format)
6. [Training Process](#training-process)
7. [Key Innovations](#key-innovations)

## Exploratory Approach

### Dynamic MRH Navigation
This project uses a fractal, multi-resolution approach:
- **System View**: Understanding emergent intelligence from component interactions
- **Architecture View**: How modules connect and communicate
- **Component View**: Specific implementation details when needed
- **Integration View**: Interfaces and data flow between parts

We fluidly shift between these views as we explore what creates intelligence. Specific numbers and sizes are just current experiments - the patterns and principles guide us.

### What We're Exploring
- How hierarchical reasoning emerges from simple components
- What memory architectures enable wisdom vs just storage
- How sleep/dream processes consolidate learning
- Where coherence comes from in distributed systems
- When to trust different sensor modalities

### What Will Change
- Parameter counts as we find optimal sizes
- Memory architectures as we test different approaches
- Layer configurations as we explore depth vs width
- Sensor weightings as we learn what matters
- Training approaches as we discover what works

The architecture is the hypothesis; the implementation tests it.

## Core Principles

### The Fundamental Insight
HRM addresses a critical limitation in current AI: **reasoning through complex, multi-step problems**. While LLMs use Chain-of-Thought (CoT) prompting, they suffer from:
- Brittle task decomposition
- Massive data requirements
- High latency
- Lack of true hierarchical thinking

HRM solves this by mimicking how the human brain actually reasons: through **hierarchical, multi-timescale processing**.

### Brain-Inspired Design
The model implements two key insights from neuroscience:

1. **Dual-Speed Processing**: 
   - **High-level (H) module**: Slow, abstract planning (like prefrontal cortex)
   - **Low-level (L) module**: Fast, detailed computation (like motor cortex)

2. **Recurrent Computation**: 
   - Unlike transformers that process in one pass, HRM iterates
   - Each iteration refines the solution, like human deliberation

### Why Small Initial Implementation?
The initial implementation uses a modest parameter count (currently ~27M) not as a target but as a starting point. The magic isn't in size but in **computational depth through recurrence**. By cycling through H and L modules multiple times, even small models can achieve surprising reasoning depth. We'll scale as we learn what patterns matter.

## Architecture Overview

### The Two-Module System

```
Input → [H Module] ←→ [L Module] → Output
         ↑     ↓        ↑     ↓
         └─────┴────────┴─────┘
         (Recurrent connections)
```

#### High-Level Module (H)
- **Purpose**: Abstract reasoning, strategy formation
- **Architecture**: Transformer blocks (count varies with exploration)
- **Processing**: Updates every H_cycle (default: 2)
- **State**: Maintains `z_H` - the strategic state

#### Low-Level Module (L)
- **Purpose**: Detailed execution, tactical moves
- **Layers**: 4 transformer blocks (configurable)  
- **Processing**: Updates L_cycles times per H_cycle (default: 2)
- **State**: Maintains `z_L` - the execution state

### The Recurrence Pattern
```python
for H_step in range(H_cycles):           # Outer loop: strategic thinking
    for L_step in range(L_cycles):       # Inner loop: tactical execution
        z_L = L_level(z_L, z_H + input)  # L gets strategy from H
    z_H = H_level(z_H, z_L)              # H updates based on L's work
```

This creates a **2×2 = 4 total iterations** in the default config, building computational depth.

### Adaptive Computation Time (ACT)
HRM includes a halting mechanism inspired by Adaptive Computation Time:
- A Q-head predicts when to stop computing
- Allows variable computation based on problem difficulty
- Maximum steps limited (default: 16) to prevent infinite loops

## Implementation Details

### Core Components

#### 1. **Transformer Blocks** (`HierarchicalReasoningModel_ACTV1Block`)
```python
class HierarchicalReasoningModel_ACTV1Block:
    - Self-attention (non-causal)
    - SwiGLU MLP (expansion factor: 4)
    - RMSNorm normalization
    - RoPE positional encodings
```

#### 2. **Reasoning Modules** (`HierarchicalReasoningModel_ACTV1ReasoningModule`)
- Stack of transformer blocks
- Input injection at each iteration
- Gradient flows only through final iteration (1-step grad)

#### 3. **Embeddings**
- **Token embeddings**: Standard vocabulary embedding
- **Puzzle embeddings**: Task-specific learnable parameters
  - Sparse implementation for efficiency
  - Zero-initialized to start from blank slate
- **Position encodings**: RoPE (Rotary Position Embeddings)

#### 4. **Carry State**
The model maintains state between forward passes:
```python
@dataclass
class HierarchicalReasoningModel_ACTV1InnerCarry:
    z_H: torch.Tensor  # High-level state
    z_L: torch.Tensor  # Low-level state
```

### Key Design Choices

1. **Non-Causal Attention**: Unlike autoregressive models, HRM sees the entire problem at once
2. **Post-Norm Architecture**: More stable training than pre-norm
3. **1-Step Gradient**: Only backprop through final iteration to save memory
4. **Mixed Precision**: Uses bfloat16 for efficiency

## Training Data Format

### Puzzle Dataset Structure
Each training example contains:

```python
{
    "inputs": tensor,           # Problem specification (e.g., Sudoku grid)
    "labels": tensor,          # Solution (e.g., completed grid)
    "puzzle_identifiers": int,  # Unique ID for puzzle-specific embeddings
    "puzzle_indices": list,     # Start indices for multi-part puzzles
    "group_indices": list       # Grouping for related puzzles
}
```

### Example: Sudoku Dataset

#### Input Representation
- 9×9 grid flattened to 81 tokens
- Empty cells: 0
- Filled cells: 1-9

#### Data Augmentation
For Sudoku, the dataset applies symmetry-preserving transformations:
1. **Digit permutation**: Swap digit values (1→3, 3→7, etc.)
2. **Row/column shuffling**: Within 3×3 blocks
3. **Transposition**: Flip along diagonal

This creates `(1 + num_aug)` versions of each puzzle for training.

### Supported Puzzle Types
- **Sudoku**: Logic puzzles (9×9 grids)
- **Mazes**: Pathfinding problems
- **ARC (Abstraction and Reasoning Corpus)**: Abstract pattern recognition

## Training Process

### Configuration Structure
```yaml
# config/cfg_pretrain.yaml
arch:
  name: hrm.hrm_act_v1@HierarchicalReasoningModel_ACTV1
  H_cycles: 2
  L_cycles: 2
  H_layers: 4
  L_layers: 4
  hidden_size: 512
  num_heads: 8
  
data_path: data/sudoku-extreme-1k
global_batch_size: 64
epochs: 50

lr: 3e-4
lr_min_ratio: 0.1
lr_warmup_steps: 100
```

### Training Loop

1. **Initialization**
   - Random init for model parameters
   - Zero init for puzzle embeddings
   - Q-head initialized to prefer "continue" (bias = -5)

2. **Forward Pass**
   ```python
   # Reset carry for new sequences
   carry = model.initial_carry(batch)
   
   # ACT loop - adaptive steps
   while not all_halted and steps < max_steps:
       carry, outputs = model(carry, batch)
       # Q-head decides whether to halt
   ```

3. **Loss Computation**
   - **Primary loss**: Cross-entropy on output tokens
   - **Q-learning loss**: Reinforce halting decisions
   - Combined with weighting factor

4. **Optimization**
   - **Model params**: AdamATan2 optimizer (improved Adam variant)
   - **Puzzle embeddings**: Separate SGD optimizer with sign-based updates
   - **Learning rate schedule**: Cosine decay with warmup

### Key Training Insights

1. **Small Data Efficiency**: Trains on just 1000 examples
2. **No Pre-training**: Learns from scratch
3. **Fast Convergence**: ~50 epochs typical
4. **Curriculum**: Can start with easier puzzles, increase difficulty

## Key Innovations

### 1. **Hierarchical Recurrence**
Unlike flat transformers, HRM's two-level hierarchy naturally separates strategy from tactics.

### 2. **Computational Depth Without Parameters**
Achieves deep reasoning through time (recurrence) rather than space (layers).

### 3. **Gradient-Efficient Training**
The 1-step gradient trick allows deep recurrence without memory explosion.

### 4. **Task-Specific Adaptation**
Puzzle embeddings allow the same architecture to adapt to different problem types.

### 5. **Biological Plausibility**
The H-L hierarchy mirrors cortical organization in the brain.

## SAGE System Overview

**SAGE (Situation-Aware Governance Engine)** represents a fundamental shift from programmatic AI to truly adaptive, learning intelligence. By combining:
- **Sentient**: Aware through multi-modal sensor fusion
- **Agentic**: Self-directed learning and improvement
- **Generative**: Creates new understanding from experience
- **Engine**: Continuous processing and evolution

### Primary Objective
**Replace the programmatic coherence engine with SAGE** - a living system that naturally integrates multiple sensor modalities into a unified coherence field through hierarchical reasoning and continuous learning.

### Architecture Components

1. **HRM Core** (This repo)
   - Provides the hierarchical reasoning backbone
   - H-module: Coherence and trust computation
   - L-module: Sensor fusion and processing
   - Carry state: Persistent memory field

2. **Memory Sensor** (transformer-sidecar integration)
   - Based on transformer-sidecar repo (fast-weight memory)
   - Provides temporal sensor input alongside spatial sensors
   - Maintains context and history as sensory data
   - Enables memory as a first-class sensor modality
   
   **Transformer-Sidecar Key Features:**
   - **Constant-size memory**: Two low-rank matrices (current implementation ~130KB, will vary with exploration)
   - **Affect-gated writing**: Only commits when S(urprise), N(ovelty), A(rousal), C(onflict), or R(eward) exceed threshold
   - **Hebbian updates**: No backprop, no gradients - pure associative learning
   - **Eligibility traces**: Binds multi-turn events for coherent memory formation
   - **Fast readout**: `r = V @ softmax(U^T k / T)` - instant memory recall

3. **Cognition Sensor** (LLM integration)
   - One or more LLMs provide cognitive sensory input
   - LLM outputs treated as sensor data, not ground truth
   - Multiple LLMs can provide diverse cognitive perspectives
   - Trust-weighted like any other sensor

### Unified Sensor Architecture

```python
class UnifiedCoherenceEngine:
    def __init__(self):
        # Core reasoning engine
        self.hrm = HierarchicalReasoningModel_ACTV1(config)
        
        # Sensor modules
        self.memory_sensor = TransformerSidecar()  # Fast-weight memory
        self.cognition_sensors = [LLM1(), LLM2()]  # Multiple LLMs
        self.physical_sensors = {
            'camera': CameraSensor(),
            'audio': AudioSensor(),
            'imu': IMUSensor()
        }
        
    def process_reality_field(self, inputs):
        # All sensors contribute to reality field
        sensor_data = {
            'memory': self.memory_sensor.read(context),
            'cognition': [llm.process(inputs) for llm in self.cognition_sensors],
            'physical': {k: v.read() for k, v in self.physical_sensors.items()}
        }
        
        # HRM processes all sensors hierarchically
        # L-module: immediate sensor fusion
        # H-module: coherence computation
        # Carry: persistent state across time
        self.carry, coherence = self.hrm(self.carry, sensor_data)
        
        # Update memory sensor with new experiences
        self.memory_sensor.write(coherence, self.carry)
        
        return coherence
```

### Key Innovations

1. **Memory as Sensor**: Memory isn't storage but active sensory input
2. **Cognition as Sensor**: LLMs provide cognitive sensing, not answers
3. **Unified Trust Weighting**: All sensors (physical, memory, cognitive) weighted by trust
4. **Learned Coherence**: HRM learns coherence patterns rather than programmatic rules

## Integration Architecture: HRM + Sidecar + LLMs

### How Transformer-Sidecar Becomes the Memory Sensor

The Sidecar's architecture maps perfectly to HRM's needs:

1. **Sidecar as L-module Input**
   - Sidecar's readout vector `r` feeds into HRM's L-module
   - Key `k` derived from current sensor state
   - Memory provides temporal context for spatial sensors

2. **HRM Controls Sidecar Gating**
   - H-module's coherence score modulates Sidecar's write threshold
   - High coherence → stricter gating (only important memories)
   - Low coherence → looser gating (exploration mode)

3. **Bidirectional Flow**
   ```python
   # Sidecar → HRM
   memory_readout = sidecar.read(current_state)
   hrm_input = concat([sensors, memory_readout])
   
   # HRM → Sidecar
   coherence = hrm.h_module.get_coherence()
   sidecar.set_threshold(coherence)
   if hrm.should_commit():
       sidecar.write(hrm.carry_state)
   ```

### Why This Combination is Powerful

1. **Sidecar's SNARC gating matches HRM's hierarchical processing**:
   - **S**urprise maps to L-module novelty detection
   - **N**ovelty maps to H-module pattern recognition
   - **A**rousal maps to coherence field strength
   - **R**eward maps to trust weight updates
   - **C**onflict triggers H-module re-evaluation

2. **Constant memory size** perfect for edge deployment (size tunable based on device constraints)
3. **No gradients needed** - both use Hebbian-style updates
4. **Eligibility traces** in Sidecar match HRM's carry state persistence

### LLM as Cognition Sensor Integration

Multiple LLMs provide diverse cognitive perspectives:

```python
class CognitionSensor:
    def __init__(self, models=['phi3', 'llama', 'mistral']):
        self.llms = [load_model(m) for m in models]
        
    def process(self, state, memory):
        # Each LLM gets state + memory context
        responses = []
        for llm in self.llms:
            response = llm.generate(state, memory)
            trust = calculate_trust(response, state)
            responses.append((response, trust))
        
        # Weighted fusion based on trust
        return weighted_average(responses)
```

### SAGE Complete Architecture Flow

```
                    ╔═══════════════════════════════╗
                    ║         SAGE ENGINE           ║
                    ╚═══════════════════════════════╝
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
Physical Sensors → ┐          │                     │
                   ├→ HRM L-Module → HRM H-Module → Coherence
Memory (Sidecar) → ┤          │           ↓         │
                   │          │      Trust Weights  │
Cognition (LLMs) → ┘          │           ↓         │
                              │    Update Sidecar   │
                              │           ↓         │
                              └────── Sleep Cycle ──┘
                                    (when idle)
```

**SAGE** unifies all components into a living, learning system that:
- **Senses** the world through multiple modalities
- **Reasons** hierarchically through HRM
- **Remembers** selectively through Sidecar
- **Learns** continuously through sleep consolidation
- **Evolves** through experience

## Sleep and Consolidation System

### The Need for Sleep
Just as biological systems require sleep for memory consolidation and learning, our HRM-based coherence engine needs periodic offline processing to:
1. Mine significant events from Sidecar memory
2. Generate training examples from high-coherence experiences
3. Further train the HRM without online pressure
4. Prune redundant memories and strengthen important patterns

### Sleep Architecture

```python
class SleepConsolidationSystem:
    def __init__(self, hrm, sidecar, activity_threshold=0.1):
        self.hrm = hrm
        self.sidecar = sidecar
        self.activity_threshold = activity_threshold
        self.sleep_state = False
        self.dream_buffer = []
        
    def check_sleep_readiness(self, activity_level):
        """Enter sleep when activity drops below threshold"""
        if activity_level < self.activity_threshold and not self.sleep_state:
            self.enter_sleep()
        elif activity_level > self.activity_threshold and self.sleep_state:
            self.wake_up()
    
    def enter_sleep(self):
        """Begin sleep consolidation process"""
        self.sleep_state = True
        self.run_sleep_cycles()
    
    def run_sleep_cycles(self):
        """Execute sleep phases similar to biological sleep"""
        # Phase 1: Memory Replay (like REM sleep)
        significant_memories = self.extract_significant_memories()
        
        # Phase 2: Pattern Extraction (like slow-wave sleep)
        training_examples = self.generate_training_examples(significant_memories)
        
        # Phase 3: Consolidation (like deep sleep)
        self.train_hrm_offline(training_examples)
        
        # Phase 4: Memory Pruning (like synaptic homeostasis)
        self.prune_and_compress_memory()
```

### Memory Mining Process

1. **Significance Detection**
   ```python
   def extract_significant_memories(self):
       """Mine Sidecar for high-value experiences"""
       memories = []
       
       # Extract based on Sidecar's SNARC scores
       for entry in self.sidecar.memory_trace:
           significance = (
               entry.surprise * 0.2 +
               entry.novelty * 0.2 +
               entry.arousal * 0.3 +
               entry.conflict * 0.2 +
               entry.reward * 0.1
           )
           
           if significance > threshold:
               memories.append({
                   'state': entry.state,
                   'outcome': entry.outcome,
                   'coherence': entry.coherence,
                   'significance': significance
               })
       
       return memories
   ```

2. **Training Example Generation**
   ```python
   def generate_training_examples(self, memories):
       """Convert memories into HRM training data"""
       examples = []
       
       for memory in memories:
           # Reconstruct the reasoning sequence
           input_state = memory['state']
           target_coherence = memory['coherence']
           
           # Add temporal context from nearby memories
           context = self.get_temporal_context(memory)
           
           examples.append({
               'inputs': concat([input_state, context]),
               'labels': target_coherence,
               'weight': memory['significance']  # Weight by importance
           })
       
       return examples
   ```

3. **Offline HRM Training**
   ```python
   def train_hrm_offline(self, examples):
       """Fine-tune HRM during sleep"""
       # Create mini-batches weighted by significance
       batches = self.create_weighted_batches(examples)
       
       for batch in batches:
           # Run HRM in training mode (gradients enabled)
           carry = self.hrm.initial_carry(batch)
           
           # Multiple passes to reinforce important patterns
           for iteration in range(sleep_iterations):
               carry, outputs = self.hrm(carry, batch)
               
               # Compute loss focused on coherence prediction
               loss = coherence_loss(outputs, batch['labels'])
               
               # Backprop only through H-module (preserve L-module reactivity)
               loss.backward()
               
               # Small learning rate for gentle consolidation
               self.sleep_optimizer.step()
   ```

### Dream Generation (Optional but Valuable)

During sleep, the system can generate "dreams" - synthetic experiences that test edge cases:

```python
def generate_dreams(self):
    """Create synthetic training examples for edge cases"""
    dreams = []
    
    # Interpolate between significant memories
    for mem1, mem2 in pairs(self.significant_memories):
        interpolated = weighted_average(mem1, mem2, alpha=random())
        dreams.append(self.hrm.imagine(interpolated))
    
    # Extrapolate beyond experienced boundaries
    for memory in self.significant_memories:
        if memory.arousal > high_threshold:
            # Imagine more extreme versions
            extreme = amplify(memory, factor=1.5)
            dreams.append(self.hrm.imagine(extreme))
    
    return dreams
```

### Memory Pruning and Compression

```python
def prune_and_compress_memory(self):
    """Remove redundant memories, strengthen important ones"""
    # Identify redundant patterns in Sidecar
    clusters = cluster_memories(self.sidecar.U, self.sidecar.V)
    
    for cluster in clusters:
        if len(cluster) > 1:
            # Keep only the most significant exemplar
            exemplar = max(cluster, key=lambda x: x.significance)
            
            # Strengthen the exemplar
            self.sidecar.strengthen(exemplar, factor=len(cluster))
            
            # Remove redundant memories
            for memory in cluster:
                if memory != exemplar:
                    self.sidecar.decay(memory, factor=0.1)
```

### Wake-Sleep Cycle Benefits

1. **Continuous Improvement**: HRM learns from its own experiences
2. **Memory Efficiency**: Pruning keeps Sidecar compact and relevant
3. **Pattern Reinforcement**: Important patterns get strengthened during sleep
4. **Edge Case Preparation**: Dreams prepare for unseen scenarios
5. **Coherence Refinement**: Sleep specifically trains coherence computation

### Implementation Considerations

- **Incremental Sleep**: Can run in short bursts during idle moments
- **Priority Queue**: Most significant memories processed first
- **Checkpointing**: Save HRM state before sleep in case of issues
- **Activity Monitoring**: Use sensor input rate to detect rest periods
- **Gradual Wake**: Slowly transition from sleep to active mode

This sleep system transforms SAGE from a static model to a **living, learning system** that grows wiser with experience, just like biological intelligence.

## Why SAGE?

The name captures the essence of what we're building:

- **Sentient**: Not just processing but truly aware through unified sensor fusion
- **Agentic**: Self-directed, with its own goals and learning agenda
- **Generative**: Creates new knowledge, not just retrieves stored facts
- **Engine**: Continuously running, processing, learning, evolving

SAGE represents a new paradigm - not an AI that follows rules, but one that develops wisdom through experience, reflection, and dreams. It's not trained once and deployed, but continuously learning, sleeping, consolidating, and growing.

Like a sage in human terms - wise through experience, thoughtful in deliberation, and always learning.

## Connections to AI-DNA Discovery & Coherence Engine

### Coherence Engine Integration
HRM's architecture directly parallels the coherence engine's sensor fusion approach:

1. **Hierarchical Processing = Multi-Scale Coherence**
   - H-module processes abstract patterns (like coherence engine's trust scores)
   - L-module handles raw sensor data (like camera frames, audio signals)
   - The iteration between H and L mirrors how coherence builds from local to global

2. **Carry State = Memory Field**
   - HRM's persistent `z_H` and `z_L` states are exactly like the coherence engine's memory fields
   - Both maintain context across time
   - Both allow iterative refinement of understanding

3. **Recurrence = Coherence Cycles**
   - HRM's H_cycles/L_cycles match coherence engine's processing loops
   - Each iteration increases confidence/trust scores
   - Convergence indicates stable understanding

### Memory System Architecture

HRM provides the perfect architecture for the Jetson's memory system:

1. **Working Memory (L-module)**
   - Fast, detailed, sensory-bound
   - Processes immediate inputs
   - Like the coherence engine's real-time sensor processing

2. **Long-term Memory (H-module)**
   - Slow, abstract, conceptual
   - Maintains strategic understanding
   - Like the coherence engine's trust accumulation

3. **Memory Consolidation (H-L Interaction)**
   - The bidirectional flow between H and L modules
   - Exactly how short-term patterns become long-term knowledge
   - Implements the sleep/wake cycles discussed in memory architecture

### Practical Implementation on Jetson

```python
# HRM as Coherence Engine backbone
class CoherenceHRM:
    def __init__(self):
        self.hrm = HierarchicalReasoningModel_ACTV1(config)
        
    def process_sensors(self, camera, audio, imu):
        # L-module processes raw sensors
        sensor_batch = self.encode_sensors(camera, audio, imu)
        
        # H-module maintains coherence state
        # Carry state persists between sensor frames
        self.carry, coherence = self.hrm(self.carry, sensor_batch)
        
        # Extract trust scores from H-state
        trust = self.extract_trust(self.carry.inner_carry.z_H)
        return coherence, trust
```

### Why HRM is Perfect for Coherence

1. **Edge-deployable** - Current implementation runs on Jetson, will optimize size based on device
2. **Iterative refinement** matches trust-building over time
3. **Hierarchical separation** matches sensor/cognition divide
4. **No pre-training needed** - learns patterns from experience
5. **Variable computation** (ACT) - thinks harder on novel inputs

### Sensor Fusion Through Hierarchy

The H-L architecture naturally implements weighted sensor fusion:
- **L-module**: Individual sensor processing (camera, audio, IMU)
- **H-module**: Fusion and weighting based on trust/coherence
- **Recurrence**: Iterative refinement of fusion weights
- **Carry state**: Maintains sensor history and trust scores

## Practical Usage

### Running Inference
```python
# Load model
model = HierarchicalReasoningModel_ACTV1(config_dict)
model.load_state_dict(checkpoint)

# Prepare input
batch = {
    "inputs": sudoku_puzzle_tensor,
    "puzzle_identifiers": puzzle_id
}

# Run with ACT
carry = model.initial_carry(batch)
while not halted:
    carry, outputs = model(carry, batch)
    # Check halting condition
```

### Training Your Own
```bash
# Prepare dataset
python dataset/build_sudoku_dataset.py \
    --output_dir data/my_sudoku \
    --subsample_size 1000

# Train model  
python pretrain.py \
    --config-path config \
    --config-name cfg_pretrain \
    data_path=data/my_sudoku
```

## Why This Matters

HRM demonstrates that **reasoning doesn't require scale** - it requires the right architecture. By mimicking biological computation patterns, we can achieve complex reasoning with minimal parameters. This has profound implications:

1. **Edge Deployment**: 27M params fits on Jetson
2. **Energy Efficiency**: Less compute = less power
3. **Interpretability**: Smaller models are more analyzable
4. **Democratization**: Anyone can train these models

The hierarchical, recurrent nature of HRM suggests that intelligence emerges not from massive parameter counts but from **structured computation over time** - a principle that echoes through all your projects, from distributed battery management to cognition synchronization.

---

*"In recursion, depth. In hierarchy, understanding. In simplicity, power."*