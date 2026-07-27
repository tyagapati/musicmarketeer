"""Engine analysis and strategy tests."""
import pytest

from app import db
from app.models import CampaignBrief, MusicAnalysis
from app.services.analysis_pipeline import run_analysis
from app.services.spotify_client import resolve_artist_id
from app.services.strategy_engine import run_strategy


def test_resolve_artist_id():
    assert resolve_artist_id("https://open.spotify.com/artist/3TVXtAsR1Inumwj472S9r4") == "3TVXtAsR1Inumwj472S9r4"
    assert resolve_artist_id("3TVXtAsR1Inumwj472S9r4") == "3TVXtAsR1Inumwj472S9r4"
    assert resolve_artist_id("not-a-url") is None



def test_run_analysis_heuristic(app, brief_with_spotify, monkeypatch):
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    with app.app_context():
        bid = brief_with_spotify.id
        analysis = run_analysis(bid)
        assert analysis.sonic_summary
        assert analysis.audience_profile
        brief = db.session.get(CampaignBrief, bid)
        assert brief.analysis_status == "complete"
        assert brief.engine_stage == "analysis"


def test_run_strategy(app, brief_with_spotify, monkeypatch):
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    with app.app_context():
        bid = brief_with_spotify.id
        run_analysis(bid)
        strategy = run_strategy(bid)
        assert len(strategy.recommended_channels) >= 1
        assert strategy.audience_insights


def test_run_analysis_lastfm(app, brief_with_spotify, monkeypatch):
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.setenv("LASTFM_API_KEY", "test-key")

    def fake_api(params):
        method = params.get("method")
        if method == "artist.search":
            return {"results": {"artistmatches": {"artist": [{"name": "Test Artist", "listeners": "1000"}]}}}
        if method == "artist.getInfo":
            return {
                "artist": {
                    "name": "Test Artist",
                    "stats": {"listeners": "5000", "playcount": "12000"},
                    "tags": {"tag": [{"name": "indie"}, {"name": "pop"}]},
                }
            }
        if method == "artist.getTopTracks":
            return {"toptracks": {"track": [{"name": "Night Drive", "playcount": "500"}]}}
        return {}

    monkeypatch.setattr("app.services.lastfm_client._api", fake_api)
    with app.app_context():
        bid = brief_with_spotify.id
        analysis = run_analysis(bid)
        assert "Last.fm" in (analysis.sonic_summary or "")
        assert analysis.top_tracks[0]["name"] == "Night Drive"


def test_intake_redirects_to_analysis(client, app):
    with app.app_context():
        resp = client.post(
            "/artist/intake",
            data={
                "artist_name": "Wizard Artist",
                "email": "wizard@example.com",
                "spotify_artist_url": "https://open.spotify.com/artist/3TVXtAsR1Inumwj472S9r4",
                "genres": "indie",
                "services_needed": "playlist_pitching",
                "budget_max": "300",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/artist/campaign/" in resp.headers["Location"]
        assert "/analysis" in resp.headers["Location"]
        brief = CampaignBrief.query.filter_by(artist_name="Wizard Artist").first()
        assert brief is not None
        assert MusicAnalysis.query.filter_by(brief_id=brief.id).count() == 1
