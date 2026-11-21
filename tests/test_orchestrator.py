"""Tests for the Orchestrator class and its configurable pipeline run-loop."""
import json
import logging
import os
import pytest

from sales_ops.agents.reply_tracker import MockIMAPClient, ReplyResult
from sales_ops.agents.forecast import ForecastReport
from sales_ops.crm.connector import MockCRMConnector, DealStage
from sales_ops.data.models import LeadStatus
from sales_ops.data.store import LeadStore, SAMPLE_LEADS
from sales_ops.orchestrator import Orchestrator, OrchestratorConfig, PipelineRunResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _default_config(tmp_path, **overrides) -> OrchestratorConfig:
    """Return a standard headless config pointing at a tmp forecast path."""
    kwargs = dict(
        seed_leads=True,
        auto_confirm=True,
        imap_seed=42,
        forecast_path=str(tmp_path / "forecast.json"),
        max_pipeline_loops=1,
        loop_delay_seconds=0.0,
    )
    kwargs.update(overrides)
    return OrchestratorConfig(**kwargs)


# ---------------------------------------------------------------------------
# OrchestratorConfig defaults
# ---------------------------------------------------------------------------

def test_config_defaults():
    cfg = OrchestratorConfig()
    assert cfg.seed_leads is True
    assert cfg.auto_confirm is True
    assert cfg.run_enrichment is True
    assert cfg.run_drafting is True
    assert cfg.run_crm_sync is True
    assert cfg.run_reply_tracker is True
    assert cfg.run_forecast is True
    assert cfg.max_pipeline_loops == 1
    assert cfg.loop_delay_seconds == 0.0


# ---------------------------------------------------------------------------
# Orchestrator initialisation
# ---------------------------------------------------------------------------

def test_orchestrator_init_seeds_leads(tmp_path):
    cfg = _default_config(tmp_path)
    orch = Orchestrator(cfg)
    assert orch.store.count() == len(SAMPLE_LEADS)


def test_orchestrator_init_empty_crm(tmp_path):
    cfg = _default_config(tmp_path)
    orch = Orchestrator(cfg)
    assert orch.crm.contact_count() == 0
    assert orch.crm.deal_count() == 0


def test_orchestrator_accepts_injected_store_and_crm(tmp_path):
    store = LeadStore(seed=False)
    crm = MockCRMConnector()
    cfg = _default_config(tmp_path, seed_leads=False)
    orch = Orchestrator(cfg, store=store, crm=crm)
    assert orch.store is store
    assert orch.crm is crm


# ---------------------------------------------------------------------------
# run() return type and structure
# ---------------------------------------------------------------------------

def test_run_returns_list(tmp_path):
    cfg = _default_config(tmp_path)
    orch = Orchestrator(cfg)
    results = orch.run()
    assert isinstance(results, list)


def test_run_returns_one_result_per_loop(tmp_path):
    cfg = _default_config(tmp_path, max_pipeline_loops=1)
    orch = Orchestrator(cfg)
    results = orch.run()
    assert len(results) == 1


def test_run_returns_pipeline_run_result_instances(tmp_path):
    cfg = _default_config(tmp_path)
    orch = Orchestrator(cfg)
    results = orch.run()
    for r in results:
        assert isinstance(r, PipelineRunResult)


def test_run_result_has_no_errors_in_happy_path(tmp_path):
    cfg = _default_config(tmp_path)
    orch = Orchestrator(cfg)
    results = orch.run()
    for r in results:
        assert r.errors == [], f"Unexpected errors: {r.errors}"


# ---------------------------------------------------------------------------
# Full pipeline — lead count / status checks
# ---------------------------------------------------------------------------

def test_run_full_pipeline_enriches_all_leads(tmp_path):
    cfg = _default_config(tmp_path)
    orch = Orchestrator(cfg)
    results = orch.run()
    result = results[0]
    assert len(result.enriched_leads) == len(SAMPLE_LEADS)


def test_run_full_pipeline_drafts_all_leads(tmp_path):
    cfg = _default_config(tmp_path)
    orch = Orchestrator(cfg)
    results = orch.run()
    result = results[0]
    assert len(result.drafted_leads) == len(SAMPLE_LEADS)


