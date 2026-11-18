"""Tests for CRMSyncAgent."""
import pytest
from sales_ops.data.store import LeadStore
from sales_ops.data.models import Lead, LeadStatus
from sales_ops.agents.enrichment import LeadEnrichmentAgent
from sales_ops.agents.drafting import OutreachDraftingAgent
from sales_ops.agents.crm_sync import CRMSyncAgent, _build_contact_payload, _build_deal_payload
from sales_ops.crm.connector import MockCRMConnector, DealStage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_enriched_lead(store: LeadStore, **kwargs) -> Lead:
    defaults = dict(
        first_name="Sarah",
        last_name="Chen",
        email="sarah.chen@techorbit.io",
        company="TechOrbit",
        title="VP of Engineering",
    )
    defaults.update(kwargs)
    lead = Lead(**defaults)
    store.upsert(lead)
    LeadEnrichmentAgent(store).enrich_lead(lead)
    return lead


def _make_drafted_lead(store: LeadStore, **kwargs) -> Lead:
    lead = _make_enriched_lead(store, **kwargs)
    OutreachDraftingAgent(store).draft_for_lead(lead)
    return lead


# ---------------------------------------------------------------------------
# Payload builder tests
# ---------------------------------------------------------------------------

def test_build_contact_payload_contains_required_fields():
    store = LeadStore(seed=False)
    lead = _make_enriched_lead(store)
    payload = _build_contact_payload(lead)
    for key in ("email", "first_name", "last_name", "company", "title", "source_lead_id"):
        assert key in payload
    assert payload["source_lead_id"] == lead.id


def test_build_deal_payload_contains_required_fields():
    store = LeadStore(seed=False)
    lead = _make_enriched_lead(store)
    payload = _build_deal_payload(lead, contact_id="some-contact-id")
    for key in ("contact_id", "company", "deal_name", "stage", "amount"):
        assert key in payload
    assert payload["contact_id"] == "some-contact-id"
    assert payload["source_lead_id"] == lead.id


def test_build_deal_payload_name_includes_company_and_title():
    store = LeadStore(seed=False)
    lead = _make_enriched_lead(store)
    payload = _build_deal_payload(lead, contact_id="cid")
    assert lead.company in payload["deal_name"]
    assert lead.title in payload["deal_name"]


# ---------------------------------------------------------------------------
# CRMSyncAgent: single lead sync
# ---------------------------------------------------------------------------

def test_sync_lead_creates_contact_in_crm():
    store = LeadStore(seed=False)
    lead = _make_enriched_lead(store)
    crm = MockCRMConnector()
    agent = CRMSyncAgent(store, crm, auto_confirm=True)

    contact, deal = agent.sync_lead(lead)
    assert contact is not None
    assert crm.contact_count() == 1
    assert crm.get_contact_by_email(lead.email) is not None


def test_sync_lead_creates_deal_in_crm():
    store = LeadStore(seed=False)
    lead = _make_enriched_lead(store)
    crm = MockCRMConnector()
    agent = CRMSyncAgent(store, crm, auto_confirm=True)

    contact, deal = agent.sync_lead(lead)
    assert deal is not None
    assert crm.deal_count() == 1


def test_sync_lead_writes_crm_contact_id_back_to_lead():
    store = LeadStore(seed=False)
    lead = _make_enriched_lead(store)
    crm = MockCRMConnector()
    agent = CRMSyncAgent(store, crm, auto_confirm=True)

    contact, _ = agent.sync_lead(lead)
    assert lead.crm_contact_id == contact.id
    # Verify persisted in store too
    assert store.get(lead.id).crm_contact_id == contact.id


def test_sync_lead_writes_crm_deal_id_back_to_lead():
    store = LeadStore(seed=False)
    lead = _make_enriched_lead(store)
    crm = MockCRMConnector()
    agent = CRMSyncAgent(store, crm, auto_confirm=True)

    _, deal = agent.sync_lead(lead)
    assert lead.crm_deal_id == deal.id
    assert store.get(lead.id).crm_deal_id == deal.id


