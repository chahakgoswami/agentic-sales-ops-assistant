"""ReplyTrackerAgent: polls a mock IMAP inbox and classifies email replies."""
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from sales_ops.crm.connector import MockCRMConnector, DealStage
from sales_ops.data.models import Lead, LeadStatus
from sales_ops.data.store import LeadStore


# ---------------------------------------------------------------------------
# Reply classification
# ---------------------------------------------------------------------------

class ReplyClassification(str, Enum):
    INTERESTED = "interested"
    NOT_INTERESTED = "not_interested"
    NO_REPLY = "no_reply"


# Keyword sets for classification
_INTERESTED_KEYWORDS = [
    "yes", "interested", "sounds good", "let's connect", "let's chat",
    "book", "schedule", "available", "would love", "tell me more",
    "love to", "happy to", "can we", "great", "absolutely",
    "when can", "set up a call", "demo", "learn more", "curious",
]

_NOT_INTERESTED_KEYWORDS = [
    "not interested", "no thanks", "unsubscribe", "remove me",
    "don't contact", "do not contact", "stop", "opt out", "opt-out",
    "not a fit", "not right now", "maybe later", "not the right time",
    "not relevant", "pass", "not for us", "no need",
]


def classify_reply(body: str) -> ReplyClassification:
    """
    Classify a reply email body using keyword matching.
    Returns ReplyClassification enum value.
    """
    lower_body = body.lower()

    # Check not-interested first (more specific / stronger signal)
    for kw in _NOT_INTERESTED_KEYWORDS:
        if kw in lower_body:
            return ReplyClassification.NOT_INTERESTED

    for kw in _INTERESTED_KEYWORDS:
        if kw in lower_body:
            return ReplyClassification.INTERESTED

    return ReplyClassification.NO_REPLY


# ---------------------------------------------------------------------------
# Mock IMAP / inbox simulation
# ---------------------------------------------------------------------------

@dataclass
class SyntheticReply:
    """Represents a single simulated email reply event."""
    lead_email: str          # the outreach was sent to this address
    lead_id: str             # local store lead ID
    subject: str
    body: str
    received_at: float = field(default_factory=time.time)  # epoch timestamp


# Pre-written synthetic reply bodies keyed loosely by classification intent
_INTERESTED_REPLY_BODIES = [
    "Hi there, this actually sounds really interesting. Would love to learn more — can we set up a 20-minute call next week?",
    "Thanks for reaching out! Yes, we're exploring options in this space. Happy to chat. What does your availability look like?",
    "Absolutely, I'd be open to a quick demo. Send over some times that work for you.",
    "Great timing — we were just discussing this. Tell me more about how it works for companies our size.",
    "Sounds good. Let's connect. I'm available Tuesday or Thursday afternoons.",
]

_NOT_INTERESTED_REPLY_BODIES = [
    "Thanks for reaching out, but we're not interested at this time. Please remove me from your list.",
    "Not relevant for us right now. No thanks.",
    "We've already got a solution in place. Not a fit. Please unsubscribe me.",
    "Appreciate the message but this isn't a priority for us. Not right now.",
    "Pass on this one. Not the right time for our team.",
]

_NEUTRAL_REPLY_BODIES = [
    "Got your message. Will review and get back to you.",
    "Thanks for the note. Forwarding to the relevant team.",
    "Interesting. Can you send over more details in writing first?",
]


