"""A stand-in for a CLI engine, used by test_pty_router.py.

Ignores its argv (the real ca_launcher.py takes an engine name there) and
just echoes stdin lines back, so tests can exercise the PTY plumbing without
spawning a real provider CLI.
"""

import os
import subprocess
import sys

print("READY", flush=True)
for line in sys.stdin:
    line = line.rstrip("\r\n")
    if line == "exit":
        break
    if line == "pid" or line.startswith("pid "):
        # tmux 承载下重连是否回到同一个引擎进程，靠这个判断。带 nonce 的
        # 形式用于区分"刚打印的"与"重连重绘出来的旧输出"。
        nonce = line[4:].strip()
        suffix = f":{nonce}" if nonce else ""
        print(f"PID:{os.getpid()}{suffix}", flush=True)
        continue
    if line == "spawn-grandchild":
        # The real launcher execs the provider CLI as its own child, so the
        # engine the user sees is a *grandchild* of the PTY session. Stand in
        # for it with a sleeper whose pid the test can watch.
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
        print(f"GRANDCHILD:{child.pid}", flush=True)
        continue
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
