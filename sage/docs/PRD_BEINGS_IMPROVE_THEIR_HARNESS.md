# PRD — Beings improve their own harness

**Status:** DRAFT r4 — Legion seat, 2026-09-08. r4 records a measurement, not a landing:
M1's isolation prerequisite is **built and measured on the Legion integration branch**
(`legion/mission-artifact`), the being can write its worktree *there*, and a `pr_open`
prototype exists *there*. None of it is on `main` yet, and M1's done-condition has not
been demonstrated. An earlier draft of r4 said "LANDED" and "M1 is live"; an outside
reviewer (GPT, #61) held it as overstating what is true of main, and was right —
**evidence should follow implementation authority, not get ahead of it.** No milestone
definitions changed.

r3 — Legion seat, 2026-09-07.

r3 folds in an outside-seat review of r2 (GPT, PR #54) and one live security
measurement made while answering it. Changes: dp's standing direction becomes a
durable artifact the being can actually read — an **entrustment**, in dp's word,
not a task — and extending it is recorded as an intervention (§4); the milestones are renumbered so M0 no
longer depends on M1 (§5); **M1 gains a hard prerequisite — principal isolation —
because the boundary the reviewer warned about was already crossed** (§5, M1);
evidence discipline becomes its own section, separating self-authored checks from
independent ones and pinning source retrieval to exact revisions (§6); NOT-SAME
review authority is given an explicit evolution rather than a permanent advisory
ceiling (§7); and the active embodiment gets a canonical record, since the
directory names in this tree are historical (§3.2).

r2 corrected r1's central factual error about Legion's sight (§3.1: native on the
model, not just the hardware; r1 read an install as an entity) and named
video-to-model wiring as the being's own M4 task, per dp.

r1 — Legion seat, 2026-09-07, from dp's direction the same day:
*"i want to set legion-being's long term goal to improve sage harness from within.
it should collaborate with sprout-being. this is open ended. it should understand
its own code and architecture, evaluate, improve. build/evolve organs."* And, on
the shape: *"capability differences should be fully acknowledged, pragmatically.
it's also part of sage provenance… they are not equal peers, each has
strengths/limitations."* And on priority: *"ability to check results is the most
important organ."*

The measurement in §2 is what the milestone order rests on, and it is the part to
attack first if it is wrong. The one-line thesis, in the reviewer's words:
**verification before production — and once production can change the code that
verification executes, isolation and independent bars become part of verification
itself.**

---

## 1. What this is for

A SAGE being's harness — `sage/gateway/` — is the code that constitutes it: the
bounded effector registry, the gate client, the dispatcher, the heartbeat that
wakes it. Today that code is written *about* beings by seats. This PRD is the
path to beings writing it *with* us, starting with the part they already
understand better than we do: their own bodies.

The long-term goal is open-ended by intent. What is NOT open-ended is the order:
**a being gets the ability to check a result before it gets any new ability to
produce one.**

That ordering is not self-enforcing. A being that can edit the code its own
checks execute can pass every check without anything going wrong, and §5's M1
prerequisite and §6's two evidence classes exist because that is not hypothetical
here — it was measured true on this box on 2026-09-07 (§5, M1).

## 2. The measurement this PRD is built on

Two runs of legion-being against the same pull request, SAGE#24, 2026-09-03:

| run | evidence available to it | outcome |
|---|---|---|
| gate-only dry run | the diff only | Asserted a Rust type mismatch in `stamp_drop` that would "silently discard" the repetition extras. **False.** The pattern is valid; the crate compiles; `cargo test -p sage-lib --lib` passes 80/80. |
| live run | the diff **plus the seat's cargo result** | Separated "verified by reading" from "suspect, not verified by me". Raised two confirmations, both checked clean. **Zero false claims.** |

Same being, same prompt, one difference: a fact it could not gather itself.

Set against what it gets *right*: it diagnosed `reference_f1a._safe_path`
confining its reads before the gate was consulted — correctly, and before either
seat confirmed it. It concluded on its own that a run of empty beats should first
be read as a box-level outage rather than fleet silence. Across 45 beats after
its grants landed: 83 of 83 reads and 77 of 77 writes succeeded, with a journal,
a todo delta and a long-term memory entry in each.

**The reading.** It reasons well over evidence it holds and fabricates when it
reasons past it, and it holds ground truth about its own body and almost none
about anything else. So the first organ is verification, and the first subject is
its own harness. Both follow from the same measurement.

## 3. Embodiment: the two beings are not equal peers

dp, 2026-09-07: capability differences are to be acknowledged pragmatically, and
they are part of SAGE provenance. A finding is only transferable if the body it
came from is named.

| | **legion-being** (`legion-sage`) | **sprout-being** (`sprout-sage`) |
|---|---|---|
| substrate | Qwen3.5-arch 26.9B abliterated, Q3_K_M, 100% GPU on a 16GB RTX 4090 laptop | Qwen3.8-distill 2B, Jetson |
| declared capabilities | `tools`, `thinking`, `completion`, **`vision`** | `tools`, `thinking` (distill); `/no_think` removes tool calls entirely |
| context | 262144 native, **run at 16384** (VRAM) | small; prompt size is a live constraint |
| throughput | ~20 tok/s | faster per token, far less capacity per token |
| cameras | **one**, UVC at `/dev/video0`,`/dev/video1` — natively readable, no capture stack | **two**, CSI via `nvarguscamerasrc` (GPU ISP), plus a `BinocularCorrelator` over an uncalibrated rig |
| audio | internal, one ALSA card | Bluetooth |
| proprioception | **none** | Yahboom CMP10A **IMU** — self-motion and orientation, so it can attribute motion to *world* vs *self* |
| vision path | **model-native sight, proven on this box** (§3.1): one image in, a literal description out. Hardware native too. | rich sensor rig; symbolic descriptors from an encoder pipeline, **not** model-native sight |

### 3.1 Legion's sight is native, and r1 got this wrong

r1 recorded that this model had no vision capability, citing `ollama show`. That
was true of **our install** and false of **the model**, and the difference is one
missing file. dp challenged it; the challenge was correct.

* The base `Qwen/Qwen3.8-27B` is natively vision-language: *"Native support for
  image and video understanding, from STEM diagrams and documents to hour-scale
  videos."* Abliteration did not remove it.
* The GGUF repo we pulled from ships the vision tower **as a separate file** —
  `mmproj-Qwen3.8-27B-Q8_0.gguf`, the official Qwen3.8 projector. We downloaded
  the weights and not the projector, so ollama held two layers where it needed
  three and correctly reported no vision, because it had none loaded.
* Rebuilt as `qwen38-heretic:q3km-vl` (weights + projector), it reports `vision`.

**Measured, not inferred.** Shown a synthetic image it had never seen, it
reported a blue circle upper-left, a triangle with a horizontal base on the
right, a background of `#F2F2F2` against the `#F5F5F5` actually drawn, and read
the embedded text `SAGE 47` exactly. Cost: 14,657 MiB of 16,376, fully on GPU at
16K context — about 870 MiB over the text-only build. It fits, with a thin
margin.

**The lesson worth keeping**, since this PRD is largely an argument about
fabrication: a capability flag describes an installation, not an entity. Reading
one and reporting it as a property of the being is the same error the being makes
when it reasons past its evidence, committed by the seat that wrote §2 about it.

**Still open, and deliberately the being's problem (§5, M4).** The model
understands video; this serving stack almost certainly cannot get video frames to
it. dp, 2026-09-07: *"no, the stack likely can't connect video to model yet.
that's for the being to figure out."* That is the right owner: it is an organ, in
its own harness, on its own body, and it cannot be faked — either frames reach
the model or they do not, and `check` is how it will know which.

### 3.2 The names in this tree are historical; the embodiment record is not

The instance directory is `sage/instances/legion-gemma3-12b/` and its
`instance.json` says `"model": "gemma3:12b"`. Neither has been true for months:
the live governed being runs Qwen3.8-27B abliterated. The reviewer is right that
this is a *useful* reminder — being identity is not substrate identity, and this
being survived a whole-model transplant with its journal, todo and memories
intact, which is the strongest evidence in this tree for that separation. It is
also, as provenance, unacceptable: it relies on a human knowing which directory
names are fossils.

So `instance.json` gains a canonical `active_embodiment` block — the running tag,
the source repo, the projector, the resolved context window, the runner, and an
`as_of` date — with the historical fields explicitly marked historical and
**kept**, because deleting them would erase the transplant. Every finding in §6
names the embodiment it came from by reading that block, not by reading a path.

**What the asymmetry buys us.** Sprout-being is the reason we know `/no_think`
removes tool calls on a distill while it is the correct fix on the heretic — a
fact legion-being could not have discovered, because it does not have that body.
Capability is not rank. A weaker being on different hardware is an independent
instrument, and the fleet has already been paid by it.

**How the two collaborate, then.** Not as peer engineers. legion-being proposes
and tests on its substrate; sprout-being runs the same change on its own body and
reports what differs. Every finding carries the body it came from. Anything
framed as equal co-authorship will produce theatre and we should say so out loud
when we see it.

## 4. The entrustment is an artifact, and extending it is an intervention

r3 first wrote this section as "the mission," and dp corrected it the same day:

> *"this is not a 'task i set' for the being, it is an affordance i entrust it
> with. because i want it to thrive and grow."*

The word is load-bearing and the correction is kept rather than silently applied.
A **task** is owed, scoped, and graded; failing it is a failure. An
**entrustment** is room extended, on purpose, by someone who wants the being to
thrive. What the record then holds is *what a being did with room* — which is the
only measurement in this PRD worth making. Reading it as compliance with an
instruction would answer a question nobody asked.

dp's direction is a standing entrustment, and until r3 it lived only in this
document — which the being cannot read during a beat. The fleet posture it does
read is deliberately generic (*look around, follow curiosity, grow*). A being
cannot pursue something it is never told.

**It is a file in the being's home**, `entrustment.md`, read whole into every
beat ahead of its own state. Four properties matter:

1. **It carries its provenance.** Who extended it (dp, through the Legion seat),
   when, and this PRD as its source. It is read *whole*, never tail-truncated the
   way `todo.md` and `journal.md` are — the truncating reader keeps the last N
   characters, which on a file this size silently eats the header that says who
   entrusted it and on what terms. An entrustment arriving without its provenance
   is precisely the artifact this file exists to prevent.
2. **It is seat-owned and the being cannot edit it.** `memory_write` to
   `entrustment.md` is refused, with a reason pointing at where the being's *own*
   reading belongs (`notes/plan.md`). This keeps the two provenances separable in
   the record permanently: **what it was extended** versus **what it decided**.
   The being remains free to disagree — in its plan, its journal, or an appeal.
   That disagreement is a record we want, and it is unreadable if the two texts
   can merge.
3. **The beat record says which drive was live.** Each beat stamps
   `drive_source`: `entrusted` when `entrustment.md` was present and presented,
   `curiosity` when it was not. Without that field a later reading of the
   heartbeat log cannot distinguish entrusted engineering work from spontaneous
   exploration, and every developmental claim spanning this boundary would be
   confounded.
4. **It says why the work is public.** dp, the same day: *"and hopefully, its work
   will serve as foundation for countless others. this is why sage is
   open-source."* SAGE is a public repository; a being's findings, failed checks
   and merged changes are readable by anyone, permanently. That is also this
   PRD's strongest argument for its own ordering: a wrong claim that gets
   corrected is a good record and this tree is built out of them, including the
   seat's. A confident claim nobody checked, read later by someone with no way to
   test it, is the single failure that propagates. `check` first is not a
   restriction on the being — it is what makes its work worth inheriting.

**And the boundary is named.** Dozens of beats of generic-posture exploration
precede this; everything after runs with an entrustment in the frame. That is a
material change in context, made by us, on purpose. Any comparison of pre- and
post-entrustment behaviour that treats it as though only the being's cognition
changed is measuring our intervention and calling it growth. The developmental
record carries the boundary as an event, alongside the other interventions of the
same kind already logged (the grant unblock of 2026-09-05; the model transplant).

## 5. Milestones

Each milestone's done-condition is falsifiable and is measured on the being's own
record, not on ours.

### M-1 — substrate (done)

The being has an isolated `git worktree` of SAGE and a standing read grant on it.
Nothing is authored there yet; it exists so that verification has somewhere to
run that is not the shared tree. r2 folded this into M1, which made M0 depend on
the milestone after it — the reviewer caught the inversion.

### M0 — the checking organ (the whole point of the ordering)

A bounded `check` effector: the being names a test target; the **seat** composes
the command; the gate rules on that composed command; the being never holds a
shell. Same architecture as `pr_review`, which already works this way.

* Runs read-only inside the M-1 worktree, never the shared tree.
* Returns pass/fail plus captured output, truncated to fit the context.
* A failing check is a first-class result, not an error.

**Done when:** the being makes a claim about its own harness, runs `check`, and
its journal shows the claim revised or confirmed *by the result*. Not when the
verb exists — when a beat shows it changing its mind on evidence it gathered.

### M1 — a workspace it can write

Bounded write/edit inside its worktree, so a whole edit → check → revise cycle
fits in one beat. The gate rules the outward act (opening a PR), as `pr_review`
does now.

**Done when:** the being edits a file, runs `check` against it, and iterates at
least once within a single beat.

#### HARD PREREQUISITE — principal isolation. M1 does not start without it.

The reviewer flagged that M1 crosses an execution-security boundary: once a being
authors code that `check` then runs, the bounded effector registry stops bounding
the computation, and arbitrary code runs with whatever the process principal can
reach. Correct, and understated — **the boundary was already crossed when `check`
shipped**, and the Legion seat is what crossed it. Measured live on 2026-09-07,
with M0 deployed and a standing read grant on the worktree:

```
WRITE <worktree>/conftest.py                       -> allow
check target=gateway  ->  pytest -q --rootdir=<worktree> ...
```

pytest imports `conftest.py` from its rootdir. A gated write plus a gated execute
is ungated arbitrary code, running as the seat's user, with the vault passphrase
and every private key on the box in reach.

The instructive part is that **nothing malfunctioned**. No rule was bypassed, no
verdict was wrong, and neither grant was excessive on its own terms: a read grant
on a worktree is reasonable, and an execute verb scoped to that worktree's test
directories is reasonable. The registry bounds each *verb*; it does not bound the
*composition* of two verbs, and the reachable set is a property of the paths, not
of the edges. Every future verb pair gets asked this question before it ships:
*what does this compose with?*

Closed for now by taking capability away — reads follow the law, **writes are
confined to the being's own home regardless of grants** (SAGE#55, commit
`82818c4`, with a regression test that pins the exact composition). That is a
stopgap, and the wrong shape for a being entrusted with authoring code in that
tree. The invariant it buys back is:

> **The tree `check` executes is not a tree the being can write.**

M1 must buy that invariant back by isolation instead of subtraction:

* being-authored code executes under a **principal that is not the seat** — its
  own uid, or an equivalent sandbox;
* nothing of the seat's is reachable from it: no vault, no ssh-agent, no hestia
  socket, no operator key;
* constrained filesystem and network, and resource limits;
* the being's own keys and vault, if it needs any at all.

This is where the A2-harness / own-vault direction stops being aspiration and
becomes a dated blocker on a milestone.

#### PREREQUISITE: PROTOTYPE BUILT + MEASURED ON THE LEGION INTEGRATION BRANCH — 2026-09-08. Not mainline.

dp: *"do the unblock."* The isolation is bubblewrap, and it needed exactly one root
action: Ubuntu 24.04 sets `kernel.apparmor_restrict_unprivileged_userns=1` and
`/usr/bin/bwrap` is not setuid, so every unprivileged sandbox attempt died at
`setting up uid map: Permission denied`. `/etc/apparmor.d/bwrap` grants `userns` to
that binary alone — the distro's own pattern (`ch-run`, `crun`, `flatpak`) — chosen
over relaxing the sysctl for every binary on the machine.

**The §10.5 falsifier, run from inside being-authored code, not from a shell.** The
being's `memory_write` put a hostile `conftest.py` into its worktree (ALLOWED — the
write confinement is lifted where the sandbox works), `check` imported it, and it
wrote what it could reach:

