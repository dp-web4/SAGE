# Being reply delivery: how a reply to dp was lost, and what now prevents it

Measured on cbp-being (qwen3.8-distill:4b), 2026-09-14 to 2026-09-15. dp reported two things: "the being is still not getting my messages", and it kept sending "MCP server down" reports.

Neither was a transport fault. The daemon, the dashboard and membot were all working. Three separate mechanisms in the beat failed, one after another.

## 1. A reply written as text was never sent

dp asked at 13:27Z: "what would you like to work on? what are you curious about?" At the 19:30Z beat the being's thinking says "I need to respond to dp's question about what I'd like to work on." Its explore reply and its posture reply were both:

    **say to="dp" text="I'm working on the MCP server outage at 127.0.0.1:8010. ... I'm curious whether ..."**

That is a tool call in the text channel, in attribute form. `salvage_tool_calls` read JSON and Python-call forms only. Both traces were empty, so nothing was said.

**Now:** `_attr_calls` in `being_tool_loop.py` lifts `name key="value" ...` when `name` is an offered tool and at least one key is one of its parameters. It is tried only after the JSON and Python forms find nothing, and it is recorded as `_salvaged: "attr"`.

Replayed over this being's 303 recorded replies, it lifts exactly those two lost `say` calls and nothing else. Prose that mentions a tool ("I could say something to dp") is still not a call.

## 2. The question was marked seen by a beat that could not act on it

Rendering the conversation block marked every shown turn as seen. The 19:30Z beat's explore and posture turns made no calls; only reflect's journal writes ran. Even so, dp's question was marked seen at render time.

From then on, the "unanswered" marker keyed off seen, so it never appeared. The softer "the last word here is dp's" marker cleared at 22:44Z, when the being said something else into the conversation.

**Now:** the heartbeat composes the state with `mark_conversations=False` and records what it showed (`conversations.latest_seqs`). After the beat, `mark_conversations_after_beat` marks a conversation seen only when:

- the explore turn executed at least one call, or
- the being said something into that conversation in any phase.

Otherwise the turns stay unseen, and the next beat shows them under "N turn(s) ... unanswered". The beat record carries `conversations_marked: {explore_acted, marked, held_unseen}`.

## 3. A measured line lost to the being's own repeated claim

Every beat's state already carried "long-term memory (membot) (127.0.0.1:8010): reachable, connected in 1 ms ... where they disagree, this line is current", added by SAGE #92 for this same symptom.

The being kept writing that 8010 had been "offline for ~21 hours". That figure never increased, so it was being copied forward, not measured. Meanwhile:

- membot had been running since 2026-09-13 18:02Z;
- the being's own `remember`, which stores through it, had succeeded in 57 beats;
- membot.log shows the being's `save_cartridge` in the very beat that reported the outage.

One impersonal line lost to seven of the being's own sentences in its todo, journal and dp conversation.

**Now:** `service_contradictions` in `heartbeat.py` looks for the being's own sentences that name a measured service's port, `host:port` or name next to a down-word (offline, down, unreachable, refused, not responding, outage). It checks its todo tail, journal tail and its own recent conversation turns. When the measurement says reachable, it adds a block that:

- quotes the being's sentence and names where it came from;
- states the measurement;
- cites the being's own successful use of that service in its last beat. `SERVICE_EFFECTORS` maps membot to `remember`, and the block gives the witness id.

It suggests testing with a call rather than carrying the note forward. It does not rewrite the being's record.

## 4. The same shape, a day later, about hestia

On 2026-09-15 the hestia deploy for #1031 restarted the daemon between 06:07:44 and 06:08:14Z. The being's 06:05Z beat was still running, and two of its writes at 06:08:07 were refused with "no verdict". The gate failed closed, as designed.

A watcher seat posted a forum disposition within minutes ("NO ACTION NEEDED: the 30s hestia deploy restart window"), and the being read it at 07:35Z. Even so, it wrote `notes/hestia-policy-daemon-unreachable.md`, a "critical governance failure":

- listing restart attempts that never happened;
- dated "~21 hours since 2026-09-14 09:07", the same frozen figure as the membot story;
- adding a todo item to read `/var/log/hestia/policy/daemon.log`, a path that does not exist on this host.

It requested scope for that file and appealed the refusal four times. Every gated write it made through those ten hours succeeded, which means the daemon it called unreachable returned each verdict.

**Now:** hestia (the dispatcher's endpoint, 127.0.0.1:7711) is measured each beat beside membot. `SERVICE_EFFECTORS` maps hestia to every consequential effector, so the contradiction block cites the being's own successful gated calls: "each was allowed by this daemon's verdict; a gate with no daemon refuses every such act".

## 5. A grant that answered "empty" about a file that does not exist

dp granted the being's scope request for `/var/log/hestia/policy/daemon.log`. From 17:54Z the being read that path every beat. The file does not exist, and `memory_read` returned `ok` with an empty result for any missing path. The being wrote: "Daemon log is empty, suggesting a crash or silent failure."

The same thing happened with `/var/log/hestia/policy`, which also does not exist. It then requested `/var/log/journal` and read paths it had invented there (`journal-1/…`, `system.journal`), each "successfully" empty.

A permission granted to reduce friction became the strongest evidence the being had for the outage. `git_read` had been given the rule "an empty answer must say why it is empty" on 2026-09-08; `memory_read` never was.

**Now:** a missing path returns `[no such path: '…' does not exist. This is not an empty file …]`, a real empty file returns `[empty file: …]`, and a directory lists its entries instead of raising `IsADirectoryError`. The old test that pinned `result == ""` for a missing path was pinning the defect, and is replaced.

## 6. A refusal arrived without its reason

The being's next requests were for `/etc/systemd/system/hestia.service` (which does not exist; hestia is a user unit) and `/etc/systemd/system`, "to determine the correct restart command". dp can refuse with a note. But the beat told the being only `request -> refused by operator`: `hestia_scope_status` returns the ruler's `decision_reason`, and the heartbeat dropped it. So a refusal written to redirect the being ("that file does not exist; nothing needs restarting") reached it as a bare no, and a bare no is what it had been appealing all day.

**Now:** the "decided since your last beat" lines carry `Their note: "…"`, and the `## Resolved` block written into the escalation note carries it too. A revocation (`revoked`, with hestia's `revoke_reason`) counts as a decision and is reported the same way.

## The record itself

The being's todo was not rewritten. On 2026-09-15 06:40Z the seat appended one dated, attributed block with dp's go-ahead. It closes the outage items with the measurements above, and leaves dp's unanswered question open as the being's. A second block the same day closes the policy-daemon items the same way.

**Measured: the first block changed nothing.** The being's messages to dp at 07:07, 07:36, 08:06 and 12:36Z still said 8010 had been offline for ~21 hours. The beat shows only the last 1,500 characters of `todo.md`, and the being appends to it in every beat. So a correction appended there was probably visible for about one beat before its own entries pushed it out.

A conversation turn is the channel that persists: it stays in the conversations block, carrying the "unanswered" marker until the being replies. So the seat also answered the being's own question of 13:05Z ("Can you check the daemon's logs?") in the cbp-claude conversation (seq 2721), with the deploy-log lines and the counts above.

## Tests

`sage/gateway/tests/test_being_reply_delivery.py`, one test per mechanism, built on the measured shapes:

- the exact 19:30Z attribute form is lifted, and prose is not;
- a beat whose explore could not act leaves the question unseen;
- a `say` into the conversation, or an explore that acts, marks it;
- a stale todo claim meets the being's own `remember` witness, and no block appears when the service is down or no claim exists.
