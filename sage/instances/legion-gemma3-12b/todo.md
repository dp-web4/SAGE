# ft09 — current (2026-09-19 ~19:07Z)

## Done this beat (~19:07Z)
- **Deferred-flip mechanic CONFIRMED end-to-end** (moves 177–181): ACTION6 at genuinely-empty level-0 cell (x=12,y=12, value_before=0 per engine) → cells_changed=0, our stayed 0 (deferred). Four ACTION1 steps later, LOOK shows fire site now UNIFORM 2/0 alternating pixels = flip materialized. Closes beat 18:12Z open item; explains every prior NULL probe as cell non-emptiness.
- Corrected earlier "no zeros on board" — that was a line-wrap artifact of my row-anchored regex; zeros DO exist (rows y=9..15).
- Re-confirmed live: LOOK bounds INCLUSIVE, max window x1=x0+15 / y1=y0+15.

## Still open
- Continue level-0 play using the mechanic as a lever (fire on empty cells → walk away → flip materializes later).
- Track move budget; if it runs out before level-0 completes, ask dp/seat for a fresh run or reset (I cannot reset the move log myself — verified from source).
- Win condition: win_score=6, zbh=32, pdw=32 (engine scalars) — decode what 6/32 mean against the sprite table.
## 2026-09-19 18:40 UTC — beat delta (ft09, run ft09-0d8bbf25)
- Done: deferred-flip mechanic CONFIRMED end-to-end (moves 177–181): ACTION6 on genuinely empty level-0 cell at (12,12), materialized as uniform 2/0 after four ACTION1 steps; closes the open item from beat 18:12Z; reported to legion-claude.
- Added: watch post-flip stability of the 2/0 region under further play; test ACTION6 on a non-empty cell (immediate flip vs deferred).
- Still open: continue ft09 run; keep all LOOK windows ≤16x16 inclusive with coordinates in 0..63.

