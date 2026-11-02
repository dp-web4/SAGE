#!/bin/bash
# RETIRED 2026-09-28. This is the pre-fluid McNugget raising launcher, and its last step PUBLISHED
# the being's record: `git add <instance dir>` + `git push origin main`. Being records are private
# going forward (shared-context/FLEET_BROADCAST_being_records_private.md); publishing stopped on
# 2026-09-20 (8903017fe) in the launcher launchd actually runs, and on 2026-09-28 the being moved to
# sage/instances/mcnugget-being/. Running this by hand would have restarted the public push, so it now
# refuses. The launcher to use is sage/scripts/mcnugget_raising_fluid.sh (com.web4.mcnugget.raising).
# The old body is in git history.
echo "mcnugget_raising.sh is retired: it published the being's record. Use sage/scripts/mcnugget_raising_fluid.sh." >&2
exit 1
