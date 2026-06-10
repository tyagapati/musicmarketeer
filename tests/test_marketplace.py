"""Marketplace supply gate and booking tests."""
import pytest

from app import db
from app.models import CampaignBrief, Marketer, MarketerPackage, MarketplaceOrder
from app.services.marketplace import fee_breakdown, marketer_can_accept_payments, platform_marketers_query
from app.services.marketplace_checkout import create_order_for_package, mark_order_paid
from app.services.matching import rank_marketers


@pytest.fixture
def platform_marketer(app):
    with app.app_context():
        m = Marketer(
            name="Solo Marketer",
            brand_name="Solo Co",
            email="solo@example.com",
            bio="Independent playlist pitcher.",
            genres=["indie"],
            services=["playlist_pitching"],
            status="approved",
            provider_type="solo",
            enrolled=True,
            portal_token="test-portal-token",
        )
        db.session.add(m)
        db.session.flush()
        pkg = MarketerPackage(
            marketer_id=m.id,
            service="playlist_pitching",
            title="Playlist pitch package",
            price_cents=14900,
            delivery_days=14,
            active=True,
        )
        db.session.add(pkg)
        db.session.commit()
        yield m, pkg


@pytest.fixture
def agency_marketer(app):
    with app.app_context():
        m = Marketer(
            name="Agency Inc",
            brand_name="Agency Inc",
            status="approved",
            provider_type="agency",
            enrolled=False,
        )
        db.session.add(m)
        db.session.commit()
        yield m


@pytest.fixture
def brief(app):
    with app.app_context():
        row = CampaignBrief(
            artist_name="Test Artist",
            email="artist@example.com",
            genres=["indie"],
            services_needed=["playlist_pitching"],
            budget_min=100,
            budget_max=500,
        )
        row.compute_maturity()
        db.session.add(row)
        db.session.commit()
        yield row


def test_platform_marketers_excludes_agency(platform_marketer, agency_marketer):
    ids = {m.id for m in platform_marketers_query().all()}
    assert platform_marketer[0].id in ids
    assert agency_marketer.id not in ids


def test_rank_marketers_only_platform_with_packages(platform_marketer, agency_marketer, brief):
    results = rank_marketers(brief, top_n=5)
    assert len(results) == 1
    assert results[0]["marketer"]["id"] == platform_marketer[0].id


def test_fee_breakdown():
    fees = fee_breakdown(10000)
    assert fees["price_cents"] == 10000
    assert fees["platform_fee_cents"] == 2000
    assert fees["marketer_payout_cents"] == 8000
    assert fees["total_cents"] > 10000


def test_create_order_and_mark_paid(app, platform_marketer, brief):
    m, pkg = platform_marketer
    with app.app_context():
        order = create_order_for_package(brief=brief, package=pkg)
        assert order.status == "pending_payment"
        assert order.marketer_payout_cents > 0
        changed = mark_order_paid(order)
        assert changed is True
        assert order.status == "in_progress"


def test_marketer_can_accept_payments_dev_bypass(platform_marketer, monkeypatch):
    monkeypatch.setenv("PAYMENTS_DEV_BYPASS", "1")
    m, _ = platform_marketer
    assert marketer_can_accept_payments(m) is True


def test_order_complete_requires_delivered(client, app, platform_marketer, brief):
    m, pkg = platform_marketer
    with app.app_context():
        order = create_order_for_package(brief=brief, package=pkg)
        mark_order_paid(order)
        order_id = order.id
    resp = client.post(f"/search/orders/{order_id}/complete", follow_redirects=True)
    assert resp.status_code == 200
    assert b"after the marketer marks" in resp.data.lower() or b"delivered" in resp.data.lower()


def test_browse_hides_agency(client, platform_marketer, agency_marketer):
    resp = client.get("/search/browse?view=all")
    assert resp.status_code == 200
    assert b"Solo Co" in resp.data
    assert b"Agency Inc" not in resp.data


def test_marketer_profile_404_for_agency(client, agency_marketer):
    resp = client.get(f"/search/marketer/{agency_marketer.id}")
    assert resp.status_code == 404
