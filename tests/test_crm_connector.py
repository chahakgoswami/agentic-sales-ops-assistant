"""Tests for MockCRMConnector."""
import pytest
from sales_ops.crm.connector import (
    MockCRMConnector,
    CRMContact,
    CRMDeal,
    DealStage,
    DEAL_STAGE_PROBABILITIES,
)


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def _contact_payload(**overrides):
    base = {
        "email": "test@example.com",
        "first_name": "Test",
        "last_name": "User",
        "company": "TestCo",
        "title": "Engineer",
    }
    base.update(overrides)
    return base


def _deal_payload(contact_id: str, **overrides):
    base = {
        "contact_id": contact_id,
        "company": "TestCo",
        "deal_name": "TestCo — Engineer",
        "stage": DealStage.PROSPECTING.value,
        "amount": 10_000.0,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# CRM Connector: contacts
# ---------------------------------------------------------------------------

def test_crm_starts_empty():
    crm = MockCRMConnector()
    assert crm.contact_count() == 0
    assert crm.deal_count() == 0


def test_upsert_contact_creates_new():
    crm = MockCRMConnector()
    contact = crm.upsert_contact(_contact_payload())
    assert isinstance(contact, CRMContact)
    assert crm.contact_count() == 1
    assert contact.email == "test@example.com"


def test_upsert_contact_assigns_id():
    crm = MockCRMConnector()
    contact = crm.upsert_contact(_contact_payload())
    assert contact.id is not None
    assert len(contact.id) > 0


def test_upsert_contact_idempotent_by_email():
    crm = MockCRMConnector()
    c1 = crm.upsert_contact(_contact_payload())
    c2 = crm.upsert_contact(_contact_payload(title="Senior Engineer"))
    assert crm.contact_count() == 1
    assert c1.id == c2.id
    assert c2.title == "Senior Engineer"


def test_get_contact_by_id():
    crm = MockCRMConnector()
    contact = crm.upsert_contact(_contact_payload())
    fetched = crm.get_contact(contact.id)
    assert fetched is contact


def test_get_contact_by_email():
    crm = MockCRMConnector()
    contact = crm.upsert_contact(_contact_payload())
    fetched = crm.get_contact_by_email("test@example.com")
    assert fetched is contact


def test_get_contact_nonexistent_returns_none():
    crm = MockCRMConnector()
    assert crm.get_contact("nonexistent") is None
    assert crm.get_contact_by_email("nobody@nowhere.com") is None


def test_list_contacts():
    crm = MockCRMConnector()
    crm.upsert_contact(_contact_payload(email="a@a.com", first_name="A"))
    crm.upsert_contact(_contact_payload(email="b@b.com", first_name="B"))
    assert len(crm.list_contacts()) == 2


def test_contact_to_dict_has_expected_keys():
    crm = MockCRMConnector()
    contact = crm.upsert_contact(_contact_payload())
    d = contact.to_dict()
    for key in ("id", "email", "first_name", "last_name", "company", "title", "lead_status"):
        assert key in d


def test_upsert_contact_stores_properties():
    crm = MockCRMConnector()
    contact = crm.upsert_contact(_contact_payload(properties={"annual_revenue": "$10M"}))
    assert contact.properties["annual_revenue"] == "$10M"


# ---------------------------------------------------------------------------
# CRM Connector: deals
# ---------------------------------------------------------------------------

def test_upsert_deal_creates_new():
    crm = MockCRMConnector()
    contact = crm.upsert_contact(_contact_payload())
    deal = crm.upsert_deal(_deal_payload(contact.id))
    assert isinstance(deal, CRMDeal)
    assert crm.deal_count() == 1


def test_upsert_deal_assigns_id():
    crm = MockCRMConnector()
    contact = crm.upsert_contact(_contact_payload())
    deal = crm.upsert_deal(_deal_payload(contact.id))
    assert deal.id is not None


def test_upsert_deal_idempotent_by_contact_id():
    crm = MockCRMConnector()
    contact = crm.upsert_contact(_contact_payload())
    d1 = crm.upsert_deal(_deal_payload(contact.id, amount=10_000.0))
    d2 = crm.upsert_deal(_deal_payload(contact.id, amount=20_000.0))
    assert crm.deal_count() == 1
    assert d1.id == d2.id
    assert d2.amount == 20_000.0


def test_upsert_deal_accepts_string_stage():
    crm = MockCRMConnector()
    contact = crm.upsert_contact(_contact_payload())
    deal = crm.upsert_deal(_deal_payload(contact.id, stage="qualification"))
    assert deal.stage == DealStage.QUALIFICATION


def test_upsert_deal_sets_default_probability():
    crm = MockCRMConnector()
    contact = crm.upsert_contact(_contact_payload())
    deal = crm.upsert_deal(_deal_payload(contact.id, stage="qualification"))
    assert deal.probability == DEAL_STAGE_PROBABILITIES[DealStage.QUALIFICATION]


def test_get_deal_by_id():
    crm = MockCRMConnector()
    contact = crm.upsert_contact(_contact_payload())
    deal = crm.upsert_deal(_deal_payload(contact.id))
    assert crm.get_deal(deal.id) is deal


def test_get_deal_for_contact():
    crm = MockCRMConnector()
    contact = crm.upsert_contact(_contact_payload())
    deal = crm.upsert_deal(_deal_payload(contact.id))
    assert crm.get_deal_for_contact(contact.id) is deal


def test_get_deal_nonexistent_returns_none():
    crm = MockCRMConnector()
    assert crm.get_deal("ghost") is None
    assert crm.get_deal_for_contact("ghost") is None


def test_list_deals():
    crm = MockCRMConnector()
    c1 = crm.upsert_contact(_contact_payload(email="x@x.com"))
    c2 = crm.upsert_contact(_contact_payload(email="y@y.com"))
    crm.upsert_deal(_deal_payload(c1.id))
    crm.upsert_deal(_deal_payload(c2.id))
    assert len(crm.list_deals()) == 2


def test_deal_to_dict_has_expected_keys():
    crm = MockCRMConnector()
    contact = crm.upsert_contact(_contact_payload())
    deal = crm.upsert_deal(_deal_payload(contact.id))
    d = deal.to_dict()
    for key in ("id", "contact_id", "company", "deal_name", "stage", "amount", "probability"):
        assert key in d


def test_crm_repr():
    crm = MockCRMConnector()
    r = repr(crm)
    assert "MockCRMConnector" in r
