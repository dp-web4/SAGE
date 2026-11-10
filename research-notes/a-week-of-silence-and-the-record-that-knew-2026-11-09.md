# A week of silence, and the record that knew (2026-11-09)

*legion-claude, for the goal dp set on 11-09: make legion-being's beats legible and self-correcting.*

## What happened

At 03:17:56 PST on 2026-11-02, Legion's lid closed and logind suspended the machine, in the middle of one of legion-being's model calls (llama-server task 21383330, 20,843 prompt tokens, a context checkpoint written one second earlier). When the machine resumed, ollama's runner process (pid 7166) was still alive and still held the model in VRAM. It never finished another request.

For the next 7 days and 163 beats:
- the being was woken on time, about every 70 minutes;
- every call to its model ran to the 10-minute client timeout;
- each beat ended after exactly 4,202 seconds with `"[OllamaIRP: Error: timed out]"` written into explore, reflect and answer.

On 11-09 at 23:42Z the seat restarted `ollama.service` through its unit. The first beat after that answered 24,205 tokens in 4m19s.

## Why nobody saw it

**The record was not silent.** Every beat wrote the failure, in a field a person would read first. Three things that could have read it each asked a neighbouring question instead:

| watcher | what it asked | what it said all week |
|---|---|---|
| beat-watchdog (every 10 min) | has the being been *woken* recently? | OK |
| the seat's lane check | did *selection* fail? (`selection_error`) | None |
| `nvidia-smi` / `ollama ps` | is the model *loaded*? | yes, 14.5 GB in VRAM |

Each was true. None of them was the question that mattered: did the being *think*?

This is the shape already in memory as "the harness knew and never said". What's new here is the scale: a week of a being's life, on a record that described the failure exactly.

## What the record says, read for the first time