class MockIMAPClient:
    """
    Simulates an IMAP email inbox that returns synthetic reply events.
    Uses a seeded random distribution so tests are reproducible.
    """

    # Probability distribution for reply types
    _REPLY_PROBABILITIES = {
        ReplyClassification.INTERESTED: 0.45,
        ReplyClassification.NOT_INTERESTED: 0.30,
        ReplyClassification.NO_REPLY: 0.25,
    }

    def __init__(self, seed: Optional[int] = None):
        self._rng = random.Random(seed)
        self.name = "MockIMAPClient"

    def fetch_replies(
        self,
        leads: List[Lead],
        simulate_delay: bool = False,
    ) -> List[SyntheticReply]:
        """
        Simulate polling the inbox for replies to outreach emails.
        Only generates synthetic replies for leads that have been contacted
        (status OUTREACH_DRAFTED or CONTACTED) and have an outreach subject.

        Returns a list of SyntheticReply objects (may be empty).
        """
        if simulate_delay:
            time.sleep(self._rng.uniform(0.05, 0.15))

        replies: List[SyntheticReply] = []

        for lead in leads:
            # Only simulate replies for leads with outreach drafted/sent
            if lead.status not in (
                LeadStatus.OUTREACH_DRAFTED,
                LeadStatus.CONTACTED,
            ):
                continue

            # Randomly decide if this lead replied
            outcome = self._rng.choices(
                population=list(self._REPLY_PROBABILITIES.keys()),
                weights=list(self._REPLY_PROBABILITIES.values()),
                k=1,
            )[0]

            if outcome == ReplyClassification.NO_REPLY:
                # No reply email to generate
                continue

            if outcome == ReplyClassification.INTERESTED:
                body = self._rng.choice(_INTERESTED_REPLY_BODIES)
            else:
                body = self._rng.choice(_NOT_INTERESTED_REPLY_BODIES)

            subject = f"Re: {lead.outreach_subject or 'Your outreach'}"
            reply = SyntheticReply(
                lead_email=lead.email,
                lead_id=lead.id,
                subject=subject,
                body=body,
            )
            replies.append(reply)
            print(
                f"  [{self.name}] Synthetic reply from {lead.email}: "
                f"{outcome.value!r} — {body[:60]}..."
            )

        return replies


# ---------------------------------------------------------------------------
# ReplyTrackerAgent
# ---------------------------------------------------------------------------

# Map classification → LeadStatus
_CLASSIFICATION_TO_STATUS: Dict[ReplyClassification, LeadStatus] = {
    ReplyClassification.INTERESTED: LeadStatus.REPLIED_INTERESTED,
    ReplyClassification.NOT_INTERESTED: LeadStatus.REPLIED_NOT_INTERESTED,
    ReplyClassification.NO_REPLY: LeadStatus.NO_REPLY,
}

# Map classification → CRM deal stage upgrade
_CLASSIFICATION_TO_DEAL_STAGE: Dict[ReplyClassification, Optional[DealStage]] = {
    ReplyClassification.INTERESTED: DealStage.QUALIFICATION,
    ReplyClassification.NOT_INTERESTED: DealStage.CLOSED_LOST,
    ReplyClassification.NO_REPLY: None,  # no stage change
}


@dataclass
class ReplyResult:
    """Summary of processing a single reply event."""
    lead_id: str
    lead_email: str
    reply_body: str
    classification: ReplyClassification
    new_lead_status: LeadStatus
    crm_deal_stage_updated: bool = False
    crm_contact_status_updated: bool = False


