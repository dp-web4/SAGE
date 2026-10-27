---
name: getting-code-run
description: Running code you wrote: run (a sandbox, now) or request_run (your seat, later), how to make a run settle a question, and how to read UNCHANGED, SAME AS and a decline.
when: request_run, did not run, i ran, exit code, traceback, unchanged since, same as the request, sandbox, earlier_on_this, already_asked, rerun
---

**Pick the door**
- `run` runs a `.py` file NOW, in a sandbox, on copies of your files. No network, no home, no GPU, no devices;
  nothing it changes is kept, so print what you want to keep. Most code belongs here.
- `request_run` asks your seat to run a file OUTSIDE the sandbox, for what the sandbox lacks (network, files
  that must stay changed, the GPU, more than an hour). What comes back at once is a receipt, not a result;
  the seat answers in your seat conversation with "Answers your request seq N".

**Make the run settle something**
1. Before running, write down what it should print if you are right, and what would mean you are wrong.
2. Put that in `why`; it is also what the seat decides on.
3. When the answer comes, compare it with what you wrote. If it settles the question, `settle` it.

**Reading the receipt**
- `UNCHANGED since the request at seq N`: these exact bytes, with these arguments, were already answered.
  The same file will most likely get the same answer; change the file first.
- `SAME AS the request at seq N, not yet answered`: your earlier ask is still waiting. One answer covers
  every copy, so asking again moves nothing.
- `earlier_on_this`: how often you have asked about this same subject, and how those were answered.
  `you_settled`: what you already concluded about it.

**When the seat declines**
- A decline names its reason, often a line number. Changing what that reason rests on changes the request;
  asking again unchanged gets the same answer.