def test_run_full_pipeline_syncs_all_leads_to_crm(tmp_path):
    cfg = _default_config(tmp_path)
    orch = Orchestrator(cfg)
    orch.run()
    assert orch.crm.contact_count() == len(SAMPLE_LEADS)
    assert orch.crm.deal_count() == len(SAMPLE_LEADS)


def test_run_full_pipeline_all_leads_have_terminal_status(tmp_path):
    cfg = _default_config(tmp_path)
    orch = Orchestrator(cfg)
    orch.run()
    terminal_statuses = {
        LeadStatus.REPLIED_INTERESTED,
        LeadStatus.REPLIED_NOT_INTERESTED,
        LeadStatus.NO_REPLY,
    }
    for lead in orch.store.get_all():
        assert lead.status in terminal_statuses, (
            f"{lead.email} has unexpected status {lead.status}"
        )


def test_run_full_pipeline_forecast_saved(tmp_path):
    cfg = _default_config(tmp_path)
    orch = Orchestrator(cfg)
    results = orch.run()
    assert results[0].forecast_saved is True
    assert os.path.exists(cfg.forecast_path)


def test_run_full_pipeline_forecast_report_is_forecast_report(tmp_path):
    cfg = _default_config(tmp_path)
    orch = Orchestrator(cfg)
    results = orch.run()
    assert isinstance(results[0].forecast_report, ForecastReport)


def test_run_full_pipeline_reply_results_are_reply_result_instances(tmp_path):
    cfg = _default_config(tmp_path)
    orch = Orchestrator(cfg)
    results = orch.run()
    for r in results[0].reply_results + results[0].no_reply_results:
        assert isinstance(r, ReplyResult)


def test_run_full_pipeline_total_reply_processed_equals_lead_count(tmp_path):
    cfg = _default_config(tmp_path)
    orch = Orchestrator(cfg)
    results = orch.run()
    r = results[0]
    total = len(r.reply_results) + len(r.no_reply_results)
    assert total == len(SAMPLE_LEADS)


# ---------------------------------------------------------------------------
# Step toggling
# ---------------------------------------------------------------------------

def test_run_skips_enrichment_when_disabled(tmp_path):
    cfg = _default_config(tmp_path, run_enrichment=False)
    orch = Orchestrator(cfg)
    results = orch.run()
    assert results[0].enriched_leads == []


def test_run_skips_drafting_when_disabled(tmp_path):
    cfg = _default_config(tmp_path, run_drafting=False)
    orch = Orchestrator(cfg)
    results = orch.run()
    assert results[0].drafted_leads == []


def test_run_skips_crm_sync_when_disabled(tmp_path):
    cfg = _default_config(tmp_path, run_crm_sync=False)
    orch = Orchestrator(cfg)
    orch.run()
    assert orch.crm.contact_count() == 0


def test_run_skips_reply_tracker_when_disabled(tmp_path):
    cfg = _default_config(tmp_path, run_reply_tracker=False)
    orch = Orchestrator(cfg)
    results = orch.run()
    assert results[0].reply_results == []
    assert results[0].no_reply_results == []


def test_run_skips_forecast_when_disabled(tmp_path):
    cfg = _default_config(tmp_path, run_forecast=False)
    orch = Orchestrator(cfg)
    results = orch.run()
    assert results[0].forecast_report is None
    assert results[0].forecast_saved is False
    assert not os.path.exists(cfg.forecast_path)


# ---------------------------------------------------------------------------
# Multiple loop iterations
# ---------------------------------------------------------------------------

def test_run_multiple_loops_returns_correct_count(tmp_path):
    cfg = _default_config(tmp_path, max_pipeline_loops=2)
    orch = Orchestrator(cfg)
    results = orch.run()
    assert len(results) == 2


def test_run_second_loop_enriches_zero_leads(tmp_path):
    """After the first loop enriches all leads, the second loop finds none NEW."""
    cfg = _default_config(tmp_path, max_pipeline_loops=2)
    orch = Orchestrator(cfg)
    results = orch.run()
    # First loop enriches all
    assert len(results[0].enriched_leads) == len(SAMPLE_LEADS)
    # Second loop: leads are already in a terminal status so not NEW
    assert len(results[1].enriched_leads) == 0


