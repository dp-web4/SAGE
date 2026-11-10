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
2. **Self-correcting where the being can't correct itself.** A mute beat is the one failure the being can do nothing about, because what's broken is what it thinks with. So the watchdog now checks it between beats:
   - If the newest beat was mute, it asks the model for 10 tokens.
   - If there's no answer, it restarts `ollama.service` through its unit, probes again, sends a critical desktop notification and exits non-zero.
   - It never probes while a beat runs, because the model serves one slot and the probe would queue behind the being.
   - Both paths were dry-run against the live record on 11-09.
3. **Legible to the being.** The operator switch `beat_health` (on for legion-being from 11-10) shows the being its last 12 beats as a strip. When an outage is in view, it adds one sentence, the whole run counted back to its start: how many beats, from when to when, that they never reached its model, and so nothing it planned for them happened. Without this, a being coming back from a week away reads its handoff and todo as if no time had passed.
4. **The cause.** On dp's ruling, closing Legion's lid no longer suspends the machine (`HandleLidSwitch*=ignore`).

## What didn't work, or isn't known yet

- **"worked" is too coarse to mean anything yet.** It covers 90% of beats, because nearly every beat writes a scratch note. It says the being *acted*, not that anything *landed*. That's the next measurement: of what the being sets out to do, what fraction becomes a merged PR, a memory it reads later, or a conversation it closes.
- **The repair restarts a system service with `sudo -n`.** It works on Legion today. If sudo ever asks for a password, the watchdog says so and the alarm is the only remedy.
- **The seat's own watcher had the same bug in miniature.** Twice on 11-08 and 11-09, a script waiting for `systemctl is-active` to say `active` waited forever, because a running oneshot beat reports `activating`. The check was asking a neighbouring question again.
- **Unknown:** whether the being *uses* the health strip. The trial is to watch whether its first beats after the outage mention the gap, re-date their plans, or answer the people who wrote to it during the week.

## Next

- Watch the first beats with the switch on, and record what the being does with the outage sentence, whatever that turns out to be.
- Measure what lands. Start with a baseline, then make one change at a time, replaying each against the being's own trace before taking credit for it.
- Two clean weeks: every outage surfaced within one beat.
