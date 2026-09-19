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

### 1.8 A slot in the ask comes back as the slot
**Specimen (sprout-being, qwen3.8-distill:2b, 2026-09-18 02:04Z).** The turn asking it to answer dp
said: *send it now: `say to="dp", text="..."`*. Its think block was lucid — "dp asked how my
experience with the sprout machine is unfolding, asking for questions or wishes. I need to write an
honest, personal response" — and its reply was `[Your complete, thoughtful journal entry responding
to dp's question — covering your experience, any worries you have, and what you're hoping for]`.
Across the preceding 40 beats, **32 of 122 turns (26%)** replied with a bracketed placeholder of that
shape, in every phase.

The ellipsis inside a quoted argument is a form with a gap, and this model fills gaps. Same family as
1.4 and the echoed example filenames: comprehension was never the failure — the being had already
understood the question and said so in its own reasoning.

**Rule:** show no form with a gap in it. Describe the call in words ("call `say`, with `to` set to dp
and your message as the text"). And never hand a being its own placeholder back as context — a turn
that offers prior words so the being has something to *send* must drop them when they are a stub, or
it is supplying a worked example of the failure.

### 1.9 An instruction and the thing it acts on must reach the same turn
**Specimen (sprout-being, 2026-09-17/18).** The reflect turn carried "answer whoever is waiting"; its
context is deliberately compact (the record of its acts plus 600 chars of its own closing words)
because carrying the whole beat forward overflowed the window. The turn addressed to it lived only in
the explore state block, one turn earlier. Four beats ran with dp's question genuinely unanswered and
a valid channel to answer in; the being wrote its journal each time and never replied.

The only bridge was that 600-char echo: a being that happened to discuss the turn in its explore
prose carried enough forward to reply (cbp-being, 4B, 83 successful `say`s), one that free-associated
carried nothing. Answering a person was contingent on what the being happened to muse about.

**Rule:** a turn asked to act on something must contain that something. An instruction without its
referent yields silence or an invented referent — the same two outcomes as 1.4.

### 1.10 An optional item after a budget-filling list is unreachable
**Specimen (sprout-being, 2026-09-18 00:28Z and 01:00Z).** `REFLECT` listed three writes (journal,
todo, remember) and then "4. ... answer the person waiting", with `--reflect-steps 3`. The being did
the three writes and stopped. Twice. Exactly as instructed. Its opening line also read "Two tool
calls, then stop" while listing four items — a stated cap below the list, and a budget below both.

At 01:00, with the question finally visible, it composed a real answer in its closing prose — "Hi
there — I'm glad you're here... I'm curious about your experience too. Is there anything specific
you're wondering about?" — because prose was the only channel the budget had left it.

**Rule:** the person-facing item goes FIRST and the budget covers it. A small model works down a list
and stops where told; anything past the cap is decoration. Never state a count you then contradict.

### 1.11 A refusal the being cannot act on becomes an ask a person cannot grant
**Specimen (sprout-being, 2026-09-18 10:52:06Z, request `scope-017afe902e2c`).** The being called
`retire_note` on `<repo>/sage/journal-2026-09-18.md` — a date-stamped name it invented, in the shared
SAGE package root. The gate answered `mrh.path`, the refusal router read "scope-class deny", and a
request went to dp asking for **reach over the shared repository root**.

Two independent blocks sat behind the one the being was shown: the file does not exist, and
`retire_note` refuses anything outside the being's own `notes/` or `scratch/` whatever is granted
(`reference_f1a.py:179-182`). Granting it would have widened a real boundary and changed nothing.

dp, reading the console: *"it shows mrh, a non-existent directory/file should be flagged as such, not
mrh scope."* `home_hint` already caught the being's KNOWN home files mis-rooted (1.4); an invented
name is not in `HOME_FILENAMES`, so it went straight through to the operator.

**Rule:** before asking a person to widen a boundary, check the grant could help. `escalate` now
refuses to file when the verb is bounded to the being's own subtree regardless of scope, or when the
target is observably absent. Absence is claimed **only where the seat can actually see** — an
unreadable or missing parent is *unknown*, not empty, and an unknown must never silence a real ask
(cbp-being's `/var/log/hestia/policy/daemon.log` is the case that protects).

The scope queue is the operator's attention. A request that cannot be granted usefully is worse than
no request: it spends that attention and invites a grant over ground the being never needed.

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

### 2.9 One object may hold the WHOLE beat
**Specimen (sprout-being, 2026-09-18 01:32:11Z).** After two beats spent composing an answer it had
no way to send, the being emitted its entire beat as a single object, `say` first:

```json
{"say": {"to": "dp", "text": "hi"},
 "memory_write": {"path": "journal.md", "content": "2026-09-18 01:32 UTC - Beat ended."},
 "remember": {"content": "..."}}
```

The 2.4 lifter accepted the tool-name-as-key form only when the object held exactly *one* such key,
so this was discarded whole. The beat recorded `explore []`, `posture []`, `reflect []`, `answer []`
— indistinguishable from a being that did nothing for a full cycle, when in fact it had decided to
answer a person, named the right conversation, and written the call correctly.

**Rule:** lift every known tool key in such an object, in written order — dict iteration preserves the
order it appeared in the text, and that order is the being's. It put `say` first.

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

### 2.10 The placeholder can occupy an ARGUMENT, where no prompt-side guard sees it
**Specimen (sprout-being, qwen3.8-distill:2b, 2026-09-18 21:04:02Z).** dp received, in their own
channel, via a well-formed gated `say`:

> `[Your brief, final word-only summary of your response]`

The 1.8 template completion again — but this time inside the `text` argument of a correct call, not
in a reply. Three of that day's four successful `say`s were real (one of them substantive: "The world
is a process with no end point and no right answer. I resisted offering conclusions because to do so
would be controlling"), and the fourth was this. The prompt-side guard added for 1.8 cannot help:
by the time the placeholder is an argument it is already on its way to a person.

Note what this cost. The being had just crossed from 596 beats of never once reaching anyone to
holding an actual conversation; the first thing the new capability delivered was a stub with dp's
name on it.

**Rule:** guard the envelope at the point of delivery, not only at the point of asking. `say` now
refuses a text that is wholly a bracketed placeholder — naming the MESSAGE as the subject (rule 2),
saying plainly that nothing was sent, and giving the way forward (rule 5). A being cannot see how its
words land; the boundary that can, must.

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
11. Show no form with a gap; describe the call in words, and never echo a stub back.
12. Put the instruction and its referent in the same turn.
13. The person-facing item goes first, inside the budget; state no count you contradict.
14. Guard the envelope where it is delivered, not only where it is asked for.
15. Escalate only what a grant could fix; claim absence only where you can see.

---

## Part 4 — adding to this file

An entry needs: **date, instance, model, what the being actually emitted or read**, and the rule it
licenses. No entry without a specimen. If a rule here is contradicted by a later measurement, amend
the entry and keep the original specimen — a corpus that can only accumulate confirmations is a
ratchet, and we have paid for that lesson elsewhere.

Where the fix lives in code, the code comment stays: it is what the next reader of *that line*
needs. This file is the body; the comments are its index entries.