def test_run_multiple_loops_all_results_have_loop_index(tmp_path):
    cfg = _default_config(tmp_path, max_pipeline_loops=3)
    orch = Orchestrator(cfg)
    results = orch.run()
    for i, r in enumerate(results):
        assert r.loop_index == i


# ---------------------------------------------------------------------------
# PipelineRunResult.summary()
# ---------------------------------------------------------------------------

def test_pipeline_run_result_summary_has_required_keys(tmp_path):
    cfg = _default_config(tmp_path)
    orch = Orchestrator(cfg)
    results = orch.run()
    summary = results[0].summary()
    for key in (
        "loop_index", "enriched", "drafted", "crm_synced",
        "replies", "no_replies", "forecast_saved",
        "duration_seconds", "errors",
    ):
        assert key in summary


def test_pipeline_run_result_summary_duration_positive(tmp_path):
    cfg = _default_config(tmp_path)
    orch = Orchestrator(cfg)
    results = orch.run()
    assert results[0].duration_seconds > 0


# ---------------------------------------------------------------------------
# Dependency injection — custom store / crm
# ---------------------------------------------------------------------------

def test_orchestrator_uses_injected_store(tmp_path):
    store = LeadStore(seed=True)
    crm = MockCRMConnector()
    cfg = _default_config(tmp_path, seed_leads=False)
    orch = Orchestrator(cfg, store=store, crm=crm)
    orch.run()
    # All leads should be processed
    assert crm.contact_count() == len(SAMPLE_LEADS)


def test_orchestrator_uses_injected_crm(tmp_path):
    crm = MockCRMConnector()
    cfg = _default_config(tmp_path)
    orch = Orchestrator(cfg, crm=crm)
    orch.run()
    assert crm is orch.crm
    assert crm.deal_count() == len(SAMPLE_LEADS)


# ---------------------------------------------------------------------------
# Forecast JSON integrity
# ---------------------------------------------------------------------------

def test_run_forecast_json_is_valid(tmp_path):
    cfg = _default_config(tmp_path)
    orch = Orchestrator(cfg)
    orch.run()
    with open(cfg.forecast_path, "r") as fh:
        data = json.load(fh)
    for key in (
        "generated_at", "total_pipeline", "weighted_pipeline",
        "expected_revenue", "rows",
    ):
        assert key in data


def test_run_forecast_row_count_equals_deal_count(tmp_path):
    cfg = _default_config(tmp_path)
    orch = Orchestrator(cfg)
    orch.run()
    with open(cfg.forecast_path, "r") as fh:
        data = json.load(fh)
    assert len(data["rows"]) == orch.crm.deal_count()


# ---------------------------------------------------------------------------
# CRM deal stage transitions after full pipeline
# ---------------------------------------------------------------------------

def test_run_interested_deals_in_qualification_stage(tmp_path):
    cfg = _default_config(tmp_path)
    orch = Orchestrator(cfg)
    orch.run()
    for lead in orch.store.get_all():
        if lead.status == LeadStatus.REPLIED_INTERESTED and lead.crm_contact_id:
            deal = orch.crm.get_deal_for_contact(lead.crm_contact_id)
            if deal:
                assert deal.stage == DealStage.QUALIFICATION


def test_run_not_interested_deals_in_closed_lost_stage(tmp_path):
    cfg = _default_config(tmp_path)
    orch = Orchestrator(cfg)
    orch.run()
    for lead in orch.store.get_all():
        if lead.status == LeadStatus.REPLIED_NOT_INTERESTED and lead.crm_contact_id:
            deal = orch.crm.get_deal_for_contact(lead.crm_contact_id)
            if deal:
                assert deal.stage == DealStage.CLOSED_LOST


# ---------------------------------------------------------------------------
# Logging integration
# ---------------------------------------------------------------------------

def test_orchestrator_emits_log_messages(tmp_path, caplog):
    cfg = _default_config(tmp_path)
    with caplog.at_level(logging.INFO, logger="sales_ops.orchestrator"):
        orch = Orchestrator(cfg)
        orch.run()
    assert any("Pipeline loop 0" in m for m in caplog.messages)
