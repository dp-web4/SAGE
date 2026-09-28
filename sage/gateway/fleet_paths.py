"""Where this seat's shared-context checkout is -- derived, not assumed.

Four places hard-coded `~/ai-workspace/shared-context`: escalate.NOTE_DIR, and the forum defaults of
heartbeat, governed_turn and dp_console. That is the Linux seats' layout. McNugget keeps its repos in
~/repos, so on 2026-09-28 mcnugget-being's FIRST escalation was written into a directory that is not
a git checkout ("not a git repository ... commit by hand") and never reached the fleet, and every beat
read the forum from a place with no forum in it.

Resolution, first hit wins:
  1. $SAGE_SHARED_CONTEXT, when set: an explicit seat override;
  2. `shared-context` BESIDE this SAGE checkout -- the fleet's layout on every seat (it is how
     sage/scripts/being_hub_join.sh already finds web4), and exactly the old path on the Linux seats,
     whose SAGE lives at ~/ai-workspace/SAGE;
  3. ~/ai-workspace/shared-context, the old default, so a seat where neither exists behaves as before.
"""
import os
from pathlib import Path

_SAGE_ROOT = Path(__file__).resolve().parents[2]


def shared_context_root() -> Path:
    explicit = os.getenv("SAGE_SHARED_CONTEXT", "").strip()
    if explicit:
        return Path(os.path.expanduser(explicit))
    beside = _SAGE_ROOT.parent / "shared-context"
    if beside.is_dir():
        return beside
    return Path.home() / "ai-workspace" / "shared-context"


def forum_dir() -> Path:
    return shared_context_root() / "forum"


def escalations_dir() -> Path:
    return shared_context_root() / "escalations"
