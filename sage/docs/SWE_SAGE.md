# SWE-SAGE relationship

**Date:** 2026-09-24

[SWE-SAGE](https://github.com/dp-web4/SWE-SAGE) is the public benchmark-specific repository for the Google / Kaggle Gemma 4 Developer Agent Competition.

It is deliberately a sibling of SAGE rather than a competition subtree inside SAGE.

## Roles

- **SAGE** remains canonical for general persistent-agent architecture: memory, evidence handling, cognition loops, identity, tools, learning concepts and governance interfaces.
- **SWE-SAGE** is canonical for the software-engineering-agent implementation, competition packaging, ablations, public experiment traces/results and paper-track artifacts.
- **`dev-SAGE`** remains private incubation space for active capability research. A mechanism may originate there and be promoted into SWE-SAGE, but a public SWE-SAGE result must not require private-repository access to reproduce.
- **Web4/Hestia** remain the optional identity/governance substrate when an experiment tests governed execution rather than raw tool access.

## Research question

The competition provides an external task distribution for a question already central to SAGE:

> How much of a capable agent needs to live in the weights, and how much can live in persistent state, evidence handling, learned procedures and governed action around the model?

The initial public ablation program compares:

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
        | explicit, scrubbed, reproducible promotion
        v
     SWE-SAGE  <---- general mechanisms ---->  public SAGE
        |
        +---- optional governed execution ----> Web4 / Hestia
```

A finding should flow back from SWE-SAGE into SAGE when it changes the general architecture rather than only the benchmark adapter.

Examples include source-grounded premise representations, reusable task-memory primitives, request/action/result identity, learned procedure representations, or convincing negative evidence against a proposed cognitive mechanism.

Kaggle packaging, task-specific heuristics and competition adapters remain in SWE-SAGE.