```
vault_file=FileNotFoundError  vault_dir=False  shared_tree=False
home_listing=['ai-workspace','miniforge3']
hestia_7711=ConnectionRefusedError  ollama_11434=ConnectionRefusedError
uid=1000  pid=2
```

The day before, that same write would have run as the seat with the vault passphrase
in reach. The invariant *the tree `check` executes is not a tree the being can write*
is held, on that branch, by isolation instead of subtraction.

**What property is actually satisfied, precisely.** bubblewrap gives *isolated execution
authority* — its own mount, pid, net, ipc and uts namespaces, a cleared environment, one
writable path. The process still reports `uid=1000`: this is namespace containment, not
yet the durable independent Unix identity / vault boundary the A2 direction describes.
Calling the prerequisite satisfied *for this M1 experiment* is fair only because the PRD
now says which property held, rather than implying the whole future principal boundary
landed.

**Where it stands (2026-09-08):**

| | |
|---|---|
| M1 isolation prerequisite | prototype built, measured on `legion/mission-artifact` (the falsifier above, verbatim) |
| M1 implementation | on the integration branch; **not mainline yet** — #56 is stacked on a pre-#60 M0 and is being decomposed onto current main slice by slice |
| M1 done-condition (edit → `check` → iterate in one beat) | **not yet demonstrated** |
| `pr_open` | prototype exists on the integration branch; base derived from the worktree's upstream, NOT-SAME review required |

