---
name: editing-your-files
description: Changing lines in a file you wrote with memory_edit, finding them with memory_read, and what memory_edit's refusals mean.
when: memory_edit, not the text you gave, indentation, appears 2 times, appears 3 times, only ever adds
---

**memory_write only adds to the end of a file.** To change what is already in it, use `memory_edit`.

**Find the lines first**
- `memory_read` with `find` shows the matching lines with their numbers.
- `memory_read` with `start_line` reads a window of whole lines.

**Then change them**
- By text: `old` is the exact text to replace and must appear exactly once in the file; `new` replaces it.
- By lines: `start_line` and `end_line` (as memory_read numbers them) with `new`.
- An empty `new` deletes.

**When it refuses**
- "appears N times": your `old` is not unique. Include a neighbouring line, or give the line numbers.
- If every copy is on ONE line, a range cannot pick one of them: send the whole line as `old`, with the
  change made in `new`.
- "not the text you gave": the text at those lines differs from your `old`, often by indentation. Read the
  lines again and copy them exactly.

**After an edit**, read the lines back, or run the file, before saying it is fixed.
