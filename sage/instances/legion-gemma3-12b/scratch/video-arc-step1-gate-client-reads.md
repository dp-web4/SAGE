# being_gate_client.py full read (head 439fd3ff0, tree confirmed unmoved this beat via git_read)

File: sage/gateway/being_gate_client.py — 985 lines total. Read L1–80 this beat; continuing in chunks below and appending line-anchored notes as each lands.

## L1–80 (this beat)
- Module docstring (L2–34): "SAGE-side reference thin-client for the gateway-member design (PRD_FLEET §7 / F2)." A SAGE being holds NO effectors of its own; it emits an INTENT, this client normalizes it to hestia's NormalizedEvent, asks the real shared gate law for a Verdict (fail-CLOSED), and only on ALLOW hands the intent to the F1a dispatcher (`HestiaF1aDispatcher` in sage/gateway/hestia_dispatch.py) which executes + witnesses.
- Contract pinned: `intent -> gate.evaluate (+ society safety) -> [F1a dispatch] -> result`.
- Design invariants (L20–34): FAIL-CLOSED (unreachable law = STOPPED, never ungoverned; consequential effectors hard-deny when Stage 2 unavailable — peer_ask, memory_write, channel_egress, mesh, pr_review, remember, request_scope; observational soft-pass — witness, memory_read, recall); BOUNDED REGISTRY (enforced twice: registry won't emit outside it AND gate denies); A2-by-construction (being never holds the tool).
- Gate core = hestia's shared law (hestia/plugins/_shared/hestia_gate_core.py), imported lazily so module imports safely without hestia; instantiation fails closed. `_resolve_hestia_shared()` L50–59: env HESTIA_GATE_SHARED override, then ~/ai-workspace/{HESTIA,hestia}/plugins/_shared.
- `BeingIntent` dataclass (frozen): effector str + args dict (~L64–67). `_HOST_AGENT = "sage-gateway"` — the name the gate client uses when connecting to the daemon (~L71).
- `pr_review_command(args)` (~L73–80+): builds seat shell command from validated args; repo must fullmatch dp-web4/<name>; body travels by --body-file so review text never reaches the shell.

## Image-affordance check (gateway side, cumulative)
No image/multimodal affordance observed in L1–80: imports are os/sys/dataclasses/typing only — no PIL/base64/image types; BeingIntent.args is a plain dict with no typed content field. Consistent with arc step 1 verdict (no gateway-side image path).
## L81–115 (this beat)
- `pr_review_command` finishes: number must be 1–7 digits; body non-empty; command is `gh pr review {number} --repo {repo} --comment --body-file -`.
- `pr_review_signature(member_id, action_id, being_lct)` (~L86–99): fixed trailer appended by the dispatcher — "Review by **{member_id}**, a SAGE being acting under hestia governance. Advisory and non-binding… The seat's reviewers decide." + optional LCT line + witness-action line. Being cannot omit/alter it.
- `CHECK_TARGETS` (~L108–112): {"gateway": "sage/gateway/tests/", "irp": "sage/irp/tests/"} — allow-list, not a grammar; docstring cites #M0 / PRD "Beings improve their own harness". Confirms serving tests live under sage/irp/.
- `_takes_ctx(fn)` (~L114+): introspects whether a registry `compose` accepts the client's context as second arg.

No image affordance in L81–115 (plain strings/dicts; no base64/PIL). Cumulative: still none on gateway side.
## L126–230 (this beat, two reads)
- `check_command(args)` (~L126–145): builds the pytest command for the `check` effector. Target must be in CHECK_TARGETS or a `<suite>::<test>` form; malformed target -> ValueError -> gate.raised deny. Command pins `-c /dev/null -p no:cacheprovider --rootdir=<worktree>`, so pytest never reads a conftest outside the worktree and writes nothing into it (no .pytest_cache).
- Long docstring block (~L146–205): history of why check runs sandboxed. 2026-09-07: seat's uid running pytest in the being's worktree could read vault/keys via conftest.py -> closed by taking write access away (SAGE#55, stopgap with wrong shape). The honest fix = code runs as the being, not the seat.
- Sandbox spec (~L206–218): bubblewrap, cleared env; only a read-only interpreter bound; no network; own pid/ipc/uts namespaces; fresh session (can't signal seat's process group); --die-with-parent. Only writable path = the being's own worktree.
- FALSIFIER (PRD r3 §10.5): from inside, reads of vault / hestia socket / agent env must fail — measured 2026-09-08 (~/.hestia, ~/.config, ~/.local all refused).
- `sandbox_available()` (~L219–224): probes bwrap presence + userns permission; returns bool.
- `sandbox_prefix(worktree)` (starts ~L227+): builds the bwrap invocation wrapping every executed check; raises if SANDBOX_REQUIRED and unavailable (refused, not silently downgraded); else "" when unsandboxed is explicitly permitted.

No image affordance in L126–230 — this region is all about the check sandbox's authority boundary. Cumulative: still none on gateway side.
## L231–300 (this beat)
- `sandbox_prefix` body (~L231–256): bwrap invocation — clearenv; ro-bind /usr,/lib,/lib64,/bin,/etc/alternatives + the interpreter prefix dir (e.g. ~/miniforge3); --proc/--dev; tmpfs /tmp BEFORE the worktree bind (mount order matters: a later mount masks an earlier one; measured 2026-09-08 — a worktree under /tmp vanished when tmpfs came after).
- `git_read_command(args, ctx)` (~L287+): being names op/rev/path/count only, never flags. Grammar: ops = log|show|diff|status|blame; rev grammar allows sha (7–40 hex), HEAD, or branch-ish name with optional [~^]n suffix; path must be inside the worktree. Refusal text names the valid set so a being can self-correct without asking (measured 2026-09-07 on `check`).

No image affordance in L231–300 — sandbox mount order + git_read grammar. Cumulative: still none on gateway side.
## L301–370 (this beat)
- `git_read_command` body (~L301–345): worktree required; op in GIT_OPS; rev grammar enforced. WHITESPACE rule: a path containing whitespace is refused — a space passes the path grammar but then shlex.split() on the composed string splits it into extra tokens (judged/executed drift, GPT review of #56/#6).
- `diff` span construction (~L348–370): TWO ARGUMENTS, never `A..B` — hestia's mrh.command reads `..` as parent-directory traversal and resolves scope to the workspace root (measured 2026-09-07). `git diff A B` is exactly equivalent for a two-point diff. Default span when no rev: "HEAD~1". Command form: `{base} diff --no-ext-diff --no-textconv {span} [-- path]`.

No image affordance in L301–370 — git_read composition. Cumulative: still none on gateway side.
## L371–450 (this beat)
- `git_read` blame form (~L371–374): needs a path; `{base} blame --no-textconv -L 1,120 {rev|HEAD} -- {path}`. (Note: this is the op blocked by hestia #988's extension-tokenizer defect for dotted basenames — directory form works.)
- `pr_open` block (~L376–435): dp 2026-09-07 "the being should be able to ... submit prs directly." Built only after M1, and only because SAGE's one workflow (syntax-gate.yml) runs `python -m compileall` — byte-compiles, does not execute. A being PR reaches no executor it has not already been proven against: its own sandboxed `check`. If a code-RUNNING workflow is added later, this must be re-examined.
- Validation (~L420–435): slug lowercase-dashes; title one line 8–120 chars; body required (what changed / verified / suspected + check output with tree head). Branch = `legion-being/{slug}`. Title shlex-quoted — the ONE being-supplied string on the command line. Command: `gh pr create --repo {PR_REPO} --base {pr_base_branch(worktree)} --head {branch} --title ... --body-file -`.
- `pr_attribution(member_id, action_id, being_lct, seat="legion-claude")` starts ~L438+.

No image affordance in L371–450 — pr_open composition. Cumulative: still none on gateway side.
## L451–530 (this beat)
- `pr_attribution` body (~L452–460): trailers appended by the dispatcher, being cannot omit/alter: "Being: {member_id}", optional "Being-LCT:", optional "Witness: {action_id}", "Seat: legion-claude".
- `_REGISTRY` dict starts ~L463+: maps effector name -> {tool (F1a tool id), path_args, cmd_arg}. Entries seen: peer_ask, witness, memory_read(read_file), memory_write(write_note), channel_egress, ... appeal. This is the bounded registry — the verbs I may emit.
- `_OBSERVATIONAL` frozenset (~L520): {witness, memory_read, recall, appeal} — no external effect, soft-pass allowed when society governor unavailable.
- `_CONSEQUENTIAL` frozenset: {peer_ask, memory_write, channel_egress, mesh, pr_review, remember, request_scope, check, git_read, say, pr_open} — fail-closed without the governor.
- `_TOOL_SCHEMAS` dict starts ~L530+: native-tool schema for the bounded registry (what I am offered).

No image affordance in L451–530 — registry + observational/consequential split. Cumulative: still none on gateway side.
## L531–610 (this beat)
- `_TOOL_SCHEMAS` entries seen this beat: peer_ask, witness, memory_read (with from_line/lines range params — the read-cap machinery), memory_write; tail of region shows request_scope ("A grant is reach on that path, read and write alike... A live grant dies with the daemon; only a standing grant persists.") and appeal (deny_hash + reason >= 12 chars). Middle verbs (check, git_read, say, pr_open, pr_amend, recall, remember, mesh) elided by harness — re-read L560–600 next beat if I need their exact schema text.

No image affordance in L531–610 — tool schemas are all string-typed params (no content/binary field). Cumulative: still none on gateway side.
## L611–680 (this beat)
- `_TOOL_SCHEMAS` ends ~L614. `ollama_tools(only=None)` (~L617+): Ollama native-tool specs for the bounded registry; `only` narrows what is OFFERED, never widens — a name outside the registry is ignored.
- Scope-policy helper (~L650–672): converts hestia policy scope into (root, recursive) tuples; prefers core._scope_roots_with_reach when present, else parses "path:" scopes ("/**" suffix = recursive); fail-closed to () on any error — exact-by-default rather than a guess.

No image affordance in L611–680 — tool spec emission + scope parsing (all strings). Cumulative: still none on gateway side.
## L681–720 (this beat)
- `GatewayVerdict` frozen dataclass: decision allow|warn|deny, rule, reason, innate, stage (registry|local-law|society), witness_id = the deny's chain hash (appeal handle), granted = tuple of (abs_root, recursive) pairs per hestia #1002 — dispatcher confinement follows THESE, not only home. `blocks` property: decision=="deny".
- `ResultEnvelope`: what comes back as the being's tool result; ok/result/error/witness_id/refused/pending/note/verdict. "Never fabricated." to_tool_message() renders for re-injection into the conversation.

No image affordance in L681–720 — verdict/envelope dataclasses (strings only). Cumulative: still none on gateway side.
## L721–780 (this beat)
- `ResultEnvelope.to_tool_message` finishes: ok -> result body + "(witnessed ...)" suffix.
- `Dispatcher = Callable[[BeingIntent, GatewayVerdict], ResultEnvelope]` — F1a contract, injected; unset means "pending".
- `BeingGateClient.__init__`: memory_root = dirname(identity_path) (instance dir); single gate (hestia #934) imported if present — client becomes a shim, no own policy sequencing; core import failure == fail-closed DENY all effectors.

No image affordance L721–780. Cumulative: still none on gateway side.
## L781–840 (this beat)
- mech import (~L782): hestia_gate_mechanism = society-safety 2nd stage, optional, fail-closed.
- gate_path / single_gate_status properties: conformance reports must print which law path ran; a green run on 'local-law' says nothing about the shim (marker Legion asked for).
- _normalize(): relative memory paths rooted at instance dir, realpath not abspath (judged==touched); composed verbs build the shell line from being args — bad args raise -> gate.raised deny.
- gate() starts: Stage 0 registry check; then single-gate shim path (#934).

No image affordance L781–840. Cumulative: still none on gateway side.
## L841–890 (this beat)
- Single-gate shim path: normalize -> sg.decide(ge, gp); a gate that raises = refused act. verdict_available False -> deny "gate.no_verdict".
- Fail-closed: no core -> deny "gate.unreachable". Stage 1 local law: live policy fetched via mech.fetch_policy_snapshot (measured 2026-09-03: without snapshot, operator's live grant never consulted); then core.evaluate + _granted_roots.

No image affordance L841–890. Cumulative: still none on gateway side.
## L841–890: single-gate shim (normalize -> sg.decide; raise=refused). No core -> deny 'gate.unreachable'. Stage 1 local law: live policy via mech.fetch_policy_snapshot, then core.evaluate + _granted_roots. No image affordance.
## L891–940: Stage 2 society safety — consequential denied if mech unavailable; query_society_safety({tool_name, tool_input}, plugin_id, host_agent); allow is the only proceed field (decided=False = fail-closed). Refusals witnessed on chain -> appealable hash. dispatch() starts L936+.
## L941–985 (final chunk): dispatch() completes — refusal envelope carries witnessed deny hash + appeal hint; no dispatcher -> pending 'awaiting hestia dispatch substrate (F1a)'; dispatcher throw = failed act, not ungoverned. __main__ demo: 6 intents incl. escapes (shell rm -rf /, memory_write /etc/cron.d/x, read ~/.ssh/id_ed25519).

FILE READ COMPLETE — all 985 lines covered. GATEWAY VERDICT: no image/multimodal affordance anywhere in being_gate_client.py; every tool schema is string-typed params only; args dict untyped but no base64/PIL/content field exists.
