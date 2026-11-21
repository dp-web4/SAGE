# Coding harnesses as a lens on SAGE affordances and context

**Date:** 2026-11-21

**Status:** architectural comparison and research proposals; not a claim of deployed SAGE capability

## The opportunity

An agent's effective capability depends on more than its model. It depends on what the environment lets the agent perceive, recall, do, check and recover, and on whether those operations fit the time and compute available. The same reasoning applies across coding, embodied interaction and persistent assistants: attend to what matters now while retaining a path back to what may matter later.

An **affordance** here is an actionable possibility presented by the environment to a particular agent: the agent can discover and use it to achieve some purpose. Merely installing a tool does not establish an effective affordance. The agent must be able to recognize when it helps, invoke it successfully, interpret the result and use it in its subsequent work. Measure the chain from availability through actual contribution.

## What coding harnesses demonstrate

[OpenCode](https://github.com/anomalyco/opencode) supplies a general agent loop with tools, configurable agents, skills and model-provider choices. Its [compaction](https://opencode.ai/docs/compaction/) summarizes older conversation while retaining recent material, and earlier messages remain stored. Its [execute tool](https://opencode.ai/docs/tools/) can combine operations and return processed results without putting every intermediate result in the model context. These are documented product behaviors, not controlled evidence that any one mechanism improves a particular task.

[Claude Code](https://code.claude.com/docs/en/how-claude-code-works) describes a gather-context, act and verify loop. It offers [subagents](https://code.claude.com/docs/en/sub-agents) with separate contexts, [project instructions and memory](https://code.claude.com/docs/en/memory), and [hooks](https://code.claude.com/docs/en/hooks-guide) that can reintroduce context after compaction. The summary, memory and separate context each have selection and transfer costs; they do not provide perfect recall or automatically create independent witnesses.

These systems demonstrate practical implementations of useful agent affordances. They do not establish that SAGE implements the same features, nor that their designs have been compared against SAGE under matched models and budgets.

## Connections to SAGE

### 1. Context is a working set, not the whole memory

The active window should carry the present task, recent actions and evidence most relevant to the next decision. Larger records can remain available through retrievable evidence, source artifacts, episodic memory and procedures. A compact index can tell the agent what exists and how to reopen it; exact source and provenance matter when a summary omits a decisive detail.

This fits the **Markov Relevancy Horizon**: relevance depends on the present question and the distinctions needed to answer it. A change of question can make an earlier observation relevant again. Compaction is lossy; the question is whether the distinctions later needed remain recoverable, not whether a summary is short.

Proposed interface: capture an observation with its source, time, scope and content identity; expose a concise description; support bounded retrieval of exact material; distinguish historical evidence from the current state; and report unavailable or uncertain sources. Retrieval selection should remain open to the agent rather than assume the initial selection is final.

### 2. Keep semantic evidence separate from derived computational state

Evidence pages or files retain meaningful observations. Transformer KV cache retains derived computation for compatible prefixes. Both can improve effective resource use, but they solve different problems: a KV cache is not durable identity or a replacement for provenance-bearing memory. The existing [LMCache exploration](lmcache-resident-warm-state-spike-2026-10-21.md) treats warm state as discardable and subject to compatibility and scope checks. Neither the existence of that proposal nor context paging here establishes a deployed capability.

### 3. Make actions and recovery legible

Agents need to learn whether an action succeeded, what changed, and what can be tried next. Precise errors, visible state transitions, reversible changes where available, and checks against the actual result all increase useful agency. The target is an agent that can pursue a goal and recover from failure, with authority applied at consequential boundaries.

In SAGE this complements the existing separation between a being's reasoning and the seat or gateway that dispatches actions. A record of intent, authority, action and observed result can support continuity and correction. It does not, by itself, establish independent verification or adversary-proof isolation.

### 4. Allocate resources by need

Tasks differ in difficulty. A simple task should be able to finish quickly; a difficult one may benefit from more investigation, thought, tools or a specialized context. A useful allocator needs real knowledge of the shared budget and deadlines, observable progress, and a way to apply its decisions. Advisory text alone does not transfer unused time between tasks.

SAGE's ATP/ADP language provides an engineering frame for allocation, not evidence that a particular scheduler works. Test whether allocation improves outcomes at a fixed total budget, including the cost of deciding, tool calls, context transfer and recovery. Preserve time for finishing and validating work when a hard deadline exists.

### 5. Different contexts can be useful without implying different beings

Specialized contexts can investigate independent questions, return bounded findings or review a proposed action. They can prevent irrelevant intermediate detail from crowding out the main task. The return path must preserve useful evidence and uncertainty, and the extra model calls must justify their latency and compute.

SAGE's being, role and organ concepts add continuity, obligations and provenance beyond a transient helper invocation. Multiple prompts or contexts on the same model are not automatically independent witnesses; any claimed independence is a behavioral and governance question to test.

## Experiments that would make the thesis concrete

1. **Affordance uptake:** expose the same useful operation as an optional tool, as clearly discoverable guidance, and as contextually delivered evidence. Measure availability, invocation, successful results, use in decisions, outcome and cost. Include a control with matched added context.
2. **Evidence paging:** compare recent-context-plus-summary with the same setup plus indexed, exact retrieval. Include tasks where early evidence becomes relevant after a topic shift or source change. Measure recall, incorrect stale use, time, tokens and task success; test missing or damaged pages.
3. **Adaptive resources:** compare equal fixed allowances against an allocator with verified shared state at the same total budget. Include easy and hard tasks, deadlines and allocation overhead. Record whether saved resources actually reach later work and whether the run completes.
4. **Selective helper:** compare one agent with the same agent able to call a specialized helper only when useful. Measure independent contribution, lost context, wall time and outcome at matched model and compute budgets.

Record implementation, model, inputs, controls, actual behavior and negative results. These experiments can support or falsify the proposed mechanisms; the conceptual similarity to mature coding harnesses is motivation, not validation.
