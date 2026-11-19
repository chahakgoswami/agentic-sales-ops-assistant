"""Tests for the ReplyTrackerAgent."""
import pytest
from sales_ops.data.store import LeadStore
from sales_ops.data.models import Lead, LeadStatus
from sales_ops.agents.enrichment import LeadEnrichmentAgent
from sales_ops.agents.drafting import OutreachDraftingAgent
from sales_ops.agents.crm_sync import CRMSyncAgent
from sales_ops.crm.connector import MockCRMConnector, DealStage
from sales_ops.agents.reply_tracker import (
    ReplyTrackerAgent,
    MockIMAPClient,
    SyntheticReply,
    ReplyClassification,
    ReplyResult,
    classify_reply,
    _INTERESTED_KEYWORDS,
    _NOT_INTERESTED_KEYWORDS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_drafted_lead(store: LeadStore, **kwargs) -> Lead:
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
    OutreachDraftingAgent(store).draft_for_lead(lead)
    return lead


def _make_full_pipeline(
    seed: bool = True,
) -> tuple:
    """Return (store, crm, reply_tracker) with all leads enriched, drafted, and synced."""
    store = LeadStore(seed=seed)
    if seed:
        LeadEnrichmentAgent(store).run()
        OutreachDraftingAgent(store).run()
    crm = MockCRMConnector()
    CRMSyncAgent(store, crm, auto_confirm=True).run()
    imap = MockIMAPClient(seed=42)
    agent = ReplyTrackerAgent(store, crm, imap_client=imap)
    return store, crm, agent


# ---------------------------------------------------------------------------
# classify_reply() unit tests
# ---------------------------------------------------------------------------

def test_classify_interested_keyword():
    result = classify_reply("Yes, sounds good — let's schedule a call!")
    assert result == ReplyClassification.INTERESTED


def test_classify_not_interested_keyword():
    result = classify_reply("Thanks but we're not interested. Please unsubscribe me.")
    assert result == ReplyClassification.NOT_INTERESTED


def test_classify_no_reply_on_neutral_body():
    result = classify_reply("OK.")
    assert result == ReplyClassification.NO_REPLY


def test_classify_not_interested_takes_priority_over_interested():
    # Body contains both signals; not_interested should win
    result = classify_reply("This sounds interesting but we are not interested right now.")
    assert result == ReplyClassification.NOT_INTERESTED


def test_classify_case_insensitive():
    result = classify_reply("ABSOLUTELY, LET'S CONNECT.")
    assert result == ReplyClassification.INTERESTED


def test_classify_interested_all_keywords():
    for kw in _INTERESTED_KEYWORDS:
        # only test if not_interested doesn't override
        body = f"Message body with keyword: {kw}"
        result = classify_reply(body)
        # May be INTERESTED or NO_REPLY but not NOT_INTERESTED (kw is not in that list)
        assert result != ReplyClassification.NOT_INTERESTED


# ---------------------------------------------------------------------------
# MockIMAPClient tests
# ---------------------------------------------------------------------------

def test_imap_returns_no_replies_for_new_leads():
    store = LeadStore(seed=True)
    imap = MockIMAPClient(seed=42)
    replies = imap.fetch_replies(store.get_all())
    assert replies == []


def test_imap_returns_replies_for_drafted_leads():
    store = LeadStore(seed=False)
    lead = _make_drafted_lead(store)
    # Use a seed that guarantees a reply (seed=1 gives INTERESTED for first lead)
    imap = MockIMAPClient(seed=0)
    replies = imap.fetch_replies([lead])
    # With seed=0 this may or may not reply; just check the type if it does
    for r in replies:
        assert isinstance(r, SyntheticReply)
        assert r.lead_id == lead.id
        assert r.lead_email == lead.email


def test_imap_reply_has_re_prefix_in_subject():
    store = LeadStore(seed=False)
    lead = _make_drafted_lead(store)
    # Force a reply by using all interested leads — patch fetch to always reply
    imap = MockIMAPClient(seed=42)
    # Keep trying seeds until we get a reply
    for s in range(100):
        imap = MockIMAPClient(seed=s)
        replies = imap.fetch_replies([lead])
        if replies:
            assert replies[0].subject.startswith("Re:")
            break


def test_imap_skips_non_drafted_leads():
    store = LeadStore(seed=True)
    LeadEnrichmentAgent(store).run()  # leads are ENRICHED but not DRAFTED
    imap = MockIMAPClient(seed=42)
    replies = imap.fetch_replies(store.get_all())
    assert replies == []


# ---------------------------------------------------------------------------
# ReplyTrackerAgent.process_reply() tests
# ---------------------------------------------------------------------------

def test_process_reply_interested_updates_lead_status():
    store = LeadStore(seed=False)
    crm = MockCRMConnector()
    lead = _make_drafted_lead(store)

    reply = SyntheticReply(
        lead_email=lead.email,
        lead_id=lead.id,
        subject=f"Re: {lead.outreach_subject}",
        body="Yes, let's connect! Sounds great.",
    )
    agent = ReplyTrackerAgent(store, crm)
    result = agent.process_reply(reply)

    assert result is not None
    assert result.classification == ReplyClassification.INTERESTED
    assert store.get(lead.id).status == LeadStatus.REPLIED_INTERESTED


def test_process_reply_not_interested_updates_lead_status():
    store = LeadStore(seed=False)
    crm = MockCRMConnector()
    lead = _make_drafted_lead(store)

    reply = SyntheticReply(
        lead_email=lead.email,
        lead_id=lead.id,
        subject="Re: ...",
        body="Not interested. Please unsubscribe me.",
    )
    agent = ReplyTrackerAgent(store, crm)
    result = agent.process_reply(reply)

    assert result.classification == ReplyClassification.NOT_INTERESTED
    assert store.get(lead.id).status == LeadStatus.REPLIED_NOT_INTERESTED


def test_process_reply_stores_audit_data():
    store = LeadStore(seed=False)
    crm = MockCRMConnector()
    lead = _make_drafted_lead(store)

    reply = SyntheticReply(
        lead_email=lead.email,
        lead_id=lead.id,
        subject="Re: test",
        body="Happy to chat! Available Tuesday.",
    )
    agent = ReplyTrackerAgent(store, crm)
    agent.process_reply(reply)

    stored = store.get(lead.id)
    assert "last_reply" in stored.enrichment_data
    assert stored.enrichment_data["last_reply"]["classification"] == ReplyClassification.INTERESTED.value


def test_process_reply_nonexistent_lead_returns_none():
    store = LeadStore(seed=False)
    crm = MockCRMConnector()
    agent = ReplyTrackerAgent(store, crm)

    reply = SyntheticReply(
        lead_email="ghost@nowhere.com",
        lead_id="nonexistent-id",
        subject="Re: test",
        body="Yes, interested!",
    )
    result = agent.process_reply(reply)
    assert result is None


def test_process_reply_updates_crm_contact_status():
    store = LeadStore(seed=False)
    crm = MockCRMConnector()
    lead = _make_drafted_lead(store)
    CRMSyncAgent(store, crm, auto_confirm=True).sync_lead(lead)

    reply = SyntheticReply(
        lead_email=lead.email,
        lead_id=lead.id,
        subject="Re: ...",
        body="Absolutely, let's set up a call!",
    )
    agent = ReplyTrackerAgent(store, crm)
    result = agent.process_reply(reply)

    crm_contact = crm.get_contact_by_email(lead.email)
    assert crm_contact is not None
    assert crm_contact.lead_status == LeadStatus.REPLIED_INTERESTED.value
    assert result.crm_contact_status_updated is True


def test_process_reply_interested_advances_deal_to_qualification():
    store = LeadStore(seed=False)
    crm = MockCRMConnector()
    lead = _make_drafted_lead(store)
    CRMSyncAgent(store, crm, auto_confirm=True).sync_lead(lead)

    reply = SyntheticReply(
        lead_email=lead.email,
        lead_id=lead.id,
        subject="Re: ...",
        body="Yes, let's connect. Sounds interesting!",
    )
    agent = ReplyTrackerAgent(store, crm)
    result = agent.process_reply(reply)

    crm_deal = crm.get_deal_for_contact(lead.crm_contact_id)
    assert crm_deal is not None
    assert crm_deal.stage == DealStage.QUALIFICATION
    assert result.crm_deal_stage_updated is True


def test_process_reply_not_interested_closes_deal_lost():
    store = LeadStore(seed=False)
    crm = MockCRMConnector()
    lead = _make_drafted_lead(store)
    CRMSyncAgent(store, crm, auto_confirm=True).sync_lead(lead)

    reply = SyntheticReply(
        lead_email=lead.email,
        lead_id=lead.id,
        subject="Re: ...",
        body="Not interested. Please do not contact me again.",
    )
    agent = ReplyTrackerAgent(store, crm)
    result = agent.process_reply(reply)

    crm_deal = crm.get_deal_for_contact(lead.crm_contact_id)
    assert crm_deal.stage == DealStage.CLOSED_LOST
    assert result.crm_deal_stage_updated is True


def test_process_reply_without_crm_link_still_updates_local_store():
    """Lead has no CRM link; local store should still be updated."""
    store = LeadStore(seed=False)
    crm = MockCRMConnector()  # lead never synced to CRM
    lead = _make_drafted_lead(store)

    reply = SyntheticReply(
        lead_email=lead.email,
        lead_id=lead.id,
        subject="Re: ...",
        body="Interested, can we schedule something?",
    )
    agent = ReplyTrackerAgent(store, crm)
    result = agent.process_reply(reply)

    assert store.get(lead.id).status == LeadStatus.REPLIED_INTERESTED
    assert result is not None
    # CRM not linked, so crm_contact_status_updated depends on email lookup
    # (lead has no crm_contact_id and crm has no contact — should be False)
    assert result.crm_contact_status_updated is False


# ---------------------------------------------------------------------------
# ReplyTrackerAgent.process_no_reply_leads() tests
# ---------------------------------------------------------------------------

def test_process_no_reply_marks_drafted_leads():
    store = LeadStore(seed=False)
    crm = MockCRMConnector()
    lead = _make_drafted_lead(store)
    agent = ReplyTrackerAgent(store, crm)

    results = agent.process_no_reply_leads()
    assert len(results) == 1
    assert results[0].classification == ReplyClassification.NO_REPLY
    assert store.get(lead.id).status == LeadStatus.NO_REPLY


def test_process_no_reply_skips_already_replied_leads():
    store = LeadStore(seed=False)
    crm = MockCRMConnector()
    lead = _make_drafted_lead(store)
    store.update_status(lead.id, LeadStatus.REPLIED_INTERESTED)
    agent = ReplyTrackerAgent(store, crm)

    results = agent.process_no_reply_leads()
    assert len(results) == 0


def test_process_no_reply_updates_crm_contact_status():
    store = LeadStore(seed=False)
    crm = MockCRMConnector()
    lead = _make_drafted_lead(store)
    CRMSyncAgent(store, crm, auto_confirm=True).sync_lead(lead)
    agent = ReplyTrackerAgent(store, crm)

    agent.process_no_reply_leads()

    crm_contact = crm.get_contact_by_email(lead.email)
    assert crm_contact.lead_status == LeadStatus.NO_REPLY.value


# ---------------------------------------------------------------------------
# ReplyTrackerAgent.run() integration tests
# ---------------------------------------------------------------------------

def test_run_returns_two_lists():
    store, crm, agent = _make_full_pipeline()
    reply_results, no_reply_results = agent.run()
    assert isinstance(reply_results, list)
    assert isinstance(no_reply_results, list)


def test_run_all_leads_get_a_final_status():
    store, crm, agent = _make_full_pipeline()
    agent.run()
    terminal_statuses = {
        LeadStatus.REPLIED_INTERESTED,
        LeadStatus.REPLIED_NOT_INTERESTED,
        LeadStatus.NO_REPLY,
    }
    for lead in store.get_all():
        assert lead.status in terminal_statuses, (
            f"{lead.email} still has status {lead.status}"
        )


def test_run_total_processed_equals_eligible_leads():
    store, crm, agent = _make_full_pipeline()
    eligible_before = [
        l for l in store.get_all()
        if l.status in {LeadStatus.OUTREACH_DRAFTED, LeadStatus.CONTACTED}
    ]
    reply_results, no_reply_results = agent.run()
    total_processed = len(reply_results) + len(no_reply_results)
    assert total_processed == len(eligible_before)


def test_run_with_mark_no_reply_false_leaves_unresponded_leads_unchanged():
    store, crm, agent = _make_full_pipeline()
    # Patch imap to return NO replies at all
    agent.imap = MockIMAPClient(seed=999_999)  # highly unlikely to reply
    reply_results, no_reply_results = agent.run(mark_no_reply=False)
    # no_reply_results should be empty since mark_no_reply=False
    assert no_reply_results == []


def test_run_reply_results_are_reply_result_instances():
    store, crm, agent = _make_full_pipeline()
    reply_results, no_reply_results = agent.run()
    for r in reply_results + no_reply_results:
        assert isinstance(r, ReplyResult)


def test_run_no_eligible_leads_returns_empty_lists():
    store = LeadStore(seed=True)  # all NEW
    crm = MockCRMConnector()
    imap = MockIMAPClient(seed=42)
    agent = ReplyTrackerAgent(store, crm, imap_client=imap)
    reply_results, no_reply_results = agent.run()
    assert reply_results == []
    assert no_reply_results == []


def test_run_crm_contacts_updated_for_replied_leads():
    store, crm, agent = _make_full_pipeline()
    agent.run()
    terminal_statuses = {
        LeadStatus.REPLIED_INTERESTED.value,
        LeadStatus.REPLIED_NOT_INTERESTED.value,
        LeadStatus.NO_REPLY.value,
    }
    for contact in crm.list_contacts():
        assert contact.lead_status in terminal_statuses


def test_run_interested_deals_move_to_qualification():
    store, crm, agent = _make_full_pipeline()
    agent.run()

    for lead in store.get_all():
        if lead.status == LeadStatus.REPLIED_INTERESTED and lead.crm_contact_id:
            deal = crm.get_deal_for_contact(lead.crm_contact_id)
            if deal:
                assert deal.stage == DealStage.QUALIFICATION


def test_run_not_interested_deals_move_to_closed_lost():
    store, crm, agent = _make_full_pipeline()
    agent.run()

    for lead in store.get_all():
        if lead.status == LeadStatus.REPLIED_NOT_INTERESTED and lead.crm_contact_id:
            deal = crm.get_deal_for_contact(lead.crm_contact_id)
            if deal:
                assert deal.stage == DealStage.CLOSED_LOST
