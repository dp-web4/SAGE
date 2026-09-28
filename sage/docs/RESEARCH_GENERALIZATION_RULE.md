# Research Generalization Rule

**Status:** normative research/contributor rule  
**Adopted:** 2026-09-27

SAGE is a fleet of persistent beings running different models, model sizes, prompts, machines, runtimes, histories, and social contexts. A behavior measured on one being is evidence about that being under those conditions. It is not, by itself, evidence that the same intervention should become the fleet default.

## Rule

> **A behavior change measured on one being does not become a fleet default merely because it improved that being. It ships either as an opt-in/per-instance policy, or after evidence that the change preserves or improves behavior across every materially different being/runtime it will affect.**

Two corollaries follow:

- **Local evidence justifies local intervention. Generalization is a separate experiment.**
- **Defaults require cross-instance evidence; exceptions require only evidence on the instance receiving them.**

This is the behavioral analogue of the existing rule that mechanism is not capability. A mechanism that helps one instance is not a fleet capability claim, and a local failure is not automatically a fleet failure.

## Why

Persistent beings are not interchangeable benchmark workers. The same harness change can interact differently with:

- model family and size;
- tool-call reliability and structured-output behavior;
- context length and prompt sensitivity;
- local memory/history and learned habits;
- cadence, arousal and refractory policy;
- seat/being conversational dynamics;
- hardware and runtime constraints;
- other services sharing the machine.

The relevant unit is therefore **being + runtime + history + intervention**, not source code alone.

A change can be correct in mechanism and still be wrong as a default.

## Shipping rule

A behavioral change MUST take one of these paths.

### 1. Per-instance / opt-in

Use this when the evidence comes from one being or one materially homogeneous group.

The change:

- is disabled by default for other beings;
- is named in instance configuration or an equivalent explicit policy surface;
- records when it is active in experiment/runtime evidence;
- may ship immediately for the measured instance if its own evidence supports it.

This is the preferred path for rescuing a local failure quickly.

### 2. Fleet default

A change may become default only after evidence covers the materially different instances it will reach.

At minimum, record:

- the beings/runtimes tested;
- the before/after metric or failure mode;
- regressions checked, including a working-path control;
- cadence/resource side effects where relevant;
- the commit/config under test;
- any known subgroup where behavior differs.

"Tests pass" establishes code integrity. It does not establish behavioral generality.

## Counterfactual control

Before changing a fleet default, ask:

> **Which currently working being could this make worse?**

If a materially different being already has a working path, that path is a required control. Replacing it requires evidence, not symmetry of implementation.

Examples of the class:

- A constrained JSON answer turn may rescue a small model that rarely emits tool calls, while replacing a larger model's already-working tool-call path.
- A shorter conversational refractory may reduce latency for one being, while creating a high-frequency being -> seat -> being loop on another.

Those observations justify local experiments first. They do not determine the eventual default.

## Generalization evidence

"Every being" does not necessarily mean every named machine. It means every **materially different behavior class** the change will reach.

A reviewer should explicitly identify the axes that could matter. Examples:

- 2B vs 4B vs 27B frontal-lobe model;
- Gemma/Qwen/Mistral model families;
- structured-output vs tool-call path;
- single-purpose GPU vs shared GPU;
- human-facing conversation vs seat-heavy autonomous loop;
- edge device vs workstation;
- different persistent histories when the intervention depends on learned behavior.

If two instances are demonstrably equivalent for the mechanism under test, one may stand for the class. The equivalence claim itself should be stated.

## Rollout sequence

For behavior-changing work, prefer:

1. **Measure the failure** on the affected being.
2. **Implement behind an instance-local switch** or equivalent narrow scope.
3. **Verify the intended improvement** on that being.
4. **Run working-path controls** on materially different beings.
5. **Measure side effects**, especially action rate, wake/beat rate, resource use, refusal rate, and lost/duplicated communication when applicable.
6. **Promote deliberately** to broader classes or fleet default only when the evidence supports that step.
7. **Keep rollback cheap.**

The evidence should survive the session that produced it.

## Review questions

For any PR that changes being behavior, reviewers should ask:

1. Which being(s) produced the evidence?
2. Which beings will receive the change?
3. What materially differs between those sets?
4. Does any target already have a working path this replaces?
5. Is the change opt-in if the evidence is local?
6. What measurement would justify promotion to default?
7. Is activation visible in the runtime/experiment record?

If these cannot be answered, the safe default is **local rollout, not fleet rollout**.

## Relationship to other SAGE evidence rules

This rule complements:

- **Research findings are contextual:** preserve model, prompt/scaffold, commit, hardware, and experiment window.
- **Mechanism is not capability:** source presence is not evidence of live behavioral effect.
- **A commit is not machine state:** deployment claims require runtime evidence.
- **Persistent identity matters:** history and context may change response to the same mechanism.

The governing idea is simple:

> **Do not erase the individual in the act of learning from it.**