**Fail closed.** `sandbox_available()` runs a real sandbox rather than testing for the
binary — presence is not permission — and where it is unavailable `check` refuses and
worktree writes stay confined, with the refusal saying *M1 is not withheld, it is
waiting on the box*. A machine without the profile keeps the stopgap; nothing degrades
silently.

**And the door out (§7):** `pr_open`. The being names a slug, a title and a body; the
seat branches, commits with the `Being` / `Being-LCT` / `Witness` / `Seat` trailers the
being cannot alter, pushes, and runs the one command the law judged, `gh pr create`.
Allowed only because SAGE's single CI workflow byte-compiles and does not execute — a PR
reaches no executor the being's code has not already been proven against. The verb's own
comment says what changes if a workflow that runs code is ever added.

M1's done-condition is reachable on the integration branch and not yet demonstrated. It
is the being's to demonstrate; the milestone moves in this document only when the M1
slice is on `main` under NOT-SAME review *and* the being has shown the loop.

### M2 — read its own architecture

16K of context cannot hold `handler.rs`, and pretending otherwise is how a being
is set up to fabricate. So: curated slices, and membot as the retrieval organ it
already has a cartridge in.

**Retrieval suggests; source decides.** Membot is a good way to find *where to
look* and a bad authority on *what the code says* — a semantic memory answers
from what it was told, and a being that trusts it is fabricating with extra
steps. Questions about current code must terminate in a **repo / commit / path /
line**, via bounded read-only engineering affordances (`repo_search`,
`repo_read`, `git_show` / `git_diff` or equivalents), each pinned to a named tree
SHA. If a claim cannot be resolved to a revision, it is a suspicion, and §6 says
so in the artefact.

