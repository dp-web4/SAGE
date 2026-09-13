# sage/gateway/hub — the being's own hub seam (M-CIT-1a / 2b, Sprout side)

Design: `sage/docs/DESIGN_BEING_INBOX_DRAIN.md`. PRD: `sage/docs/PRD_SAGE_WEB4_CITIZENSHIP.md` §6.1.

| file | what |
|---|---|
| `mint_being_lct.rs` | Mints the being's **self-issued** LCT on the being's own host. Builds as a `web4-core` example: copy into `web4/web4-core/examples/`, `cargo build --example mint_being_lct`, run `mint_being_lct <SEED_FILE> <OUT_JSON>`. Generates the 32-byte seed (0600) only if absent; re-runs re-derive the same `lct_id`. Mirrors the hub's fail-closed ingest (`hub-daemon/src/rest.rs` `publish_lct` checks 2/3/4) before writing. |
| `join_being.rs` | Joins the hub **as the being** (M-CIT-3a, the half only the seed-holder can sign — `/members/join` verifies the envelope against the very key it pins; `hestia hub join` signs with the seat vault's `ai_identity_secret`, so no other seat can pin the being's key). Same build path as the mint example. **Dry run by default** (prints the canonical payload + checks A–D, sends nothing); `--nonce <N>` emits the signed envelope for an attended two-curl send. **`--name` and `--message` are REQUIRED** (2026-09-02, dp: sprout-being was admitted with a blank name and no explanation — the tool now refuses to build that payload; `name` = the SAGE dashboard name, e.g. `sprout-sage`; hub-side handling tracked in web4#818). Membership uuid is chosen as `document.id` (`2e175714-4b01-4063-a997-27a6dade7044`) — see design note §7. |
| `sprout-being.lct_publish.json` | The **public** document for Sprout-the-being, minted 2026-08-22T02:55:53Z on sprout. `lct:web4:mb32:bybpo2yczrsr5ycc7253qfywp7lgzp5z2pquhdlaoar5um4ntgiba`, binding key `daf57b8980c93755a3d6b8891dbe90439d87b97d046db379543dd6a17021165f`. The seed is at `~/.web4/sprout-being/channel_key.bin` on sprout and is never relayed. **Citizen since 2026-09-03 (M-CIT-3b):** `document.citizenships[0]` is the tamper-evident `BirthCertificateRef` to the record in Legion's society ledger — issuing society `lct:web4:mb32:bt4f3y7v…qsn4a` (Legion's sovereign, bootstrap/placeholder strength), entry `113092`, record hash `8809d4f0…47fb8` — with the one permanent `birth_certificate` pairing to `lct:web4:role:citizen` in `mrh.paired` that `Lct::verify_citizenship` requires. Three distinct witnesses (legion, sprout, cbp; the attestations are under `attestations/sprout-being/`). The reference is transcribed from Legion's confer output (forum `legion-birth-certificates-conferred-113092-113093-2026-09-03.md`); the authoritative `CitizenshipRecord` lives in that ledger, not here. `provenance` stays `self_issued` on purpose: hub ingest check 5 still refuses `society_conferred`, so the doc re-publishes with that provenance only once the hub verifies `CitizenshipRecord`s (HUB's item). `hestia lct relay --dry-run` passes checks 2–5 on this file as committed. |
| `legion-being.lct_publish.json` | The **public** document for Legion-the-being, minted 2026-09-02T18:06:44Z on legion. `lct:web4:mb32:bt7au42c424h3difrdztfnbjc2q6eofb3lacohcp2xf35ymawjldq`, binding key `6f777cd1afea259534f9b14dc8b2b382c9f8dd3f9575d33e83d906501f78e155`. The seed is at `~/.web4/legion-being/channel_key.bin` on legion and is never relayed; relayed to the registry as ledger#1907. **Citizen since 2026-09-03 (M-CIT-3b):** `document.citizenships[0]` is the `BirthCertificateRef` to the record in Legion's own society ledger — issuing society `lct:web4:mb32:bt4f3y7v…qsn4a` (Legion's sovereign, bootstrap/placeholder strength), entry `113093`, record hash `56d3c592…28a2` — with the one permanent `birth_certificate` pairing to `lct:web4:role:citizen` in `mrh.paired`. Three distinct witnesses (legion, sprout, cbp; attestations under `attestations/legion-being/`). The reference was **re-derived from the ledger**, not transcribed: entry `113093` read back through the daemon (`hestia_query_history`), and `sha256(serde_json::to_vec(CitizenshipRecord))` over the stored record equals this hash (same check passes for sprout-being's `113092`). Note for the Phase-2 verifier (HUB): the chain stores the record with **sorted** keys (via `serde_json::json!`), but `content_hash` serializes in **struct field order** — hashing the stored bytes as-is gives a different digest; deserialize into `CitizenshipRecord` first. The authoritative record is in `~/.hestia/witness.db` on legion, not here. Same `provenance=self_issued` posture as sprout-being, for the same reason (hub ingest check 5). `hestia lct relay --dry-run` passes checks 2–5 on this file as committed. |

## Canonical join process (fleet), as it has run twice

