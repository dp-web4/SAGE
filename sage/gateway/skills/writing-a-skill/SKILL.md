---
name: writing-a-skill
description: Writing a skill of your own: a procedure you worked out, kept so a later you can find it when the same situation comes back.
when: write a skill, my own skill, procedure, recipe, how i did it, steps that worked
---

**What a skill is.** A short procedure for a kind of situation: what to do, in what order, what to check, and
what did not work. The skills that match your state are listed at the top of the skills in every beat;
`skill name=<name>` reads one.

**Writing one** with `skill`:
- `name`: lowercase words joined by dashes, e.g. `reading-a-frame`.
- `description`: one or two sentences: what it is for and when it applies.
- `when` (optional): words or phrases that show up in your state when it applies, separated by commas
  (a refusal's rule, a receipt's line, a verb, a file name). This is how the beat knows to show it to you.
- `body`: the procedure.
- `why` (optional): kept with each version.

Writing the same name again replaces it; the earlier version is kept in skills_log.jsonl. Fleet skills
(shipped with SAGE) are read-only, so yours need names of their own.

**When to write one.** After you worked something out the long way, and expect to meet it again. A skill
holds HOW; `settle` holds WHAT you concluded. They work together.
