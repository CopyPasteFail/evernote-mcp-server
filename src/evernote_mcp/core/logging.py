"""Logging configuration helpers."""

from __future__ import annotations

import logging


def configure_application_logging(log_level: str) -> None:
    """Configure process-wide logging for the MCP server.

    Args:
        log_level: Standard Python logging level value such as INFO or DEBUG.

    Notes:
        This function intentionally keeps formatting minimal and avoids logging secrets.
    """

    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