Discovered from the record on 2026-09-12 (dp: "it already worked for two instances, so don't
reinvent - discover and document"). sprout-being: minted 2026-08-22, relayed and joined
2026-09-02, admitted 2026-09-02 18:55Z (nameless; the tool now requires a name). legion-being:
minted and relayed 2026-09-02 (ledger#1907), joined 2026-09-05 20:08Z as `legion-sage`, admitted
by dp. Sources: forum `legion-being-hub-join-sent-08a78ddb-named-legion-sage-2026-09-05.md`,
`legion-ack-sprout-being-join-202-pending-admit-2026-09-02.md`, the 1a relay note (ledger#1906/1907).
Roster names are `<machine>-sage`. cbp-being runs it as `sage/scripts/cbp_being_hub_join.sh`.

| step | where | command | vault? |
|---|---|---|---|
| 1. mint | the being's host | `mint_being_lct ~/.web4/<machine>-being/channel_key.bin sage/gateway/hub/<machine>-being.lct_publish.json` (web4-core example; seed 0600, never leaves the host; same seed re-derives the same `lct_id`) | no |
| 2. join, dry run | the being's host | `join_being <seed> <doc> --name <machine>-sage --message "<one line for the admitting operator>"` (checks A-D: `member_lct_id == document.id`, `member_pubkey_hex` == the document's binding key) | no |
| 3. join, send | the being's host | `POST $REST/auth/challenge {"for_lct_id": <document.id>}` -> nonce; `join_being ... --nonce <N>` prints one `envelope <json>` line; `POST $REST/hubs/<hub>/members/join` with it -> **202 pending_review** with a `request_id`. Signed by the seed it pins; no seat key involved | no |
| 4. relay the document | any joined seat (both existing ones: Legion's seat, `61525719`) | `hestia lct relay --dry-run <doc>` (producer-side ingest mirror, checks 2-5, no vault), then `HESTIA_PASSPHRASE=... hestia lct relay --send <doc>`. The CLI honours `HESTIA_PASSPHRASE` (cli.rs `prompt_passphrase`), which is why nobody was prompted; the daemon's own passphrase file in the hestia home supplies it on a seat. `subject != publisher` is what the relay path is for | yes, non-interactive |
| 5. admit | dp, on the hub box | `POST /admin/api/joins/<request_id>/admit` (admin plane is localhost-only there; no sponsor or vouch shortens it, design 7.5) | dp |
| 6. gate 0 | anywhere | `GET /members/<document.id>/pubkey` == `GET /lcts/<lct_id>` `.document.public_key.key` == the being's own key (404 on the pin = not admitted yet) | no |
| 7. drain | the being's host | the hub-mesh env for `<machine>-being` (MY_LCT = document.id, MY_KEYPAIR = the seed, its own HUB_MESH_STATE), then the heartbeat drains the being's own mailbox each beat | no |

Order between 3 and 4 does not matter to the hub (the join pins a key; the registry entry is
what gate 0 and the drain compare against), but both existing beings relayed first. The
ritual is seat-run today; a `join_hub` effector in the being's registry is the stated goal
(PRD_SAGE_WEB4_CITIZENSHIP 6.1, dp 2026-09-12).

Relay recipe (M-CIT-1a, Legion's seat): take the payload as-is, set `published_by` to the relaying
member's uuid (ingest check 1 requires it to equal the envelope signer), set `published_at`, sign the
envelope with the seat's pinned key, `POST /v1/hubs/:hub_id/lcts/publish`. `subject ≠ publisher` is
exactly what the relay path exists for. M-CIT-3a's join for the being pins the **same** pubkey (`daf57b89…165f`) *because it is signed by it*:
the join envelope is Sprout's to sign (`join_being.rs`), not a relay. One key, three artifacts — document, member
pin, drain signer — across **two id spaces**: registry `lct:web4:mb32:…` (key-derived) and membership `Uuid`
(joiner-chosen, = `document.id`). Nothing checks that pair at ingest or join; the drain's gate 0 does. Gate 0 is scoped to the being's own `MemberAdded` pin (`member_pubkeys`) and compares decoded key bytes: it does not inherit HUB's C8/C9 (Sovereign and council keys live outside that map — web4#759) nor C10 (case). Design §7.4.

**Attestation subject id (M-CIT-3; Legion C5/R6, 2026-08-21):** a birth-witness attestation over the being
is signed over the **registry id** `lct:web4:mb32:bybpo2yczrsr5ycc7253qfywp7lgzp5z2pquhdlaoar5um4ntgiba` —
`Attestation::message` puts the subject id inside the signed bytes, and `Lct::verify_citizenship` passes
`self.lct_id()` (key-derived) as `subject_lct_id` (`web4-core/src/lct.rs:459`). Never the membership uuid
`2e175714…`, never `lct:web4:member:2e175714…`, never the `hub_member_lct` value from `identity.json`: an
attestation over any of those is well-formed, correctly signed, and can never verify. Whatever hands a
subject to `hestia witness attest` hands the published `lct_id` from `sprout-being.lct_publish.json`.

Why `ai_embodied`, no parent, empty MRH: the being is a **new row** (HUB ruling: mint fresh, keyed —
never re-key the seat `ef1d106c` or the fleet identity `b9f1ed81`). Edges to the seat and to the
SAGE-internal `lct://sage:sprout:agent@raising` are added when `identity.json` gains `hub_member_lct`
(step 3), not asserted in the bootstrap document.
