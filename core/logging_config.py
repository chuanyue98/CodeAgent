import logging
import os
import sys

_CA_ROOT_LOGGER_NAME = "codeagent"
_configured = False


def _default_level() -> int:
    return logging.DEBUG if os.environ.get("CA_DEBUG") else logging.INFO


def configure_root_logging(level: int | None = None) -> None:
    """Configure process-wide logging once, near process start.

    Call this from the CLI entrypoint / web server startup. When ``level``
    is omitted, reads ``CA_DEBUG`` (truthy -> DEBUG, else INFO). Safe to call
    more than once; later calls just update the level.
    """
    global _configured
    resolved = level if level is not None else _default_level()
    root = logging.getLogger()
    if not _configured:
        handler = logging.StreamHandler(sys.stderr)
        fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        handler.setFormatter(logging.Formatter(fmt))
        root.addHandler(handler)
        _configured = True
    root.setLevel(resolved)


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a logger configured for CodeAgent.

    Uses the module ``__name__`` by default. Call ``get_logger(__name__)``
    from each module to get a hierarchical logger that respects the root
    configuration set up by ``configure_root_logging()``. If that hasn't
    been called yet (e.g. import-time logger creation, or a script that
    skips the normal entrypoints), it's configured lazily here so logging
    still works.
    """
    logger = logging.getLogger(name or _CA_ROOT_LOGGER_NAME)
    if not _configured:
        configure_root_logging()
    return logger
