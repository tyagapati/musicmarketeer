"""Payment gating and brief paid-state tests."""
import os

import pytest

from app import db
from app.models import CampaignBrief
from app.services.payments import brief_is_paid, mark_brief_paid_from_session, payments_dev_bypass


@pytest.fixture
def brief(app):
    with app.app_context():
        row = CampaignBrief(
            artist_name="Test Artist",
            email="artist@example.com",
            genres=["indie"],
            services_needed=["playlist_pitching"],
            budget_min=500,
            budget_max=2000,
        )
        row.compute_maturity()
        db.session.add(row)
        db.session.commit()
        yield row


def test_brief_is_unpaid_by_default(brief):
    assert brief_is_paid(brief) is False


def test_brief_is_paid_with_dev_bypass(brief, monkeypatch):
    monkeypatch.setenv("PAYMENTS_DEV_BYPASS", "1")
    assert payments_dev_bypass() is True
    assert brief_is_paid(brief) is True


def test_mark_brief_paid_grants_intro_credit(app, brief):
    with app.app_context():
        changed = mark_brief_paid_from_session(brief)
        assert changed is True
        assert brief.payment_status == "paid"
        assert brief.paid_at is not None
        assert brief.concierge_intros_remaining == 1

        changed_again = mark_brief_paid_from_session(brief)
        assert changed_again is False


def test_match_page_shows_marketplace_copy(client, brief):
    resp = client.get(f"/search/match/{brief.id}")
    assert resp.status_code == 200
    assert b"marketplace" in resp.data.lower() or b"Platform matches" in resp.data
