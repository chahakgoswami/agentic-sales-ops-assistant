"""ForecastUpdateAgent: reads CRM deal stages and reply statuses, computes weighted pipeline forecast, and stores as JSON."""
import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sales_ops.crm.connector import DEAL_STAGE_PROBABILITIES, CRMDeal, DealStage, MockCRMConnector


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_FORECAST_PATH = "forecast_report.json"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class DealForecastRow:
    """Forecast contribution from a single deal."""
    deal_id: str
    contact_id: str
    company: str
    deal_name: str
    stage: str
    amount: float
    probability: float
    weighted_value: float  # amount * probability
    lead_status: str  # from associated CRM contact

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ForecastReport:
    """Aggregated forecast report produced by ForecastUpdateAgent."""
    generated_at: str
    total_pipeline: float          # sum of all deal amounts (unweighted)
    weighted_pipeline: float       # sum of amount * probability for all open deals
    expected_revenue: float        # sum of CLOSED_WON amounts
    closed_lost_value: float       # sum of CLOSED_LOST amounts
    deals_by_stage: Dict[str, int]       # stage -> count
    weighted_by_stage: Dict[str, float]  # stage -> weighted_value sum
    rows: List[DealForecastRow] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "generated_at": self.generated_at,
            "total_pipeline": self.total_pipeline,
            "weighted_pipeline": self.weighted_pipeline,
            "expected_revenue": self.expected_revenue,
            "closed_lost_value": self.closed_lost_value,
            "deals_by_stage": self.deals_by_stage,
            "weighted_by_stage": self.weighted_by_stage,
            "rows": [r.to_dict() for r in self.rows],
            "metadata": self.metadata,
        }
        return d


# ---------------------------------------------------------------------------
# Human-in-the-loop confirmation helper
# ---------------------------------------------------------------------------

def _confirm_overwrite(path: str, auto_confirm: bool = False) -> bool:
    """
    Ask the user whether to overwrite an existing forecast file.
    If auto_confirm=True, skips the prompt and returns True.
    """
    if auto_confirm:
        print(f"  [HITL] Auto-confirmed: overwrite forecast at '{path}'.")
        return True
    answer = input(
        f"  [HITL] Forecast file '{path}' already exists. Overwrite? [y/N]: "
    ).strip().lower()
    return answer in ("y", "yes")


# ---------------------------------------------------------------------------
# ForecastUpdateAgent
# ---------------------------------------------------------------------------

