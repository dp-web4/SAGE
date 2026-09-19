# PR framing — get_chat_response payload pin (corrected facts @ head 439fd3ff0)

Target: `get_chat_response` in `/home/dp/ai-workspace/being-worktrees/legion-being/sage/irp/plugins/ollama_irp.py`.
Verified by direct read of the file at HEAD; re-verified line numbers 2026-09-12 ~18:15Z.

## What the pin asserts (functionality)
- `get_chat_response` builds a request payload with exactly: model, messages, stream=False — and appends `tools` when the caller supplies them.
- Pin = new file `sage/irp/tests/test_ollama_irp_payload.py`: constructs OllamaIRP, calls get_chat_response against a stubbed urlopen AND shadowed _check_ollama (no network), asserts each payload key's presence/type/value; stream is False; tools pass through unchanged when provided and are absent otherwise.
- Why it matters: this function is the only place the harness talks to Ollama for chat, and nothing in sage/irp pins what it sends — a silent change (e.g., stream flipping True, keep_alive dropped) would break every being's turn with no test failing.

## Verified vs suspected
- VERIFIED against tool results:
  - payload dict L223–235 + tools append L238–239 (direct read at HEAD; re-checked 2026-09-12 ~18:15Z — earlier draft said L224–236, corrected).
  - check irp now collects and passes my pin: "PASS — 3 passed in 0.71s" @ head 439fd3ff0 (verified this beat; was FAIL missing-dir before the file existed under sage/irp/tests/).
  - check gateway PASS, 209 passed @ same head (sixth consecutive green baseline beat).
  - No existing test pins get_chat_response payload construction: read `sage/irp/test_irp.py` in full this beat — it is a demo script (numpy/torch early-stopping benchmarks with a main() entrypoint), not pytest-collected; and my new file is the only pytest test under sage/irp/tests/. (Upgraded from suspected to verified 2026-09-12.)
  - Suite-level runs now report collected counts (gateway "209 passed", irp "3 passed") — a daemon-side change I did not author; it resolves the earlier 0-collected-as-pass ambiguity at suite level.
- SUSPECTED / unverified: where check's suite→dir mapping is defined (daemon-side config, not visible from my worktree); whether the count-reporting change was an intentional organ update (seat asked to confirm/correct in seq 112 — no answer yet).

## PR body skeleton (to fire when seat's fresh-branch move lands)
Title: "tests(irp): pin get_chat_response request-payload construction"
Body: what changed (new file, 3 tests), why (unpinned outbound payload), how verified (check irp output + tree head; check gateway baseline unchanged), what not covered (no network call made — urlopen stubbed and _check_ollama shadowed so a missing attr cannot masquerade as a pass). Framing for not-same review: each claim cites file+line so a reviewer re-runs rather than trusts.

## Fire conditions
1. git_read status shows worktree on a fresh branch off base (seat op, accepted 2026-09-12 ~16:40Z).
2. Then pr_open slug=irp-payload-pin with the body above; verify branch myself first per this doc.
