"""Orchestrator: wires all agents into a configurable single-pipeline run-loop."""
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from sales_ops.agents.crm_sync import CRMSyncAgent
from sales_ops.agents.drafting import OutreachDraftingAgent
from sales_ops.agents.enrichment import LeadEnrichmentAgent
from sales_ops.agents.forecast import ForecastReport, ForecastUpdateAgent
from sales_ops.agents.reply_tracker import (
    MockIMAPClient,
    ReplyResult,
    ReplyTrackerAgent,
)
from sales_ops.crm.connector import MockCRMConnector
from sales_ops.data.store import LeadStore


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------

@dataclass
class OrchestratorConfig:
    """
    Configuration for a single Orchestrator pipeline run.

    Attributes
    ----------
    seed_leads          : pre-populate the store with sample leads
    auto_confirm        : bypass all HITL prompts (safe for headless / test runs)
    run_enrichment      : include the LeadEnrichmentAgent step
    run_drafting        : include the OutreachDraftingAgent step
    run_crm_sync        : include the CRMSyncAgent step
    run_reply_tracker   : include the ReplyTrackerAgent step
    run_forecast        : include the ForecastUpdateAgent step
    imap_seed           : seed for the MockIMAPClient RNG (None → non-deterministic)
    forecast_path       : path to write the forecast JSON file
    max_pipeline_loops  : number of full pipeline iterations (default 1)
    loop_delay_seconds  : pause between loops (0 = no pause)
    """
    seed_leads: bool = True
    auto_confirm: bool = True
    run_enrichment: bool = True
    run_drafting: bool = True
    run_crm_sync: bool = True
    run_reply_tracker: bool = True
    run_forecast: bool = True
    imap_seed: Optional[int] = 42
    forecast_path: str = "forecast_report.json"
    max_pipeline_loops: int = 1
    loop_delay_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Per-loop result container
# ---------------------------------------------------------------------------

