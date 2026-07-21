import json
import stat
import sys
from pathlib import Path


def write_fake_cli(
    bin_dir: Path, name: str, exit_code: int = 0, stderr: str = ""
) -> None:
    """Write an executable fake CLI that records its argv to ``<name>_argv.json``.

    The fake script writes its argv (minus the script path itself) to a JSON
    file next to the script, then exits with the given code.  Tests can
    assert on the exact command line the framework built without spawning
    any real engine CLI.

    On Windows, an extensionless file with a ``#!`` shebang isn't something
    ``CreateProcess`` knows how to launch, and ``shutil.which`` -- which
    only matches ``PATHEXT`` extensions there -- skips right past it. That
    silently falls through to any *real* same-named CLI later on PATH
    (e.g. a real ``claude.exe``), so a ``.bat`` shim is written too, on top
    of the ``.py`` file carrying the actual logic.
    """
    body = (
        "import json, sys, os\n"
        f"out = os.path.join(os.path.dirname(__file__), '{name}_argv.json')\n"
        "with open(out, 'w') as f:\n"
        "    json.dump(sys.argv[1:], f)\n"
        f"sys.stderr.write({stderr!r})\n"
        f"sys.exit({exit_code})\n"
    )

    if sys.platform == "win32":
        py_script = bin_dir / f"{name}.py"
        py_script.write_text(body, encoding="utf-8")
        batch_shim = bin_dir / f"{name}.bat"
        batch_shim.write_text(
            f'@echo off\r\n"{sys.executable}" "%~dp0{name}.py" %*\r\n'
            "exit /b %ERRORLEVEL%\r\n",
            encoding="utf-8",
        )
    else:
        script = bin_dir / name
        script.write_text("#!/usr/bin/env python3\n" + body, encoding="utf-8")
        script.chmod(script.stat().st_mode | stat.S_IEXEC)


def recorded_argv(bin_dir: Path, name: str) -> list[str]:
    """Return the argv recorded by the fake CLI named ``name``."""
    return json.loads((bin_dir / f"{name}_argv.json").read_text(encoding="utf-8"))
