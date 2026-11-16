"""Tests for the LeadEnrichmentAgent."""
import pytest
from sales_ops.data.store import LeadStore
from sales_ops.data.models import Lead, LeadStatus
from sales_ops.agents.enrichment import LeadEnrichmentAgent, _stub_company_api, _stub_linkedin_api


def test_stub_company_api_returns_expected_keys():
    result = _stub_company_api("TechOrbit")
    for key in ("company", "industry", "company_size", "annual_revenue", "hq_location", "tech_stack"):
        assert key in result


def test_stub_company_api_known_company():
    result = _stub_company_api("TechOrbit")
    assert result["industry"] == "SaaS / Cloud Infrastructure"
    assert result["company_size"] == "51-200"


def test_stub_company_api_unknown_company():
    result = _stub_company_api("UnknownCorp")
    assert result["industry"] == "Technology"


def test_stub_linkedin_api_returns_expected_keys():
    result = _stub_linkedin_api("test@example.com", "John", "Doe", "TestCo")
    for key in ("linkedin_url", "headline", "connections"):
        assert key in result


def test_stub_linkedin_api_url_format():
    result = _stub_linkedin_api("test@example.com", "Jane", "Smith", "AcmeCo")
    assert result["linkedin_url"].startswith("https://www.linkedin.com/in/")


def test_enrich_lead_sets_fields():
    store = LeadStore(seed=False)
    lead = Lead(
        first_name="Sarah",
        last_name="Chen",
        email="sarah.chen@techorbit.io",
        company="TechOrbit",
        title="VP of Engineering",
    )
    store.upsert(lead)
    agent = LeadEnrichmentAgent(store)
    enriched = agent.enrich_lead(lead)

    assert enriched.industry == "SaaS / Cloud Infrastructure"
    assert enriched.company_size == "51-200"
    assert enriched.linkedin_url is not None
    assert enriched.linkedin_headline is not None
    assert enriched.linkedin_connections is not None
    assert enriched.status == LeadStatus.ENRICHED


def test_enrich_lead_persists_to_store():
    store = LeadStore(seed=False)
    lead = Lead(
        first_name="Marcus",
        last_name="Williams",
        email="m.williams@growfast.com",
        company="GrowFast Inc.",
        title="CRO",
    )
    store.upsert(lead)
    agent = LeadEnrichmentAgent(store)
    agent.enrich_lead(lead)

    stored = store.get(lead.id)
    assert stored.status == LeadStatus.ENRICHED
    assert stored.industry == "Marketing Technology"


def test_agent_run_enriches_all_new_leads():
    store = LeadStore(seed=True)
    agent = LeadEnrichmentAgent(store)
    enriched = agent.run()

    assert len(enriched) == 5
    for lead in store.get_all():
        assert lead.status == LeadStatus.ENRICHED


def test_agent_run_skips_already_enriched():
    store = LeadStore(seed=True)
    agent = LeadEnrichmentAgent(store)
    # Enrich all first
    agent.run()
    # Second run should find 0 NEW leads
    second_run = agent.run()
    assert len(second_run) == 0


def test_enrichment_data_audit_stored():
    store = LeadStore(seed=False)
    lead = Lead(
        first_name="Priya",
        last_name="Patel",
        email="priya.patel@cloudnova.ai",
        company="CloudNova AI",
        title="Head of Product",
    )
    store.upsert(lead)
    agent = LeadEnrichmentAgent(store)
    agent.enrich_lead(lead)

    assert "company_api" in lead.enrichment_data
    assert "linkedin_api" in lead.enrichment_data