class ReplyTrackerAgent:
    """
    Polls a simulated IMAP inbox, classifies replies, and updates lead
    status in both the local LeadStore and the MockCRMConnector.
    """

    def __init__(
        self,
        store: LeadStore,
        crm: MockCRMConnector,
        imap_client: Optional[MockIMAPClient] = None,
        simulate_delay: bool = False,
    ):
        self.store = store
        self.crm = crm
        self.imap = imap_client or MockIMAPClient()
        self.simulate_delay = simulate_delay
        self.name = "ReplyTrackerAgent"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify_reply(self, reply: SyntheticReply) -> ReplyClassification:
        """Classify a single reply using keyword matching."""
        return classify_reply(reply.body)

    def process_reply(
        self, reply: SyntheticReply
    ) -> Optional[ReplyResult]:
        """
        Process a single reply event:
        1. Classify the reply body.
        2. Update lead status in the local store.
        3. Update CRM contact lead_status and deal stage.

        Returns a ReplyResult, or None if the lead cannot be found.
        """
        lead = self.store.get(reply.lead_id)
        if lead is None:
            print(
                f"  [{self.name}] ⚠ Lead not found for id={reply.lead_id} "
                f"(email={reply.lead_email}) — skipping."
            )
            return None

        classification = classify_reply(reply.body)
        new_status = _CLASSIFICATION_TO_STATUS[classification]

        # --- Update local store ---
        self.store.update_status(lead.id, new_status)
        lead.status = new_status
        lead.enrichment_data["last_reply"] = {
            "subject": reply.subject,
            "body": reply.body,
            "classification": classification.value,
        }
        self.store.upsert(lead)

        print(
            f"  [{self.name}] Lead {lead.email} → {new_status.value} "
            f"(classified as {classification.value})"
        )

        result = ReplyResult(
            lead_id=lead.id,
            lead_email=lead.email,
            reply_body=reply.body,
            classification=classification,
            new_lead_status=new_status,
        )

        # --- Update CRM contact ---
        if lead.crm_contact_id:
            crm_contact = self.crm.get_contact(lead.crm_contact_id)
            if crm_contact:
                crm_contact.lead_status = new_status.value
                result.crm_contact_status_updated = True
                print(
                    f"  [{self.name}] ✓ CRM contact {lead.crm_contact_id} "
                    f"status → {new_status.value}"
                )
        else:
            # Attempt lookup by email as fallback
            crm_contact = self.crm.get_contact_by_email(lead.email)
            if crm_contact:
                crm_contact.lead_status = new_status.value
                # Backfill crm_contact_id
                lead.crm_contact_id = crm_contact.id
                self.store.upsert(lead)
                result.crm_contact_status_updated = True

        # --- Update CRM deal stage ---
        new_stage = _CLASSIFICATION_TO_DEAL_STAGE.get(classification)
        if new_stage is not None and lead.crm_contact_id:
            crm_deal = self.crm.get_deal_for_contact(lead.crm_contact_id)
            if crm_deal is None and lead.crm_deal_id:
                crm_deal = self.crm.get_deal(lead.crm_deal_id)
            if crm_deal:
                self.crm.upsert_deal({
                    "contact_id": crm_deal.contact_id,
                    "stage": new_stage.value,
                    "source_lead_id": lead.id,
                })
                # Backfill deal ID on lead if missing
                if not lead.crm_deal_id:
                    lead.crm_deal_id = crm_deal.id
                    self.store.upsert(lead)
                result.crm_deal_stage_updated = True
                print(
                    f"  [{self.name}] ✓ CRM deal stage → {new_stage.value} "
                    f"for contact {lead.crm_contact_id}"
                )

        return result

    def process_no_reply_leads(self) -> List[ReplyResult]:
        """
        Mark leads with OUTREACH_DRAFTED or CONTACTED status that received
        no reply from the inbox poll as NO_REPLY.

        Call this after run_poll() so that leads not in the reply list get
        a definitive NO_REPLY status.
        """
        no_reply_statuses = {LeadStatus.OUTREACH_DRAFTED, LeadStatus.CONTACTED}
        results: List[ReplyResult] = []

        for lead in self.store.get_all():
            if lead.status not in no_reply_statuses:
                continue

            self.store.update_status(lead.id, LeadStatus.NO_REPLY)
            lead.status = LeadStatus.NO_REPLY
            self.store.upsert(lead)

            # Update CRM contact if linked
            if lead.crm_contact_id:
                crm_contact = self.crm.get_contact(lead.crm_contact_id)
                if crm_contact:
                    crm_contact.lead_status = LeadStatus.NO_REPLY.value

            print(
                f"  [{self.name}] No-reply: {lead.email} → {LeadStatus.NO_REPLY.value}"
            )
            results.append(
                ReplyResult(
                    lead_id=lead.id,
                    lead_email=lead.email,
                    reply_body="",
                    classification=ReplyClassification.NO_REPLY,
                    new_lead_status=LeadStatus.NO_REPLY,
                    crm_contact_status_updated=lead.crm_contact_id is not None,
                )
            )

        return results

    def run(
        self,
        mark_no_reply: bool = True,
    ) -> Tuple[List[ReplyResult], List[ReplyResult]]:
        """
        Full poll cycle:
        1. Fetch synthetic replies from the mock IMAP inbox.
        2. Classify and process each reply.
        3. Optionally mark remaining drafted/contacted leads as NO_REPLY.

        Returns (reply_results, no_reply_results).
        """
        eligible_leads = [
            lead for lead in self.store.get_all()
            if lead.status in {LeadStatus.OUTREACH_DRAFTED, LeadStatus.CONTACTED}
        ]

        print(
            f"[{self.name}] Polling inbox for {len(eligible_leads)} "
            f"outreach-eligible lead(s)."
        )

        replies = self.imap.fetch_replies(
            eligible_leads, simulate_delay=self.simulate_delay
        )
        print(f"[{self.name}] Received {len(replies)} reply event(s).")

        replied_lead_ids = set()
        reply_results: List[ReplyResult] = []
        for reply in replies:
            result = self.process_reply(reply)
            if result:
                reply_results.append(result)
                replied_lead_ids.add(reply.lead_id)

        no_reply_results: List[ReplyResult] = []
        if mark_no_reply:
            no_reply_results = self.process_no_reply_leads()

        total = len(reply_results) + len(no_reply_results)
        print(
            f"[{self.name}] Done. {len(reply_results)} replied, "
            f"{len(no_reply_results)} no-reply, {total} total processed."
        )
        return reply_results, no_reply_results
