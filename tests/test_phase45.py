"""Phase 4–5: lyrical essence, matcher signals, feedback."""
import pytest

from app import db
from app.models import CampaignBrief, Marketer, MatchFeedback, MusicAnalysis, CampaignStrategy
from app.services.analysis_pipeline import run_analysis
from app.services.lyrical_analysis import build_lyrical_essence
from app.services.matching import rank_marketers
from app.services.strategy_engine import run_strategy


def test_build_lyrical_essence_from_brief():
    brief = CampaignBrief(
        artist_name="Luna",
        genres=["indie", "folk"],
        goals=["grow on tiktok", "playlist placement"],
        tiktok_followers=12000,
        spotify_monthly_listeners=800,
    )
    lyrical = build_lyrical_essence(brief, [{"name": "Night Drive"}])
    assert "nocturnal" in lyrical["themes"]  # from real title word "night"
    assert "short-form growth" in lyrical["goal_priorities"]
    assert "short-form-led" in lyrical["platform_signals"]
    assert "narrative_voice" not in lyrical
    assert "emotional_arc" not in lyrical
    assert "hook_patterns" not in lyrical


def test_genius_enrichment_optional(monkeypatch):
    monkeypatch.setenv("GENIUS_ACCESS_TOKEN", "test-token")

    def fake_search(title, artist=""):
        return {"id": 1, "title": title, "url": "https://genius.com/test", "primary_artist": artist}

    monkeypatch.setattr("app.services.genius_client.search_song", fake_search)
    from app.services.genius_client import enrich_tracks_with_genius

    enriched = enrich_tracks_with_genius([{"name": "Night Drive"}], "Luna")
    assert enriched[0]["genius"]["url"] == "https://genius.com/test"


def test_analysis_includes_evidence_cues(app, brief_with_spotify, monkeypatch):
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("LASTFM_API_KEY", raising=False)
    with app.app_context():
        analysis = run_analysis(brief_with_spotify.id)
        assert analysis.lyrical_analysis.get("source") == "evidence"
        assert analysis.audience_profile.get("tags")
        assert analysis.audio_features.get("averages") == {}
        assert "energy/tempo" in (analysis.sonic_summary or "").lower() or "brief" in (analysis.sonic_summary or "").lower()


def test_matcher_uses_audience_signals(app, brief_with_spotify, monkeypatch):
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    with app.app_context():
        run_analysis(brief_with_spotify.id)
        run_strategy(brief_with_spotify.id)
        marketer = Marketer(
            name="Indie Specialist",
            brand_name="Indie Specialist",
            bio="We help introspective indie artists with playlist pitching and tiktok-native campaigns.",
            genres=["indie"],
            services=["playlist_pitching", "social_media_strategy"],
            status="approved",
            proof_strength=70,
            confidence_score=80,
        )
        db.session.add(marketer)
        db.session.commit()
        brief = db.session.get(CampaignBrief, brief_with_spotify.id)
        results = rank_marketers(brief, top_n=3)
        assert results
        top_reasons = " ".join(results[0]["top_reasons"]).lower()
        assert "genre" in top_reasons or "audience" in top_reasons or "channel" in top_reasons


def test_match_feedback_route(client, app, brief_with_spotify, monkeypatch):
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    with app.app_context():
        run_analysis(brief_with_spotify.id)
        run_strategy(brief_with_spotify.id)
        marketer = Marketer(
            name="Feedback Target",
            brand_name="Feedback Target",
            genres=["indie"],
            services=["playlist_pitching"],
            status="approved",
        )
        db.session.add(marketer)
        db.session.commit()
        bid = brief_with_spotify.id
        mid = marketer.id

    resp = client.post(
        f"/search/match/{bid}",
        data={"marketer_id": str(mid), "hired": "yes", "rating": "5", "notes": "Great intro"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        row = MatchFeedback.query.filter_by(brief_id=bid, marketer_id=mid).first()
        assert row is not None
        assert row.hired is True
        assert row.rating == 5


def test_campaign_report_page(client, app, brief_with_spotify, monkeypatch):
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    with app.app_context():
        run_analysis(brief_with_spotify.id)
        run_strategy(brief_with_spotify.id)
        bid = brief_with_spotify.id
    resp = client.get(f"/artist/campaign/{bid}/report")
    assert resp.status_code == 200
    assert b"Campaign report" in resp.data or b"campaign report" in resp.data