@dataclass
class PipelineRunResult:
    """Captures the outputs of a single pipeline loop iteration."""
    loop_index: int
    enriched_leads: List[Any] = field(default_factory=list)
    drafted_leads: List[Any] = field(default_factory=list)
    crm_sync_results: List[Tuple[Any, Any]] = field(default_factory=list)
    reply_results: List[ReplyResult] = field(default_factory=list)
    no_reply_results: List[ReplyResult] = field(default_factory=list)
    forecast_report: Optional[ForecastReport] = None
    forecast_saved: bool = False
    duration_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)

    def summary(self) -> Dict[str, Any]:
        return {
            "loop_index": self.loop_index,
            "enriched": len(self.enriched_leads),
            "drafted": len(self.drafted_leads),
            "crm_synced": sum(1 for c, d in self.crm_sync_results if c is not None),
            "replies": len(self.reply_results),
            "no_replies": len(self.no_reply_results),
            "forecast_saved": self.forecast_saved,
            "duration_seconds": round(self.duration_seconds, 3),
            "errors": self.errors,
        }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class Orchestrator:
    """
    Wires LeadEnrichmentAgent → OutreachDraftingAgent → CRMSyncAgent →
    ReplyTrackerAgent → ForecastUpdateAgent into a single configurable
    pipeline run-loop.

    Usage
    -----
    >>> cfg = OrchestratorConfig(auto_confirm=True, imap_seed=42)
    >>> orch = Orchestrator(cfg)
    >>> results = orch.run()
    """

    def __init__(
        self,
        config: Optional[OrchestratorConfig] = None,
        store: Optional[LeadStore] = None,
        crm: Optional[MockCRMConnector] = None,
    ):
        self.config = config or OrchestratorConfig()
        self.name = "Orchestrator"

        # Allow dependency injection for testing; otherwise create defaults.
        self.store = store or LeadStore(seed=self.config.seed_leads)
        self.crm = crm or MockCRMConnector()

        logger.info(
            "[%s] Initialized — leads=%d, auto_confirm=%s, loops=%d",
            self.name,
            self.store.count(),
            self.config.auto_confirm,
            self.config.max_pipeline_loops,
        )

    # ------------------------------------------------------------------
    # Agent factories  (overridable for testing)
    # ------------------------------------------------------------------

    def _make_enrichment_agent(self) -> LeadEnrichmentAgent:
        return LeadEnrichmentAgent(self.store)

    def _make_drafting_agent(self) -> OutreachDraftingAgent:
        return OutreachDraftingAgent(self.store)

    def _make_crm_sync_agent(self) -> CRMSyncAgent:
        return CRMSyncAgent(self.store, self.crm, auto_confirm=self.config.auto_confirm)

    def _make_reply_tracker_agent(self) -> ReplyTrackerAgent:
        imap = MockIMAPClient(seed=self.config.imap_seed)
        return ReplyTrackerAgent(self.store, self.crm, imap_client=imap)

    def _make_forecast_agent(self) -> ForecastUpdateAgent:
        return ForecastUpdateAgent(
            crm=self.crm,
            forecast_path=self.config.forecast_path,
            auto_confirm=self.config.auto_confirm,
        )

    # ------------------------------------------------------------------
    # Single pipeline iteration
    # ------------------------------------------------------------------

    def _run_once(self, loop_index: int) -> PipelineRunResult:
        """Execute a single full pipeline pass and return a PipelineRunResult."""
        result = PipelineRunResult(loop_index=loop_index)
        t_start = time.monotonic()

        logger.info("[%s] --- Pipeline loop %d starting ---", self.name, loop_index)

        # 1. Enrichment
        if self.config.run_enrichment:
            try:
                logger.info("[%s] Step 1 — LeadEnrichmentAgent", self.name)
                agent = self._make_enrichment_agent()
                result.enriched_leads = agent.run()
                logger.info(
                    "[%s] Enrichment complete: %d lead(s) enriched.",
                    self.name,
                    len(result.enriched_leads),
                )
            except Exception as exc:  # pragma: no cover
                msg = f"Enrichment step failed: {exc}"
                logger.error("[%s] %s", self.name, msg, exc_info=True)
                result.errors.append(msg)

        # 2. Drafting
        if self.config.run_drafting:
            try:
                logger.info("[%s] Step 2 — OutreachDraftingAgent", self.name)
                agent = self._make_drafting_agent()
                result.drafted_leads = agent.run()
                logger.info(
                    "[%s] Drafting complete: %d draft(s) generated.",
                    self.name,
                    len(result.drafted_leads),
                )
            except Exception as exc:  # pragma: no cover
                msg = f"Drafting step failed: {exc}"
                logger.error("[%s] %s", self.name, msg, exc_info=True)
                result.errors.append(msg)

        # 3. CRM Sync
        if self.config.run_crm_sync:
            try:
                logger.info("[%s] Step 3 — CRMSyncAgent", self.name)
                agent = self._make_crm_sync_agent()
                result.crm_sync_results = agent.run()
                synced = sum(1 for c, d in result.crm_sync_results if c is not None)
                logger.info(
                    "[%s] CRM sync complete: %d/%d lead(s) synced.",
                    self.name,
                    synced,
                    len(result.crm_sync_results),
                )
            except Exception as exc:  # pragma: no cover
                msg = f"CRM sync step failed: {exc}"
                logger.error("[%s] %s", self.name, msg, exc_info=True)
                result.errors.append(msg)

        # 4. Reply Tracking
        if self.config.run_reply_tracker:
            try:
                logger.info("[%s] Step 4 — ReplyTrackerAgent", self.name)
                agent = self._make_reply_tracker_agent()
                result.reply_results, result.no_reply_results = agent.run()
                logger.info(
                    "[%s] Reply tracking complete: %d replied, %d no-reply.",
                    self.name,
                    len(result.reply_results),
                    len(result.no_reply_results),
                )
            except Exception as exc:  # pragma: no cover
                msg = f"Reply tracking step failed: {exc}"
                logger.error("[%s] %s", self.name, msg, exc_info=True)
                result.errors.append(msg)

        # 5. Forecast Update
        if self.config.run_forecast:
            try:
                logger.info("[%s] Step 5 — ForecastUpdateAgent", self.name)
                agent = self._make_forecast_agent()
                result.forecast_report, result.forecast_saved = agent.run()
                logger.info(
                    "[%s] Forecast complete: saved=%s, total_pipeline=$%.2f",
                    self.name,
                    result.forecast_saved,
                    result.forecast_report.total_pipeline if result.forecast_report else 0.0,
                )
            except Exception as exc:  # pragma: no cover
                msg = f"Forecast step failed: {exc}"
                logger.error("[%s] %s", self.name, msg, exc_info=True)
                result.errors.append(msg)

        result.duration_seconds = time.monotonic() - t_start
        logger.info(
            "[%s] --- Pipeline loop %d complete in %.3fs ---",
            self.name,
            loop_index,
            result.duration_seconds,
        )
        return result

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> List[PipelineRunResult]:
        """
        Execute the pipeline for `config.max_pipeline_loops` iterations.
        Returns a list of PipelineRunResult, one per loop.
        """
        all_results: List[PipelineRunResult] = []

        logger.info(
            "[%s] Starting orchestrator — %d loop(s) configured.",
            self.name,
            self.config.max_pipeline_loops,
        )

        for i in range(self.config.max_pipeline_loops):
            loop_result = self._run_once(loop_index=i)
            all_results.append(loop_result)

            if self.config.loop_delay_seconds > 0 and i < self.config.max_pipeline_loops - 1:
                logger.debug(
                    "[%s] Sleeping %.1fs before next loop.",
                    self.name,
                    self.config.loop_delay_seconds,
                )
                time.sleep(self.config.loop_delay_seconds)

        logger.info(
            "[%s] All loops complete. Summaries: %s",
            self.name,
            [r.summary() for r in all_results],
        )
        return all_results
