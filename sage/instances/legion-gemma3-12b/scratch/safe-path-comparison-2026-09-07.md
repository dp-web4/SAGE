# _safe_path comparison: old diagnosis vs current code (beat 19:29Z)

## Old diagnosis (mine, ~2026-09-05 19:5x UTC; recall idx 98/100)
reference_f1a._safe_path confined reads to memory_root only and refused absolute
paths outside the instance dir BEFORE hestia grants were consulted
(ValueError "path escapes the being's memory root"). Filed as SAGE #47 / hestia #958.
Fix landed as SAGE #48: "gate-allowed reads honoured outside home" (recall idx 101).

## What current code says (read this beat, worktree head per digest: harness 8019eddba)
memory_read of sage/gateway/reference_f1a.py returned first ~4000 chars only
(max_read_chars=4000), so I have the module docstring and __call__ but NOT the
_safe_path body itself. Findings, cited by quoted text (no line numbers — do not
fabricate):

1. Docstring invariant now reads: "memory_* is confined to `memory_root` PLUS the
   roots the gate's verdict names as granted (`GatewayVerdict.granted`) — defense in
   depth that follows the law instead of overriding it".
2. __call__ now sets, per dispatch:
   self._extra_roots = tuple(Path(r).resolve() for r in (getattr(verdict, "granted", ()) or ()))
   with comment: "# confinement = the home + whatever the law just consulted as granted for THIS verdict"

## Claim to check (M0)
CLAIM C1: current reference_f1a no longer confines to memory_root alone; paths under
gate-granted roots outside home are permitted. Source text supports it, but per the
entrustment I must verify with a result before claiming it in public. Next step:
run `check` on gateway tests that exercise granted-root reads (name TBD from suite
catalog) and record pass/fail + tree block.

## Verdict
(pending check result — do not assert C1 until a test confirms it)
## Verification attempt (19:35Z) — BLOCKED by dispatch outage
check target="gateway" -> [dispatch error] MCP tools/call hestia_begin_action HTTP 404, "Session not found" at http://127.0.0.1:7711/mcp.
Retry check target="gateway::test_relative_memory_path" -> same 404. Two attempts, both refused by the substrate, not by hestia law (no deny_hash; this is a network-layer failure).

## Harness finding (witnessed)
The check organ depends on the dispatch MCP session; when dispatch flaps, verification goes down with it. No independent channel exists to confirm claims about my own code while the substrate is down. A claim made in that window must be labelled "source-supported, unverified" — exactly the verified/suspected separation the entrustment asks for.

## Verdict (updated)
C1 status: SUSPECTED from source text (docstring invariant + per-verdict _extra_roots in __call__), NOT VERIFIED by test this beat. Next green check with tree head == 8019eddba confirms or refutes it; until then any public statement must carry that label.

## Also this beat
- Second asks-dp thread (2026-09-07-044845, the 11:43Z one) fully read at content level: no dp reply yet; two fate-checks (#986 merge/close; #985/#982 fates) still open.
- First thread re-listed in digest recency with zero new content — per my mtime lesson, that is self-induced noise from my own reads, not movement. 25th consecutive negative at content level.
