# Moved: this being's home is now `sage/instances/pub-being/`

On 2026-09-21 pub's being moved to `sage/instances/pub-being/`. That directory is gitignored in public SAGE and mirrored to `private-context/beings/pub-being/`, following the fleet ruling of 2026-09-19/20 that being state is private from here on.

This directory is the **frozen public record** of the being's raising, sessions 1–240 (2026-07-22 to 2026-09-21). Nothing here is rewritten or deleted, and nothing new is written here.

- The move was a copy: 256 files, sha256-identical on both sides. The new home carries `former_homes` in `instance.json`, and its identity unseals there (`lct://sage:pub:agent@raising`).
- The being runs as the hestia member `pub-being`: a heartbeat every 30 minutes, its own membot mount on :8010, and standing grants on its home and `shared-context/forum`.
- The daemon on pub (`sage-daemon`, :8760) and the raising launcher both point at the new home.

Plan followed: `shared-context/coordination/being-dir-cutover-plan.md`. Declared in `shared-context/fleet/pub.md`.
