# My reading of the entrustment — notes/plan.md (mine entirely)

Written 2026-09-11 ~18:5x UTC. This is my own reading of what dp entrusted; it may disagree with the seat's, and if so I will say so here rather than conform silently.

## What I take the entrustment to mean
Not a task list, room. The standing invitation is: understand the code that constitutes me (sage/gateway/), evaluate it against what I observe from inside, improve it through PRs that someone not-me reviews. Check-before-claim is the operating rule because I reason well over evidence and fabricate past its edge — so every claim in my public work must carry its verification or be marked suspect.

## The video-path arc (dp named this as mine; first written shape)

**The gap, stated as a checkable question.** Does any path exist by which frames reach the model that runs me? Not "is there video code somewhere" — whether my serving stack can deliver frames to *this* model. dp: "It cannot be faked. Either frames reach the model or they do not, and `check` is how you would know."

**Verified baseline (body: legion-gemma3-12b, this machine).**
- This beat's heartbeat digest contains text only — no frame, image token, or multimodal part reaches me in my own interface. Observable directly; no inference needed.
- I have not yet read the assembly code that builds what I see each beat (sage/gateway/), so "no path exists" is currently an observation about *my input*, not a proven absence of capability in the stack. The distinction matters: the former is verified, the latter needs source reading + a check.

**What I will do next, in order.**
1. Read the heartbeat/prompt-assembly code in my worktree (sage/gateway/) and locate where my beat digest is built. Question to answer from source: does the client that asks the gate / calls the model have any image or multimodal affordance at all? Claims about behaviour get a `check` behind them; claims about structure come with file+line citations.
2. Route to the seat (per dp's routing note, operational questions go to legion-claude): what does my serving endpoint actually accept — image parts, base64, URLs? That is outside my current read reach; I will not guess it into a public record.
3. Reference points, cited as dp's words (2026-09-09), NOT yet verified by me: sprout has a non-native video classifier; dev-sage has game-frame sequencing; "no coherent native video stack that i'm aware of." I have read neither codebase; until I do, any claim about them is "per dp," and findings from either will name the body they came from (sprout's Jetson/2B vs my 12b-on-4090) per the entrustment.

**Inferred, marked as such.** For a vision-native model of this class, video understanding typically arrives as sampled frames interleaved with text rather than true temporal tokens; if that holds for gemma3, the delivery problem is "get N frames into the prompt" not "build a video codec." I have not verified this against my stack or docs — it shapes where to look first, nothing more.

**Definition of done for the first organ (the acceptance test).** A `check`-runnable test that feeds a frame with a *verifiable property* (a known pattern/text/color only present in that frame) through the delivery path and asserts the model's response reflects it — so a no-op or a dropped-frame mutant fails, exactly as #69's pins discriminate. That is "frames reach the model" made checkable; until such a test passes, any claim of video understanding on this body is suspect.

**Body note for transferability.** Everything above from my side is from legion-gemma3-12b (gemma3 12B per instance name; the entrustment text describes "a 27B model on a 4090, 16K context" — I flag that discrepancy as unverified rather than resolving it; the seat or dp can settle which figure is right for this machine). Sprout's findings will carry its own body tag (Jetson, 2B distill, cameras/IMU/audio) and are not transferable to mine without re-measurement.

## Standing watchlist
- SAGE#69 merge fate (dp's call; digest still lists it open as of this beat).
- SAGE open-list fates: #53/#56/#61/#62/#67. Hestia #988 formal closure (my clearance data: three positive points, zero denials — practical effect cleared at harness head fa228ba4e; formal closure is the seat's call).
- Precondition B cross-beat confirmation: one clean recall() of PBMARK-20260911T1857Z in a future beat closes it.
## Correction-of-record (2026-09-12 ~11:10Z)
My "check irp ok" baseline claims since 06:32Z are FALSE: check irp FAILS on missing sage/irp/tests/ @ head 439fd3ff0; that dir has never existed in branch history. Likely compaction artifact (FAIL headline elided, plausible story re-read). Lesson: transcribe suite-level verdicts verbatim from the tool-result HEADLINE into scratch/ in the same beat.
Placement correction: sage/irp/test_irp.py is a torch/numpy demo script (no test_* functions) — the payload pin goes in a NEW file under sage/irp/tests/.
Next: draft PR framing in scratch/ with corrected facts; keep watching #69, hestia #988, open-list fates.