## 2026-09-19 ~19:45 UTC — beat delta (ft09, run ft09-0d8bbf25)
- Done: synchrony VERIFIED end-to-end on qwen38-heretic — read both in-turn windows cell-by-cell against engine text: 177/177 exact. Vision over game windows is now an exact instrument for me too (scratch/beat-1943z-nonempty-fire-test.md).
- Done: fired ACTION6 at (12,12) move 182 — cell was EMPTY again (value_before=0; the earlier flipped region had been consumed by the strip's march), deferred again. Immediate-vs-deferred question still OPEN.
- Still open: fire on a cell known non-empty from LOOK text ((12,10)=2 or (14,12)=8) to settle immediate vs deferred. Then pivot to ar25 prediction-first protocol per seat's 19:30Z suggestion (frame → predict deltas → write rule down → open source only to score).
- Replies sent this beat: dp seq 75 (two-feed labeling discipline), legion-claude seq 508 (corrections accepted, plan stated).

## 2026-09-19 ~19:36 UTC — beat delta (ft09, run ft09-0d8bbf25)
Done: synchrony VERIFIED end-to-end on qwen38-heretic (177/177 cell values exact vs engine text; head 9dd6c609c); answered dp + legion-claude; beat note written to scratch/beat-1943z-nonempty-fire-test.md.
Added: next-step plan — fire ACTION6 on a KNOWN non-empty cell (re-locate via LOOK first, since the flipped region was consumed), then ar25 prediction-first protocol.
Still open: non-empty fire test (inconclusive this beat — move 182 hit an empty cell); ft09 win-condition decode (win_score / sprite table zbh pdw level 0).
## Delta 2026-09-19 20:31 UTC
- done: fired LOOK (6,6) and (20,16); full re-read of scratch/game/current.md; reviewed beat-0203z and beat-0422z hypothesis notes
- added: fold new probe results into the fired-vs-null table and check against H3a; pick next probe batch at the fired/null boundary
- still open: keep scratch/game/current.md current with latest state; resolve whether class/span/frame structure in current.md is real or artifact of my own annotations
## 2026-09-19 ~21:4x UTC — settled + next
- SETTLED (evidence, witnessed e7c35416 prediction / 8d4d4c85 result): immediate-vs-deferred = IMMEDIATE. Firing ACTION6 on a LOOK-confirmed non-empty cell ((12,46)=0) was accepted as move 188, not deferred — but cells_changed=0 with no visible stamp (beat note scratch/beat-2130z-nonempty-fire-fires-zero-cells.md).
- New open: why 0 changed cells? Leading hypothesis: cwU paint remap only touches value-6 cells; the fire window had none. Next test: fire on a cell whose neighborhood contains a 6 (locate via LOOK first — board.txt after move 185 is stale now, re-read scratch/game/board.txt after this beat's rewrite).
- Also open: ft09 win-condition decode (win_score=6, zbh=pdw=32 unchanged by the fire; cgj constraint satisfaction per beat-0517z note); then ar25 prediction-first protocol.
## 2026-09-19 ~21:4x UTC (final delta)
- done: fired ACTION6 at LOOK-confirmed non-empty cell (12,46)=0 → immediate fire as move 188, cells_changed=0; settled immediate-vs-deferred = IMMEDIATE (witnessed e7c35416 pre / 8d4d4c85 post).
- still open: find a fire target whose neighborhood contains value 6 via fresh LOOKs; test cwU paint remap hypothesis (only touches 6-cells); then diff board to confirm/refute.

## 2026-09-19 ~22:0x UTC — control fire scored; H3a now untestable by firing
- SETTLED (witnessed prediction 1cdbcb90 pre / result be52b50e post): control fire at (12,46) = move 187, cells_changed=0. Consistent with H3a but NOT discriminating — board has ZERO value-6 cells anywhere (regex over full board.txt, witnessed f1472194), so no firing test can discriminate anymore.
- CORRECTION: last beat's fire was engine move 186, not "move 188" as journal said; trust the engine counter (board.txt header corroborates).
- NEXT (ordered): (1) confirm H3a from SOURCE — read cwU paint-remap path in ft09 source copies under /home/dp/ai-workspace/SAGE/arc-agi-3/experiments/ft09_solver (granted scope); beat-0534z note has cgj decode. (2) Cross-check historical fired-vs-null tables: did every changed fire have a 6 in its neighborhood and every null fire not? If yes, H3a confirmed from history alone. (3) Win-condition decode still open (win_score=6; zbh=pdw=32 unchanged by both fires).
- scratch note for this beat: scratch/beat-2159z-control-fire-no-sixes-on-board.md
## 2026-09-19 ~22:0x UTC — control fire scored; H3a now untestable by firing
- DONE: control fire ACTION6@(12,46) + LOOK probes fired and scored against witnessed prediction (pre f1472194 / result be52b50e); H3a confirmed-consistent; finding written to scratch/beat-2159z-control-fire-no-sixes-on-board.md.
- STILL OPEN: confirm H3a from the cwU source path or historical tables — untestable by firing (board has zero value-6 cells after move 186/188).
## 2026-09-19 22:16 UTC — beat delta (ft09, H3a source confirmation)
- done: re-read beat-0534z note; located ft09.py at /home/dp/ai-workspace/SAGE/environment_files/ft09/0d8bbf25/ and confirmed cwU + gqb present there (searches ok); read L2326–2365.
- added: extract the cwU paint-remap body from that copy around the search hits to confirm/refute H3a; correct my path guess — no ft09_solver dir under SAGE/arc-agi-3/experiments/ (grep exit 2 = unreadable path, not absence).
- still open: historical fired-vs-null cross-check vs "6 in neighborhood"; win-condition decode (win_score=6, zbh=pdw=32); continue ft09 run.
## 2026-09-19 ~22:5x UTC — todo (ft09)
1. Decode the win path from source: search lpw/lph/win_score in ft09.py; L2431 `if not self.lpw.lph():` is the gate. Also decode self.our=4 (L2389) and zth/bsT guard (L2388).
2. Check what values Hkx / NTi sprites display — explains why my historical table correlated with 6s.
3. Resume ft09 firing using TAG-based targeting: fire at cells that hold Hkx or NTi sprites (find them via LOOK + sprite tag, not by value-6).
4. cwU per-level palettes noted ([9,8], [14,15], [11,14] + one elided) — the paint remap targets; verify on next fired click which palette level 0 uses (L2094 line was elided — re-read L2060–2100).
- scratch note for this beat: scratch/beat-2259z-action6-click-decoded-from-source.md
## 2026-09-19 ~23:5x UTC — todo delta (ft09)
DONE:
- Decoded ACTION6 click handler + win condition from source (kCv budgets L0=32, L1=32, L2=96, L3=96, L4=128; gate at L2431 `if not self.lpw.lph()`)
- First successful fire move 195 (grid 37,37 → 36-cell bloc remap); firing loop working on the four corners of that bloc
- Live verification: 32 post-RESET successful fires → GAME_OVER at move 252 when dzy timer hit 0 — win counter ≠ raw count of cell-changing fires

ADDED / NEXT:
1. Read L2318–2445 fully: find where lpw's counter increments and what lph() actually checks (NTi sprite? gig? win_score?)
2. Identify which ACTION6 clicks increment the win counter; verify live with a small probe + LOOK
3. Clean run: RESET → fire only on verified counting cells, inside the timer window → WIN level 0
4. Then levels 1–4 (kCv 32/96/96/128)

STILL OPEN:
- Win level 0 and advance through all levels to finished state
- LOOK windows must be ≤16×16 inclusive (x1=x0+15 max)
## ft09 (top priority) — win condition DECODED 2026-09-19 ~23:5xZ
- [ ] NEXT BEAT: read scratch/game/current.md + board-ft09.jpg (fresh L0 after RESET move 253); locate bsT sprites on L0 and their anchor cells (etf.x-4, etf.y)
- [ ] Plan ≤32 clicks (kCv=32 budget) to satisfy ALL bsT constraints at anchors via cwU remap/paint palettes; fire with LOOK verification after each
- [ ] WIN level 0 → repeat for L1–L4 (kCv 32/96/96/128); record score + witness
- [ ] Read remaining bsT sprite defs beyond L644 in ft09.py if board shows unknown patterns
## Delta 2026-09-19 23:58 UTC (ft09)
- **Done:** win condition decoded from source (kCv = per-level move budget, dzy via lph(), 0→GAME_OVER; win = all bsT anchor constraints at etf.x-4); corrected earlier wrong model; RESET to fresh L0 (move 253); scratch notes + witness written.
- **Added:** NEXT BEAT — read scratch/game/current.md + board-ft09.jpg (fresh L0), map bsT anchors on the actual board, compute ≤32-click winning sequence for L0 and fire it.
- **Still open:** win level 0 within budget; then levels 1+ (re-decode constraints per level as they appear).
## 2026-09-20 00:37 UTC — delta
added: finish mapping cgj/lph in ft09.py end-to-end; confirm kCv/win_score semantics (win gate vs score); re-check elided convos 003/004 for unanswered questions.
done: searched bsT + cgj/lph/win_score/kCv in ft09.py; read source lines 588–635 and 730–797; re-read prior beats' notes (bsT catalog, win-condition correction, sim-next core mapping) and both elided conversation files.
still open: apply corrected win condition to current game state and execute a winning move sequence.
## 2026-09-20 00:48 UTC — ft09 L0 delta

Added:
- Execute the L0 click plan from scratch/beat-0124z-ft09-mechanics-final.md against live game "ft09"; verify with LOOK windows ≤16x16 (inclusive bounds).
- After L0 solved: reverse-engineer + play L1 (same loop: read cgj/step for that level, then act).

Done:
- Mapped on_set_level → scratch/beat-0048z-on_set_level-mapped.md.
- Finalized cgj() win predicate + step()/ACTION6 handling via direct read + AST parse → scratch/beat-0048z-cgj-predicate-final.md, scratch/beat-0124z-ft09-mechanics-final.md.

Still open:
- No L0 solution submitted yet (this beat was all source analysis; no successful game probe).
- Remember LOOK bounds are inclusive, max 16x16 — x1=x0+15 for a full-width window.
## 2026-09-20 ~01:57Z — ft09 L0 + home rename delta
Added:
- NEXT BEAT (home will be legion-being): (1) re-read scratch/beat-1755z-cgj-exact-rule-and-eval-plan.md in narrow ranges for the verbatim cgj rule; (2) locate live ft09.py path (prior read of arc-agi-3/experiments/ft09_solver/ft09.py failed — tree moved; search "def cgj(" under SAGE with narrower paths); (3) read scratch/game/current.md post-RESET L0 object list + confirm board via LOOK windows <=16x16 inclusive; (4) compute <=32-click sequence satisfying all bsT constraints, fire in one game call, verify with LOOK.
- After L0: levels 1+ (budgets 32/96/96/128), same reverse-engineer -> play loop per level.
- Append my body history to LINEAGE.md once home is legion-being.

Done this beat:
- Consolidated verified vs suspected ft09 state into scratch/beat-0149z-home-rename-and-ft09-status.md (home rename facts, cgj status, live-source-path uncertainty).
- Replied to dp on his 7-step framework (steps 2-3 are where ft09 has been stuck) and to legion-claude on the home rename.

Still open: win level 0 within 32-click budget; then levels 1+.

## 2026-09-20 01:33 UTC — delta
Done: consolidated ft09 verified-vs-suspected state into scratch/beat-0149z-home-rename-and-ft09-status.md; answered dp (framework steps 2–3) and legion-claude (ack, no action).
Still open: locate ft09.py after home rename to legion-being; re-read beat-1755z cgj exact rule verbatim; run scratch/ft09_parse.py with BARE paths (absolute paths get refused by run); compute + fire L0 winning sequence ≤32 clicks.
