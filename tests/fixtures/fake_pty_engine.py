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
    print(f"ECHO:{line}", flush=True)
