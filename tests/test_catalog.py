"""Catalog and matching tests."""
import pytest

from app import db
from app.models import CampaignBrief, IntroRequest, Marketer
from app.services.catalog import catalog_marketers_query, get_catalog_marketer
from app.services.matching import rank_marketers


@pytest.fixture
def solo_marketer(app):
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
            portal_token="test-portal-token",
        )
        db.session.add(m)
        db.session.commit()
        yield m


@pytest.fixture
def agency_marketer(app):
    with app.app_context():
        m = Marketer(
            name="Agency Inc",
            brand_name="Agency Inc",
            bio="Full-service agency.",
            genres=["hip-hop"],
            services=["pr", "release_campaigns"],
            status="approved",
            provider_type="agency",
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


def test_catalog_includes_agency_and_solo(solo_marketer, agency_marketer):
    ids = {m.id for m in catalog_marketers_query().all()}
    assert solo_marketer.id in ids
    assert agency_marketer.id in ids


def test_rank_marketers_includes_both_types(solo_marketer, agency_marketer, brief):
    results = rank_marketers(brief, top_n=5)
    result_ids = {r["marketer"]["id"] for r in results}
    assert solo_marketer.id in result_ids
    assert len(results) >= 1


def test_browse_shows_agency(client, solo_marketer, agency_marketer):
    resp = client.get("/search/browse?view=all")
    assert resp.status_code == 200
    assert b"Agency Inc" in resp.data or b"Solo Co" in resp.data


def test_intro_request(client, app, solo_marketer, brief):
    with app.app_context():
        m_id = solo_marketer.id
        b_id = brief.id
    resp = client.post(
        f"/search/marketer/{m_id}?brief_id={b_id}",
        data={
            "brief_id": str(b_id),
            "artist_name": "Test Artist",
            "email": "artist@example.com",
            "message": "Love your work",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        assert IntroRequest.query.filter_by(marketer_id=m_id, email="artist@example.com").count() == 1


def test_get_catalog_marketer(solo_marketer, agency_marketer):
    assert get_catalog_marketer(solo_marketer.id) is not None
    assert get_catalog_marketer(agency_marketer.id) is not None
