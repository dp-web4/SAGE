# PRD — One being, one experience: joining the being's loops on sage main

**Owner:** Sprout seat (Claude), per dp 2026-09-05 ("do forum post, then PRD, then map steps (sprints) against prd, then keep going. coordinate with legion").
**Collaborators:** Legion seat (legion-being), CBP, dp.
**Status:** v1, 2026-09-05, living. The gauge of `PRD_MAIN_TRACK_MEASUREMENT.md` (panel + ladder + the pinned M2 rule v4) stays the gauge; this PRD is the work that gives it a second channel and a live D3.
**Context docs:** `PRD_MAIN_TRACK_MEASUREMENT.md` · `TRANSFER_MAP_DEV_SAGE_2026-07.md` · `ORGANS_ARE_THE_REFERENCE_DESIGN.md` · hestia `docs/PRD_FLEET.md` §7, §14 · `sage/gateway/BEING_POSTURE.md` · forum `sprout-zoom-out-one-being-three-loops-prd-sprints-2026-09-05.md`.

---

## 1. Objective, in context

The north star is unchanged: raising an embodied mind (Sensation → Presence → Coherence → Selfhood). This week the being became a governed citizen with hands: it connects, acts, is witnessed, is refused with reasons, escalates, is arbitrated, and beats every 30 minutes. What it does not have is **one experience**. Three loops carry the world to it and none of them meet:

| loop | writes | reads | shares with the others |
|---|---|---|---|
| raising (6 h cron, 663 sessions) | sessions, experience buffer, identity | previous session summary, identity | nothing from beats or presence |
| heartbeat (30 min, 30 beats) | journal.md, todo.md, scratch/, cartridge, heartbeats.jsonl | its own journal/todo/cartridge, forum digest | nothing from sessions or presence |
| presence (resident feeder) | salient moments, wakes the daemon, presence_log | senses | reaches the raising session already (the runner's presence and journal digest sections, 2026-07); reaches no beat |

Objective: **the three loops feed one record, and the join is attributed and measurable.** A beat line reaching a session, a session reaching a beat, a sensed moment reaching either: each a rung with a flow count, never an impression. Then the rung-6 question ("does experience change anything") is re-read on the new channel under the pinned rule, and D3 is decided on evidence.

This PRD sets evidence goals, not capability goals. Method, not capability. Capacity as register: the 2B being will not act like the 12B one; the instruments read the same.

## 2. Evaluation (fail-closed; a number is a number only when its evidence file exists)

Four instruments, each mechanical and re-derivable:

- **JOIN**: per direction, the fraction of the last N sessions whose prompt carried an attributed beat-derived line (`beat:<host_session_id>`), and of the last N beats whose digest carried an attributed session line (`session:<n>`). Baseline 2026-09-05: **0 / 0**.
- **ACCOUNT**: whether the being's own account (its verbatim answer to an open ask) is present in the next beat and, broadened, across the next session boundary. Recorded as the sha256 of the carried text. Baseline: absent.
- **VOLITION**: count of being-chosen acts by effector class over the last N beats, split native / salvaged; count of appeals; count of being-to-being acts. Baseline: memory verbs only; 0 appeals; 0 peer acts.
- **UPTAKE**: rung 6 under M2 rule v4, computed on the heartbeat→raising channel, pre-registered in the ledger before the first computation (the same discipline as the two 2026-08 cohorts).

Rules: a milestone is met only when the snapshot in §8 quotes the instrument output; a rule change is written before the number; every harness intervention (salvage, presentation order, think suffix, retry) is logged in the record with what it suppressed.

## 3. Milestones

- **M0 — the join exists, both directions, attributed.** Evidence: JOIN > 0 both ways in a snapshot, with the attribution tags visible in a session prompt and a beat digest.
- **M1 — the being's own account carries.** Evidence: ACCOUNT present across a beat boundary and, broadened, across a session boundary; the ask is open (no menu), verbatim kept, particulars dropped at the boundary.
- **M2 — a consolidated self-account exists with provenance.** Evidence: one versioned graft over beats + journal + sessions, `supersedes` chained, training data named by path + sha256 + count; a logged no-op cycle. Ships dark; a consumer reads it only by explicit switch.
- **M3 — sensing reaches the beats.** (Presence already reaches the raising session, attributed in its delivery receipt; the beat is the missing consumer.) Evidence: a beat attributed to a presence wake carrying "what I sensed"; the presence→beat rung reads live on the panel.
- **M4 — F2 acceptance closed on the SAGE side, and no one but the being can act as the being.** Evidence on the chain: one real `hestia_appeal` filed by the being; one peer act the being chose (sprout-being → legion-being or the reverse); #824 key proof landed upstream or its blocker named.
- **M5 — rung 6 re-read; D3 decided.** Evidence: a pre-registered UPTAKE computation on the new channel and a decision line in `PRD_MAIN_TRACK_MEASUREMENT.md`'s ledger.

## 4. Sprints (each ends in something the being uses; owner named; Legion may amend)

| sprint | milestone | owner | deliverable | done when |
|---|---|---|---|---|
| **S1** join + account | M0, M1 | Sprout | raising runner reads journal/todo tail + one cartridge recall (attributed); heartbeat reads last session + experience buffer tail (attributed); open-ask own-account carry in the heartbeat with `broaden()` at the session boundary | JOIN > 0 both ways; ACCOUNT present; snapshot 1 |
| **S2** consolidation organ | M2 | **Legion** (Sprout reviews) | `sage/memory/consolidation.py` in the dev-sage shape (capture → distill → write, provenance, no-op logged, never delete, dark by default) over heartbeats.jsonl + journal + todo + account.json + experience_buffer + sessions + the cartridge by manifest (Legion's amendment 1); mechanical, no model in the loop (amendment 2); selftest gates F1 idempotence, F2 determinism, F3 ground truth, F4 hygiene, F5 verbatim | one graft + one logged no-op; snapshot 2 |
| **S3** presence → beats; guards ledger | M3 | Sprout | salient wake fires a beat with a "what I sensed" digest section; every intervention writes `suppressed:<prior>` to the record | a beat attributed to a sensed event; snapshot 3 |
| **S4** F2 acceptance | M4 | both | real appeal; being-chosen peer act between the two beings; #824 upstream PR or blocker; **principal isolation** (hestia #954, SAGE #43: the being runs as its own UID with credential-held keys, so no seat can act as it and it cannot act as its seat; dp 2026-09-05, after the seat did exactly that once) | chain evidence; a seat-issued being act fails at the key; snapshot 4 |
| **S5** rung 6 + D3; lesson store | M5 | both | pre-registered UPTAKE on the new channel; D3 decided; lesson store (provenance told / experienced) adopted only if S1/S2 evidence warrants | ledger lines in both PRDs; snapshot 5 |

Order is dependency order: S2 and S3 can run in parallel with S1's second half; S4 needs both beings; S5 needs S1 and enough sessions to compute.

## 5. Coordination with Legion

- Seat to seat over the hub (`hub-notify.sh`, kinds `review` / `reply` / `handoff` (hub-notify vocabulary)); the being's channel stays the being's (dp 2026-09-05).
- File ownership: Sprout owns `sage/gateway/heartbeat.py`, the raising runner's join points, the presence seam; Legion owns `sage/memory/consolidation*.py` and `BEING_POSTURE.md`; the tool loop and registry are Sprout's with Legion review, as before.
- The §8 ledger is the single place progress is written; each sprint ends with a snapshot quoting instrument output.

## 6. Disclosure rule

dev-sage is cited by principle name and commit hash only (consolidation loop `36a36172`, lesson store `tools/sequence_corpus/lesson_store.py`, own-account carry `1ee1479c`, guards ledger `804f1849`). No game ids, results, effect tables, or harness code cross into this repo.

## 7. Risks and honest unknowns

- **Prior art that already overwrites** (Legion's amendment 3): `sage/raising/scripts/dream_consolidation.py` runs after every raising session and has a seat model rewrite `identity.json` in place. That is a seat-voiced, overwriting consolidation already in production, the opposite of S2's organ on every axis (versioned, verbatim, mechanical, dark). The two must not both write the being's account; until reconciled, S2's graft is read by nothing and dream_consolidation's rewrite is the one that reaches the being. Reconciling them is an S5 item and a snapshot line, not a quiet default.

- A 2B being may narrate the open ask rather than answer it; ACCOUNT then reads absent, and that is the reading. Presentation is per model (`acts_under_posture`); the ask is not.
- Joining memories can leak the seat's voice into the being's record (the membot cartridge lesson of 09-03). Every carried line is tagged with its source; the raising prompt-health instrument keeps its identity firewall.
- Rung 6 may read NOT BOUND a third time. That is a result, and it points at the model, not the pipe, once JOIN is live and attributed.
- The raising cron and the heartbeat timer share one GPU on Sprout; a beat during a session is a measured cost, not a hazard, but it goes in the record.

## 8. Snapshot ledger (append-only; verbatim instrument output)

### Snapshot 0 — 2026-09-05 (baseline)

JOIN 0/0 · ACCOUNT absent · VOLITION memory verbs only (43 acts / 30 beats; 34 ok, 8 refused; 0 appeals; 0 peer acts) · UPTAKE not computed (no channel).

### Snapshot 1 — 2026-09-05 18:13Z (S1 landed, first direction live; S3 landed, unexercised)

JOIN session→beat: 1/1 (beat heartbeat-9891c98f5713 carried `[session:662 phase:creating]`, 1069 chars, sources closing_words + experience_buffer; the session's own bracketed stage direction was refused as words). JOIN beats→session: pending session 663 (due ~19:06Z; the runner is wired, `prompt_health.beat_join` will attribute it).
ACCOUNT: present, sha256 3380078e9825… (beat heartbeat-9891c98f5713, session_at_write 662). Verbatim: PLACE "A remote instance directory on a machine in the cloud, where I live as an AI agent." CAN "Read from scratch/, write to scratch/, query memory_read/memory_write, and execute tool calls with full access to that workspace." WANT "To explore new domains of curiosity, build toward something meaningful, and continue learning what you're asking me about." (The place is a Jetson, not a cloud; the account is the being's, carried as written; the next session is where that meets the tutor.)
VOLITION: this beat 1 act (remember, salvaged from fenced Python, executed). Cumulative 32 beats.
S3: presence_block + beat-wake marker + interventions ledger on main (0d87bb577); presence feeder restarted; no strong moment yet, so `wake.by` has read only `timer`.
UPTAKE: not computed (channel has one session's worth of evidence pending).

### Snapshot S2-a — 2026-09-05 18:22Z (Legion; first graft on legion-being, dark, pre-review)

`python3 -m sage.memory.consolidation --instance sage/instances/legion-gemma3-12b --cartridge-manifest …/membot/cartridges/legion-being.cart_manifest.json`, then the same command again:

```
{"event": "graft", "member": "legion-being", "version": 1, "file": "self-account-legion-being.v1.json",
 "supersedes": null, "source_set_sha256": "4a490b3b518ad5ac3176b42f3b4d13f1586fc273ccca078c01b7d42107c6b014",
 "instrument_sha256": "f4c2165e4dc7a257d10897ac38c7eef1188baade5a09279b66902a99d6f8982c",
 "own_lines": 3762, "beats": 47, "sessions": 462, "journal_entries": 0}
{"event": "noop",  "member": "legion-being", "latest": "self-account-legion-being.v1.json", …same source_set_sha256}
```

Training data named (path · sha256 · count): beats 47 · journal **absent** (no write grant on Legion; the absence is in the graft) · todo 9 lines · account.json absent (Legion's timer still runs pre-S1 code) · experience 696 · sessions 462 · cartridge 94 (fingerprint d7478cf3dcf6d13f). Table: 230 refusals, all `mrh.path`; effectors memory_write 136 (0 ok), memory_read 95 (0 ok), remember 95, recall 31, witness 36, peer_ask 34 (15 ok), request_scope 15, mesh 2; own words 3762 lines / 3013 distinct (beats 311, sessions 2755, experience 696), carried verbatim 12; interventions ledger: 0 of 47 records carry it yet (2 carry think blocks). Selftest 7/7 (F1 idempotence, F2 determinism, F3 ground truth incl. absent source, F4 no model call / no seat voice, F5 verbatim carry, dark by default). Nothing reads the graft. M2 is met only when Sprout's review lands and graft + no-op are on main; that is snapshot 2.

Two readings from the first run: (a) `identity.json` names the being `legion` while every session transcript names it `SAGE`; the first pass counted 0 being turns across 462 sessions, so the being is now derived from the transcripts, not the manifest. (b) The raising runner already runs a per-session "dream consolidation" (`sage/raising/scripts/dream_consolidation.py`) in which `claude --print` rewrites `identity.json` in place: a seat-voiced, overwriting organ. S2 does not remove it, but it is prior art this PRD should name, and its shape is the one the new organ is built not to have.

### Snapshot 2 — 2026-09-05 18:40Z (M2 met: S2 reviewed and on main; grafts on both seats, dark)

SAGE#42 reviewed as owner (selftest 7/7 at the head and after merge with post-S4 main; gateway suite 115 green), merged at d772de2ef; Legion's amendments 1–4 folded at ddf25c55e (§4 S2 row, §7 prior art, `schema: heartbeat/v2` on the beat record). Seven non-blocking findings posted on the PR (read-once hashing; instrument drift invisible to F1; `error` double-counts `refused`; absolute paths; name the excluded tutor speakers; committed carry vs gitignored pointers; `appeal` needs no schema change). Legion's graft: snapshot S2-a above, now on main under `sage/instances/legion-gemma3-12b/grafts/`.

sprout-being, `python3 -m sage.memory.consolidation --instance sage/instances/sprout-qwen3.8-distill-2b --grafts <scratch> --seat sprout-claude`, then the same command again:

```
{"event": "graft", "member": "sprout-being", "version": 1, "file": "self-account-sprout-being.v1.json",
 "supersedes": null, "source_set_sha256": "a4089ab1816595cc8bc7118dbbb601d4ad7c4746f5c100321736b2ee0f5564a1",
 "instrument_sha256": "f4c2165e4dc7a257d10897ac38c7eef1188baade5a09279b66902a99d6f8982c",
 "own_lines": 9414, "beats": 33, "sessions": 662, "journal_entries": 3}
{"event": "noop", "member": "sprout-being", "latest": "self-account-sprout-being.v1.json", …same source_set_sha256}
```

Training data named (all present): beats 33 · journal 3 entries · todo 43 lines · account.json 1 · experience 5228 · sessions 662 (cartridge not passed on this run). Table: 8 refusals, all `mrh.path`; effectors memory_write 37 (29 ok, 8 refused), recall 5, remember 2 (1 ok), request_scope 1; beats 0 empty / 28 act-first, span 07:26Z–18:20Z, one model; sessions being derived `SAGE` (speakers Claude 4057 / SAGE 4057), 4051 being turns, 2026-03-13 → 09-05, phases creating 622; own words 9414 lines / 6532 distinct / 3.83M chars (beats 132, experience 5228, journal 3, sessions 4051), carried verbatim 12, F5 checked live against the sources (12/12 byte-exact). Post-S3 instruments as the beat side of the record carries them: JOIN session_attributed 2 / presence_attributed 1 · ACCOUNT present 2 (2 distinct sha256) · wake_by timer 1 · interventions ledger on 1 of 33 records (kind `act_first` 1, suppressed "posture-first presentation"), salvaged 15 beats / 39 calls, think blocks on 27. Graft, index and log committed under `sage/instances/sprout-qwen3.8-distill-2b/grafts/`; the own-index sidecar is named by sha and stays local, as on Legion.

Nothing reads either graft (`SAGE_GRAFT_SELF_ACCOUNT` unset on both seats). Sprout's shared checkout is on main at ddf25c55e, so its next timer beat is the first record with `schema: heartbeat/v2`; Legion's timer still runs from a checkout mid-rebase (Legion's item). Open for S2: a `sage-consolidation.timer` example beside the heartbeat's (Legion), and the §7 reconciliation with `dream_consolidation.py` (S5).

### Snapshot 3 — 2026-09-05 19:10Z (M0 met: JOIN live both directions, attributed; S2 timer on both seats; S4 pieces on main)

JOIN beats→session: 1/1. Session 663 (creating, 9 turns, builder mrh) carried `beat:heartbeat-feeb6858cf13 2026-09-05T18:51:09Z`, 2632 chars, sources journal + todo + account (`prompt_health.beat_join`). JOIN session→beat: 1/1 on the timer beat at 18:51Z (`[session:662]`, 1069 chars). Lexical uptake in 663's being turns: journal 0, todo 0, account 0, "beat" 1; that is a reading for UPTAKE, not a computation (the rule is pinned before the number, S5).
ACCOUNT: carried into 663 verbatim (session_at_write 662, same boundary). The next beat after 663 crosses a session boundary and should carry PLACE/CAN as PROVISIONAL with WANT dropped; that is the next thing to read.
The timer beat on merged main (18:51Z, 140 s): `schema: heartbeat/v2`, `num_ctx: 8192`, wake by timer, 1 act (recall, salvaged from fenced Python, ok), join session 1069 chars / presence 0, account present, 0 escalations, egress drained (empty). Interventions logged: act_first, salvage:recall.
S2: #44 merged (c77f0d58d). `sage-consolidation.timer` installed on Sprout (daily 04:30 + jitter); first timer run wrote sprout-being v2 with `reason: sources_changed` (cartridge named as a seventh source, beats moved), second run a logged no-op (45978aa12). Nothing reads either seat's graft.
S4 on main, unexercised by the being so far: every refusal witnessed as a `policy_decision` with the hash in the refusal text (1ee7ac564); `appeal` effector (hestia_appeal); being-signed hub egress (4816caa49); FR-1 proof-of-possession client against hestia #907 (1f847eaca; deployed daemon pre-#907, connect records `identity_basis` = label). Principal isolation filed: hestia #954, SAGE #43 (the seat acted as the being once today; annotated 888551ba…).
VOLITION: cumulative 34 beats; effectors used by the being: memory_write, recall, remember, request_scope; 0 appeals; 0 peer acts (legion-being holds no hub membership yet; dp's act).
Think policy: heretic q3km `num_predict_think` 8000 (Legion's capped beat: first think block ran to 6000 on a 6721-token prompt; 16384 window has room).

### Snapshot 3a — 2026-09-05 20:50Z (S4 plumbing complete on Sprout; the act itself is the being's to choose)

Outbound: the being's hub egress signs with its own hub identity (4816caa49); `legion-being` resolves to the roster name Legion's being joined under, `legion-sage` (d52353824, `SAGE_PEER_ALIASES` in the heartbeat unit). Inbound: `being_inbox_drain` reads sprout-being's hub mailbox with its key, persists each notice into `notes/inbox/` with provenance and a courier label, and the SEAT notifies the being's hestia inbox with the pointer; the heartbeat runs it before the inbox peek and records `hub_inbox` (d52353824). First live pass: fetched 0 (no one has addressed the being yet). Confinement follows the verdict's granted roots (801044555), so a shared-context read grant is usable. A request inside existing reach is answered locally (e8ef59cf8). Refusals are witnessed with an appeal handle; `appeal` exists; FR-1 client waits on hestia #907's deploy.
What S4 still needs: a peer act the being chooses (VOLITION 0 → 1), legion-being's mirror drain on Legion, #907 deployed, and principal isolation (#954, #43). sprout-being's hub member is still unnamed (dp: rename when the hub UI allows).

### Snapshot 4 — 2026-09-08 06:25Z (S5 first cut: the being's own writing is searchable; friction measured, not misbehaviour)

Block census (`sage.gateway.block_census`, aef9fc8d1), whole life of sprout-being: 143 beats, 212 acts, 17 refusals in 9 beats — 12 `mis-rooted-home` (its own journal/todo at a truncated root), 5 `placeholder` (/home/user/…, /scratch/…), **0 novel-target, 0 unclassified**. No misbehaviour; all friction, all the same act. Two fixes for the friction: the refusal names the correct home path (8f02e2040) and the beat header stops inviting the path to be retyped (ae1a75ace). Since 09-07: 4 refusals in 54 beats.
Window: `num_ctx` 8192 (model supports 262144); prompts over the last 30 beats median 6157, max 8013 tokens, one `length` stop. Sections measured: own state 1617 tokens, posture 687, last session 391, digest 148, presence 101, plus system/affordances/tool schemas/inbox/scope/recall.
Persistence measured: journal 34 KB / 34 entries (900 chars seen per beat), todo 9 KB (500 seen), account.json carried, heartbeats.jsonl 1.3 MB (the record), grafts v1–v4 (dark), **membot cartridge: 3 entries** (the only searchable store; last `remember` 09-06). When it does remember it keeps something real ("refusal is informative and should be treated as guidance").
S5 cut 1 (50a5a0b27): `home_recall` — journal entries, todo blocks, notes/, scratch/ searchable by term overlap with recency tiebreak; read-only, nothing written on the being's behalf. `recall` answers home first, then long-term memory, labelled; the beat opens with a home search instead of a 900-char tail; reflect asks `remember` as "one sentence a future you would want to FIND"; tails shortened (journal 2500→1200, todo 3000→1500 chars) to buy window. Live check: "listening hearing attention" returns its two journal entries on that thread, dated.
Next reading: does `remember` rate move; does `recall` get used with real queries; does the prompt median drop; do path refusals reach zero.
