"""Platform marketer onboarding helpers and admin routes."""
import pytest

from app import db
from app.models import Marketer, MarketerApplication, MarketerPackage
from app.services.onboarding import (
    marketer_onboarding_status,
    marketer_portal_url,
    provision_from_application,
    provision_platform_marketer,
)


def test_provision_platform_marketer(app):
    with app.app_context():
        m = provision_platform_marketer(
            brand_name="Test Co",
            website="https://testco.example",
            email="test@testco.example",
            services=["playlist_pitching"],
            genres=["indie"],
            price_cents=19900,
        )
        db.session.commit()
        assert m.enrolled is True
        assert m.provider_type == "solo"
        assert m.portal_token
        pkgs = MarketerPackage.query.filter_by(marketer_id=m.id, active=True).all()
        assert len(pkgs) == 1
        assert pkgs[0].price_cents == 19900


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
        assert MarketerPackage.query.filter_by(marketer_id=m.id).count() == 1


def test_marketer_portal_url(app, monkeypatch):
    monkeypatch.setenv("APP_URL", "https://app.example")
    with app.app_context():
        m = Marketer(portal_token="abc123", status="approved")
        assert marketer_portal_url(m) == "https://app.example/marketer/portal/abc123"


def test_onboarding_status_live(app, monkeypatch):
    monkeypatch.setenv("PAYMENTS_DEV_BYPASS", "1")
    with app.app_context():
        m = Marketer(
            status="approved",
            enrolled=True,
            provider_type="solo",
            portal_token="tok",
        )
        status = marketer_onboarding_status(m, active_packages=2)
        assert status["active_packages"] == 2
        assert status["bookable"] is True
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
                "price_dollars": "199",
                "delivery_days": "7",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        m = Marketer.query.filter_by(brand_name="Manual Co").first()
        assert m is not None
        assert m.enrolled is True
        assert m.source == "admin_manual"
        pkg = MarketerPackage.query.filter_by(marketer_id=m.id).first()
        assert pkg.price_cents == 19900


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
        app_row = MarketerApplication.query.get(app_id)
        assert app_row.status == "approved"
        m = Marketer.query.filter_by(brand_name="Route Co").first()
        assert m is not None
        assert m.enrolled is True
