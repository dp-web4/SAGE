# SWE-SAGE relationship

**Date:** 2026-09-26

`SWE-SAGE` is the **private** benchmark-specific working repository for the Google / Kaggle Gemma 4 Developer Agent Competition.

It is deliberately a sibling of public SAGE rather than a competition subtree inside SAGE. Keeping it private during the active competition separates open general research from competition implementation and avoids accidentally publishing evolving competition code outside an intentional release process.

## Roles

- **SAGE** remains public and canonical for general persistent-agent architecture: memory, evidence handling, cognition loops, identity, tools, learning concepts and governance interfaces.
- **SWE-SAGE** is private and canonical for the software-engineering-agent implementation, competition packaging, competition-specific ablations, internal experiment traces/results and paper-development artifacts.
- **`dev-SAGE`** remains private deeper incubation space for capability research that may be broader than the competition or may contain fleet-private evidence.
- **Web4/Hestia** remain the public identity/governance substrate when a general mechanism is promoted back into the open ecosystem.

## Research question

The competition provides an external task distribution for a question already central to SAGE:

> How much of a capable agent needs to live in the weights, and how much can live in persistent state, evidence handling, learned procedures and governed action around the model?

The competition ablation program compares, as evidence permits:

1. base Gemma 4 + competition tools;
2. post-trained Gemma 4;
3. base Gemma 4 + persistent SAGE scaffold;
4. post-trained Gemma 4 + persistent SAGE scaffold;
5. the combined system with explicit governed/witnessed action.

This framing is intentionally falsifiable. The scaffold is not presumed to outperform post-training, and governance is not presumed to be free.

## Information flow

```text
private dev-SAGE exploration
        |
        | explicit competition-safe promotion
        v
  private SWE-SAGE  <---- general mechanisms ---->  public SAGE
        |                                          ^
        | deliberate publication/generalization   |
        +------------------------------------------+
        |
        +---- optional governed-execution research ----> Web4 / Hestia
```

A finding should flow back from SWE-SAGE into public SAGE when it changes the general architecture rather than only the benchmark adapter.

Examples include source-grounded premise representations, reusable task-memory primitives, request/action/result identity, learned procedure representations, or convincing negative evidence against a proposed cognitive mechanism.

Kaggle packaging, task-specific heuristics, unpublished competition traces and competition adapters remain in private SWE-SAGE.

## Publication rule

Private competition work does not become public merely because it is scientifically interesting.

A public release is deliberate and should:

1. be checked against the current competition sharing rules;
2. remove private fleet data, credentials and unreleasable artifacts;
3. preserve enough provenance and code/data for the published claim to be independently inspected;
4. avoid making a public claim depend on inaccessible private evidence.

After the competition, SWE-SAGE may be published whole or as a scrubbed archival/reproducibility release. That is a release decision, not an assumption of the working repository.
