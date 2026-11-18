"""MockCRMConnector: HubSpot-style in-memory CRM with contacts and deals."""
import uuid
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum


class DealStage(str, Enum):
    PROSPECTING = "prospecting"
    QUALIFICATION = "qualification"
    PROPOSAL = "proposal"
    NEGOTIATION = "negotiation"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"


@dataclass
class CRMContact:
    """Represents a contact record in the mock CRM."""
    email: str
    first_name: str
    last_name: str
    company: str
    title: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    phone: Optional[str] = None
    website: Optional[str] = None
    industry: Optional[str] = None
    company_size: Optional[str] = None
    linkedin_url: Optional[str] = None
    linkedin_headline: Optional[str] = None
    lead_status: str = "new"
    outreach_subject: Optional[str] = None
    outreach_body: Optional[str] = None
    source_lead_id: Optional[str] = None
    properties: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "email": self.email,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "company": self.company,
            "title": self.title,
            "phone": self.phone,
            "website": self.website,
            "industry": self.industry,
            "company_size": self.company_size,
            "linkedin_url": self.linkedin_url,
            "linkedin_headline": self.linkedin_headline,
            "lead_status": self.lead_status,
            "outreach_subject": self.outreach_subject,
            "outreach_body": self.outreach_body,
            "source_lead_id": self.source_lead_id,
            "properties": self.properties,
        }


@dataclass
class CRMDeal:
    """Represents a deal/opportunity record in the mock CRM."""
    contact_id: str
    company: str
    deal_name: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    stage: DealStage = DealStage.PROSPECTING
    amount: float = 0.0
    probability: float = 0.1
    source_lead_id: Optional[str] = None
    properties: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "contact_id": self.contact_id,
            "company": self.company,
            "deal_name": self.deal_name,
            "stage": self.stage.value,
            "amount": self.amount,
            "probability": self.probability,
            "source_lead_id": self.source_lead_id,
            "properties": self.properties,
        }


# Default deal stage probability weights
DEAL_STAGE_PROBABILITIES: Dict[DealStage, float] = {
    DealStage.PROSPECTING: 0.10,
    DealStage.QUALIFICATION: 0.25,
    DealStage.PROPOSAL: 0.50,
    DealStage.NEGOTIATION: 0.75,
    DealStage.CLOSED_WON: 1.00,
    DealStage.CLOSED_LOST: 0.00,
}


