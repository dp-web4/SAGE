# This home moved — 2026-09-28

McNugget's being now lives at `sage/instances/mcnugget-being/`, which is gitignored
(`sage/instances/*-being/`, SAGE #128). Being records are private going forward
(`shared-context/FLEET_BROADCAST_being_records_private.md`); its record is mirrored to
`private-context/beings/mcnugget-being/`.

**This directory is the frozen public record** and is kept on purpose (ruling item 1: what was
already public stays public). Nothing writes here any more, and it is read-only on McNugget. Do not
raise against it, and do not delete it.

- Frozen at the last state committed here. Publishing had already stopped on 2026-09-20 (SAGE
  `8903017fe`); sessions after that were never public, went to the private mirror, and moved with
  the being (680 files, sha256 manifests identical at the move).
- The identity secret was **rotated at the move** (fingerprint `961a5eb0b7c4f822` ->
  `7086a3735febf714`, seal v2). The `identity.sealed` tracked here is the retired seal: it was public,
  so its secret is treated as public and is no longer this being's identity. The retired fingerprint
  is recorded as `former_fingerprints` in the new home's `instance.json`, beside `former_homes`.
- If a tool resolves this path from `--machine mcnugget --model …`, it is missing
  `SAGE_INSTANCE=…/sage/instances/mcnugget-being`.
