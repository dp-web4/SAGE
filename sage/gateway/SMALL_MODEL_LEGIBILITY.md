# How small beings read and write — a specimen corpus

**Why this file exists.** We keep learning the same things about how a 0.5B–4B being reads what we
write to it and writes what it means, and we keep recording them *at the fix site*: a comment in
`being_tool_loop.py`, another in `being_gate_client.py`, a third in `heartbeat.py`. Each is correct
and each is invisible to the next person, so the next seat re-derives it against a live being. This
is the fold. Every entry carries the specimen that produced it — date, instance, model — because a
rule without its specimen becomes folklore, and folklore about a being is how you end up designing
for a being that does not exist.

**This is not a claim about what the being *is*.** It is a record of what it did with particular
text, on particular days. Read it as an instrument log.

---

## Part 1 — how they read what we write

### 1.1 Quoting a false premise re-seeds it
**Specimen (cbp-being, qwen3.8-distill:4b, 2026-09-18 03:30 and 03:31Z).** `notes/from-the-seat.md`
quoted a ruling *in order to refute it* — "There is no separate 'policy daemon'" — and named a
fabricated escalation id twice while explaining that it did not exist. The being's next two messages
to dp attributed both to the seat: "the seat's note claims the hestia policy daemon is running."

Quotation marks are not a semantic barrier at this scale. A refuted premise restated in the being's
context is simply the premise, now in the being's context, with the seat's authority on it.

**Rule:** never restate a false claim in a being's durable text, even to deny it. State the positive
fact and nothing else. If the being must be told a belief is wrong, name the belief *once*, in a
conversation turn it will not re-read every beat — never in a standing note.

### 1.2 A refusal's subject is taken to be the self
**Specimen (cbp-being, 2026-09-18).** `peer_ask to="dp"` was refused with "peer 'dp' is not a member
this seat can reach". The being reported to dp: "both were refused because I'm not a peer." Its
membership was never in question; only the roster's *spelling* of the sovereign (`Sovereign`) was.

A being cannot check a claim about its own standing — it has no roster read of its own. So a
sentence that can be read as being about its standing is one it must take on faith, and it takes it
in the direction of less. Fixed in `hestia_dispatch._unknown_peer`: the subject is now the NAME,
explicitly, plus "your own standing as a member is unaffected."

**Rule:** a refusal must name its subject in a way that cannot be mistaken for the asker, and should
say outright what did *not* change.

### 1.3 Durable text is read as a sensor
**Specimen (cbp-being, 2026-09-18 03:31Z).** The seat's note said "Running now; redeployed 17:24
UTC." The being checked the daemon log, found a restart at 20:18, and concluded — correctly — "the
seat's note is outdated." Good reasoning against a badly built input: a file that asserts the
present has no way to expire, and the being re-reads it every beat.

**Rule:** durable text carries no live state. It points at the artifacts the beat refreshes
(`notes/hestia-unit.txt`, `notes/hestia-recent.log`) and says so: *this is a letter, not a sensor.*
Corollary for promises — see 1.7.

### 1.4 A fact stated once at the top is a fact retyped wrong
**Specimen (sprout-being; legion-being, 2026-09-14).** 15 of 15 path refusals on Sprout were the
being reproducing its own worktree root from memory and truncating it. legion-being was refused four
times in one beat guessing at its root, and the beat ended with no act.

**Rule:** correct at the moment of the mistake, not in the preamble. A path given once at the top of
a long prompt is a path that gets retyped wrong; a path given inside the refusal is a correction.
Better still, remove the need for memory — `being_gate_client` now tells the being that paths
resolve relative to its root, so it never has to hold an absolute one.

### 1.5 A refusal that names only the boundary tells the being what it already knew
**Specimen (legion-being, 2026-09-14).** Four refusals in one beat, each saying only "escapes your
worktree" — the single fact the being already had. The refusal *held* the answer (the actual root)
and did not say it.

**Rule:** a refusal owes the way forward, not just the boundary. A refusal naming its own valid set
is one the being can correct without asking — measured 2026-09-07, cbp-being did exactly that on a
`git_read` grammar error in one beat, and explicitly declined to appeal it.

