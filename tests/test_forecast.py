"""Tests for ForecastUpdateAgent."""
import json
import os
import pytest

from sales_ops.agents.crm_sync import CRMSyncAgent
from sales_ops.agents.drafting import OutreachDraftingAgent
from sales_ops.agents.enrichment import LeadEnrichmentAgent
from sales_ops.agents.forecast import (
    DEFAULT_FORECAST_PATH,
    DealForecastRow,
    ForecastReport,
    ForecastUpdateAgent,
)
from sales_ops.agents.reply_tracker import ReplyTrackerAgent, MockIMAPClient
from sales_ops.crm.connector import (
    DEAL_STAGE_PROBABILITIES,
    DealStage,
    MockCRMConnector,
)
from sales_ops.data.models import LeadStatus
from sales_ops.data.store import LeadStore


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _build_full_crm(seed_reply_tracker: bool = True) -> MockCRMConnector:
    """Return a CRM populated with enriched, drafted, synced and (optionally) replied leads."""
    store = LeadStore(seed=True)
    LeadEnrichmentAgent(store).run()
    OutreachDraftingAgent(store).run()
    crm = MockCRMConnector()
    CRMSyncAgent(store, crm, auto_confirm=True).run()
    if seed_reply_tracker:
        imap = MockIMAPClient(seed=42)
        ReplyTrackerAgent(store, crm, imap_client=imap).run()
    return crm


@pytest.fixture
def tmp_forecast_path(tmp_path):
    return str(tmp_path / "forecast_test.json")


@pytest.fixture
def crm_with_deals():
    return _build_full_crm(seed_reply_tracker=True)


@pytest.fixture
def agent(crm_with_deals, tmp_forecast_path):
    return ForecastUpdateAgent(
        crm=crm_with_deals,
        forecast_path=tmp_forecast_path,
        auto_confirm=True,
    )


# ---------------------------------------------------------------------------
# compute_forecast() unit tests
# ---------------------------------------------------------------------------

def test_compute_forecast_returns_forecast_report(agent):
    report = agent.compute_forecast()
    assert isinstance(report, ForecastReport)


def test_compute_forecast_row_count_matches_deal_count(agent, crm_with_deals):
    report = agent.compute_forecast()
    assert len(report.rows) == crm_with_deals.deal_count()


def test_compute_forecast_rows_are_deal_forecast_row_instances(agent):
    report = agent.compute_forecast()
    for row in report.rows:
        assert isinstance(row, DealForecastRow)


def test_compute_forecast_weighted_value_equals_amount_times_probability(agent):
    report = agent.compute_forecast()
    for row in report.rows:
        expected = round(row.amount * row.probability, 10)
        assert abs(row.weighted_value - expected) < 1e-6


def test_compute_forecast_total_pipeline_sums_all_amounts(agent, crm_with_deals):
    report = agent.compute_forecast()
    expected_total = sum(d.amount for d in crm_with_deals.list_deals())
    assert abs(report.total_pipeline - expected_total) < 1e-6


def test_compute_forecast_weighted_pipeline_excludes_closed_deals(agent, crm_with_deals):
    """Weighted pipeline should NOT include CLOSED_WON or CLOSED_LOST amounts."""
    report = agent.compute_forecast()
    closed_stages = {DealStage.CLOSED_WON.value, DealStage.CLOSED_LOST.value}
    manual_weighted = sum(
        row.weighted_value for row in report.rows if row.stage not in closed_stages
    )
    assert abs(report.weighted_pipeline - manual_weighted) < 1e-6


def test_compute_forecast_expected_revenue_is_closed_won_sum(agent, crm_with_deals):
    report = agent.compute_forecast()
    closed_won_total = sum(
        d.amount
        for d in crm_with_deals.list_deals()
        if d.stage == DealStage.CLOSED_WON
    )
    assert abs(report.expected_revenue - closed_won_total) < 1e-6


def test_compute_forecast_closed_lost_value_is_closed_lost_sum(agent, crm_with_deals):
    report = agent.compute_forecast()
    closed_lost_total = sum(
        d.amount
        for d in crm_with_deals.list_deals()
        if d.stage == DealStage.CLOSED_LOST
    )
    assert abs(report.closed_lost_value - closed_lost_total) < 1e-6


def test_compute_forecast_deals_by_stage_sums_to_total(agent, crm_with_deals):
    report = agent.compute_forecast()
    total_in_dict = sum(report.deals_by_stage.values())
    assert total_in_dict == crm_with_deals.deal_count()


