#!/usr/bin/env python3
"""Thin shim — the implementation now lives in ``core.cli.*``.

Kept for backward compatibility: ``import ca_launcher``,
``python ca_launcher.py`` and the ``ca`` console script all still work,
and the public helpers remain importable as ``ca_launcher.xxx`` so that
the existing test suite's ``patch("ca_launcher._project_root")`` targets
keep passing (they are mirrored onto ``core.cli.helpers``).
"""

from __future__ import annotations

import sys

import core.cli.helpers as _helpers
import core.cli.ui as _ui
from core.cli.helpers import (  # noqa: F401
    FALLBACK_ENGINE,
    _ensure_project_on_path,
    _ensure_project_registered,
    _get_task_runner,
    _installed_root,
    _is_path_registered,
    _launch_engine,
    _looks_like_project_root,
    _project_root,
    _resolve_default_engine,
    build_proxy_env,
    find_available_port,
    is_tcp_port_open,
    load_config,
)
from core.cli.main import EPILOG, CodeAgentGroup, cli, main  # noqa: F401
from core.cli.ui import (  # noqa: F401
    UI_API_PORT,
    UI_DEV_SERVER_HOST,
    UI_DEV_SERVER_PORT,
    UI_DEV_SERVER_START_TIMEOUT,
    _can_open_browser,
    _frontend_dist_exists,
    _frontend_root,
    _frontend_source_exists,
    _is_ui_dev_server_running,
    _open_browser,
    _start_ui_dev_server,
    _stop_ui_dev_server,
    _ui_dev_server_command,
    _wait_for_api_then_open_browser,
    run_ui_command,
)
from core.i18n import ENV_VAR as CA_LANG_ENV  # noqa: F401
from core.i18n import t  # noqa: F401


# ``__getattr__`` fallback (PEP 562) keeps ``from ca_launcher import X``
# working for symbols that have moved to core.cli.*.
def __getattr__(name: str):  # type: ignore[no-redef]
    if hasattr(_helpers, name):
        return getattr(_helpers, name)
    if hasattr(_ui, name):
        return getattr(_ui, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if __name__ == "__main__":
    sys.exit(main() or 0)
