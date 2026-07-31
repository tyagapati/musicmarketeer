"""MVP synthesis: preferred type, history, admin CSV."""
from app import db
from app.models import CampaignBrief, Marketer
from app.services.matching import rank_marketers


def test_preferred_provider_type_boost(app):
    with app.app_context():
        solo = Marketer(
            name="Solo Pro",
            brand_name="Solo Pro",
            email="solo@example.com",
            genres=["indie"],
            services=["playlist_pitching"],
            provider_type="solo",
            status="approved",
            proof_strength=60,
            confidence_score=70,
        )
        agency = Marketer(
            name="Agency Co",
            brand_name="Agency Co",
            email="agency@example.com",
            genres=["indie"],
            services=["playlist_pitching"],
            provider_type="agency",
            status="approved",
            proof_strength=60,
            confidence_score=70,
        )
        brief = CampaignBrief(
            artist_name="Pref Artist",
            email="pref@example.com",
            genres=["indie"],
            services_needed=["playlist_pitching"],
            budget_max=1000,
            preferred_provider_type="solo",
        )
        brief.compute_maturity()
        db.session.add_all([solo, agency, brief])
        db.session.commit()

        results = rank_marketers(brief, top_n=5)
        assert results
        top = results[0]
        assert top["marketer"]["provider_type"] == "solo"
        assert any("Preferred solo" in r for r in top["top_reasons"])
        assert top["marketer"].get("email") == "solo@example.com"


def test_artist_history_lookup(client, app):
    with app.app_context():
        brief = CampaignBrief(
            artist_name="History Artist",
            email="history@example.com",
            genres=["pop"],
            services_needed=["ads"],
            budget_max=500,
            preferred_provider_type="either",
            engine_stage="matched",
        )
        brief.compute_maturity()
        db.session.add(brief)
        db.session.commit()
        bid = brief.id

    resp = client.post("/artist/history", data={"email": "history@example.com"}, follow_redirects=True)
    assert resp.status_code == 200
    assert b"History Artist" in resp.data
    assert f"/search/match/{bid}".encode() in resp.data


def test_admin_artists_csv(client, app, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "test-admin")
    with app.app_context():
        brief = CampaignBrief(
            artist_name="CSV Artist",
            email="csv@example.com",
            genres=["hip-hop"],
            goals=["streams"],
            services_needed=["playlist_pitching"],
            budget_min=200,
            budget_max=800,
            preferred_provider_type="agency",
        )
        brief.compute_maturity()
        db.session.add(brief)
        db.session.commit()

    client.post("/admin/login", data={"password": "test-admin"}, follow_redirects=True)
    resp = client.get("/admin/artists/export")
    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    body = resp.data.decode("utf-8")
    assert "CSV Artist" in body
    assert "csv@example.com" in body
    assert "preferred_provider_type" in body