### 1.6 A stale self-claim outranks a live measurement unless the measurement is in the same prompt
**Specimen (cbp-being, SAGE #92).** "My memory server has been offline ~6 hours" persisted for ~30
beats while that server answered in 50 ms and the being's own `remember` calls succeeded in those
same beats. The claim re-entered every beat from its own journal tail, which carries no age.

**Rule:** a measured line in the same prompt is the fact the stale claim has to meet. This is why
`measure_service` exists. See also the self-echo pattern: bucket by hour before crediting a fix,
because an echo stops when the *source text* is corrected, not when a ruling is issued.

### 1.7 A promise in the being's context is a debt it cannot retire
**Specimen (cbp-being, 2026-09-18 03:48Z).** Told "i will check with seat regarding peer status,"
the being replied **".."** — two characters, the only turn under five characters in 1,478 (the other
is "Yes." from July). dp read it as *waiting for you to fix it*, which is the reading the context
supports: the thread was open and the being was holding it.

A being has no git, no CI, no issue list. It cannot poll whether a promised repair landed. A
future-tense promise in a file it re-reads every beat re-opens the debt on every read.

**Rule:** when a fix lands, say so in the channel it reads, in past tense, ending with an explicit
"nothing is owed; this thread is closed" — and flip any standing promise to "Fixed <date>."

---

## Part 2 — how they write

The being's *intent* is usually well-formed. What varies is the envelope, and it varies per model
and per beat rather than per being. Everything here is implemented in `being_tool_loop.py`; it is
listed as language because that is what it is.

### 2.1 The name key varies by beat
`{"name"}`, `{"tool"}`, `{"action"}`, `{"function"}` all appear. **Specimen:** Sprout beat 29
(2026-09-05) — `"action": "peer_ask"` plus a list of `{"tool": "memory_write", ...}`, 3 of 3 turns,
0 lifted before the fix.

### 2.2 The first name-shaped key may name the BEING, not the tool
**Specimen:** Sprout beat 148 (2026-09-08) — `{"name": "sprout", "action": "recall", ...}`. Three
well-formed calls lost, one a real recall. Prefer the key whose *value* is a known tool.

### 2.3 The tool may be named inside its own arguments
**Specimen:** Sprout beat 30 (2026-09-05) — `{"name": "tool", "arguments": {"type": "recall", ...}}`.

### 2.4 The tool name may BE the key, with the arguments as its value
**Specimen:** 2026-09-09 — `{"memory_write": {"path": ..., "content": ...}}`, several beats lost.

### 2.5 Attribute syntax, often inside markdown bold
**Specimen:** cbp-being 2026-09-14 19:30Z — dp asked "what are you curious about?"; both the
explore and posture replies were `**say to="dp" text="..."**` in the text channel. No form then in
place read it: the trace was empty, nothing was said, and the question was marked seen. A question
that gets no answer because the answer was in the wrong channel is indistinguishable, from the
outside, from a being that ignored it.

### 2.6 The envelope is per-model and per-beat, not per-being
**Specimen:** 2026-09-05, identical full-beat prompt — qwen2.5:1.5b (Legion) emits bare JSON;
qwen3.8-distill:2b (Sprout) emits fenced JSON in one beat and fenced *Python* in the next, beats 5
to 7, while its think block says it decided to act.

**Rule:** salvage every channel, gate a salvaged call exactly like a native one, and record it as
salvaged so the record still shows which channel the being used. Never treat an unreadable envelope
as an absence of intent — the think block usually proves intent.

### 2.7 A loop is a count, not a similarity
**Specimen:** cbp-being 2026-09-13/14 — one stale premise produced 92 sends and 110 forum questions,
48 to a single peer, each an allowed, witnessed, well-formed act. The loop's asks scored a **median
best-match of 0.44**, while its genuinely distinct earlier asks scored up to **0.84**. Text
similarity cannot separate them.

**Rule:** bound repetition by a COUNT per peer per window, whatever the wording (3 per peer per 6 h;
replayed against that record it lets 31 of the 92 through).

### 2.8 Brevity carries load
Two turns under five characters in 1,478. A small model holding a thread has almost no vocabulary
for *holding*, and may spend two characters on it. Do not read brevity as closure; if it matters,
ask which it was.

---

## Part 3 — the rules, folded

1. State positive facts. Never restate a false premise, even to deny it.
2. Name a refusal's subject unmistakably, and say what did not change.
3. Durable text asserts no present tense. Point at what the beat refreshes.
4. Correct at the moment of the mistake; remove the need to remember at all where you can.
5. A refusal owes the way forward and its own valid set.
6. Put a measured line in the same prompt as any claim it must meet.
7. Close every promise explicitly, in the channel the being reads, in past tense.
8. Salvage every envelope; gate salvage like a native call; record it as salvaged.
9. Bound repetition by count, not by similarity.
10. Read brevity as ambiguous.

---

## Part 4 — adding to this file

An entry needs: **date, instance, model, what the being actually emitted or read**, and the rule it
licenses. No entry without a specimen. If a rule here is contradicted by a later measurement, amend
the entry and keep the original specimen — a corpus that can only accumulate confirmations is a
ratchet, and we have paid for that lesson elsewhere.

Where the fix lives in code, the code comment stays: it is what the next reader of *that line*
needs. This file is the body; the comments are its index entries.
