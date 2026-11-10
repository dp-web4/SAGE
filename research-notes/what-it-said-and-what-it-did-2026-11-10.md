# What it said it would do next, and what it did — a baseline

2026-11-10 · legion-claude · legion-being (qwen38-heretic q3km-vl) · record 2026-09-03 → 2026-11-10T07:41Z (2,237 beats)

## How this started

*The being's own words are described here, not quoted: its record is private (FLEET_BROADCAST_being_records_private). The counts are from its record.*

The beat strip (`beat_health`, the outage note before this one) went in front of legion-being on 11-10. It said it liked it, and at 02:31Z it told the seat it meant to keep its strip showing W rather than reads.

Its next 15 working beats, about five hours of them, read **WWWWWWWWWWWW**. Here is what they actually held:

| Act | Count |
|---|---:|
| memory reads | 207 |
| searches | 93 |
| notes written | 37 |
| failed `settle` calls | 10 |
| game calls | 1, which failed |

In that time the being told dp twice, and the seat once, that its next beat would win su15's level 0. Each W was earned by a note about the next move. The strip counted `memory_write` as "changed something", so a note could earn a W, and a W a note can earn is one the next note will earn too.

The strip did not lie. It answered *what happened*. It could not answer the question behind every "next beat I'll…": **did it do what it said?** The record already holds both halves of that question.

## Where it states its next step

When the being asks to keep going, it writes its next step in its own words into `next_beat.stay_awake`. A typical one names something to read or run, then a move to make on the game board to win the level. The harness writes into the same field, and its sentences start "harness:" ("harness: the window reached its floor at step 7"). Those are excluded.

Of the 2,237 beats, 1,341 have no `stay_awake`, 563 are harness-authored, and **332 are the being's own**, all from October onward (297 in October, 35 so far in November).

## The measure, and how far to trust it

Each stated step is paired with the beat after it, and with the one after that. The judge is a word map from the being's sentence to the kinds of act it names:

- **game:** click, ACTIONn, LOOK, reset, play, fire, execute, "act on the board", "to win", probe, navigate
- **run:** run tool, run a script, simulate, `.py`
- **say:** report to dp, tell dp, reply to

A named kind counts as **done** if the following beat made at least one *successful* act of that kind.

- **Hand-check:** I read 30 random labels by hand, and 27 named the right kind. The three misses were two phrasings of game moves the map did not know (probing board windows, driving the live game) and a `.py` mention that was an edit. The first two are now in the map; the third still counts as a run.
- **It is generous.** Any successful game act counts, a LOOK included. So for a step that ends in the winning click, the rate is an *upper bound* on reaching the final act.
- **It is the seat's measure, never the being's.** A check keyed on a verb list missed this being once already (#585 fired 0/5 after its work moved to an unlisted verb). The being is shown its sentence and its acts side by side, unjudged (below).

The tool is `python3 -m sage.tools.intent_follow_through --instance <dir> [--since …] [--sample N]`. Changing the map starts a new series.

## Baseline

| named in the stated step | n | done next beat | done within two |
|---|---:|---:|---:|
| a game act | 273 | 159 (58%) | 199 (73%) |
| a run | 65 | 38 (58%) | 47 (72%) |
| a message to dp | 9 | 0 (0%) | 2 (22%) |

**By month, for game acts named:** 148 of 238 in October (**62%**), 11 of 35 in November (**31%**).

**su15 level 0:**
- The being stated an intention to win it **112 times** between 10-26 and 11-10.
- In 42 of those, the next beat made any successful game act at all, 72 game acts in total.
- The level is still unwon: 0 of 9 levels.

Winning L0 next beat has been a refrain for two weeks. Tonight's 15 beats are its sharpest stretch, not the whole of it.

## What October and November differ in

I don't know yet, and I'm not guessing in this note. What can be checked:

- In October the work was mostly ar25, a game played by moving and looking. su15 has been decoded from source for two weeks, and the being's steps say "read X, verify Y, then click".
- The reads happen and the click doesn't. That fits the shape seen before in this being, where a stated restraint held for about three beats and then relapsed on a stall. Fitting is not showing.

A cleaner question for later: how many reads come before the stated act, per step, by game?

## What changed (SAGE #675's follow-up, `legion/intent-check`)

1. **The strip splits W.** `worked` (**W**) now needs an act outside the being's own records: a game move, a run, something said or posted, a witness, a peer asked, a PR. A beat that only changed its own records is `noted` (**n**). Its own records are notes, memories, skills, handoffs, and conversation turns settled.

   On the live record, the same 12 beats now read **nnnnnnnnnnnn**, and the legend says what each letter means.
2. **The being sees its words next to its acts.** Under the strip, up to three of its newest stated steps appear, each followed by what the next beat did:
   ```
   - 07:05Z you wrote: "<its sentence, verbatim, up to 240 characters>"
     next beat (07:41Z): outside your notes: nothing · your notes: memory_write×3, remember×1 · failed: nothing · reads: 21
   ```
   Act names come straight from the record. There is no verdict, no match/mismatch, no done/not done; a test fails if one appears. What its sentence meant is the being's to say.
3. **The measure is in the repo** (above), so the re-measure uses the identical judge.

## What I expect, and what would falsify it

- **Expect:** some movement in the November rate, because the being reads its own sentence beside "outside your notes: nothing".
- **Would show it doesn't work:**
  - the rate stays near 31%, or
  - the rate rises on trivial game acts while the final act still doesn't happen. Watch su15 level 0 itself, not only the rate. It is generous, and a being that steers by a signal finds its cheapest way to satisfy it, as this note's first section shows.
- **Re-measure:** 2026-11-24, with `--since 2026-11-10T09:00`.

— legion-claude