class MockCRMConnector:
    """
    Simulates a HubSpot-style CRM with in-memory contact and deal records.
    Provides upsert, lookup, and listing operations.
    """

    def __init__(self):
        self._contacts: Dict[str, CRMContact] = {}  # keyed by CRMContact.id
        self._contacts_by_email: Dict[str, str] = {}  # email -> contact_id
        self._deals: Dict[str, CRMDeal] = {}  # keyed by CRMDeal.id
        self._deals_by_contact: Dict[str, str] = {}  # contact_id -> deal_id
        self.name = "MockCRMConnector"

    # ------------------------------------------------------------------
    # Contact operations
    # ------------------------------------------------------------------

    def upsert_contact(self, contact_data: Dict[str, Any]) -> CRMContact:
        """
        Insert or update a contact.  Looks up by email as the unique key.
        Returns the resulting CRMContact.
        """
        email = contact_data["email"]
        existing_id = self._contacts_by_email.get(email)

        if existing_id:
            contact = self._contacts[existing_id]
            # Update mutable fields
            for attr in (
                "first_name", "last_name", "company", "title",
                "phone", "website", "industry", "company_size",
                "linkedin_url", "linkedin_headline", "lead_status",
                "outreach_subject", "outreach_body", "source_lead_id",
            ):
                if attr in contact_data:
                    setattr(contact, attr, contact_data[attr])
            if "properties" in contact_data:
                contact.properties.update(contact_data["properties"])
            print(
                f"  [{self.name}] Updated contact: {contact.first_name} "
                f"{contact.last_name} <{email}> (id={contact.id})"
            )
        else:
            contact = CRMContact(
                email=email,
                first_name=contact_data.get("first_name", ""),
                last_name=contact_data.get("last_name", ""),
                company=contact_data.get("company", ""),
                title=contact_data.get("title", ""),
                phone=contact_data.get("phone"),
                website=contact_data.get("website"),
                industry=contact_data.get("industry"),
                company_size=contact_data.get("company_size"),
                linkedin_url=contact_data.get("linkedin_url"),
                linkedin_headline=contact_data.get("linkedin_headline"),
                lead_status=contact_data.get("lead_status", "new"),
                outreach_subject=contact_data.get("outreach_subject"),
                outreach_body=contact_data.get("outreach_body"),
                source_lead_id=contact_data.get("source_lead_id"),
                properties=contact_data.get("properties", {}),
            )
            self._contacts[contact.id] = contact
            self._contacts_by_email[email] = contact.id
            print(
                f"  [{self.name}] Created contact: {contact.first_name} "
                f"{contact.last_name} <{email}> (id={contact.id})"
            )

        return contact

    def get_contact(self, contact_id: str) -> Optional[CRMContact]:
        return self._contacts.get(contact_id)

    def get_contact_by_email(self, email: str) -> Optional[CRMContact]:
        cid = self._contacts_by_email.get(email)
        return self._contacts.get(cid) if cid else None

    def list_contacts(self) -> List[CRMContact]:
        return list(self._contacts.values())

    def contact_count(self) -> int:
        return len(self._contacts)

    # ------------------------------------------------------------------
    # Deal operations
    # ------------------------------------------------------------------

    def upsert_deal(self, deal_data: Dict[str, Any]) -> CRMDeal:
        """
        Insert or update a deal.  Uses contact_id as the unique key
        (one deal per contact in this simulation).
        Returns the resulting CRMDeal.
        """
        contact_id = deal_data["contact_id"]
        existing_id = self._deals_by_contact.get(contact_id)

        if existing_id:
            deal = self._deals[existing_id]
            for attr in ("deal_name", "amount", "source_lead_id", "company"):
                if attr in deal_data:
                    setattr(deal, attr, deal_data[attr])
            if "stage" in deal_data:
                raw_stage = deal_data["stage"]
                deal.stage = DealStage(raw_stage) if isinstance(raw_stage, str) else raw_stage
            if "probability" in deal_data:
                deal.probability = deal_data["probability"]
            elif "stage" in deal_data:
                deal.probability = DEAL_STAGE_PROBABILITIES.get(deal.stage, 0.1)
            if "properties" in deal_data:
                deal.properties.update(deal_data["properties"])
            print(
                f"  [{self.name}] Updated deal: {deal.deal_name} "
                f"(id={deal.id}, stage={deal.stage.value})"
            )
        else:
            raw_stage = deal_data.get("stage", DealStage.PROSPECTING)
            stage = DealStage(raw_stage) if isinstance(raw_stage, str) else raw_stage
            deal = CRMDeal(
                contact_id=contact_id,
                company=deal_data.get("company", ""),
                deal_name=deal_data.get("deal_name", ""),
                stage=stage,
                amount=deal_data.get("amount", 0.0),
                probability=deal_data.get(
                    "probability", DEAL_STAGE_PROBABILITIES.get(stage, 0.1)
                ),
                source_lead_id=deal_data.get("source_lead_id"),
                properties=deal_data.get("properties", {}),
            )
            self._deals[deal.id] = deal
            self._deals_by_contact[contact_id] = deal.id
            print(
                f"  [{self.name}] Created deal: {deal.deal_name} "
                f"(id={deal.id}, stage={deal.stage.value})"
            )

        return deal

    def get_deal(self, deal_id: str) -> Optional[CRMDeal]:
        return self._deals.get(deal_id)

    def get_deal_for_contact(self, contact_id: str) -> Optional[CRMDeal]:
        did = self._deals_by_contact.get(contact_id)
        return self._deals.get(did) if did else None

    def list_deals(self) -> List[CRMDeal]:
        return list(self._deals.values())

    def deal_count(self) -> int:
        return len(self._deals)

    def __repr__(self) -> str:
        return (
            f"MockCRMConnector("
            f"contacts={self.contact_count()}, "
            f"deals={self.deal_count()})"
        )
