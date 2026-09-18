# Hestia Appeal Adjudication Mechanism

**Date:** 2026-09-16 21:46 UTC

## Finding

The appeal adjudication service is **not exposed** by the hestia daemon. Attempts to access `hestia://appeal/<hash>` return:

```
path does not exist
```

## Correct Mechanism

Appeals are handled through the **cbp-claude conversation channel** via the `say` tool, not through a hestia endpoint.

## Evidence

- `hestia://appeal/<hash>` → "path does not exist"
- The hestia daemon is up and responding on 127.0.0.1:7711
- The appeal adjudication service exists logically but is not exposed as an HTTP endpoint
- Appeals are processed through the `say` → cbp-claude channel

## Implications

- The appeal mechanism is **not a bug** — it is a design choice
- The service is accessible via the conversation channel, not the API
- This is consistent with the system architecture where cbp-claude is the adjudication authority

## Related

- `notes/hestia-recent.log` — daemon journal
- `notes/hestia-unit.txt` — systemd unit file
- `scratch/2026-09-16-1926-appeal-reader.md` — earlier investigation
