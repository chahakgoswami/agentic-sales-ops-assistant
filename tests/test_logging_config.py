"""Tests for the logging configuration helper."""
import logging
import io

import pytest

from sales_ops.logging_config import configure_logging, DEFAULT_FORMAT


def test_configure_logging_sets_level():
    configure_logging(level=logging.DEBUG)
    assert logging.getLogger().level == logging.DEBUG
    # Reset
    configure_logging(level=logging.WARNING)


def test_configure_logging_writes_to_custom_stream():
    stream = io.StringIO()
    configure_logging(level=logging.INFO, stream=stream)
    logging.getLogger("sales_ops.test_logging").info("hello test")
    output = stream.getvalue()
    assert "hello test" in output


def test_configure_logging_no_duplicate_handlers():
    configure_logging(level=logging.INFO)
    configure_logging(level=logging.INFO)
    root = logging.getLogger()
    assert len(root.handlers) == 1


def test_configure_logging_custom_format():
    stream = io.StringIO()
    configure_logging(level=logging.INFO, fmt="CUSTOM %(message)s", stream=stream)
    logging.getLogger("sales_ops.test_fmt").info("fmt_test")
    output = stream.getvalue()
    assert "CUSTOM" in output
    assert "fmt_test" in output