def test_compute_forecast_generated_at_is_iso_string(agent):
    report = agent.compute_forecast()
    # Should parse without error
    from datetime import datetime
    dt = datetime.fromisoformat(report.generated_at.replace("Z", "+00:00"))
    assert dt is not None


def test_compute_forecast_lead_status_populated(agent):
    report = agent.compute_forecast()
    for row in report.rows:
        assert row.lead_status != ""  # should be some string


def test_compute_forecast_empty_crm_returns_zero_pipeline(tmp_forecast_path):
    crm = MockCRMConnector()
    agent = ForecastUpdateAgent(crm=crm, forecast_path=tmp_forecast_path, auto_confirm=True)
    report = agent.compute_forecast()
    assert report.total_pipeline == 0.0
    assert report.weighted_pipeline == 0.0
    assert report.expected_revenue == 0.0
    assert report.rows == []


def test_compute_forecast_stage_probabilities_match_defaults(tmp_forecast_path):
    """Deals at their default stage should use the default probability."""
    crm = MockCRMConnector()
    contact = crm.upsert_contact({
        "email": "a@a.com", "first_name": "A", "last_name": "B",
        "company": "ACo", "title": "CEO",
    })
    crm.upsert_deal({
        "contact_id": contact.id,
        "company": "ACo",
        "deal_name": "Test Deal",
        "stage": DealStage.QUALIFICATION.value,
        "amount": 20_000.0,
    })
    agent = ForecastUpdateAgent(crm=crm, forecast_path=tmp_forecast_path, auto_confirm=True)
    report = agent.compute_forecast()
    row = report.rows[0]
    expected_prob = DEAL_STAGE_PROBABILITIES[DealStage.QUALIFICATION]
    assert row.probability == expected_prob
    assert abs(row.weighted_value - 20_000.0 * expected_prob) < 1e-6


# ---------------------------------------------------------------------------
# ForecastReport.to_dict() / serialisability
# ---------------------------------------------------------------------------

def test_forecast_report_to_dict_has_required_keys(agent):
    report = agent.compute_forecast()
    d = report.to_dict()
    for key in (
        "generated_at", "total_pipeline", "weighted_pipeline",
        "expected_revenue", "closed_lost_value",
        "deals_by_stage", "weighted_by_stage", "rows", "metadata",
    ):
        assert key in d


def test_forecast_report_to_dict_is_json_serialisable(agent):
    report = agent.compute_forecast()
    serialised = json.dumps(report.to_dict())  # should not raise
    assert len(serialised) > 0


def test_forecast_report_rows_to_dict_has_required_keys(agent):
    report = agent.compute_forecast()
    if report.rows:
        row_dict = report.rows[0].to_dict()
        for key in (
            "deal_id", "contact_id", "company", "deal_name",
            "stage", "amount", "probability", "weighted_value", "lead_status",
        ):
            assert key in row_dict


# ---------------------------------------------------------------------------
# save_report() / load_report() tests
# ---------------------------------------------------------------------------

def test_save_report_creates_file(agent, tmp_forecast_path):
    report = agent.compute_forecast()
    saved = agent.save_report(report)
    assert saved is True
    assert os.path.exists(tmp_forecast_path)


def test_save_report_writes_valid_json(agent, tmp_forecast_path):
    report = agent.compute_forecast()
    agent.save_report(report)
    with open(tmp_forecast_path, "r") as fh:
        data = json.load(fh)
    assert "weighted_pipeline" in data


def test_save_report_values_match_computed(agent, tmp_forecast_path):
    report = agent.compute_forecast()
    agent.save_report(report)
    with open(tmp_forecast_path, "r") as fh:
        data = json.load(fh)
    assert abs(data["total_pipeline"] - report.total_pipeline) < 1e-6
    assert abs(data["weighted_pipeline"] - report.weighted_pipeline) < 1e-6


def test_load_report_returns_none_when_no_file(tmp_forecast_path):
    crm = MockCRMConnector()
    agent = ForecastUpdateAgent(crm=crm, forecast_path=tmp_forecast_path, auto_confirm=True)
    result = agent.load_report()
    assert result is None


def test_load_report_returns_dict_after_save(agent, tmp_forecast_path):
    report = agent.compute_forecast()
    agent.save_report(report)
    loaded = agent.load_report()
    assert isinstance(loaded, dict)
    assert "generated_at" in loaded


# ---------------------------------------------------------------------------
# Human confirmation gate tests
# ---------------------------------------------------------------------------

