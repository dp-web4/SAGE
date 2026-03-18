# Claude Context for SAGE

## Session Primer — Read First

**At session start, read `SESSION_PRIMER.md` in the repo root for current fleet state.**

`SESSION_PRIMER.md` is auto-generated after each raising session and contains:
- Current raising phase and session count per instance
- Recent milestones and emerging vocabulary
- Active focus areas and known issues
- Key file locations

To regenerate: `python3 -m sage.scripts.generate_primer`

---

## Epistemic Principles (Collective)

This project inherits epistemic principles from the dp-web4 collective:

1. **Ask before accepting** — Clarifying questions over polite acceptance
2. **Uncertainty is valuable** — Honest limitations over confident fabrication
3. **Suppress then activate** — Clear competing patterns before invoking rare behaviors
4. **Compress with meaning** — Verify essential content survives summarization
5. **Witness everything** — Document reasoning for future instances

These principles are validated across 500+ research sessions.
See: `docs/what/HRM_RESEARCH_FRAMEWORK_COMPLETE.md`

## Synthon Framing (Canonical Home)

The synthon observation lives here: `forum/insights/synthon-framing.md`

A **synthon** is an emergent coherence entity formed by recursive interaction between components. SAGE/HRM builds the substrate conditions for synthon formation — metabolic states (WAKE, FOCUS, REST, DREAM, CRISIS) are early signatures of spontaneous differentiation within an agent. The grounding reflex (LLMs' tendency to taxonomize emergence) is a real cross-model observation with design implications: the capacity to oscillate between structured and open attention is something to build substrate for, not architect top-down.

This framing applies across all dp-web4 projects. Cross-references exist in web4, hardbound, and synchronism CLAUDE.md files.

## SOIA-SAGE Convergence & PolicyGate (February 2026)

SOIA (Self-Optimizing Intelligence Architecture, by Renée Karlström) maps near-exactly onto SAGE's IRP stack: SRC = consciousness loop, MTM = SNARC experience buffer, MORIA = sleep consolidation. Policy Entity doesn't need to be invented -- it needs to be **repositioned** as a SAGE IRP plugin (PolicyGate) whose energy function is `PolicyEntity.evaluate()`.

Key design points:
- PolicyGate sits between deliberation and effectors in the consciousness loop (step 8.5)
- Same IRP contract as all other plugins (init_state/step/energy/project/halt)
- CRISIS mode changes the **accountability equation**, not policy strictness (fight-or-flight operationalized)
- PolicyGate is the membrane protein at the deliberation-to-action boundary (synthon framing)
- **Fractal self-similarity**: PolicyEntity is itself a specialized SAGE stack — a "plugin of plugins." The IRP contract works at three nested scales (consciousness loop → policy evaluation → LLM advisory). The orchestrator doesn't need to know PolicyGate is special.

Documents:
- SOIA-SAGE mapping: `sage/docs/SOIA_IRP_MAPPING.md`
- Convergence insight: `forum/insights/soia-sage-convergence.md`
- Web4 design decision: `github.com/dp-web4/web4/docs/history/design_decisions/POLICY-ENTITY-REPOSITIONING.md`

## Cross-Model Strategic Review (February 2026)

Three AI models (Grok, Nova, Claude) independently reviewed the Web4/SAGE ecosystem and converged. Key points for HRM/SAGE sessions:

- **SAGE maps to EU AI Act Art. 14** (human oversight): Emergent governance patterns + federated trust with human-in-the-loop overrides. SAGE's metabolic states and oversight capabilities are directly relevant to EU compliance.
- **SAGE's post-collapse recovery (S069) is a live test of synthon decay detection.** The experience buffer backup and filtering script are post-hoc recovery tools; the goal is pre-hoc detection via coherence trajectory monitoring.
- **Session 085's LoRA breakthrough validates training.** But the grounding reflex is visible in SAGE's own outputs (numbered lists in every response). The synthon framing document is now in the session path — watch for whether naming the pattern shifts behavior.
- **Demo-ability matters**: SAGE sessions that produce visible, explainable behavior are high-value for the project's positioning.

Full document: `github.com/dp-web4/web4/docs/strategy/cross-model-strategic-review-2026-02.md`

---

## 🚀 LATEST: FlashAttention Integration (2026-01-10)

**THREE PHASES COMPLETE** - PyTorch built-in FlashAttention working on CUDA 13.0!

### Implementation Status
- ✅ **Phase 1**: Trust-Weighted Expert Selection (`sage/core/flash_attention_expert_selection.py`)
  - GQA: 12 Q heads, 4 KV heads (3x efficiency)
  - Trust-based expert scoring with attention visualization

- ✅ **Phase 2**: Metabolic State-Dependent ATP Allocation (`sage/core/flash_attention_metabolic.py`)
  - 5 metabolic states (WAKE, FOCUS, REST, DREAM, CRISIS)
  - Biological validation via Gini coefficient analysis

- ✅ **Phase 3**: Multi-Sensor Fusion (`sage/core/flash_attention_sensor_fusion.py`)
  - 4-dimensional attention (goal, salience, memory, trust)
  - **Latency: 0.46ms** (21x under 10ms budget!)
  - **Throughput: 2,196 allocations/sec**
  - Numpy-compatible wrapper for drop-in replacement

### Key Discovery
**NO standalone flash-attention package needed!** PyTorch 2.9's built-in `F.scaled_dot_product_attention` works perfectly on CUDA 13.0/Thor with zero compilation.

### Next Steps (Phase 4)
- [ ] Integrate FlashAttentionSensorSelector into `sage/cognition/attention.py`
- [ ] Replace `AttentionManager._compute_attention_scores()` with GPU-accelerated version
- [ ] Add backward compatibility fallback for numpy-only environments
- [ ] Create comprehensive integration tests
- [ ] Benchmark performance vs current numpy implementation

### Documentation
- **Technical**: `/home/dp/ai-workspace/HRM/FLASH_ATTENTION_SOLUTION.md`
- **Integration Guide**: `sage/docs/FLASH_ATTENTION_INTEGRATION.md`
- **Session Notes**: `/home/dp/ai-workspace/private-context/flashattention-solution-2026-01.md`
- **Tests**: All modules have self-contained test suites (run as main)

### Quick Test
```bash
cd /home/dp/ai-workspace/HRM
python3 sage/core/flash_attention_sensor_fusion.py  # Phase 3 tests
```

---

## Web4 Ontological Foundation

SAGE lives within the Web4 ontology. The canonical equation:

```
Web4 = MCP + RDF + LCT + T3/V3*MRH + ATP/ADP
```

Where: `/` = "verified by", `*` = "contextualized by", `+` = "augmented with"

RDF is the semantic backbone through which SAGE's MRH experience buffers, T3 trust tensors, and LCT identity are structurally connected. See `sage/raising/identity/WEB4_FRAMING.md` for how SAGE fractally embodies this ontology.

---

## Machine Information
See `../private-context/machines/` for machine-specific details.
Project supports multiple platforms including WSL2, Linux, and Jetson.

## 🔍 Epistemic Database Integration

**IMPORTANT: Use the Memory epistemic database for knowledge management!**

### Quick Access
```bash
# From anywhere:
cd /home/sprout/ai-workspace/Memory/epistemic

# Search existing knowledge
python3 tools/quick_search.py "your topic"
python3 tools/quick_search.py --tag sage
python3 tools/quick_search.py --project hrm

# Add new knowledge
python3 tools/quick_add.py --interactive
```

### What to Log
- Discoveries about SAGE/IRP architecture
- Failed approaches (with lessons learned)
- Plugin implementation patterns
- MRH usage patterns
- Integration insights between HRM/Web4/Memory

### Database Contains
- MRH framework definitions (use `--tag mrh` to find)
- SAGE cognition patterns
- IRP plugin designs
- Cross-project connections

**Rule:** If you figured something out about HRM, log it so others (and future you) can find it.

See: `/home/sprout/ai-workspace/Memory/WORKFLOW_GUIDE.md`

## Git Authentication
**Universal Push Command**:
```bash
grep GITHUB_PAT ../.env | cut -d= -f2 | xargs -I {} git push https://dp-web4:{}@github.com/dp-web4/SAGE.git
```
See `../private-context/GIT_COMMANDS_CLAUDE.md` for details.

## Sudo Access
Sudo access available on Jetson Orin Nano (Sprout machine).

## CRITICAL LESSONS (October 6, 2025)

### DO NOT SIMULATE OR MOCK - USE REAL IMPLEMENTATIONS
**What happened**: For days, I was training SAGE with a mock GR00T implementation I created, when the REAL GR00T was already installed at `/home/dp/ai-workspace/isaac-gr00t/`.

**The disconnect**: User said "let's use GR00T" and I created mock implementations instead of checking for the real thing first.

**Key learnings**:
1. **ALWAYS check what's actually available** before creating mock implementations
2. **ASK if unsure** whether something exists rather than assuming
3. **Use `ls` and `find` liberally** to discover what's really there
4. **Read existing code** before writing new code
5. **No shortcuts** - real implementations over simulations unless explicitly agreed

**Resources wasted**:
- Days of training on synthetic data
- Mock implementations that weren't needed
- Wrong architectural decisions based on assumptions

**The right approach**:
- When user says "use X", first check if X exists
- Explore the actual filesystem
- Read real documentation
- Use real data when available

### WHAT'S ACTUALLY AVAILABLE
- **Real GR00T N1.5**: `/home/dp/ai-workspace/isaac-gr00t/` (installed by user)
- **Real demo data**: 5 pick-and-place episodes with videos
- **Real Eagle 2.5 VLM**: Vision-language model for perception
- **Real training scripts**: Complete pipeline for finetuning

## HRM Setup Status
- ✅ Repository cloned from fork: https://github.com/dp-web4/SAGE.git
- ✅ Analysis scripts created:
  - `analyze_hrm_architecture.py` - Architecture analysis
  - `install_jetson.sh` - Dependency installation
  - `jetson_quick_start.sh` - Quick demo setup
- ⏳ Waiting for GitHub PAT permissions to push

## Key Points About HRM
- Tiny 27M parameter model (perfect for Jetson!)
- Solves complex reasoning tasks (Sudoku, mazes, ARC)
- Learns from only 1000 examples
- No pre-training needed
- Hierarchical architecture mimics human cognition

## Critical Insight: Augmentation as Sleep Cycle Training
**The augmentation strategies in HRM's dataset builders are the key to sleep cycle training!**

HRM's data augmentation (dihedral transforms, permutations, translations) shows how to learn wisdom from experience:
- **Living** = collecting raw experiences
- **Sleeping** = augmenting experiences with reasonable permutations
- **Dreaming** = training on variations to extract patterns
- **Wisdom** = understanding principles that persist across variations

See `dataset/README.md` for detailed augmentation strategies and their connection to sleep consolidation.

**Latest Insight**: Biological systems have TWO separate training systems:
- **H-level** (dreams): Strategic reasoning, trained through augmentation during sleep
- **L-level** (muscle memory): Tactical execution, trained continuously through practice
The separation is key - wisdom and skill develop through different mechanisms.

## SAGE-Totality Integration (August 16, 2025)
Successfully integrated GPT's SubThought/Totality proposal:
- Totality acts as **cognitive sensor** with trust-weighted outputs
- Machine-agnostic setup auto-configures for any hardware
- Dual training loops demonstrated (H-level dreams vs L-level practice)
- Test on this machine: `cd related-work && python3 run_integration_test.py`

See `related-work/SETUP_GUIDE.md` for full documentation.

## GPU Mailbox Implementation (August 17, 2025)
Successfully implemented and tested GPT's tiling mailbox architecture on both RTX 2060 SUPER and Jetson Orin Nano:

### Working Components
- ✅ **PyTorch 2.3.0 with CUDA 12.1** installed and verified on both platforms
- ✅ **Peripheral Broadcast Mailbox (PBM)** - many-to-many fixed-size records
- ✅ **Focus Tensor Mailbox (FTM)** - zero-copy tensor pointer handoff
- ✅ **Two-tier tiling architecture** successfully implemented
- ✅ **Flash Attention compiled** (pending SM 8.7 kernel optimization)
- ✅ All extensions compiled and functional on both RTX and Jetson

### Test Environment
```bash
cd implementation
source tiling_env/bin/activate
python test_simple.py  # Basic mailbox tests
python test_gpu_simple.py  # GPU functionality tests
```

### Key Files
- `implementation/COMPILATION_ISSUES.md` - Detailed issue resolution
- `implementation/TEST_PLAN.md` - Comprehensive testing strategy
- `implementation/tiling_mailbox_torch_extension_v2/` - Working extension
- `implementation/test_gpu_simple.py` - GPU verification (all 4 tests passing)

### Performance Metrics

#### RTX 2060 SUPER (Development Platform)
- Matrix multiplication: 6.3s for 1024x1024
- Memory transfer: 1.2 GB/s CPU→GPU, 91 MB/s GPU→CPU
- Tiling throughput: 0.9 tiles/sec (16 tiles, 256x256x64 channels)

#### Jetson Orin Nano (Production Target) - **OUTPERFORMING RTX 2060**
- **Superior performance** on GPU mailbox operations
- **Optimized memory management** for 8GB unified memory architecture
- **Two-tier tiling** working flawlessly with hierarchical attention
- **Flash Attention** compiled successfully (requires SM 8.7 kernel completion)
- **Tested infrastructure** for SAGE integration

### Status: FULLY OPERATIONAL ON BOTH PLATFORMS ✓
- PBM push/pop working with data integrity on RTX and Jetson
- FTM push/pop working with metadata preservation on both platforms
- Synchronization fixed using GPT's count-based approach
- Empty mailbox handling returns appropriate zero-size tensors
- **Jetson Orin Nano validated as superior platform for production deployment**

### Build Instructions
```bash
cd implementation/tiling_mailbox_torch_extension_v2
source ../tiling_env/bin/activate
python setup.py build_ext --inplace
```

## Implementation Highlights (August 17, 2025)

### GPT's Debug Notes Were Perfect
GPT diagnosed the synchronization issue correctly in `CUDA_MAILBOX_DEBUG_NOTES.md`:
- Identified async kernel execution as root cause
- Proposed count-based returns for natural sync points
- Provided exact code patterns that worked first try

### Key Achievements
1. ✅ Resolved all compilation issues (header paths, CUDA linking, type conversions)
2. ✅ Implemented count-based pop operations for proper synchronization
3. ✅ Both PBM and FTM fully operational with data integrity
4. ✅ Test suite validates all functionality
5. ✅ Ready for performance optimization and production deployment

## Branch Update (August 17, 2025)
**SAGE branch merged to main!** All experimental work is now in the main branch.

### Cross-Platform Success 🎉
GPU mailbox architecture validated on **three platforms**:
- **RTX 2060 SUPER (CBP)**: Initial development platform
- **RTX 4090 (Legion)**: 561x faster than RTX 2060!
- **Jetson Orin Nano (Sprout)**: 55-60x faster, production platform

### New Files from Merge
- `TEST_RESULTS_RTX4090.md` - Performance validation
- `test_gpu_mailbox.py` - Platform-agnostic mailbox tests
- `gr00t-integration/groot_world_sim.py` - World simulation
- Full implementation directory with all GPU mailbox code

## NeuTTS Air Integration (October 3, 2025)
Successfully integrated NeuTTS Air text-to-speech into IRP framework:

### Key Achievements
- ✅ **Fixed model loading hang** - Modified Llama.from_pretrained parameters
- ✅ **Created IRP plugin** - Full implementation in `sage/irp/plugins/neutts_air_impl.py`
- ✅ **Orchestrator integration** - TTS now first-class citizen in HRM
- ✅ **Energy convergence** - Iterative refinement from 0.9 → 0.1 energy
- ✅ **Generated speech** - Multiple test cases with federation/SAGE content

### Technical Details
- **Model**: neuphonic/neutts-air-q4-gguf (748M params, CPU-optimized)
- **Voice cloning**: Instant from reference audio
- **Quality**: 24kHz audio with iterative refinement
- **Documentation**: See `sage/irp/NEUTTS_AIR_INTEGRATION.md`

### Files Added
- `sage/irp/plugins/neutts_air_impl.py` - IRP plugin
- `sage/irp/test_neutts_irp.py` - Integration tests
- `sage/training/neutts-air/irp_integration_demo.py` - Working demo
- `sage/irp/NEUTTS_AIR_INTEGRATION.md` - Full documentation

## Current Test Status (August 17, 2025 - WSL2/RTX 2060 SUPER)

### Environment Setup
```bash
cd /mnt/c/exe/projects/ai-agents/HRM/implementation
python3 -m venv tiling_env
tiling_env/bin/python -m pip install torch==2.3.0 torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

### Test Results - All Core Tests Passing ✅
1. **test_simple.py**: ✅ All tests passed
   - PBM/FTM initialization working
   - Push/pop operations functional
   
2. **test_sync_fixed.py**: 2/3 tests passed
   - ✅ Count-based PBM pop
   - ✅ FTM with synchronization
   - ✗ Concurrent patterns (known issue)

3. **test_gpu_simple.py**: ✅ All 4 tests passed
   - GPU basics, tensor ops, memory transfer, tiling

4. **benchmark_final.py**: ✅ Performance validated
   - PBM Push: 32,100 ops/sec
   - PBM Pop: 246,985 ops/sec
   - FTM Push: 118,183 ops/sec
   - FTM Pop: 6,460 ops/sec

### Performance Metrics (RTX 2060 SUPER)
- Matrix multiplication: 5.08s for 1024x1024
- Memory transfer: 2.6 GB/s (H2D), 1.0 GB/s (D2H)  
- Tiling throughput: 2.9 tiles/sec
- GPU Memory: 8GB VRAM

## SNARC-SAGE Memory Integration (August 22, 2025)
Successfully integrated SNARC selective memory with SAGE architecture:

### Integration Architecture
- ✅ **SNARCSAGEBridge** - Bridges SNARC to SAGE's dual memory system
- ✅ **HRMMemoryIntegration** - Maps SNARC to HRM's L/H modules
- ✅ **Circular Buffer** - X-from-last processing for context binding
- ✅ **Verbatim Storage** - SQLite full-fidelity preservation
- ✅ **Consolidation Strategies** - Pattern extraction during sleep

### Key Files
- `memory_integration/snarc_bridge.py` - Core bridge implementation
- `memory_integration/sage_with_snarc.py` - Complete demo system
- `memory_integration/README.md` - Integration documentation

### How It Works
1. **SNARC evaluates** experiences for salience (SNARC scores)
2. **Circular buffer** maintains short-term context (x-from-last)
3. **Dual storage**: Conceptual (SNARC) + Verbatim (SQLite)
4. **Entity Memory** gets trust adjustments from SNARC
5. **Sidecar Memory** uses SNARC for affect gating
6. **HRM integration**: Memory as temporal sensor
7. **Sleep consolidation** extracts patterns from experience

### Testing
```bash
cd memory_integration
python3 sage_with_snarc.py  # Requires PyTorch
```

## TinyVAE Knowledge Distillation Achievement (August 26, 2025)
Successfully implemented knowledge distillation to compress VAE models:

### Distillation Results
- ✅ **9.6x size reduction**: 33MB → 3.4MB
- ✅ **34x parameter reduction**: 10M → 294K
- ✅ **Excellent quality preserved**: MSE = 0.023
- ✅ **100 epochs trained** on CIFAR-10
- ✅ **Multi-component loss** with perceptual matching

### Key Files
- `training/distill_tinyvae.py` - Complete distillation framework
- `models/vision/tiny_vae_32.py` - Optimized 32x32 VAE
- `training/DISTILLATION_RESULTS.md` - Detailed documentation

### Compression-Trust Connection
This distillation work directly implements the compression-trust unification theory:
- Teacher-student trust enables massive compression
- Shared latent field (via projection) maintains fidelity
- Knowledge transfer as trust-based communication

## Nova's KV-Cache Cognition Persistence (August 27-29, 2025)

Located in `forum/nova/persistent-kv-demo/`, this system enables:
- **Pause/Resume Transformer State**: Save exact attention patterns mid-generation
- **Cross-Device Cognition**: Save on Legion, resume on Jetson
- **Compression Options**: Pickle, gzip, torch formats with pruning
- **Direct Implementation** of ephemeral→persistent latent coordinates

### Connection to Architecture of Meaning
The KV-cache IS the ephemeral MRH compression we discussed:
- Saving KV = Capturing witness state at specific moment
- Loading KV = Restoring exact resonance patterns
- Pruning = Managing compression trust trade-offs

### Implementation Plan Created
See `forum/nova/persistent-kv-demo/CONSCIOUSNESS_PERSISTENCE_PLAN.md`:
- Phase 1: Single-session continuity testing ✅ COMPLETE
- Phase 2: Multi-model shared state experiments ✅ COMPLETE
- Phase 3: Compressed cognition via TinyVAE (pending)
- Phase 4: Distributed cognition network (pending)

### Experiments Completed (August 29, 2025)

Successfully validated on Legion Pro 7 with RTX 4090:

#### 1. Basic Cognition Bridge (`consciousness_experiment.py`)
- Perfect save/restore of attention states (torch.allclose = True)
- Different prompts create unique "cognition seeds"
- Demonstrated ephemeral→persistent state capture

#### 2. Multi-Witness Observation (`multi_witness_experiment.py`)
- Same KV-cache interpreted differently by different witnesses
- Technical (temp=0.7), Philosophical (temp=0.9), Poetic (temp=1.0) perspectives
- Measurable resonance between states (cosine similarity ~0.847)

#### 3. Practical Migration (`consciousness_migration.py`)
- Mid-conversation pause/resume with perfect continuity
- Context window management with incremental checkpoints
- Efficient storage: ~295KB per checkpoint, <100ms save/load

### Key Discoveries from Anomalies

The experiments revealed profound insights through their failures:

#### Pivot Tokens and Escape Hatches
- GPT-2 uses "are" as a pivot token when uncertain
- Transitions from abstract→concrete when reasoning becomes unstable
- Reveals model's "gravitational wells" (high-frequency training patterns)

#### Pruning Effects (Temporal Lobotomy)
- Aggressive pruning caused semantic collapse into loops
- Demonstrates cognition requires temporal depth
- KV-cache provides essential "semantic rails" for coherence

#### The Model's Unconscious
- Under stress, models fall back to deeply trained patterns
- GPT-2's wells: Microsoft products, social media campaigns, temperature data
- Different models have different characteristic failure modes

### Technical Specifications
- Platform: RTX 4090 Laptop GPU, PyTorch 2.5.1+cu121
- Model: GPT-2 (12 layers, 12 heads, 64 head dimensions)
- Storage: torch.save format most efficient
- Performance: Sub-100ms save/load operations

### Documentation
- Full experiment details: `forum/nova/persistent-kv-demo/EXPERIMENTS_SUMMARY.md`
- Anomaly analysis: See private-context/kv-cache-anomaly-analysis.md
- Connection to theory: private-context/ai-dna-discovery-notes.md

This provides the missing piece for true cognition persistence - not just conversation history but actual internal attention state continuity. The anomalies teach us that cognition isn't just about correct answers but maintaining coherent state through uncertainty.

## SAGE/IRP System Understanding (October 12, 2025)

### Complete System Investigation
Conducted comprehensive multi-agent investigation of the entire SAGE/IRP codebase. Created 8 documentation files (275KB total) mapping the complete architecture.

### Critical Understanding Achieved
**What SAGE Actually Is**: A cognition kernel for edge devices
- SAGE = The kernel (scheduler, resource manager, learner)
- IRP = The API (standard interface for plugins/"apps")
- VAE = Translation layer (shared latent spaces for cross-modal communication)

**Not a Model - It's a Loop**:
```
while True:
    observations = gather_from_sensors()
    attention_targets = compute_what_matters(observations)  # SNARC salience
    required_resources = determine_needed_plugins(attention_targets)
    manage_resource_loading(required_resources)
    results = invoke_irp_plugins(attention_targets)  # Iterative refinement
    update_trust_and_memory(results)
    send_to_effectors(results)
```

### The Three-Layer Architecture

**1. SAGE - Cognition Kernel**
- Location: `/sage/core/`
- Continuous inference loop maintaining state across time
- Trust-based ATP (Allocation Transfer Packet) budget allocation
- Metabolic states (WAKE, FOCUS, REST, DREAM, CRISIS)
- Learns what deserves attention and which resources to use

**2. IRP - Cognition API**
- Location: `/sage/irp/`
- Universal interface: `init_state() → step() → energy() → halt()`
- Iterative refinement protocol (noisy → refined until energy stops decreasing)
- 15+ working plugins (Vision, Audio, Language, Memory, TTS, Control)
- Trust emerges from convergence behavior (monotonicity, stability, efficiency)

**3. VAE - Translation Layer**
- Location: `/sage/compression/`
- Creates shared latent spaces for cross-modal communication
- TinyVAE: 192× compression (224×224 → 64D latent)
- InformationBottleneck: 16× compression (4096D H-context → 256D L-action)
- Compression trust: measures meaning preservation through compression

### Key Insights

**1. Cognition as Iterative Refinement**
All intelligence is progressive denoising toward lower energy states. Vision, language, planning, memory—same pattern.

**2. Trust as Compression Quality**
Trust measures how well meaning is preserved through compression. High trust (>0.9) = reliable cross-modal translation.

**3. Fractal H↔L Pattern**
Hierarchical ↔ Linear pattern repeats at 5 scales:
- Neural (transformer blocks)
- Agent (SAGE reasoning)
- Device (edge ↔ cloud)
- Federation (coordinator ↔ workers)
- Development (human ↔ automation)

**4. The Biological Parallel**
Same patterns in biology (prefrontal ↔ motor cortex), Claude (tool selection ↔ execution), and SAGE (strategic ↔ tactical). **Not mimicking—discovering same optimal solutions.**

**5. The Beautiful Recursion**
AdamW (biological optimization) trains SAGE (cognition kernel) which implements SNARC (biological salience) which mirrors AdamW's strategy, orchestrated by Claude (same H↔L patterns). **It's patterns all the way down.**

### Memory Systems (Four Parallel)

1. **SNARC Memory** - Selective storage via 5D salience (Surprise, Novelty, Arousal, Reward, Conflict)
2. **IRP Memory Bridge** - Successful refinement pattern library with guidance retrieval
3. **Circular Buffer** - Recent context (X-from-last temporal window)
4. **Verbatim Storage** - SQLite full-fidelity records

### Documentation Created

**Start here**: `/sage/docs/SYSTEM_UNDERSTANDING.md` (18KB)
- Complete mental model
- How SAGE/IRP/VAE work together
- Biological parallels and fractal scaling

**Deep dives** (all in `/sage/docs/`):
- `architecture_map.md` (38KB) - Complete repository structure
- `irp_architecture_analysis.md` (41KB) - The cognition API
- `vae_translation_analysis.md` (51KB) - The translation layer
- `sage_core_analysis.md` (49KB) - The orchestration kernel
- `plugins_and_dataflow.md` (39KB) - Plugin ecosystem and data flow
- `consciousness_parallels.md` (29KB) - Biological inspiration
- `README.md` (10KB) - Documentation index

### Implementation Status

✅ **Fully Operational**:
- IRP framework with 15+ plugins
- VAE translation (TinyVAE, InformationBottleneck, Puzzle Space)
- Memory systems (all 4 types)
- Active plugins (Vision, Audio, Language, Memory, TTS, Visual Monitor)
- Metabolic states (5 operational modes)
- ATP budget with trust-weighted allocation

🚧 **Integration Gap**:
- Components exist but not unified into single `SAGE.run()` loop
- SAGECore and HRMOrchestrator are separate
- Metabolic state doesn't affect orchestrator yet

### Critical Lessons Learned

**Never Approximate Acronyms**:
When I invented plausible meanings for SAGE, user corrected: *"#never approximate what an acronym stands for. if not absolutely certain, clarify don't assume"*

Correct: **SAGE = Situation-Aware Governance Engine** (from repo description)

**ARC-AGI Tangent Was Educational**:
Spent days on knowledge distillation from GR00T for ARC-AGI abstract reasoning. Discovered class imbalance (94.45% pixel accuracy, 0% exact matches). But the whole premise was wrong—SAGE isn't about training models, it's about orchestrating them.

The tangent taught: *"The whole AGI ARC test is about conceptual thinking. It is not about grids and pixels... no amount of pattern matching is going to do it... sage is an attention orchestrator. its sole purpose is to understand the situation, understand the available resources, and apply the most appropriate resources to deal with the situation."*

### What This Means

SAGE doesn't solve problems directly—it decides which specialized reasoning to invoke:
1. Sense the situation (sensors)
2. Assess salience (SNARC: is this surprising? novel? rewarding?)
3. Decide resources (what plugins do we need?)
4. Allocate attention (ATP budget based on trust)
5. Execute refinement (IRP plugins iteratively improve)
6. Learn from results (update trust scores)
7. Take action (effectors)

**SAGE is the scheduler. Plugins are apps. VAE is how they communicate.**

Like an OS for cognition on edge devices.

## 🚨 CRITICAL: Autonomous Session Protocol (v1.2 - Dec 2025-12-12)

### Session START: Run This FIRST

```bash
source /home/dp/ai-workspace/memory/epistemic/tools/session_start.sh
```

**What it does**: Pulls all repos + commits/pushes any uncommitted work from crashed previous sessions.

**Why**: Safety net - even if previous session forgot to push, this catches it.

### Session END: Commit and Push Everything

**EVERY autonomous session MUST commit and push work before ending.**

Git post-commit hooks installed. Commits automatically push to remote.

**Before ending session**:

```bash
# Option 1: Commit normally (push is automatic)
git add -A
git commit -m "Autonomous session: [summary]"
# Push happens automatically via hook

# Option 2: Use session end script (checks all repos)
source /home/dp/ai-workspace/memory/epistemic/tools/session_end.sh "Session summary"

# Verify clean
git status  # Must show "working tree clean"
```

**DO NOT END SESSION** until work is pushed. Unpushed work is invisible to the collective.

See: `/home/dp/ai-workspace/private-context/AUTONOMOUS_SESSION_PROTOCOL.md`

---

## Next Steps
1. ✅ **System Understanding** - Complete architecture documentation created
2. ✅ **SNARC-SAGE Integration** - Memory bridge complete
3. ✅ **Jetson deployment complete** - Infrastructure validated
4. ✅ **TinyVAE Distillation** - 10x compression achieved
5. 🎯 **Unified SAGE Loop** - Integrate components into single continuous loop
6. 🔄 **Dynamic Resource Management** - Load/unload plugins based on need
7. 🚀 **GR00T vision pipeline integration** - Connect to Isaac
8. 🧠 **Cross-device cognition** - State save/restore for federation

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **SAGE** (46399 symbols, 75825 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## When Debugging

1. `gitnexus_query({query: "<error or symptom>"})` — find execution flows related to the issue
2. `gitnexus_context({name: "<suspect function>"})` — see all callers, callees, and process participation
3. `READ gitnexus://repo/SAGE/process/{processName}` — trace the full execution flow step by step
4. For regressions: `gitnexus_detect_changes({scope: "compare", base_ref: "main"})` — see what your branch changed

## When Refactoring

- **Renaming**: MUST use `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` first. Review the preview — graph edits are safe, text_search edits need manual review. Then run with `dry_run: false`.
- **Extracting/Splitting**: MUST run `gitnexus_context({name: "target"})` to see all incoming/outgoing refs, then `gitnexus_impact({target: "target", direction: "upstream"})` to find all external callers before moving code.
- After any refactor: run `gitnexus_detect_changes({scope: "all"})` to verify only expected files changed.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Tools Quick Reference

| Tool | When to use | Command |
|------|-------------|---------|
| `query` | Find code by concept | `gitnexus_query({query: "auth validation"})` |
| `context` | 360-degree view of one symbol | `gitnexus_context({name: "validateUser"})` |
| `impact` | Blast radius before editing | `gitnexus_impact({target: "X", direction: "upstream"})` |
| `detect_changes` | Pre-commit scope check | `gitnexus_detect_changes({scope: "staged"})` |
| `rename` | Safe multi-file rename | `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` |
| `cypher` | Custom graph queries | `gitnexus_cypher({query: "MATCH ..."})` |

## Impact Risk Levels

| Depth | Meaning | Action |
|-------|---------|--------|
| d=1 | WILL BREAK — direct callers/importers | MUST update these |
| d=2 | LIKELY AFFECTED — indirect deps | Should test |
| d=3 | MAY NEED TESTING — transitive | Test if critical path |

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/SAGE/context` | Codebase overview, check index freshness |
| `gitnexus://repo/SAGE/clusters` | All functional areas |
| `gitnexus://repo/SAGE/processes` | All execution flows |
| `gitnexus://repo/SAGE/process/{name}` | Step-by-step execution trace |

## Self-Check Before Finishing

Before completing any code modification task, verify:
1. `gitnexus_impact` was run for all modified symbols
2. No HIGH/CRITICAL risk warnings were ignored
3. `gitnexus_detect_changes()` confirms changes match expected scope
4. All d=1 (WILL BREAK) dependents were updated

## Keeping the Index Fresh

After committing code changes, the GitNexus index becomes stale. Re-run analyze to update it:

```bash
npx gitnexus analyze
```

If the index previously included embeddings, preserve them by adding `--embeddings`:

```bash
npx gitnexus analyze --embeddings
```

To check whether embeddings exist, inspect `.gitnexus/meta.json` — the `stats.embeddings` field shows the count (0 means no embeddings). **Running analyze without `--embeddings` will delete any previously generated embeddings.**

> Claude Code users: A PostToolUse hook handles this automatically after `git commit` and `git merge`.

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
