"""LeadEnrichmentAgent: enriches leads via stubbed API calls."""
import random
import time
from typing import Dict, Any
from sales_ops.data.models import Lead, LeadStatus
from sales_ops.data.store import LeadStore


# ---------------------------------------------------------------------------
# Stubbed "API" payloads – realistic fake data keyed loosely by company name
# ---------------------------------------------------------------------------

_INDUSTRY_MAP: Dict[str, str] = {
    "TechOrbit": "SaaS / Cloud Infrastructure",
    "GrowFast Inc.": "Marketing Technology",
    "CloudNova AI": "Artificial Intelligence",
    "ScalePath": "Business Consulting",
    "DataBridge Networks": "Data & Analytics",
}

_SIZE_MAP: Dict[str, str] = {
    "TechOrbit": "51-200",
    "GrowFast Inc.": "201-500",
    "CloudNova AI": "11-50",
    "ScalePath": "1-10",
    "DataBridge Networks": "501-1000",
}

_REVENUE_MAP: Dict[str, str] = {
    "TechOrbit": "$10M-$50M",
    "GrowFast Inc.": "$50M-$200M",
    "CloudNova AI": "$1M-$10M",
    "ScalePath": "<$1M",
    "DataBridge Networks": "$200M-$500M",
}

_LOCATION_MAP: Dict[str, str] = {
    "TechOrbit": "San Francisco, CA",
    "GrowFast Inc.": "New York, NY",
    "CloudNova AI": "Palo Alto, CA",
    "ScalePath": "Austin, TX",
    "DataBridge Networks": "Atlanta, GA",
}

_TECH_STACK_MAP: Dict[str, list] = {
    "TechOrbit": ["AWS", "Kubernetes", "Terraform", "Go", "PostgreSQL"],
    "GrowFast Inc.": ["Salesforce", "HubSpot", "Marketo", "Segment", "Snowflake"],
    "CloudNova AI": ["Azure", "Python", "PyTorch", "FastAPI", "Redis"],
    "ScalePath": ["Google Workspace", "Notion", "Zapier", "Stripe"],
    "DataBridge Networks": ["AWS", "Databricks", "dbt", "Kafka", "Redshift"],
}

_LINKEDIN_HEADLINE_MAP: Dict[str, str] = {
    "sarah.chen@techorbit.io": "VP Engineering @ TechOrbit | Cloud-native infrastructure enthusiast",
    "m.williams@growfast.com": "CRO @ GrowFast | Scaling revenue from $10M to $100M",
    "priya.patel@cloudnova.ai": "Head of Product @ CloudNova AI | Building AI that matters",
    "jobrien@scalepath.co": "CEO & Founder @ ScalePath | Helping startups scale smarter",
    "aisha.nkosi@databridge.net": "Director of Ops @ DataBridge | Data-driven decision making",
}

_CONNECTIONS_RANGE = (300, 1200)


def _stub_company_api(company: str) -> Dict[str, Any]:
    """Simulate an external company enrichment API (e.g., Clearbit)."""
    # Simulate network latency
    time.sleep(random.uniform(0.05, 0.15))
    return {
        "company": company,
        "industry": _INDUSTRY_MAP.get(company, "Technology"),
        "company_size": _SIZE_MAP.get(company, "11-50"),
        "annual_revenue": _REVENUE_MAP.get(company, "$1M-$10M"),
        "hq_location": _LOCATION_MAP.get(company, "United States"),
        "tech_stack": _TECH_STACK_MAP.get(company, ["AWS", "Python"]),
        "source": "mock_company_api_v1",
    }


def _stub_linkedin_api(email: str, first_name: str, last_name: str, company: str) -> Dict[str, Any]:
    """Simulate a LinkedIn enrichment API (e.g., ProxyCurl)."""
    time.sleep(random.uniform(0.05, 0.15))
    slug = f"{first_name.lower()}-{last_name.lower()}-{random.randint(10, 99)}"
    headline = _LINKEDIN_HEADLINE_MAP.get(
        email,
        f"{first_name} {last_name} | {company} | Growth & Innovation",
    )
    connections = random.randint(*_CONNECTIONS_RANGE)
    return {
        "linkedin_url": f"https://www.linkedin.com/in/{slug}",
        "headline": headline,
        "connections": connections,
        "source": "mock_linkedin_api_v1",
    }


class LeadEnrichmentAgent:
    """Agent that enriches leads using stubbed external API calls."""

    def __init__(self, store: LeadStore):
        self.store = store
        self.name = "LeadEnrichmentAgent"

    def enrich_lead(self, lead: Lead) -> Lead:
        """Enrich a single lead with company and LinkedIn data."""
        print(f"  [{self.name}] Enriching lead: {lead.first_name} {lead.last_name} <{lead.email}>")

        # --- Company enrichment ---
        company_data = _stub_company_api(lead.company)
        lead.industry = company_data["industry"]
        lead.company_size = company_data["company_size"]
        lead.annual_revenue = company_data["annual_revenue"]
        lead.hq_location = company_data["hq_location"]
        lead.tech_stack = company_data["tech_stack"]

        # --- LinkedIn enrichment ---
        linkedin_data = _stub_linkedin_api(
            lead.email, lead.first_name, lead.last_name, lead.company
        )
        lead.linkedin_url = linkedin_data["linkedin_url"]
        lead.linkedin_headline = linkedin_data["headline"]
        lead.linkedin_connections = linkedin_data["connections"]

        # Store raw API payloads for audit / downstream use
        lead.enrichment_data = {
            "company_api": company_data,
            "linkedin_api": linkedin_data,
        }

        lead.status = LeadStatus.ENRICHED
        self.store.upsert(lead)

        print(
            f"  [{self.name}] ✓ Enriched: industry={lead.industry}, "
            f"size={lead.company_size}, linkedin={lead.linkedin_url}"
        )
        return lead

    def run(self) -> List[Lead]:
        """Enrich all NEW leads in the store."""
        new_leads = self.store.get_by_status(LeadStatus.NEW)
        print(f"[{self.name}] Found {len(new_leads)} new lead(s) to enrich.")
        enriched = []
        for lead in new_leads:
            enriched.append(self.enrich_lead(lead))
        print(f"[{self.name}] Enrichment complete. {len(enriched)} lead(s) enriched.")
        return enriched


# Fix missing import that only affects run() return annotation
from typing import List  # noqa: E402  (placed after usage intentionally for clarity)
