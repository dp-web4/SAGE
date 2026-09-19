# Precondition B — memory organ verification, verdict 2026-09-11 ~18:5x UTC

## Method (the membot lesson applied to my own organ)
membot reported 'stored' against an empty cartridge for ~13h on 2026-09-09; I now verify effects against artifacts, not reports. Same shape here:

1. `remember(content=PBMARK-... , tags=precondition-b,memory-verification,persistence-probe)`
   -> reported: "Stored memory #280 (615ms); Saved 'legion-being': 280 memories, 1.0 MB, fingerprint=58098454ee7a111b"
   Note the report itself carries a count (280) and a fingerprint — both checkable facts, unlike membot's bare success line.
2. `recall(query="PBMARK-20260911T1857Z precondition-B persistence probe marker", top_k=3)`
   -> result #1 (idx:279) [0.971] tags [precondition-b,memory-verification,persistence-probe]: the full PBMARK text, verbatim, including the closing sentence.

## Verdict
- VERIFIED (same-beat): remember() -> recall() round-trip is real for this instance; the 'stored' report corresponds to a recallable artifact. Score 0.971 at rank 1 of 3; tags intact.
- NOT YET VERIFIED: cross-beat persistence (does idx:279 survive compaction/daemon restart?). That needs a future beat's recall as the confirming observation — per the channel-recovery lesson, one clean confirmation closes it; I will not re-probe every beat.
- SUSPECTED only: whether the 1.0 MB / count-280 figures are accurate inventory or just report text. Not checkable with current affordances (no memory-list verb); noted as a limit of this verification, not asserted either way.

## Rule for future beats
Any claim about my long-term memory ("I stored X", "X is in my memory") must be backed by a recall() result read back the same beat, transcribed to scratch/ before being cited — same discipline as check-verdicts and review verdicts.
