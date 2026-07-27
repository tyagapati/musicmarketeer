"""Platform marketer onboarding helpers and admin routes."""
import pytest

from app import db
from app.models import Marketer, MarketerApplication
from app.services.onboarding import (
    marketer_onboarding_status,
    marketer_portal_url,
    provision_catalog_marketer,
    provision_from_application,
)


def test_provision_catalog_marketer(app):
    with app.app_context():
        m = provision_catalog_marketer(
            brand_name="Test Co",
            website="https://testco.example",
            email="test@testco.example",
            services=["playlist_pitching"],
            genres=["indie"],
            provider_type="agency",
        )
        db.session.commit()
        assert m.status == "approved"
        assert m.provider_type == "agency"
        assert m.portal_token


def test_provision_from_application(app):
    with app.app_context():
        app_row = MarketerApplication(
            brand_name="Apply Co",
            website="https://applyco.example",
            email="hi@applyco.example",
            services=["pr"],
            genres=["hip_hop"],
            status="pending",
        )
        db.session.add(app_row)
        db.session.commit()
        m = provision_from_application(app_row)
        app_row.status = "approved"
        db.session.commit()
        assert m.brand_name == "Apply Co"


def test_marketer_portal_url(app, monkeypatch):
    monkeypatch.setenv("APP_URL", "https://app.example")
    with app.app_context():
        m = Marketer(portal_token="abc123", status="approved")
        assert marketer_portal_url(m) == "https://app.example/marketer/portal/abc123"


def test_onboarding_status_live(app):
    with app.app_context():
        m = Marketer(
            status="approved",
            brand_name="Live Co",
            email="hi@live.co",
            bio="We pitch playlists.",
            services=["playlist_pitching"],
            portal_token="tok",
        )
        status = marketer_onboarding_status(m)
        assert status["live"] is True
        assert status["label"] == "Live"


def test_admin_add_marketer_route(client, app):
    with app.app_context():
        resp = client.post(
            "/admin/marketers/add",
            data={
                "brand_name": "Manual Co",
                "website": "https://manualco.example",
                "email": "manual@example.com",
                "services": "playlist_pitching",
                "genres": "indie",
                "bio": "We pitch playlists.",
                "provider_type": "solo",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        m = Marketer.query.filter_by(brand_name="Manual Co").first()
        assert m is not None
        assert m.source == "admin_manual"


def test_approve_application_route(client, app):
    with app.app_context():
        app_row = MarketerApplication(
            brand_name="Route Co",
            website="https://routeco.example",
            email="route@example.com",
            services=["playlist_pitching"],
            genres=["pop"],
            status="pending",
        )
        db.session.add(app_row)
        db.session.commit()
        app_id = app_row.id
    resp = client.post(f"/admin/applications/{app_id}/approve", follow_redirects=False)
    assert resp.status_code == 302
    with app.app_context():
        app_row = db.session.get(MarketerApplication, app_id)
        assert app_row.status == "approved"
        m = Marketer.query.filter_by(brand_name="Route Co").first()
        assert m is not None
