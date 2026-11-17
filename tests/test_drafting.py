"""Tests for the OutreachDraftingAgent."""
import pytest
from sales_ops.data.store import LeadStore
from sales_ops.data.models import Lead, LeadStatus
from sales_ops.agents.enrichment import LeadEnrichmentAgent
from sales_ops.agents.drafting import (
    OutreachDraftingAgent,
    _mock_llm,
    _build_prompt,
    _build_tech_stack_snippet,
)


# ---------------------------------------------------------------------------
# Helper: create and enrich a lead so drafting has all required fields
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
    agent = LeadEnrichmentAgent(store)
    agent.enrich_lead(lead)
    return lead


# ---------------------------------------------------------------------------
# Unit tests for helpers
# ---------------------------------------------------------------------------

def test_build_tech_stack_snippet_full():
    result = _build_tech_stack_snippet(["AWS", "Kubernetes", "Terraform", "Go"])
    assert result == "AWS, Kubernetes, Terraform"


def test_build_tech_stack_snippet_short():
    result = _build_tech_stack_snippet(["Python"])
    assert result == "Python"


def test_build_tech_stack_snippet_none():
    result = _build_tech_stack_snippet(None)
    assert result == "your current stack"


def test_build_tech_stack_snippet_empty():
    result = _build_tech_stack_snippet([])
    assert result == "your current stack"


def test_build_prompt_contains_lead_fields():
    store = LeadStore(seed=False)
    lead = _make_enriched_lead(store)
    prompt = _build_prompt(lead)
    assert "Sarah" in prompt
    assert "TechOrbit" in prompt
    assert lead.industry in prompt


# ---------------------------------------------------------------------------
# Unit tests for _mock_llm
# ---------------------------------------------------------------------------

def test_mock_llm_returns_required_keys():
    context = {
        "first_name": "Sarah",
        "last_name": "Chen",
        "company": "TechOrbit",
        "title": "VP of Engineering",
        "industry": "SaaS / Cloud Infrastructure",
        "company_size": "51-200",
        "tech_stack": ["AWS", "Kubernetes"],
        "annual_revenue": "$10M-$50M",
        "hq_location": "San Francisco, CA",
        "linkedin_headline": "VP Engineering @ TechOrbit",
    }
    result = _mock_llm("test prompt", "SaaS / Cloud Infrastructure", context)
    for key in ("subject", "body", "model", "industry_template_used"):
        assert key in result


def test_mock_llm_uses_known_industry_template():
    context = {
        "first_name": "Priya",
        "last_name": "Patel",
        "company": "CloudNova AI",
        "title": "Head of Product",
        "industry": "Artificial Intelligence",
        "company_size": "11-50",
        "tech_stack": ["Azure", "Python"],
        "annual_revenue": "$1M-$10M",
        "hq_location": "Palo Alto, CA",
        "linkedin_headline": "Head of Product @ CloudNova AI",
    }
    result = _mock_llm("prompt", "Artificial Intelligence", context)
    assert result["industry_template_used"] == "Artificial Intelligence"


def test_mock_llm_falls_back_to_default_for_unknown_industry():
    context = {
        "first_name": "Alice",
        "last_name": "Smith",
        "company": "GenericCo",
        "title": "CEO",
        "industry": "Underwater Basket Weaving",
        "company_size": "10",
        "tech_stack": [],
        "annual_revenue": None,
        "hq_location": None,
        "linkedin_headline": None,
    }
    result = _mock_llm("prompt", "Underwater Basket Weaving", context)
    assert result["industry_template_used"] == "default"


def test_mock_llm_interpolates_company_name():
    context = {
        "first_name": "Marcus",
        "last_name": "Williams",
        "company": "GrowFast Inc.",
        "title": "CRO",
        "industry": "Marketing Technology",
        "company_size": "201-500",
        "tech_stack": ["Salesforce", "HubSpot"],
        "annual_revenue": "$50M-$200M",
        "hq_location": "New York, NY",
        "linkedin_headline": "CRO @ GrowFast",
    }
    result = _mock_llm("prompt", "Marketing Technology", context)
    assert "GrowFast Inc." in result["subject"] or "GrowFast Inc." in result["body"]


