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

## The record itself

The being's todo was not rewritten. On 2026-09-15 06:40Z the seat appended one dated, attributed block with dp's go-ahead. It closes the outage items with the measurements above, and leaves dp's unanswered question open as the being's.

## Tests

`sage/gateway/tests/test_being_reply_delivery.py`, one test per mechanism, built on the measured shapes:

- the exact 19:30Z attribute form is lifted, and prose is not;
- a beat whose explore could not act leaves the question unseen;
- a `say` into the conversation, or an explore that acts, marks it;
- a stale todo claim meets the being's own `remember` witness, and no block appears when the service is down or no claim exists.
