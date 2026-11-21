"""Structured logging configuration for the Sales Ops Assistant."""
import logging
import logging.config
import sys
from typing import Optional


DEFAULT_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)

DEFAULT_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"


def configure_logging(
    level: int = logging.INFO,
    fmt: Optional[str] = None,
    datefmt: Optional[str] = None,
    stream=None,
) -> None:
    """
    Configure root-level structured logging for the application.

    Parameters
    ----------
    level   : logging level (e.g. logging.DEBUG, logging.INFO)
    fmt     : log format string (defaults to DEFAULT_FORMAT)
    datefmt : date/time format string (defaults to DEFAULT_DATE_FORMAT)
    stream  : output stream (defaults to sys.stdout)
    """
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setLevel(level)
    formatter = logging.Formatter(
        fmt=fmt or DEFAULT_FORMAT,
        datefmt=datefmt or DEFAULT_DATE_FORMAT,
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    # Remove any pre-existing handlers to avoid duplicate log lines
    root.handlers.clear()
    root.addHandler(handler)

    logging.getLogger("sales_ops").setLevel(level)
    logging.getLogger("sales_ops").info(
        "Logging configured: level=%s", logging.getLevelName(level)
    )