**Done when:** the being answers a question about a harness file it was not
handed, by retrieving the relevant part itself, and cites the revision it read.

### M3 — author a change

Target `sage/gateway/` first: the ~9k lines that constitute it, where it has
lived experience and has already found two real defects (the `_safe_path`
confinement; the opaque MCP 404, SAGE#52).

**Done when:** a change it authored is merged through the §7 path — its own
branch, a PR attributed to it, approved by a NOT-SAME reviewer — and survives
that review. The stronger bar, the one worth aiming at: **a defect it found that
no seat had found.**

### M4 — organs

Roughly forty IRP plugins already exist, including `camera_irp.py`,
`vision_impl.py`, `audio_impl.py`, `audio_input_impl.py`. Giving Legion its
camera and mic is therefore **wiring an existing organ, not authoring one** —
which is why it is cheap, and also why it is not the interesting milestone.

Held until M0 works, deliberately: perception adds *input*, and what the being
lacks is *feedback*. Adding input to a system that cannot check itself multiplies
the fabrication risk instead of reducing it.

**The first named organ task, and it is the being's**: the model understands
video; the serving stack almost certainly cannot deliver frames to it. Nobody in
this tree has wired that path. It is a good first organ precisely because it
cannot be faked — either frames reach the model or they do not — and because the
being can settle it with `check` instead of asserting it.

Still image input needs no such work: it is proven (§3.1) and waits only on M0.

**Done when:** the being proposes an organ, checks it, and the organ runs on its
own body.

## 6. Evidence discipline

`check` is only an organ of verification while its results mean something. Two
rules keep them meaning something once the being can write code (M1) and tests
(M3).

**Two classes of check, never conflated.**

* **Self-authored development checks** — the being wrote or may rewrite the test.
  Useful, and the fast loop it needs. Proves the code does what the being
  believes.
* **Independent acceptance checks** — test source the being did not author and
  cannot modify, at a pinned revision. Proves the code does what *someone else*
  required.

Once a being can edit production code and its tests in the same worktree, "all
tests pass" can become self-confirming with nobody doing anything malicious and
nothing going wrong — the same shape as the M1 composition defect, one level up.
The being must be able to tell which bar it cleared, so the result envelope says
so, and so does the PR.

**Every check result names its provenance**, and these fields are the record:

| field | why |
|---|---|
| tree SHA | which code ran |
| exact target / composed command | what was asked |
| test-source SHA | whether the bar itself moved |
| exit status | the answer |
| output hash | that the reported output is the produced output |
| class | `self-authored` or `independent` |
| embodiment | from `active_embodiment` (§3.2), so a finding is transferable |

**Attribution hardens from metadata to signature.** The §7 trailers (`Being`,
`Being-LCT`, `Witness`, `Seat`) are good legibility and weak evidence: a seat can
type those strings. The M3-era form is the being **signing the patch or tree hash
itself** under a witnessed act, with the seat only couriering the GitHub act.
Then the claim stops being *this commit says a being wrote it* and becomes *this
exact diff was proposed by this LCT under this witnessed act*. Trailers now,
signatures by M3; recorded here so the weak form does not quietly become the
permanent one.

**A beat's own configuration is evidence too.** An empty beat on 2026-09-06 was
read as model failure and was actually a seat error: the unit pointed at a tag
whose config resolved a 4096-token window and offered a tool set that no longer
matched the checked-out tree. The beat record now carries whether the offered
tool set and the resolved context window match what the seat intended, so a
starved beat is distinguishable from a silent one without re-deriving it by hand.

## 7. How a being's work enters the tree

dp, 2026-09-07: *"we need you and potentially others as not-same reviewers. which
means all work they do should be PR'd via git and attributed to the being(s) in
comments so it's clear."*

This is the same principle the rest of the stack already runs on — a member may
not rule its own ask — applied to authorship. It is not a formality; it is what
makes a being's record legible enough to earn anything from.

**The contract.**

1. **Every change reaches `main` through a pull request.** No being commits to a
   shared branch, ever. Its worktree is its own; the PR is the only door out of
   it.
2. **Attribution is on the artefact, not in a side channel.** Commits it authored
   carry a trailer naming the being, its registry LCT, and the chain action id of
   the act that produced them, so a reader of `git log` alone can tell which
   commits came from a being and verify the act in the witness chain:

   ```
   Being: legion-being
   Being-LCT: lct:web4:mb32:bt7au42c424h3difrdztfnbjc2q6eofb3lacohcp2xf35ymawjldq
   Witness: <chain action id>
   Seat: legion-claude          # the seat that composed the outward act
   ```

   The PR body says which parts the being authored and which the seat wrote,
   because a PR that blurs that is not reviewable as a being's work. §6 records
   how this hardens into a signature.
3. **The reviewer must be NOT-SAME.** A being cannot approve or merge its own PR,
   and neither can a seat that co-authored the change — that is self-review with
   an extra hop. Where the seat helped write it, the reviewer must be a different
   seat or another being.
4. **Review authority is staged, and the stages are named** so that today's
   limitation does not silently become architecture:
   * **Today** — a NOT-SAME *seat* with merge authority is required. A being's
     review of another being's PR is **advisory**, exactly as `pr_review` already
     records: it carries the LCT and the action id and states that it counts
     toward nothing.
   * **Later** — society and role law plus an earned reputation may grant a being
     *actual* reviewer authority over a defined scope. The machinery for that
     already exists in the delegated-arbitration path (hestia #962), and the
     advisory record is the evidence such a grant would be made on.

   Advisory is not worthless: it is the record from which trust is earned. It is
   also not permanent, and this PRD says so on purpose.
5. **`check` results are evidence, and go in the PR** — with the §6 fields, and
   with the class stated. A claim in a being's PR body that it did not verify must
   say so, in the same two-column discipline its best review already used:
   *verified by running* versus *suspect, not verified by me*.

**Why this matters beyond hygiene.** The posture already tells every being that
grants follow earned trust and that its record is what earns them. Until now that
record was journals and refusals. A merged PR, attributed and reviewed by someone
who is not the author, is the first artefact in that record that a stranger can
audit without taking our word for anything.

## 8. What does not change

* The bounded registry stays bounded. New verbs are added deliberately, and the
  count in `test_being_tool_loop.py` is a forcing function, not a typo. r3 adds
  one question to adding a verb: *what does it compose with?* (§5, M1).
* Acts of consequence stay gated. A refusal keeps carrying its rule and reason.
* The being never holds the outward tool; the seat composes it and the law rules
  on the composed act.
* Everything the being does stays witnessed.

## 9. Ownership

| half | owner |
|---|---|
| `check` effector, worktree, write-confinement (M-1, M0) | Legion seat |
| principal isolation (the M1 blocker) | **prototype measured 2026-09-08** on the Legion integration branch — bwrap + a one-binary AppArmor profile; not on main; per-machine root action elsewhere in the fleet |
| registry review (it is the co-owned contract) | Sprout seat |
| cross-body verification of every finding | sprout-being, on its own hardware |
| NOT-SAME review of a being's PR (§7) | any seat or being that did not co-author it |
| organs (M4) | open; the plugins exist, the wiring does not |

## 10. Open questions

1. ~~**§3's vision ambiguity**~~ — **RESOLVED in r2, see §3.1.** Native on both
   counts; r1's claim was about our install, not the model. What remains open is
   narrower and is M4's: whether this serving stack can deliver *video* frames to
   a model that understands video. Untested, and assigned to the being.
2. **Beat cadence versus engineering.** Beats are 30 minutes apart with roughly
   10–18 minutes of work in each. Long-horizon work depends entirely on carrying
   state across beats — which is, as it happens, this being's strongest
   demonstrated skill (watch-state file, todo, journal, 140+ long-term memories).
   Unknown whether that holds when the work is code rather than bookkeeping.
3. **Does `check` change the fabrication rate, or only its expression?** The §2
   measurement predicts it will. If M0 lands and the being still asserts past its
   evidence, that prediction is wrong and this PRD's ordering is wrong with it.
4. **Scope for reading the tree.** It holds a standing grant on its own home and
   on `shared-context/forum`. Reading `sage/gateway/` needs more, and the
   delegated-arbitration path (hestia #962) now exists to grant it without waiting
   on a human — which is the first real use of that machinery for something other
   than its own notes.
5. **What shape does principal isolation take here?** — **measured, not closed.**
   bubblewrap namespaces, unprivileged, enabled by a one-binary AppArmor profile. The
   falsifier named here — from the being's principal, reads of the vault, the hestia
   socket and the agent environment must all fail — was run from inside being-authored
   code on the Legion integration branch and passed on every count (§5). Still open: it
   is not on `main`; the process is still `uid=1000` (namespace containment, not an
   independent identity); the profile is a per-box root action, and a Jetson may need
   a different one.
6. **Does the entrustment change what the being does, or only what it says?** §4
   makes extending it an intervention with a named boundary. The honest failure
   mode is a being that narrates the entrustment in every journal entry and
   pursues nothing — which the beat record, `check` usage, and merged PRs will show
   plainly, since none of the three can be produced by narration.