def test_sync_lead_idempotent_second_sync():
    store = LeadStore(seed=False)
    lead = _make_enriched_lead(store)
    crm = MockCRMConnector()
    agent = CRMSyncAgent(store, crm, auto_confirm=True)

    agent.sync_lead(lead)
    agent.sync_lead(lead)  # second sync

    assert crm.contact_count() == 1
    assert crm.deal_count() == 1


def test_sync_lead_outreach_draft_stored_in_crm_contact():
    store = LeadStore(seed=False)
    lead = _make_drafted_lead(store)
    crm = MockCRMConnector()
    agent = CRMSyncAgent(store, crm, auto_confirm=True)

    contact, _ = agent.sync_lead(lead)
    crm_contact = crm.get_contact_by_email(lead.email)
    assert crm_contact.outreach_subject == lead.outreach_subject
    assert crm_contact.outreach_body == lead.outreach_body


def test_sync_lead_deal_stage_is_prospecting_by_default():
    store = LeadStore(seed=False)
    lead = _make_enriched_lead(store)
    crm = MockCRMConnector()
    agent = CRMSyncAgent(store, crm, auto_confirm=True)

    _, deal = agent.sync_lead(lead)
    assert deal.stage == DealStage.PROSPECTING


# ---------------------------------------------------------------------------
# CRMSyncAgent: denial / rejection flow
# ---------------------------------------------------------------------------

def test_sync_lead_returns_none_none_when_contact_declined(monkeypatch):
    store = LeadStore(seed=False)
    lead = _make_enriched_lead(store)
    crm = MockCRMConnector()
    agent = CRMSyncAgent(store, crm, auto_confirm=False)

    # Simulate user typing 'n'
    monkeypatch.setattr("builtins.input", lambda _: "n")
    contact, deal = agent.sync_lead(lead)

    assert contact is None
    assert deal is None
    assert crm.contact_count() == 0


def test_sync_lead_returns_contact_none_when_deal_declined(monkeypatch):
    store = LeadStore(seed=False)
    lead = _make_enriched_lead(store)
    crm = MockCRMConnector()
    agent = CRMSyncAgent(store, crm, auto_confirm=False)

    # First confirm (contact) = y, second confirm (deal) = n
    answers = iter(["y", "n"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    contact, deal = agent.sync_lead(lead)

    assert contact is not None
    assert deal is None
    assert crm.contact_count() == 1
    assert crm.deal_count() == 0


# ---------------------------------------------------------------------------
# CRMSyncAgent: run() – batch sync
# ---------------------------------------------------------------------------

def test_run_syncs_all_eligible_leads():
    store = LeadStore(seed=True)
    LeadEnrichmentAgent(store).run()
    crm = MockCRMConnector()
    agent = CRMSyncAgent(store, crm, auto_confirm=True)

    results = agent.run()
    assert len(results) == 5
    assert crm.contact_count() == 5
    assert crm.deal_count() == 5


def test_run_skips_new_leads():
    store = LeadStore(seed=True)  # all leads are NEW
    crm = MockCRMConnector()
    agent = CRMSyncAgent(store, crm, auto_confirm=True)

    results = agent.run()
    assert len(results) == 0
    assert crm.contact_count() == 0


def test_run_syncs_drafted_leads():
    store = LeadStore(seed=True)
    LeadEnrichmentAgent(store).run()
    OutreachDraftingAgent(store).run()
    crm = MockCRMConnector()
    agent = CRMSyncAgent(store, crm, auto_confirm=True)

    results = agent.run()
    assert len(results) == 5
    assert crm.contact_count() == 5


def test_run_returns_tuples():
    store = LeadStore(seed=True)
    LeadEnrichmentAgent(store).run()
    crm = MockCRMConnector()
    agent = CRMSyncAgent(store, crm, auto_confirm=True)

    results = agent.run()
    for item in results:
        assert isinstance(item, tuple)
        assert len(item) == 2
