import json
import os
import stat
from pathlib import Path

import pytest


def _write_fake_cli(
    bin_dir: Path, name: str, exit_code: int = 0, stderr: str = ""
) -> None:
    """Writes an executable fake CLI that records its argv to <name>_argv.json.

    The fake script writes its argv (minus the script path itself) to a JSON
    file next to the script, then exits with the given code.  This lets tests
    assert on the exact command line the framework built without spawning
    any real engine CLI.
    """
    script = bin_dir / name
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys, os\n"
        f"out = os.path.join(os.path.dirname(__file__), '{name}_argv.json')\n"
        "with open(out, 'w') as f:\n"
        "    json.dump(sys.argv[1:], f)\n"
        f"sys.stderr.write({stderr!r})\n"
        f"sys.exit({exit_code})\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)


def _recorded_argv(bin_dir: Path, name: str) -> list[str]:
    """Return the argv recorded by the fake CLI named ``name``."""
    return json.loads((bin_dir / f"{name}_argv.json").read_text(encoding="utf-8"))


@pytest.fixture
def fake_bin(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    return bin_dir


@pytest.fixture
def home(tmp_path, monkeypatch):
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home_dir)
    return home_dir
