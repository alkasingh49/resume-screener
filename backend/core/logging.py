"""Logging setup, called once at process startup (backend/main.py)."""

import logging
import sys

from backend.core.config import get_settings

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def setup_logging() -> None:
    """Configure the root logger. Idempotent - safe to call more than once."""
    settings = get_settings()
    root = logging.getLogger()

    if root.handlers:
        # Already configured (e.g. re-imported under --reload); just update the level.
        root.setLevel(settings.LOG_LEVEL)
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    root.addHandler(handler)
    root.setLevel(settings.LOG_LEVEL)

    # Quiet down noisy third-party loggers; app code stays at the configured level.
    for noisy in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
