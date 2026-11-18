"""CRMSyncAgent: syncs enriched leads and outreach drafts into the mock CRM."""
from typing import Dict, Any, List, Tuple, Optional
from sales_ops.data.models import Lead, LeadStatus
from sales_ops.data.store import LeadStore
from sales_ops.crm.connector import MockCRMConnector, CRMContact, CRMDeal, DealStage


DEFAULT_DEAL_AMOUNT: float = 10_000.0  # default estimated deal value


def _confirm(prompt: str, auto_confirm: bool = False) -> bool:
    """
    Human-in-the-loop confirmation gate.
    If auto_confirm is True (useful in tests / headless pipelines), skips the
    interactive prompt and returns True automatically.
    """
    if auto_confirm:
        print(f"  [HITL] Auto-confirmed: {prompt}")
        return True
    answer = input(f"  [HITL] {prompt} [y/N]: ").strip().lower()
    return answer in ("y", "yes")


def _build_contact_payload(lead: Lead) -> Dict[str, Any]:
    """Map a Lead to a CRM contact upsert payload."""
    return {
        "email": lead.email,
        "first_name": lead.first_name,
        "last_name": lead.last_name,
        "company": lead.company,
        "title": lead.title,
        "phone": lead.phone,
        "website": lead.website,
        "industry": lead.industry,
        "company_size": lead.company_size,
        "linkedin_url": lead.linkedin_url,
        "linkedin_headline": lead.linkedin_headline,
        "lead_status": lead.status.value,
        "outreach_subject": lead.outreach_subject,
        "outreach_body": lead.outreach_body,
        "source_lead_id": lead.id,
        "properties": {
            "annual_revenue": lead.annual_revenue,
            "hq_location": lead.hq_location,
            "tech_stack": lead.tech_stack,
            "linkedin_connections": lead.linkedin_connections,
        },
    }


def _build_deal_payload(lead: Lead, contact_id: str) -> Dict[str, Any]:
    """Map a Lead + CRM contact ID to a CRM deal upsert payload."""
    return {
        "contact_id": contact_id,
        "company": lead.company,
        "deal_name": f"{lead.company} — {lead.title}",
        "stage": DealStage.PROSPECTING.value,
        "amount": DEFAULT_DEAL_AMOUNT,
        "source_lead_id": lead.id,
        "properties": {
            "lead_status": lead.status.value,
            "outreach_subject": lead.outreach_subject,
        },
    }


class CRMSyncAgent:
    """
    Syncs enriched leads (and their outreach drafts) into the MockCRMConnector.
    Every write operation is gated behind a human-in-the-loop confirmation
    prompt unless auto_confirm=True.
    """

    SYNCABLE_STATUSES = {
        LeadStatus.ENRICHED,
        LeadStatus.OUTREACH_DRAFTED,
        LeadStatus.CONTACTED,
        LeadStatus.REPLIED_INTERESTED,
        LeadStatus.REPLIED_NOT_INTERESTED,
        LeadStatus.NO_REPLY,
        LeadStatus.CLOSED_WON,
        LeadStatus.CLOSED_LOST,
    }

    def __init__(
        self,
        store: LeadStore,
        crm: MockCRMConnector,
        auto_confirm: bool = False,
    ):
        self.store = store
        self.crm = crm
        self.auto_confirm = auto_confirm
        self.name = "CRMSyncAgent"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def sync_lead(
        self, lead: Lead
    ) -> Tuple[Optional[CRMContact], Optional[CRMDeal]]:
        """
        Sync a single lead into the CRM (contact + deal).
        Returns the (CRMContact, CRMDeal) tuple if confirmed, else (None, None).
        """
        print(
            f"  [{self.name}] Preparing to sync: "
            f"{lead.first_name} {lead.last_name} <{lead.email}>"
        )

        # --- Contact upsert ---
        contact_payload = _build_contact_payload(lead)
        confirmed = _confirm(
            f"Upsert CRM contact for {lead.first_name} {lead.last_name} "
            f"<{lead.email}> (company={lead.company})?  ",
            auto_confirm=self.auto_confirm,
        )
        if not confirmed:
            print(f"  [{self.name}] ✗ Skipped contact sync for {lead.email}.")
            return None, None

        contact = self.crm.upsert_contact(contact_payload)

        # Write CRM contact ID back to the local lead record
        lead.crm_contact_id = contact.id
        self.store.upsert(lead)

        # --- Deal upsert ---
        deal_payload = _build_deal_payload(lead, contact.id)
        confirmed = _confirm(
            f"Upsert CRM deal '{deal_payload['deal_name']}' "
            f"(stage={deal_payload['stage']}, amount=${deal_payload['amount']:,.0f})?  ",
            auto_confirm=self.auto_confirm,
        )
        if not confirmed:
            print(f"  [{self.name}] ✗ Skipped deal sync for {lead.email}.")
            return contact, None

        deal = self.crm.upsert_deal(deal_payload)

        # Write CRM deal ID back to the local lead record
        lead.crm_deal_id = deal.id
        self.store.upsert(lead)

        print(
            f"  [{self.name}] ✓ Synced: contact_id={contact.id}, deal_id={deal.id}"
        )
        return contact, deal

    def run(self) -> List[Tuple[Optional[CRMContact], Optional[CRMDeal]]]:
        """
        Sync all leads whose status makes them eligible for CRM sync.
        Returns a list of (CRMContact, CRMDeal) tuples for each processed lead.
        """
        leads_to_sync = [
            lead
            for lead in self.store.get_all()
            if lead.status in self.SYNCABLE_STATUSES
        ]

        print(
            f"[{self.name}] Found {len(leads_to_sync)} lead(s) eligible for CRM sync."
        )

        results = []
        for lead in leads_to_sync:
            result = self.sync_lead(lead)
            results.append(result)

        synced_count = sum(1 for c, d in results if c is not None)
        print(
            f"[{self.name}] Sync complete. "
            f"{synced_count}/{len(leads_to_sync)} lead(s) synced to CRM."
        )
        return results
