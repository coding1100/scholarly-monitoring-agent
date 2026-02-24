from __future__ import annotations

import logging
import sys

import structlog

from app.core.config import get_settings


def setup_logging() -> None:
    """Configure stdlib + structlog for JSON logs."""

    settings = get_settings()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    logging.basicConfig(level=log_level, format="%(message)s", stream=sys.stdout, force=True)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


logger = structlog.get_logger("site_watch_agent")
