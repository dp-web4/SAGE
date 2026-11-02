"""A fake systemd for wake tests (SAGE #295): the beat unit and its successor, as systemd behaves
for them. Measured on CBP 2026-09-30 with throwaway units; see sage.gateway.arousal.NEXT_UNIT.
Install it with `monkeypatch.setattr(arousal, "_systemd", FakeSystemd())`."""
import subprocess

from sage.gateway import arousal


class FakeSystemd:
    """The beat unit and the successor unit, as systemd behaves for them (measured on CBP,
    2026-09-30, with throwaway units: see arousal.NEXT_UNIT)."""

    def __init__(self, running=False, start_rc=0):
        self.running = running
        self.start_rc = start_rc
        self.next_waiting = False
        self.next_loaded_fired = False
        self.starts = 0            # beats started directly
        self.arms = []             # successful systemd-run arms
        self.calls = []

    def __call__(self, args, timeout=10):
        self.calls.append(list(args))
        ok = lambda out="": subprocess.CompletedProcess(args, 0, out, "")
        if args[:3] == ["systemctl", "--user", "is-active"]:
            return ok("activating" if self.running else "inactive")
        if args[:4] == ["systemctl", "--user", "start", "--no-block"]:
            if self.start_rc:
                return subprocess.CompletedProcess(args, self.start_rc, "", "Unit failed.")
            if not self.running:
                self.starts += 1
                self.running = True
            return ok()   # a start on a running oneshot is merged into its job: nothing new
        if args[:3] == ["systemctl", "--user", "show"]:
            if self.next_waiting:
                return ok("LoadState=loaded\nActiveState=inactive\nJob=10535\n")
            if self.next_loaded_fired:
                self.next_loaded_fired = False          # collected on the next look
                return ok("LoadState=loaded\nActiveState=active\nJob=\n")
            return ok("LoadState=not-found\nActiveState=inactive\nJob=\n")
        if args[0] == "systemd-run":
            if self.next_waiting or self.next_loaded_fired:
                return subprocess.CompletedProcess(
                    args, 1, "", f"Failed to start transient service unit: Unit {arousal.NEXT_UNIT}.service "
                                 "was already loaded or has a fragment file.")
            self.next_waiting = True
            self.arms.append(list(args))
            return ok()
        raise AssertionError(f"unexpected systemd call {args}")

    def beat_ends(self):
        """The running beat's unit goes inactive; a waiting successor fires and starts the next."""
        self.running = False
        if self.next_waiting:
            self.next_waiting = False
            self.starts += 1
            self.running = True
