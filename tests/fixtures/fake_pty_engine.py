"""A stand-in for a CLI engine, used by test_pty_router.py.

Ignores its argv (the real ca_launcher.py takes an engine name there) and
just echoes stdin lines back, so tests can exercise the PTY plumbing without
spawning a real provider CLI.
"""

import sys

print("READY", flush=True)
for line in sys.stdin:
    line = line.rstrip("\n")
    if line == "exit":
        break
    if line == "burst":
        # Small enough to fit in the kernel's PTY output buffer without
        # blocking on backpressure (which would otherwise force us to
        # drain concurrently, masking the race), then exit immediately
        # with no flush delay -- exercises the race between the process
        # dying and pty.py still draining buffered output.
        sys.stdout.write("X" * 2_000 + "\nBURST_DONE\n")
        sys.stdout.flush()
        sys.exit(0)
    print(f"ECHO:{line}", flush=True)
