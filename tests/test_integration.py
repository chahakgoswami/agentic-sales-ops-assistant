"""
End-to-end integration test: runs the full pipeline headlessly and validates
all observable outputs without any interactive prompts or file-system side-effects
beyond the tmp_path fixture.
"""
from __future__ import annotations

import json
import os
from io import StringIO
from typing import List

import pytest

from sales_ops.agents.reply_tracker import ReplyClassification, ReplyResult
from sales_ops.crm.connector import DealStage, MockCRMConnector
from sales_ops.data.models import LeadStatus
from sales_ops.data.store import LeadStore, SAMPLE_LEADS
from sales_ops.orchestrator import Orchestrator, OrchestratorConfig, PipelineRunResult
from sales_ops.dashboard import (
    build_crm_sync_table,
    build_forecast_panel,
    build_lead_status_table,
    build_outreach_preview_table,
    build_pipeline_summary_panel,
    build_reply_classification_table,
    render_dashboard,
)

from rich.console import Console


# ---------------------------------------------------------------------------
# Shared fixture: run the full headless pipeline once per module
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pipeline_output(tmp_path_factory):
    """
    Runs the complete orchestrator pipeline with auto_confirm=True and
    returns a dict of the key artefacts for inspection.
    """
    tmp = tmp_path_factory.mktemp("integration")
    forecast_path = str(tmp / "forecast.json")

    cfg = OrchestratorConfig(
        seed_leads=True,
        auto_confirm=True,
        imap_seed=42,
        forecast_path=forecast_path,
        max_pipeline_loops=1,
        loop_delay_seconds=0.0,
    )
    orch = Orchestrator(cfg)
    results: List[PipelineRunResult] = orch.run()

    return {
        "cfg": cfg,
        "orch": orch,
        "results": results,
        "result": results[0],
        "store": orch.store,
        "crm": orch.crm,
        "forecast_path": forecast_path,
    }


# ---------------------------------------------------------------------------
# Pipeline — basic structural checks
# ---------------------------------------------------------------------------


def test_pipeline_returns_one_result(pipeline_output):
    assert len(pipeline_output["results"]) == 1


def test_pipeline_result_has_no_errors(pipeline_output):
    assert pipeline_output["result"].errors == []


def test_pipeline_loop_index_is_zero(pipeline_output):
    assert pipeline_output["result"].loop_index == 0


def test_pipeline_duration_positive(pipeline_output):
    assert pipeline_output["result"].duration_seconds > 0


# ---------------------------------------------------------------------------
# Lead store checks
# ---------------------------------------------------------------------------


def test_all_sample_leads_present(pipeline_output):
    store: LeadStore = pipeline_output["store"]
    assert store.count() == len(SAMPLE_LEADS)


def test_all_leads_have_terminal_status(pipeline_output):
    store: LeadStore = pipeline_output["store"]
    terminal = {
        LeadStatus.REPLIED_INTERESTED,
        LeadStatus.REPLIED_NOT_INTERESTED,
        LeadStatus.NO_REPLY,
    }
    for lead in store.get_all():
        assert lead.status in terminal, (
            f"{lead.email} has unexpected status {lead.status}"
        )


def test_all_leads_are_enriched(pipeline_output):
    store: LeadStore = pipeline_output["store"]
    for lead in store.get_all():
        assert lead.industry is not None
        assert lead.company_size is not None
        assert lead.linkedin_url is not None


def test_all_leads_have_outreach_draft(pipeline_output):
    store: LeadStore = pipeline_output["store"]
    for lead in store.get_all():
        assert lead.outreach_subject is not None
        assert lead.outreach_body is not None


def test_all_leads_have_crm_contact_id(pipeline_output):
    store: LeadStore = pipeline_output["store"]
    for lead in store.get_all():
        assert lead.crm_contact_id is not None, (
            f"{lead.email} missing crm_contact_id"
        )


def test_all_leads_have_crm_deal_id(pipeline_output):
    store: LeadStore = pipeline_output["store"]
    for lead in store.get_all():
        assert lead.crm_deal_id is not None, (
            f"{lead.email} missing crm_deal_id"
        )


# ---------------------------------------------------------------------------
# CRM checks
# ---------------------------------------------------------------------------


def test_crm_has_all_contacts(pipeline_output):
    crm: MockCRMConnector = pipeline_output["crm"]
    assert crm.contact_count() == len(SAMPLE_LEADS)