# ---------------------------------------------------------------------------
# Unit tests for OutreachDraftingAgent
# ---------------------------------------------------------------------------

def test_draft_for_lead_sets_subject_and_body():
    store = LeadStore(seed=False)
    lead = _make_enriched_lead(store)
    agent = OutreachDraftingAgent(store)
    result = agent.draft_for_lead(lead)

    assert result.outreach_subject is not None
    assert len(result.outreach_subject) > 0
    assert result.outreach_body is not None
    assert len(result.outreach_body) > 0


def test_draft_for_lead_updates_status():
    store = LeadStore(seed=False)
    lead = _make_enriched_lead(store)
    agent = OutreachDraftingAgent(store)
    agent.draft_for_lead(lead)

    assert lead.status == LeadStatus.OUTREACH_DRAFTED


def test_draft_for_lead_persists_to_store():
    store = LeadStore(seed=False)
    lead = _make_enriched_lead(store)
    agent = OutreachDraftingAgent(store)
    agent.draft_for_lead(lead)

    stored = store.get(lead.id)
    assert stored.outreach_subject == lead.outreach_subject
    assert stored.outreach_body == lead.outreach_body
    assert stored.status == LeadStatus.OUTREACH_DRAFTED


def test_draft_for_lead_stores_audit_metadata():
    store = LeadStore(seed=False)
    lead = _make_enriched_lead(store)
    agent = OutreachDraftingAgent(store)
    agent.draft_for_lead(lead)

    assert "outreach_draft" in lead.enrichment_data
    draft_meta = lead.enrichment_data["outreach_draft"]
    assert "prompt" in draft_meta
    assert "model" in draft_meta
    assert "industry_template_used" in draft_meta


def test_draft_for_unenriched_lead_raises():
    store = LeadStore(seed=False)
    lead = Lead(
        first_name="Test",
        last_name="User",
        email="test@example.com",
        company="TestCo",
        title="Engineer",
    )
    store.upsert(lead)
    agent = OutreachDraftingAgent(store)

    with pytest.raises(ValueError, match="not been enriched"):
        agent.draft_for_lead(lead)


def test_agent_run_drafts_all_enriched_leads():
    store = LeadStore(seed=True)
    enrichment_agent = LeadEnrichmentAgent(store)
    enrichment_agent.run()

    drafting_agent = OutreachDraftingAgent(store)
    drafted = drafting_agent.run()

    assert len(drafted) == 5
    for lead in store.get_all():
        assert lead.status == LeadStatus.OUTREACH_DRAFTED
        assert lead.outreach_subject is not None
        assert lead.outreach_body is not None


def test_agent_run_skips_non_enriched_leads():
    store = LeadStore(seed=True)  # all leads are NEW
    agent = OutreachDraftingAgent(store)
    drafted = agent.run()

    assert len(drafted) == 0


def test_agent_run_returns_only_enriched():
    store = LeadStore(seed=True)
    enrichment_agent = LeadEnrichmentAgent(store)
    # Enrich only the first lead
    first_lead = store.get_all()[0]
    enrichment_agent.enrich_lead(first_lead)

    drafting_agent = OutreachDraftingAgent(store)
    drafted = drafting_agent.run()

    assert len(drafted) == 1
    assert drafted[0].id == first_lead.id


def test_draft_body_contains_first_name():
    store = LeadStore(seed=False)
    lead = _make_enriched_lead(
        store,
        first_name="James",
        last_name="O'Brien",
        email="jobrien@scalepath.co",
        company="ScalePath",
        title="CEO",
    )
    agent = OutreachDraftingAgent(store)
    agent.draft_for_lead(lead)

    assert "James" in lead.outreach_body


def test_draft_subject_contains_company_name():
    store = LeadStore(seed=False)
    lead = _make_enriched_lead(
        store,
        first_name="Aisha",
        last_name="Nkosi",
        email="aisha.nkosi@databridge.net",
        company="DataBridge Networks",
        title="Director of Operations",
    )
    agent = OutreachDraftingAgent(store)
    agent.draft_for_lead(lead)

    assert "DataBridge Networks" in lead.outreach_subject
