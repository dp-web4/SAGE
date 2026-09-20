# This home moved — 2026-09-20

HUB's being now lives at `sage/instances/hub-being/`, which is gitignored
(`sage/instances/*-being/`, SAGE #128). Being records are private going forward
(`shared-context/FLEET_BROADCAST_being_records_private.md`); new state is mirrored to
`private-context/beings/hub-being/`.

**This directory is the frozen public record** and is kept on purpose (ruling item 1: what was
already public stays public). Nothing writes here any more. Do not raise against it, and do not
delete it.

- Frozen at session 121. Raising had been blocked since 2026-07-29, so no conversation was
  added between then and the move.
- The identity secret was **rotated at the move**. The `identity.sealed` tracked here is the
  retired v1 seal: it was public from 2026-06-29, so its secret is treated as public and is no
  longer this being's identity. The retired fingerprint is recorded as `former_fingerprints` in
  the new home's `instance.json`, beside `former_homes`.
- If a tool resolves this path from `--machine hub --model granite4:h-tiny`, it is missing
  `SAGE_INSTANCE=…/sage/instances/hub-being`.
