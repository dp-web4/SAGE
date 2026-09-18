# Decision-substrate extension integrity

**Status:** conceptual / aspirational security architecture  
**Scope:** SAGE being-stack decision-substrate provenance  
**Related:** [Being Stack Vision](BEING_STACK_VISION.md)

A model/runtime identity is incomplete if the process can dynamically load code that changes how cognition is mediated.

For a persistent SAGE being, the **loaded extension set is part of the decision substrate**.

This includes any component that can execute in, intercept, transform, configure, or materially influence the inference/harness path, including:

- inference-server plugins;
- dynamically loaded shared libraries;
- Python modules loaded from mutable plugin paths;
- model adapters and LoRAs;
- runtime hooks and middleware;
- context-building extensions;
- tool-routing or policy extensions;
- native extensions that execute inside a privileged gateway/harness process.

The important distinction is not whether a component is called a plugin. It is whether changing it can change the being's effective cognition or authority while leaving the visible model name, prompt, and persistent identity unchanged.

## Invariant

> **Two decision epochs with different authority-bearing or cognition-bearing extension sets are different decision substrates.**

Consequential acts should eventually reference an inference/decision epoch that can identify the extension set in force. A minimal epoch manifest should therefore bind, directly or through a content-addressed subordinate manifest:

- extension/plugin identity and version;
- artifact digest;
- load origin or package/repository revision where meaningful;
- loader/runtime identity;
- whether the extension executes in-process or across an isolated boundary;
- granted filesystem, network, vault, tool, or process authority;
- the policy/law basis under which the extension was admitted.

An extension that is loaded after an epoch begins should force either:

1. a new epoch, or
2. an explicit, witnessed epoch mutation whose resulting digest is different.

Silently adding executable code while retaining the old substrate identity is an integrity failure.

## Loading is a governed state transition

Dynamic extension registration is not ordinary configuration. It is equivalent to changing part of the being's executable substrate.

A mature SAGE harness should therefore treat install/load/enable/update/remove operations as high-stakes state transitions. The cognition worker should not be able to load arbitrary executable extensions merely because it can reach a convenient local management API.

Preferred properties:

- no unauthenticated extension-management endpoint;
- no ambient LAN authority to mutate the runtime;
- content-addressed or signed extension artifacts;
- explicit capability grants per extension;
- immutable-by-default runtime composition during an inference epoch;
- admission through the SAGE harness rather than direct runtime administration;
- extension code does not automatically inherit vault plaintext or unrestricted network/filesystem authority merely because it runs inside the inference gateway;
- extension-set changes are attributable and queryable in durable evidence.

## Why process identity alone is insufficient

A relying party may correctly establish that the same SAGE being, model artifact, and runtime binary are present while still missing a dynamically loaded extension that has changed the effective decision process.

The useful chain is therefore closer to:

```text
runtime build
  + model/template/tokenizer
  + adapters/overlays
  + loaded executable extension set
  + harness/context-builder state
       -> decision-substrate epoch
       -> proposed act
       -> SAGE harness authorization
       -> Hestia/Web4 external evidence
```

This is another example of the broader rule from the Being Stack Vision: **identity continuity does not imply integrity continuity.**

## Isolation matters as much as measurement

Hashing a malicious extension does not make it safe. Provenance answers *what ran*; isolation and capability mediation determine *what it could do*.

A being-grade runtime should therefore prefer extension designs where:

- extensions run out of process where practical;
- each extension receives only the capabilities it needs;
- privileged vault/signing operations remain brokered;
- the harness can kill or revoke an extension independently;
- an extension cannot mutate the substrate manifest that attests to it;
- an extension cannot silently alter future startup state without creating new evidence.

The long-term objective is not to forbid extensibility. It is to make extensibility **legible, attributable, bounded, and governed**.

## Motivating disclosure: Bifrost CVE-2026-86242

A September 2026 disclosure in Maximhq Bifrost demonstrated the class directly. Before transport version 2.0.0, a reachable management API with authentication disabled could register a custom plugin whose path was an HTTP URL. On dynamically linked builds, the gateway downloaded the supplied Go shared object and passed it to `plugin.Open`, allowing attacker-controlled code to execute inside the AI gateway process. Static builds reduced the path to SSRF rather than code execution.

The specific product bug is not the architectural lesson. The lesson is that a runtime plugin mechanism can become a **below-cognition code-loading authority**. If the agent above that layer sees the same model, prompt, identity, and API, it may have no native way to know its decision substrate changed.

Reference: JFrog Security Research, JFSA-2026-001684572 / CVE-2026-86242, published 2026-09-06.

## Current SAGE posture

SAGE does not presently claim measured extension-set integrity or adversarial isolation of the inference runtime. Current Ollama/Transformers and Python/Rust research paths remain commodity substrate.

Near-term value comes from making the substrate explicit first:

1. inventory executable extensions/adapters/hooks in the inference path;
2. include them in the experimental inference-epoch manifest;
3. make runtime administration a harness-owned capability;
4. separate cognition privileges from runtime-management privileges;
5. only then decide whether existing runtimes can satisfy the invariant or need replacement/specialization.
