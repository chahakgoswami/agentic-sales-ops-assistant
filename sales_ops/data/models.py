"""Data models for the Sales Ops Assistant."""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from enum import Enum
import uuid


class LeadStatus(str, Enum):
    NEW = "new"
    ENRICHED = "enriched"
    OUTREACH_DRAFTED = "outreach_drafted"
    CONTACTED = "contacted"
    REPLIED_INTERESTED = "replied_interested"
    REPLIED_NOT_INTERESTED = "replied_not_interested"
    NO_REPLY = "no_reply"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"


@dataclass
class Lead:
    first_name: str
    last_name: str
    email: str
    company: str
    title: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: LeadStatus = LeadStatus.NEW
    phone: Optional[str] = None
    website: Optional[str] = None
    # Enriched fields
    company_size: Optional[str] = None
    industry: Optional[str] = None
    linkedin_url: Optional[str] = None
    linkedin_headline: Optional[str] = None
    linkedin_connections: Optional[int] = None
    annual_revenue: Optional[str] = None
    hq_location: Optional[str] = None
    tech_stack: Optional[list] = None
    # Outreach fields
    outreach_subject: Optional[str] = None
    outreach_body: Optional[str] = None
    # Metadata
    enrichment_data: Dict[str, Any] = field(default_factory=dict)
    crm_contact_id: Optional[str] = None
    crm_deal_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "email": self.email,
            "company": self.company,
            "title": self.title,
            "status": self.status.value,
            "phone": self.phone,
            "website": self.website,
            "company_size": self.company_size,
            "industry": self.industry,
            "linkedin_url": self.linkedin_url,
            "linkedin_headline": self.linkedin_headline,
            "linkedin_connections": self.linkedin_connections,
            "annual_revenue": self.annual_revenue,
            "hq_location": self.hq_location,
            "tech_stack": self.tech_stack,
            "outreach_subject": self.outreach_subject,
            "outreach_body": self.outreach_body,
            "enrichment_data": self.enrichment_data,
            "crm_contact_id": self.crm_contact_id,
            "crm_deal_id": self.crm_deal_id,
        }