def test_save_report_no_confirmation_needed_for_new_file(tmp_forecast_path):
    """File doesn't exist yet — should write without prompting."""
    crm = _build_full_crm()
    # auto_confirm=False but file doesn't exist yet, so no prompt should fire
    agent = ForecastUpdateAgent(crm=crm, forecast_path=tmp_forecast_path, auto_confirm=False)
    report = agent.compute_forecast()
    saved = agent.save_report(report)
    assert saved is True
    assert os.path.exists(tmp_forecast_path)


def test_save_report_declined_does_not_overwrite(tmp_forecast_path, monkeypatch):
    crm = _build_full_crm()
    agent = ForecastUpdateAgent(crm=crm, forecast_path=tmp_forecast_path, auto_confirm=False)
    # First write (no prompt since file new)
    report = agent.compute_forecast()
    agent.save_report(report)
    # Read original content
    with open(tmp_forecast_path, "r") as fh:
        original = fh.read()
    # Now decline the overwrite
    monkeypatch.setattr("builtins.input", lambda _: "n")
    saved = agent.save_report(report)
    assert saved is False
    # File should be unchanged
    with open(tmp_forecast_path, "r") as fh:
        after = fh.read()
    assert original == after


def test_save_report_confirmed_does_overwrite(tmp_forecast_path, monkeypatch):
    crm = _build_full_crm()
    agent = ForecastUpdateAgent(crm=crm, forecast_path=tmp_forecast_path, auto_confirm=False)
    report = agent.compute_forecast()
    agent.save_report(report)
    monkeypatch.setattr("builtins.input", lambda _: "y")
    saved = agent.save_report(report)
    assert saved is True


def test_auto_confirm_true_overwrites_without_input(tmp_forecast_path):
    crm = _build_full_crm()
    agent = ForecastUpdateAgent(crm=crm, forecast_path=tmp_forecast_path, auto_confirm=True)
    report = agent.compute_forecast()
    agent.save_report(report)  # first write
    saved = agent.save_report(report)  # second write — should auto-confirm
    assert saved is True


# ---------------------------------------------------------------------------
# run() integration tests
# ---------------------------------------------------------------------------

def test_run_returns_tuple(agent):
    result = agent.run()
    assert isinstance(result, tuple)
    assert len(result) == 2


def test_run_returns_forecast_report_and_bool(agent):
    report, saved = agent.run()
    assert isinstance(report, ForecastReport)
    assert isinstance(saved, bool)


def test_run_saves_file_on_first_run(agent, tmp_forecast_path):
    _, saved = agent.run()
    assert saved is True
    assert os.path.exists(tmp_forecast_path)


def test_run_auto_confirm_saves_twice(tmp_forecast_path):
    crm = _build_full_crm()
    agent = ForecastUpdateAgent(crm=crm, forecast_path=tmp_forecast_path, auto_confirm=True)
    _, saved1 = agent.run()
    _, saved2 = agent.run()
    assert saved1 is True
    assert saved2 is True


def test_run_declined_second_write(tmp_forecast_path, monkeypatch):
    crm = _build_full_crm()
    agent = ForecastUpdateAgent(crm=crm, forecast_path=tmp_forecast_path, auto_confirm=True)
    agent.run()  # first run OK
    # Second run with manual confirmation = no
    agent.auto_confirm = False
    monkeypatch.setattr("builtins.input", lambda _: "n")
    _, saved = agent.run()
    assert saved is False


def test_run_with_no_deals_produces_zero_report(tmp_forecast_path):
    crm = MockCRMConnector()
    agent = ForecastUpdateAgent(crm=crm, forecast_path=tmp_forecast_path, auto_confirm=True)
    report, saved = agent.run()
    assert report.total_pipeline == 0.0
    assert report.weighted_pipeline == 0.0
    assert saved is True


def test_run_weighted_pipeline_is_non_negative(agent):
    report, _ = agent.run()
    assert report.weighted_pipeline >= 0.0


def test_run_metadata_includes_deal_count(agent, crm_with_deals):
    report, _ = agent.run()
    assert report.metadata["deal_count"] == crm_with_deals.deal_count()


def test_run_all_deal_stages_represented(agent, crm_with_deals):
    report, _ = agent.run()
    crm_stage_values = {d.stage.value for d in crm_with_deals.list_deals()}
    report_stage_values = set(report.deals_by_stage.keys())
    assert crm_stage_values == report_stage_values
