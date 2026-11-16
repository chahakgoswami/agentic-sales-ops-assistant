"""Tests for the in-memory lead store."""
import pytest
from sales_ops.data.store import LeadStore, SAMPLE_LEADS
from sales_ops.data.models import Lead, LeadStatus


def test_store_seeds_sample_leads():
    store = LeadStore(seed=True)
    assert store.count() == len(SAMPLE_LEADS)


def test_store_empty_without_seed():
    store = LeadStore(seed=False)
    assert store.count() == 0


def test_get_all_returns_all_leads():
    store = LeadStore(seed=True)
    leads = store.get_all()
    assert len(leads) == len(SAMPLE_LEADS)


def test_upsert_adds_new_lead():
    store = LeadStore(seed=False)
    lead = Lead(
        first_name="Test",
        last_name="User",
        email="test@example.com",
        company="TestCo",
        title="Engineer",
    )
    store.upsert(lead)
    assert store.count() == 1
    assert store.get(lead.id) is lead


def test_upsert_updates_existing_lead():
    store = LeadStore(seed=False)
    lead = Lead(
        first_name="Test",
        last_name="User",
        email="test@example.com",
        company="TestCo",
        title="Engineer",
    )
    store.upsert(lead)
    lead.title = "Senior Engineer"
    store.upsert(lead)
    assert store.count() == 1
    assert store.get(lead.id).title == "Senior Engineer"


def test_get_by_status():
    store = LeadStore(seed=True)
    new_leads = store.get_by_status(LeadStatus.NEW)
    assert len(new_leads) == len(SAMPLE_LEADS)


def test_update_status():
    store = LeadStore(seed=True)
    lead = store.get_all()[0]
    store.update_status(lead.id, LeadStatus.ENRICHED)
    assert store.get(lead.id).status == LeadStatus.ENRICHED


def test_get_nonexistent_returns_none():
    store = LeadStore(seed=False)
    assert store.get("nonexistent-id") is None
