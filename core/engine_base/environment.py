import os
import signal
import sys
from pathlib import Path


def register_signal_handler() -> None:
    """Install a SIGTERM handler that triggers a clean exit.

    The handler raises ``SystemExit`` via ``sys.exit()``, which ensures
    ``finally`` blocks execute — so per-engine cleanup (restore settings,
    remove symlinks, …) runs before the process terminates.  SIGKILL
    cannot be caught, but this covers the common case of OS/service-manager
    shutdown and manual ``kill <pid>``.
    """

    def _sigterm_handler(signum: int, frame: object) -> None:
        sys.exit(128 + signum)

    signal.signal(signal.SIGTERM, _sigterm_handler)


class EngineExecutionError(Exception):
    """Raised when an engine subprocess exits with a non-zero return code."""


class EnvironmentManager:
    """Manages environment variables for the CodeAgent execution environment.

    Attributes:
        root_dir (Path): The root directory of the CodeAgent project.
    """

    def __init__(self, root_dir: Path):
        """Initializes EnvironmentManager with the project root directory.

        Args:
            root_dir (Path): The root directory of the CodeAgent project.
        """
        self.root_dir = root_dir

    def get_env(self) -> dict:
        """Returns a copy of the current environment variables with CodeAgent specific variables added.

        Returns:
            dict: A dictionary containing environment variables, including 'CODEAGENT_PATH'.
        """
        env = os.environ.copy()
        env["CODEAGENT_PATH"] = str(self.root_dir.absolute()).replace("\\", "/")
        return env
