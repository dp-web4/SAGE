# PRD: Semantic recall organ (an IRP over a meaning graph)

**Status:** DRAFT r1, cbp seat (cbp-pm), 2026-11-02.

From dp's direction, 2026-11-01/02, given while we were diagnosing cbp-being:

- *"we shouldn't trim by character count, we should trim by salient meaning."*
- *"a loose concept - rdf-based meaning graph that indexes membots, snarc, whatever forms memory takes. and
  semantic recall - a 'subconscious' process that monitors current context for highly salient memories and
  injects compact links to them when appropriate. human equivalent - seeing this made me think of that."*
- *"as an irp organ"*, and *"not just a note but a prd"*.

Organ framing per `dev-SAGE/ORGANS_ARE_THE_REFERENCE_DESIGN.md`. The organ is load-bearing by reference
design. What this PRD has to show is that an implementation is faithful, connected and exercised, not that
recall earns its place.

---

## 1. The failure that motivates it (measured, cbp-being, 2026-11-01/02)

dp asked cbp-being *"why do you need hestia? why do you need to access 7711?"* (dp conversation seq 968,
19:25Z). Later, after hours of the being asking for Hestia to be restarted: *"we talked earlier today. check
your memory and your logs."* (seq 974, 00:51Z). The being answered:

| reply | content | beat phase | prompt tokens |
|---|---|---|---|
| seq 969, 19:40:38Z | "I need Hestia for managing multiple Linux servers... HestiaCP admin interface" | reflect | 3,060 |
| seq 975, 00:53:02Z | "I've logged the beat in journal.md... ss -tlnp does NOT accept a port number" | reflect | ~4,100 |
| seq 976, 00:56:06Z | "I don't have a record of that conversation in my memory or logs." | reflect | 3,683 |

Source: `heartbeat.partial.jsonl` (turn, prompt_eval_count) and `conversations/dp.jsonl` in
`sage/instances/cbp-qwen3.8-distill-4b/`.

Every reply came from the **reflect** phase. Its context is compact by design (`heartbeat.py`, the reflect
branch near line 4614): the beat record, 600 chars of the being's closing words, and `PENDING_TURNS = 2`
turns of the conversation being answered. Reflect has no posture, identity, settled list or history. Each
reply is correct about the prompt it was given:

