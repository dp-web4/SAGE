# Caps on a being's units (#834, S1.5)

Drop-ins that cap and attribute a being's own units while they still run as the operator. With them in place, a
runaway beat is killed alone, inside its own cgroup, and the shared model server and hestia keep running. Without
them, the kernel's global OOM killer picks the largest process on the machine, which is usually the model server
(11-24..26: 27 kills from one whole-file read, #832). When the being has its own account (S4), the same numbers move
to its `user-<uid>.slice`.

The numbers are measured per machine, never fleet-wide. Each file names where its numbers came from.

**Sprout, 2026-11-28 (22 beats, systemd MemoryPeak, file cache included):** beat peak 547–694 MB, median 620 MB, at
most 11 tasks. Daemon 89 MB. Memory server 113 MB. Before #832 a beat peaked at about 1.1–1.3 GB.

- `MemoryHigh` is where the kernel starts reclaiming and throttling the unit. For the beat it is about 1.3× the
  measured peak.
- `MemoryMax` is where the unit alone is killed. For the beat it is about 1.7× the measured peak. The daemon and
  the memory server are small and steady, so they get more relative headroom (about 3×) at little absolute cost.
- `MemorySwapMax` keeps a capped unit from moving its overage into swap and slowing the whole machine.
- No `CPUQuota`: a beat spends about 30 s of CPU in 5–20 min of wall time. The model's compute is the model
  server's, which is shared and sits outside these units.

## Install (operator, one line)

    for u in sage-heartbeat sage-daemon membot-sprout; do mkdir -p ~/.config/systemd/user/$u.service.d && cp sage/gateway/systemd/caps/$u.caps.conf ~/.config/systemd/user/$u.service.d/caps.conf; done && systemctl --user daemon-reload

The heartbeat's cap applies from its next beat. A running daemon or memory server picks up its cap at its next
restart (or `systemctl --user restart <unit>` in a quiet moment).

## Check

    systemctl --user show sage-heartbeat sage-daemon membot-sprout -p Id -p MemoryHigh -p MemoryMax -p MemoryPeak

A kill by a cap shows in the kernel log as `Memory cgroup out of memory: Killed process` (the global killer writes
`Out of memory: Killed process`). Count the two separately.

## Undo

    rm ~/.config/systemd/user/sage-heartbeat.service.d/caps.conf ~/.config/systemd/user/sage-daemon.service.d/caps.conf ~/.config/systemd/user/membot-sprout.service.d/caps.conf && systemctl --user daemon-reload