class ForecastUpdateAgent:
    """
    Reads all deal records from the MockCRMConnector, applies weighted
    pipeline calculation using DEAL_STAGE_PROBABILITIES, and writes an
    updated ForecastReport to a JSON file.

    A human confirmation gate is presented before overwriting an existing
    forecast file (unless auto_confirm=True).
    """

    def __init__(
        self,
        crm: MockCRMConnector,
        forecast_path: str = DEFAULT_FORECAST_PATH,
        auto_confirm: bool = False,
    ):
        self.crm = crm
        self.forecast_path = forecast_path
        self.auto_confirm = auto_confirm
        self.name = "ForecastUpdateAgent"

    # ------------------------------------------------------------------
    # Core calculation
    # ------------------------------------------------------------------

    def _get_lead_status_for_contact(self, contact_id: str) -> str:
        """Return the lead_status string from the CRM contact, or 'unknown'."""
        contact = self.crm.get_contact(contact_id)
        if contact:
            return contact.lead_status
        return "unknown"

    def compute_forecast(self) -> ForecastReport:
        """
        Compute the weighted forecast from all deals currently in the CRM.
        Returns a ForecastReport without writing to disk.
        """
        deals: List[CRMDeal] = self.crm.list_deals()

        print(f"[{self.name}] Computing forecast over {len(deals)} deal(s).")

        rows: List[DealForecastRow] = []
        total_pipeline: float = 0.0
        weighted_pipeline: float = 0.0
        expected_revenue: float = 0.0
        closed_lost_value: float = 0.0

        deals_by_stage: Dict[str, int] = {}
        weighted_by_stage: Dict[str, float] = {}

        for deal in deals:
            stage_str = deal.stage.value if isinstance(deal.stage, DealStage) else str(deal.stage)
            stage_enum = DealStage(stage_str)

            # Use deal's stored probability; fall back to table default
            probability = deal.probability
            if probability is None:
                probability = DEAL_STAGE_PROBABILITIES.get(stage_enum, 0.0)

            weighted_value = deal.amount * probability
            lead_status = self._get_lead_status_for_contact(deal.contact_id)

            row = DealForecastRow(
                deal_id=deal.id,
                contact_id=deal.contact_id,
                company=deal.company,
                deal_name=deal.deal_name,
                stage=stage_str,
                amount=deal.amount,
                probability=probability,
                weighted_value=weighted_value,
                lead_status=lead_status,
            )
            rows.append(row)

            # Accumulate stage-level aggregates
            deals_by_stage[stage_str] = deals_by_stage.get(stage_str, 0) + 1
            weighted_by_stage[stage_str] = (
                weighted_by_stage.get(stage_str, 0.0) + weighted_value
            )

            # Accumulate totals
            total_pipeline += deal.amount

            if stage_enum == DealStage.CLOSED_WON:
                expected_revenue += deal.amount
            elif stage_enum == DealStage.CLOSED_LOST:
                closed_lost_value += deal.amount
            else:
                # Only open deals contribute to weighted pipeline
                weighted_pipeline += weighted_value

        generated_at = datetime.now(timezone.utc).isoformat()

        report = ForecastReport(
            generated_at=generated_at,
            total_pipeline=round(total_pipeline, 2),
            weighted_pipeline=round(weighted_pipeline, 2),
            expected_revenue=round(expected_revenue, 2),
            closed_lost_value=round(closed_lost_value, 2),
            deals_by_stage=deals_by_stage,
            weighted_by_stage={k: round(v, 2) for k, v in weighted_by_stage.items()},
            rows=rows,
            metadata={
                "deal_count": len(deals),
                "crm_name": self.crm.name,
                "forecast_path": self.forecast_path,
            },
        )

        print(
            f"[{self.name}] Forecast: total_pipeline=${total_pipeline:,.2f}, "
            f"weighted_pipeline=${weighted_pipeline:,.2f}, "
            f"expected_revenue=${expected_revenue:,.2f}"
        )
        return report

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_report(self, report: ForecastReport) -> bool:
        """
        Write the ForecastReport to disk as JSON.
        If a file already exists at self.forecast_path, presents a human
        confirmation gate before overwriting.

        Returns True if the file was written, False if the user declined.
        """
        path = self.forecast_path
        file_exists = os.path.exists(path)

        if file_exists:
            confirmed = _confirm_overwrite(path, auto_confirm=self.auto_confirm)
            if not confirmed:
                print(
                    f"  [{self.name}] ✗ User declined to overwrite '{path}'. "
                    "Forecast NOT updated."
                )
                return False

        with open(path, "w", encoding="utf-8") as fh:
            json.dump(report.to_dict(), fh, indent=2)

        print(f"  [{self.name}] ✓ Forecast written to '{path}'.")
        return True

    def load_report(self) -> Optional[Dict[str, Any]]:
        """
        Load and return the previously saved forecast as a raw dict.
        Returns None if no forecast file exists yet.
        """
        path = self.forecast_path
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(self) -> Tuple[ForecastReport, bool]:
        """
        Full forecast update cycle:
        1. Compute weighted pipeline from CRM deals.
        2. Present confirmation gate if an existing forecast exists.
        3. Write updated forecast to JSON.

        Returns (ForecastReport, was_saved: bool).
        """
        print(f"[{self.name}] Starting forecast update run.")
        report = self.compute_forecast()
        saved = self.save_report(report)
        status_msg = "saved" if saved else "NOT saved (user declined)"
        print(f"[{self.name}] Forecast update complete — {status_msg}.")
        return report, saved