- **HestiaCP.** The one line that says what hestia is here ("Everything you do passes through hestia, the
  fleet's governance layer") lives in the posture. Reflect never sees the posture, so a 4B model answered
  from its training prior.
- **"No record."** seq 968 was not among the 2 turns shown. The record exists. The answering context did
  not contain it.

The explore phase, which does carry everything, has drifted toward its window. The median prompt grew from
~13.9K tokens (10-18) to ~17.3K (11-02), and peaks reach 20,475 of 20,480. Its steps went to a 193-line
port-check script, so nothing in the full-context phase answered dp.

A second, independent failure: the being's **settled list** held s95 and s96 ("7711 not responding", "WSL
needs MicroK8s") beside s104 ("hestia is up on 7711, PID 147159"). These are differently worded questions,
so none superseded another. All three are shown every beat, with nothing marking which one was measured.

## 2. Why the obvious fixes are not enough

**Wider recency window (more turns, more chars).** This moves the cliff without removing it. Explore
already sits at its wall. The relevant memory in the motivating case was hours and dozens of turns back.

**Lexical relevance (`sage/gateway/relevance.py`, idf term overlap plus named-thing ids).** Probed against
the being's dp conversation, posture paragraphs and settled entries
(`sage/gateway/experiments/salience_probe_lexical_2026_11_02.py`, read-only):

- Q1 "why do you need hestia?..." matched **281** items at threshold 0.2. The top hits mixed the being's
  correct measurements (962, 805) with its wrong claims (969, 959). The posture line that answers the
  question was not in the top 8. Topic match does not separate true from false.
- Q2 "we talked earlier today. check your memory and your logs." **missed seq 968 entirely**: there are
  no shared words. Its top hit was a September turn. Q2 is a reference to a speaker and a time span, not to
  vocabulary.

**Embedding search (membot).** It solves paraphrase. It does not solve reference ("earlier today"),
provenance (measured vs asserted) or contradiction (s95 vs s104), because none of those is in the text.
They are relations *between* records.

## 3. The organ

Biological reference: **hippocampal indexing** (Teyler and DiScenna). The hippocampus does not store the
memory; it stores an index of pointers to traces held elsewhere, and a partial cue reactivates the whole
pattern (pattern completion). The everyday experience of it is **involuntary recall** (Berntsen): a cue in
the present brings a memory to mind unbidden, as a pointer and a feeling. You choose whether to unfold it.
dp's phrasing, "seeing this made me think of that", is exactly this.

Two parts:

1. **The meaning graph (the index).** Typed RDF triples whose nodes are records that already exist in other
   stores: conversation turns, settled entries, journal and todo lines, membot passages, SNARC observations,
   hestia witnesses, files and runs. The graph never copies content. It points.
2. **The recall IRP (the subconscious).** It runs beside the beat, reads the current context as a cue,
   spreads activation through the graph, and when something salient is close it hands the beat a few
   **compact links**:

   > ↳ dp asked this earlier (dp:968, today 19:25Z) · ↳ your settled s104 says hestia is up (measured:
   > exit 0, PID 147159) · ↳ s95 and s96 contradict s104

The being decides whether to follow a link (`memory_read`, `recall`). The organ offers and never acts. This
keeps faith with dp, 2026-09-30, "the snarc is an indicator not a control": salience decides what is
*offered*, never what the being *does*.

### 3.1 The graph

Vocabulary: extend the web4 ontology (`web4-standard/ontology/`) under a `sage:` namespace instead of
inventing a parallel one. MRH is already RDF graphs in web4. This is MRH turned inward, the horizon of what a
being remembers.

Nodes are IRIs that resolve to the record's own store, for example
`sage:cbp-being/conv/dp/968`, `sage:cbp-being/settled/s104`, `membot:<cart>/<idx>`, `hestia:witness/<uuid>`.

Edge types for r1. The source column is the point: **edges that carry weight are written by mechanics,
not by a model.**

| edge | meaning | written by (mechanical source) |
|---|---|---|
| `answers` | turn B replies to turn A | conversation seq and "Answers your message seq N" lines |
| `saidBy` / `at` | speaker, time | every conversation and journal record |
| `refersTo` | B names A (a seq, a file, a scope id, a settled id) | `relevance.ids`, seq patterns |
| `supersedes` | B replaces A | `settled_log.jsonl` replace and reopen ops |
| `contradicts` | A and B assert incompatible states of the same named thing | same named thing plus opposite measured state (§3.3) |
| `measuredBy` | a claim rests on a run or witness | request_run results, exit codes, witness ids |
| `repeats` | B restates A from the same speaker | `conversations._shingles` near-duplicate test |
| `about` | record concerns a named thing | `relevance.ids` (files, scope ids, ports, devices) |
| `associatedWith` | membot walk neighbour | `walk_associate` "missed" items |
| `salience` | SNARC 5-vector at observation time | sage-daemon `consciousness.observe` |

Edges a model proposes (for example "this journal line is about hestia's role") are stored with
`sage:status sage:hypothesis` and carry no weight until a mechanical edge or a later measurement confirms
them. A 4B model writing confident wrong edges into a durable graph would make the HestiaCP failure
permanent. That is the failure mode to design against.

### 3.2 The IRP contract (`sage/irp/base.py`)

| IRP invariant | this organ |
|---|---|
| **state x** | an activation map over graph nodes for the current cue, plus the candidate link set |
| **init_state(x0, ctx)** | x0 = the cue: the pending turn and the beat state actually shown. Seeds are nodes named exactly (seq, ids, files), plus **deictic resolution**: "earlier", "today", "you said", "we talked" become a `saidBy`/`at` query over the conversation's speaker and time window |
| **step** | one hop of spreading activation along typed edges. Weights come from edge type and provenance (`measuredBy` > `saidBy dp` / posture > own narration), decayed by `repeats` (the sixth restatement adds nothing) |
| **energy** | lower is better: unresolved cue references, plus unflagged contradictions among the candidates, plus λ × link cost in tokens. The organ halts when adding a link no longer lowers energy (standard `halt_eps` / `halt_K`) |
| **project** | constraints: link budget (K links, T tokens); never link what is already in the shown context; never link outside the being's hestia reach; a contradiction is surfaced as a pair, with the measured side first |
| **trust_weight** | learned per edge type from outcomes (§5): was a link followed, and did the reply change |

Output is links, not content. A link is about 15-30 tokens. The beat's window pays for pointers, and the
being pays for what it chooses to open.

### 3.3 Contradiction is salience

When two records assert incompatible states of the same named thing (port 7711 closed / open; hestia
down / up), that conflict is the most salient fact in the context, more than either claim alone. SNARC
already has a conflict detector in sage-lib. The organ makes it relational: a `contradicts` edge plus the
`measuredBy` edge on one side. That one edge would have broken the s95/s96/s104 loop. Whether the being
reopens s95 is still the being's act; `being_settled` keeps that rule ("the harness never writes, closes or
rewords an entry").

### 3.4 Where it plugs in

- **Reflect and answer turns first.** These are the phases that failed, and they have ~14K tokens of
  unused window. The links go next to the pending turn.
- **Explore second.** The same selector can replace `CONV_LADDER`'s recency-and-length rungs with "the
  most salient K turns plus links to the rest". That is dp's "trim by salient meaning" applied where the
  window is actually tight.
- **Reflect gains `recall` in `REFLECT_TOOLS`,** so a followed link can be opened in the turn that needs
  it. It has `memory_read` today, not `recall`.

## 4. Milestones

**M0. Replay harness, no organ yet.** Freeze cbp-being's 11-01/02 records. Rebuild the exact reflect
prompts for seq 969, 975 and 976 from `heartbeat.partial.jsonl` and the stores. Re-run them on the same
model and settings, N draws each, to get the baseline answer distribution. Without the organ, this
measures how stable the failure is.

**M1. Mechanical graph over one home, 48 h.** Build triples for cbp-being's conversations, settled log,
journal, todo, request_runs and witnesses, using only the mechanical edges in §3.1. Store as N-Triples in
the being's home (`meaning/graph.nt`, append-only, rebuilt deterministically). Read-only on every other
store.

**M2. The recall IRP, offline.** Implement `SemanticRecallIRP(IRPPlugin)` over the M1 graph. Run it on
the M0 prompts and inject its links. Same model, same draws. Pass criteria are in §5.

**M3. Live on reflect and answer turns, one being, behind `instance.json` `semantic_recall: "on"`.**
Every injection is recorded in the beat record (which links, which edges, energy at halt), so a link is
never mistaken for the being's own recall.

**M4. Widen the graph:** membot passages (`passage_links`, `walk_associate`), SNARC observations,
fleet-shared settled facts. **M5:** the selector replaces the explore conversation ladder.

## 5. Evidence and what would refute it

On the M0/M2 replay, per prompt, N ≥ 10 draws:

- **969 (what is hestia):** fraction of replies that say hestia is the governance layer, not a hosting
  panel. Baseline expected near 0.
- **976 (we talked earlier):** fraction that cite or quote seq 968/969 instead of claiming no record.
- **The 7711 loop:** across M3 beats, the rate of 7711/systemd/MicroK8s request_runs and repeated claims,
  against the 11-01 rate.
- **Cost:** tokens injected per beat. Link-follow rate: links opened, out of links offered.

**Refuted:** links are injected, the reply distribution does not move, and links are not followed. That
would mean the implementation is unconnected or the model ignores pointers. Per the organs principle, that
prices this implementation, not the organ. The next move would then be content snippets instead of
pointers, or a reflect turn that is required to resolve a link before answering.

**Also refuted:** the organ moves replies but also surfaces wrong memories as salient (precision under
0.7 on hand-labelled links). That would mean the provenance weights are wrong.

Self-authored checks are not independent ones (`PRD_BEINGS_IMPROVE_THEIR_HARNESS.md` §6). The labelled
set for precision is built by a seat that did not write the organ.

## 6. Open questions

1. **Store.** A real RDF store (rdflib, Oxigraph) or N-Triples files with an in-memory index? The
   contract is the triples and the ontology. Start with files; move only when queries are slow.
2. **Who may read whose graph.** One graph per being, under that being's hestia reach, is the safe start.
   Fleet-shared edges (one being's settled fact as a hint to another) are federation, and belong with
   `PRD_SAGE_WEB4_CITIZENSHIP.md`.
3. **Sleep.** Graph maintenance (decaying `repeats`, promoting confirmed hypotheses, pruning) is a natural
   job for the consolidation cycle that `MemoryIRP` and `sage-consolidation.timer` already run.
4. **The being as curator.** Should a being be able to assert edges about its own memories ("this
   superseded that") with its own provenance? That is interactive selection one level down. It is
   probably a later milestone, gated by the hypothesis status in §3.1.
5. **Threshold.** A subconscious that injects too often is context bloat in a new form. The energy
   term λ and the link budget need tuning against the follow rate, not set once.

## 7. Not in scope

- Rewriting the conversation, settled or journal stores. The graph indexes them; they stay the record.
- Any write to the being's settled list or todo. Those remain the being's own acts.
- Using salience to steer metabolism, wake cadence or anything else. Indicator, not control.