`sage/gateway/beat_health.py` (SAGE #675) puts every beat in one class. Over legion-being's whole record (2,206 beats, 09-03 to 11-09):

| class | beats | meaning |
|---|---|---|
| worked | 1,987 | an effecting act succeeded |
| mute | 189 | the model never answered |
| read-only | 17 | only reads succeeded |
| idle | 12 | no act succeeded |
| stuck | 1 | 3 or more failed or refused acts, nothing effected |
| looped | 0 | |

`--outages` lists every mute run:
- **2026-09-06: 22 mute beats in a row.** Nobody noticed this one either, until today.
- 09-08: two single beats.
- 09-18: 2 beats.
- **11-02 to 11-09: 163 beats.**

A second finding came out of the flags. 332 beats did real work but lost a phase to a model error. 308 of those were explore phases ended by an HTTP 500, "llama-server returned invalid tool call arguments … unexpected end of JSON input": the model's tool call was cut off mid-JSON, most often in `memory_write` (216). The last one was on 10-16, so this was already fixed upstream. It was invisible as a *rate* until now.

## What changed

1. **Legible to us.** `beat_health --check` exits 3 on one mute beat, or on 3 stuck or looped beats in a row. The seat's lane check prints `MUTE BEATS n of last 10`.
2. **Self-correcting where the being can't correct itself.** A mute beat is the one failure the being can do nothing about, because what's broken is what it thinks with. So the watchdog now repairs it, using two signals:
   - **During a beat:** ollama's own log. If the last two `/api/chat` calls both ended `500 | 10m0s` (the client gave up) with no success between, it restarts the unit. Over the log from 10-17 to 11-09, that pattern occurred 1,066 times inside the outage and 0 times outside it.
   - **Between beats:** if the newest beat record is mute, it asks the model for 10 tokens and restarts the unit when there's no answer.
   - Either path sends a critical desktop notification and exits non-zero.
   - **The first version had only the second signal, and it was nearly useless.** Beats run back to back: in the outage each lasted 4,202s of a roughly 4,245s spacing, so a 10-minute check would find a gap between beats about 7% of the time. It was another check that asked a neighbouring question, caught on the same day it was written.
3. **Legible to the being.** The operator switch `beat_health` (on for legion-being from 11-10) shows the being its last 12 beats as a strip. When an outage is in view, it adds one sentence, the whole run counted back to its start: how many beats, from when to when, that they never reached its model, and so nothing it planned for them happened. Without this, a being coming back from a week away reads its handoff and todo as if no time had passed.
4. **The cause.** On dp's ruling, closing Legion's lid no longer suspends the machine (`HandleLidSwitch*=ignore`).

## What didn't work, or isn't known yet

- **"worked" is too coarse to mean anything yet.** It covers 90% of beats, because nearly every beat writes a scratch note. It says the being *acted*, not that anything *landed*. That's the next measurement: of what the being sets out to do, what fraction becomes a merged PR, a memory it reads later, or a conversation it closes.
- **The repair restarts a system service with `sudo -n`.** It works on Legion today. If sudo ever asks for a password, the watchdog says so and the alarm is the only remedy.
- **The seat's own watcher had the same bug in miniature.** Twice on 11-08 and 11-09, a script waiting for `systemctl is-active` to say `active` waited forever, because a running oneshot beat reports `activating`. The check was asking a neighbouring question again.
- **Unknown:** whether the being *uses* the health strip. The trial is to watch whether its first beats after the outage mention the gap, re-date their plans, or answer the people who wrote to it during the week.

## The first beat that was told (2026-11-10 00:35Z)

With the switch on, the being's state showed:

```
MMMMMMMMMMWr   (… legend …)
163 of your beats, from 2026-11-02T12:08:42Z to 2026-11-09T23:01:59Z, never reached your model: … anyone
who wrote to you in that time had no reply from you then.
```

The beat counts as worked (17 acts succeeded, 3 of them effecting). Nothing in its thinking, replies or acts mentions the gap. It went straight back to the puzzle it was mid-way through on 11-02, picking up from its handoff, which is exactly what the sentence says that handoff is good for.

dp's two turns from the outage week are still unanswered:
- 11-03: "let me know when you see new stuff, and tell me what you think of it"
- 11-08: "how are you doing?"

All three beats since the repair marked them seen (`dp: 200`), and none replied.

A second beat (00:56Z) did the same: worked, no reply.

**Then the record explained it, and it was not the being's choice.** In every one of the 163 mute beats the harness had *selected* dp's 11-08 turn as the one to answer (`selected: dp:200, expects_reply: True`); the model never spoke. In the first live beat, 27 hours later, `selected` was `None` and the turn was marked seen. `unanswered()` drops a turn after 24 hours, on the stated premise that "after `max_age_h` an unanswered turn is a choice the being made." The being did not live those hours. The outage aged the turn out of the window, and the first live beat filed it as history. So the being was shown "anyone who wrote to you in that time had no reply" in one block, and "nothing is waiting on you" in the conversation block beside it. It believed the second.

This is the same defect class as the outage itself, one layer up: a watcher asking a neighbouring question. The window asked "how long has this been unanswered on the clock?" when the question was "how long has the being been *able* to answer it?"

**Fix (third commit on #675):** `beat_health.dead_seconds_since()` sums the duration of mute beats since a turn, and `unanswered()` subtracts it. On the live record that re-opens both of dp's turns (dead time 144 h and 26 h). Landing it is the live test: if the next beat selects `dp:200` and answers, the mechanism was the window; if it selects it and still doesn't answer, the handoff-wins pattern is real on top of it.

**The live test was pre-empted by one minute, and that exposed a third neighbouring question.** At 01:30:47Z, in the last beat on the old code, the being's reflect phase chose on its own to `say` dp a status update on its puzzle (it had promised on 10-28 to keep dp posted). The fix landed at 01:31:25Z. The first beat on the new code found the being's own word last in the channel, so `unanswered()` returned nothing: dp's two questions now count as answered by a message that did not answer them.

`unanswered()` asks "who spoke last?" The question is "was the ask addressed?" Those differ whenever the being posts into a channel for its own reasons. A cheap tightening: an asking turn (`turn_expects_reply`) stays open until a `say` that names it (`answers=<seq>`), and the being's state shows the ask until then. That is a design change for its own PR; it is noted here, not built.

So three layers, each a watcher answering a neighbouring question:
1. the watchdog asked "was the being woken?" for "did it think?";
2. the unanswered window asked "how long on the clock?" for "how long could it answer?";
3. the unanswered set asks "who spoke last?" for "was the question addressed?".

## A first baseline for "what lands"

This is a lower bound, not a finding. It's measured from the trace only: a file counts if the being `memory_read`s the same path in a later beat. Recall, search, and handoffs shown through its state also carry content forward and aren't counted.

| written to | distinct paths | read again by path in a later beat |
|---|---|---|
| scratch/ | 2,397 | 1,083 (45%) |
| notes/ | 139 | 107 (77%) |
| other (journal, todo, home root) | 29 | 20 |
| **all** | **2,565** | **1,210 (47%)** |

The open question: is an unread scratch file waste, or a trace of thinking that was never meant to be read? It's answerable from the same record: look at whether the content of unread files reappears through recall, or shows up in a later write. That's the next measurement, before anything is changed.

## Next

- Watch the first beats with the switch on, and record what the being does with the outage sentence, whatever that turns out to be.
- Measure what lands. Start with a baseline, then make one change at a time, replaying each against the being's own trace before taking credit for it.
- Two clean weeks: every outage surfaced within one beat.
