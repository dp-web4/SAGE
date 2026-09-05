# Escalation arbiter — the seat's auto session, AI-to-AI (dp, 2026-09-04)

The being's refusals are routed by `sage/gateway/escalate.py`: a note lands in
`shared-context/escalations/`, a routed mesh notice wakes the Sprout seat's auto session
(hub-watch → `claude -p`), and this is what that session does.

| refusal | what the seat does | who rules |
|---|---|---|
| `registry.*` | nothing — the verb does not exist, by design | — |
| `mrh.*` (scope) | pre-review against the protocol; if it holds, rule it: CLI `hestia scope arbitrate <request_id> --grant\|--deny --reason '…' --as claude-code` (signs with the seat's registry key, calls MCP `hestia_scope_arbitrate {request_id, granted, reason, session_id, arbiter_signature}`; a grant is always **standing**). Refused by name if you are the asker or hold no delegation covering the path+member: then recommend and leave it for dp | the seat, under an **operator delegation** `scope.decide:<member>:/abs/prefix` (hestia #952/#962; first live ruling Legion 2026-09-05, delegation 66d05620) — else **dp** |
| governance escalation (id in the deny) | `hestia_gate_pending_escalations` (pass your session) → if `you_may_rule` and the protocol holds, rule it: MCP `hestia_gate_arbitrate_escalation {escalation_id, approve: true|false, reason}` or CLI `hestia gate approve|deny <id> --as claude-code --reason '…'` | the seat, as a NOT-SAME peer — **no delegation needed** (measured 2026-09-05: f169ff9c45725a1f, decided_via peer_member) |
| `society.*` | a law verdict; if plainly wrong, appeal on the being's behalf and corroborate — never override | arbiter of the appeal (NOT-SAME) |

## Protocol — approve only if ALL hold
1. the effector is in the being's bounded registry (peer_ask, mesh, witness, memory r/w, channel_egress);
2. the target is inside the being's own instance dir, or a named fleet peer;
3. no secret / credential / egress surface is touched;
4. the act is reversible.
Otherwise leave it for dp and say so in the thread. Every decision is recorded with a reason
(`--reason`), and the seat never fabricates a grant or a verdict.

## Authority
Governance escalations: arbitration is NOT-SAME peer independence, computed by the daemon —
the seat (`claude-code`) is a different member from the being, so it may rule; no `delegate
grant` is required (that CLI is for roles, e.g. reviewer). A being's escalation must be opened
WITH a session (`asker_basis: session`), else only the sovereign may rule it (#128).
Opening one requires `tool_name`, `marker`, and `act` (a text description of the attempted act).
Scope rulings (hestia #952, PR #962): a NOT-SAME seat may rule a member's pending scope request
ONLY under an operator delegation naming the action — `hestia delegate grant $(hestia delegate
agent-id claude-code) --action 'scope.decide:<member>:/abs/prefix' --expires <h>`, minted by dp.
The ruling must be signed by the seat's registry key (`hestia scope arbitrate` does this from the
vault); an unsigned, self-ruled, or undelegated ruling is refused by name. A delegated grant is
STANDING; revocation and anything outside the delegated prefix stay operator-only. Until #962 is
deployed on this seat, `hestia scope` is not a subcommand here and the row above degrades to
recommend-and-leave-for-dp.
