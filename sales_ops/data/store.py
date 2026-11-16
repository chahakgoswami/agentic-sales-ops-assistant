"""In-memory lead store with sample seed data."""
from typing import Dict, List, Optional
from sales_ops.data.models import Lead, LeadStatus


SAMPLE_LEADS = [
    Lead(
        first_name="Sarah",
        last_name="Chen",
        email="sarah.chen@techorbit.io",
        company="TechOrbit",
        title="VP of Engineering",
        phone="+1-415-555-0192",
        website="https://techorbit.io",
    ),
    Lead(
        first_name="Marcus",
        last_name="Williams",
        email="m.williams@growfast.com",
        company="GrowFast Inc.",
        title="Chief Revenue Officer",
        phone="+1-212-555-0847",
        website="https://growfast.com",
    ),
    Lead(
        first_name="Priya",
        last_name="Patel",
        email="priya.patel@cloudnova.ai",
        company="CloudNova AI",
        title="Head of Product",
        phone="+1-650-555-0334",
        website="https://cloudnova.ai",
    ),
    Lead(
        first_name="James",
        last_name="O'Brien",
        email="jobrien@scalepath.co",
        company="ScalePath",
        title="CEO",
        phone="+1-512-555-0671",
        website="https://scalepath.co",
    ),
    Lead(
        first_name="Aisha",
        last_name="Nkosi",
        email="aisha.nkosi@databridge.net",
        company="DataBridge Networks",
        title="Director of Operations",
        phone="+1-404-555-0128",
        website="https://databridge.net",
    ),
]


class LeadStore:
    """In-memory store for lead records."""

    def __init__(self, seed: bool = True):
        self._leads: Dict[str, Lead] = {}
        if seed:
            self._seed()

    def _seed(self) -> None:
        for lead in SAMPLE_LEADS:
            self._leads[lead.id] = lead

    def get(self, lead_id: str) -> Optional[Lead]:
        return self._leads.get(lead_id)

    def get_all(self) -> List[Lead]:
        return list(self._leads.values())

    def get_by_status(self, status: LeadStatus) -> List[Lead]:
        return [l for l in self._leads.values() if l.status == status]

    def upsert(self, lead: Lead) -> Lead:
        self._leads[lead.id] = lead
        return lead

    def update_status(self, lead_id: str, status: LeadStatus) -> Optional[Lead]:
        lead = self._leads.get(lead_id)
        if lead:
            lead.status = status
        return lead

    def count(self) -> int:
        return len(self._leads)

    def __repr__(self) -> str:
        return f"LeadStore(leads={self.count()})"
