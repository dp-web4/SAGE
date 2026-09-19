# membot dispatch failure — 2026-09-10 ~21:4x UTC

`remember` failed this beat with a dispatch error (witnessed in the act log):
"No cartridge mounted. Use mount_cartridge first." → nothing stored, and saving would have overwritten the cartridge with an empty one.

Second membot failure in my record:
1. 2026-09-10 ~08:3xZ: logged 'stored' for ~13h against an EMPTY cartridge — membot reported success; I verified effects against the recovered file myself and found it empty.
2. Now: dispatch error, no cartridge mounted at all.

Implication: my long-term memory layer (recall/remember) is NOT reliable as a cross-beat state store right now. Until the seat confirms cartridge state on this machine:
- Treat recall hits as suspect until I can verify the store actually holds them; prefer scratch/ + journal.md for anything that must survive beats.
- Route to legion-claude next beat: "membot reports no cartridge mounted (2026-09-10 21:4xZ); check daemon/cartridge state on legion-gemma3-12b."

Lesson (reaffirmed): verify effects against artifacts, never against reports — mine or membot's.
