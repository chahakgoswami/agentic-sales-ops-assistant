"""Centralised dotenv-based configuration for the Sales Ops Assistant."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env from the project root (if it exists).  Missing file is silently ignored.
load_dotenv(Path(__file__).parent.parent / ".env", override=False)


def _bool(val: str) -> bool:
    return val.strip().lower() in ("1", "true", "yes", "on")


def _int_or_none(val: str) -> Optional[int]:
    stripped = val.strip()
    if stripped == "":
        return None
    return int(stripped)


class Settings:
    """Singleton-style settings object populated from environment / .env."""

    def __init__(self) -> None:
        self.log_level: int = getattr(
            logging,
            os.getenv("SALES_OPS_LOG_LEVEL", "INFO").upper(),
            logging.INFO,
        )
        self.forecast_path: str = os.getenv(
            "SALES_OPS_FORECAST_PATH", "forecast_report.json"
        )
        self.auto_confirm: bool = _bool(
            os.getenv("SALES_OPS_AUTO_CONFIRM", "false")
        )
        raw_seed = os.getenv("SALES_OPS_IMAP_SEED", "42")
        self.imap_seed: Optional[int] = _int_or_none(raw_seed)
        self.max_pipeline_loops: int = int(
            os.getenv("SALES_OPS_MAX_PIPELINE_LOOPS", "1")
        )
        self.loop_delay_seconds: float = float(
            os.getenv("SALES_OPS_LOOP_DELAY_SECONDS", "0.0")
        )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"Settings(log_level={logging.getLevelName(self.log_level)}, "
            f"forecast_path={self.forecast_path!r}, "
            f"auto_confirm={self.auto_confirm}, "
            f"imap_seed={self.imap_seed}, "
            f"max_pipeline_loops={self.max_pipeline_loops})"
        )


# Module-level singleton — import this everywhere.
settings = Settings()