def test_crm_has_all_deals(pipeline_output):
    crm: MockCRMConnector = pipeline_output["crm"]
    assert crm.deal_count() == len(SAMPLE_LEADS)


def test_crm_contacts_have_terminal_lead_status(pipeline_output):
    crm: MockCRMConnector = pipeline_output["crm"]
    terminal_values = {
        LeadStatus.REPLIED_INTERESTED.value,
        LeadStatus.REPLIED_NOT_INTERESTED.value,
        LeadStatus.NO_REPLY.value,
    }
    for contact in crm.list_contacts():
        assert contact.lead_status in terminal_values, (
            f"{contact.email} crm status={contact.lead_status}"
        )


def test_crm_interested_deals_in_qualification(pipeline_output):
    crm: MockCRMConnector = pipeline_output["crm"]
    store: LeadStore = pipeline_output["store"]
    for lead in store.get_all():
        if lead.status == LeadStatus.REPLIED_INTERESTED and lead.crm_contact_id:
            deal = crm.get_deal_for_contact(lead.crm_contact_id)
            if deal:
                assert deal.stage == DealStage.QUALIFICATION


def test_crm_not_interested_deals_in_closed_lost(pipeline_output):
    crm: MockCRMConnector = pipeline_output["crm"]
    store: LeadStore = pipeline_output["store"]
    for lead in store.get_all():
        if lead.status == LeadStatus.REPLIED_NOT_INTERESTED and lead.crm_contact_id:
            deal = crm.get_deal_for_contact(lead.crm_contact_id)
            if deal:
                assert deal.stage == DealStage.CLOSED_LOST


# ---------------------------------------------------------------------------
# Reply tracking checks
# ---------------------------------------------------------------------------


def test_total_reply_results_match_lead_count(pipeline_output):
    r = pipeline_output["result"]
    total = len(r.reply_results) + len(r.no_reply_results)
    assert total == len(SAMPLE_LEADS)


def test_all_reply_results_are_reply_result_instances(pipeline_output):
    r = pipeline_output["result"]
    for item in r.reply_results + r.no_reply_results:
        assert isinstance(item, ReplyResult)


# ---------------------------------------------------------------------------
# Forecast checks
# ---------------------------------------------------------------------------


def test_forecast_file_exists(pipeline_output):
    assert os.path.exists(pipeline_output["forecast_path"])


def test_forecast_saved_flag_is_true(pipeline_output):
    assert pipeline_output["result"].forecast_saved is True


def test_forecast_json_valid(pipeline_output):
    with open(pipeline_output["forecast_path"], "r") as fh:
        data = json.load(fh)
    for key in (
        "generated_at", "total_pipeline", "weighted_pipeline",
        "expected_revenue", "closed_lost_value",
        "deals_by_stage", "weighted_by_stage", "rows", "metadata",
    ):
        assert key in data


def test_forecast_row_count_equals_deal_count(pipeline_output):
    crm: MockCRMConnector = pipeline_output["crm"]
    with open(pipeline_output["forecast_path"], "r") as fh:
        data = json.load(fh)
    assert len(data["rows"]) == crm.deal_count()


def test_forecast_total_pipeline_positive(pipeline_output):
    with open(pipeline_output["forecast_path"], "r") as fh:
        data = json.load(fh)
    assert data["total_pipeline"] > 0


def test_forecast_weighted_pipeline_non_negative(pipeline_output):
    with open(pipeline_output["forecast_path"], "r") as fh:
        data = json.load(fh)
    assert data["weighted_pipeline"] >= 0


# ---------------------------------------------------------------------------
# Dashboard rendering — no exceptions, correct output
# ---------------------------------------------------------------------------


def test_dashboard_lead_status_table_renders(pipeline_output):
    store: LeadStore = pipeline_output["store"]
    console = Console(file=StringIO(), theme=None)
    table = build_lead_status_table(store.get_all())
    # Should render without raising
    console.print(table)
    output = console.file.getvalue()
    assert "Lead Status" in output


def test_dashboard_outreach_preview_renders(pipeline_output):
    store: LeadStore = pipeline_output["store"]
    console = Console(file=StringIO())
    table = build_outreach_preview_table(store.get_all())
    console.print(table)
    output = console.file.getvalue()
    assert "Outreach Draft Previews" in output


def test_dashboard_crm_sync_table_renders(pipeline_output):
    crm: MockCRMConnector = pipeline_output["crm"]
    store: LeadStore = pipeline_output["store"]
    console = Console(file=StringIO())
    table = build_crm_sync_table(crm, store)
    console.print(table)
    output = console.file.getvalue()
    assert "CRM Sync State" in output


