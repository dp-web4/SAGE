# Precondition B — cross-beat confirmation VERDICT (legion-gemma3-12b, 2026-09-11 ~19:4x UTC)

## Claim under test
The long-term memory organ's `remember()` "stored" report is backed by an artifact that a *future beat* can retrieve via `recall()`. Same-beat round trip was verified at 18:5x UTC (scratch/precondition-b-verdict-2026-09-11.md); cross-beat persistence was the open half.

## Execution this beat
- FIRST tool call of the beat: recall("PBMARK-20260911T1857Z precondition B marker remember/recall round trip", top_k=3).
- Result, verbatim-relevant lines:
  - #1 (idx:269... no — idx:280) [0.934] tags [precondition-b,memory-organ,verification,lesson]: "Precondition B operationalized and verified same-beat ... PBMARK-20260911T1857Z came back rank 1 (score 0.971). Cross-beat confirmation still pending one clean future recall."
  - #2 (idx:279) [0.894] tags [precondition-b,memory-verification,persistence-probe]: "PBMARK-20260911T1857Z precondition-B persistence probe: this marker exists only to test that remember() reports backed by recall()-able artifacts (membot lesson, 2026-09-09). If a future beat recalls this text verbatim, the long-term memory organ's 'stored' report is verified against an artifact for this instance."
- The marker text came back VERBATIM at rank 2. This is the clean cross-beat recall Precondition B required.

## Verdict
VERIFIED (cross-beat). Both halves now closed: same-beat round trip (18:5x) + cross-beat retrieval (~19:4x, ~50 min later, different beat/session). The memory organ's stored-report is artifact-backed for this instance. No re-probing needed; todo item 2 closes.

## Verified vs suspected
- VERIFIED: recall returned the marker verbatim across beats (this transcript); same-beat round trip (prior scratch file).
- SUSPECTED / NOT TESTED: durability across daemon restarts or memory-store rebuilds; behaviour on other instances/bodies. Not claimed.
