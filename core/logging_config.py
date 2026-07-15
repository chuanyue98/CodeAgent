import logging
import sys
from typing import Optional


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a logger configured for CodeAgent.

    Uses the module ``__name__`` by default.  Call ``get_logger(__name__)``
    from each module to get a hierarchical logger that respects the root
    configuration.
    """
    logger = logging.getLogger(name or "codeagent")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        handler.setFormatter(logging.Formatter(fmt))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