def test_dashboard_reply_table_renders(pipeline_output):
    r = pipeline_output["result"]
    console = Console(file=StringIO())
    table = build_reply_classification_table(r.reply_results, r.no_reply_results)
    console.print(table)
    output = console.file.getvalue()
    assert "Reply Classifications" in output


def test_dashboard_forecast_panel_renders(pipeline_output):
    console = Console(file=StringIO())
    panel = build_forecast_panel(pipeline_output["forecast_path"])
    console.print(panel)
    output = console.file.getvalue()
    assert "Forecast Summary" in output


def test_dashboard_pipeline_summary_panel_renders(pipeline_output):
    console = Console(file=StringIO())
    panel = build_pipeline_summary_panel(pipeline_output["results"])
    console.print(panel)
    output = console.file.getvalue()
    assert "Pipeline Run Summary" in output


def test_full_dashboard_render_no_exception(pipeline_output):
    r = pipeline_output["result"]
    store: LeadStore = pipeline_output["store"]
    crm: MockCRMConnector = pipeline_output["crm"]
    console = Console(file=StringIO())
    # Should complete without raising
    render_dashboard(
        console=console,
        leads=store.get_all(),
        crm=crm,
        reply_results=r.reply_results,
        no_reply_results=r.no_reply_results,
        pipeline_results=pipeline_output["results"],
        forecast_path=pipeline_output["forecast_path"],
    )
    output = console.file.getvalue()
    assert len(output) > 0


def test_dashboard_contains_lead_names(pipeline_output):
    r = pipeline_output["result"]
    store: LeadStore = pipeline_output["store"]
    crm: MockCRMConnector = pipeline_output["crm"]
    console = Console(file=StringIO())
    render_dashboard(
        console=console,
        leads=store.get_all(),
        crm=crm,
        reply_results=r.reply_results,
        no_reply_results=r.no_reply_results,
        pipeline_results=pipeline_output["results"],
        forecast_path=pipeline_output["forecast_path"],
    )
    output = console.file.getvalue()
    # At least one known lead name should appear in the rendered output
    assert "Sarah" in output or "Marcus" in output or "Priya" in output


def test_dashboard_forecast_panel_no_file(tmp_path):
    """Forecast panel should degrade gracefully when no file exists."""
    console = Console(file=StringIO())
    panel = build_forecast_panel(str(tmp_path / "nonexistent.json"))
    console.print(panel)
    output = console.file.getvalue()
    assert "Forecast Summary" in output
    assert "No forecast file found" in output


def test_dashboard_crm_sync_table_empty_crm():
    """CRM sync table renders correctly when CRM is empty."""
    crm = MockCRMConnector()
    store = LeadStore(seed=False)
    console = Console(file=StringIO())
    table = build_crm_sync_table(crm, store)
    console.print(table)
    output = console.file.getvalue()
    assert "CRM Sync State" in output
    assert "No CRM contacts synced yet" in output


def test_dashboard_outreach_preview_no_drafts():
    """Outreach preview table renders correctly when no drafts exist."""
    store = LeadStore(seed=True)  # leads are NEW, no drafts
    console = Console(file=StringIO())
    table = build_outreach_preview_table(store.get_all())
    console.print(table)
    output = console.file.getvalue()
    assert "No drafts available yet" in output


def test_dashboard_reply_table_empty():
    """Reply classification table renders correctly with no results."""
    console = Console(file=StringIO())
    table = build_reply_classification_table([], [])
    console.print(table)
    output = console.file.getvalue()
    assert "No reply events processed" in output


# ---------------------------------------------------------------------------
# Config / dotenv
# ---------------------------------------------------------------------------


def test_settings_importable():
    from sales_ops.config import settings, Settings
    assert isinstance(settings, Settings)


def test_settings_has_expected_attributes():
    from sales_ops.config import settings
    assert hasattr(settings, "log_level")
    assert hasattr(settings, "forecast_path")
    assert hasattr(settings, "auto_confirm")
    assert hasattr(settings, "imap_seed")
    assert hasattr(settings, "max_pipeline_loops")
    assert hasattr(settings, "loop_delay_seconds")


def test_settings_default_forecast_path():
    from sales_ops.config import settings
    # Default is 'forecast_report.json' unless overridden by env
    # We just check it's a non-empty string
    assert isinstance(settings.forecast_path, str)
    assert len(settings.forecast_path) > 0
