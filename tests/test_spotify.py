"""Spotify client + analysis path tests (mocked HTTP)."""
import pytest

from app import db
from app.models import CampaignBrief
from app.services.analysis_pipeline import run_analysis
from app.services.spotify_client import (
    analyze_artist,
    estimate_features_from_genres,
    resolve_artist_id,
)


def test_estimate_features_from_genres():
    feats = estimate_features_from_genres(["indie pop", "alternative rock"])
    assert 0.3 <= feats["energy"] <= 0.9
    assert feats["tempo"] > 0


def test_analyze_artist_soft_fails_restricted_endpoints(monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret")

    def fake_get(path, *, params=None, soft=False):
        if path.startswith("/artists/") and path.count("/") == 2:
            return {
                "id": "3TVXtAsR1Inumwj472S9r4",
                "name": "Drake",
                "genres": ["canadian hip hop", "rap"],
                "popularity": 95,
                "followers": {"total": 90000000},
                "images": [],
                "external_urls": {"spotify": "https://open.spotify.com/artist/3TVXtAsR1Inumwj472S9r4"},
            }
        if "top-tracks" in path:
            return None  # restricted
        if path.endswith("/albums") or "/albums/" in path:
            return None
        if path.startswith("/audio-features"):
            return None
        return {}

    monkeypatch.setattr("app.services.spotify_client._api_get", fake_get)
    monkeypatch.setattr("app.services.spotify_client._get_token", lambda: "tok")

    result = analyze_artist("3TVXtAsR1Inumwj472S9r4")
    assert result["profile"]["name"] == "Drake"
    assert result["feature_source"] == "genre_estimate"
    assert result["averages"]["energy"] > 0
    assert result["warnings"]


def test_run_analysis_spotify_path(app, brief_with_spotify, monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret")
    monkeypatch.delenv("LASTFM_API_KEY", raising=False)

    def fake_analyze(artist_id, *, market=None):
        return {
            "profile": {
                "id": artist_id,
                "name": "Test Artist",
                "genres": ["indie"],
                "popularity": 40,
                "followers": 1500,
                "source": "spotify",
            },
            "tracks": [{"id": "t1", "name": "Night Drive", "popularity": 55}],
            "features": {},
            "averages": {"energy": 0.55, "valence": 0.5, "danceability": 0.52, "tempo": 112},
            "track_source": "top_tracks",
            "feature_source": "genre_estimate",
            "warnings": ["Audio features endpoint restricted for this Spotify app — estimated sonic profile from genres."],
        }

    monkeypatch.setattr("app.services.analysis_pipeline.analyze_artist", fake_analyze)
    with app.app_context():
        bid = brief_with_spotify.id
        analysis = run_analysis(bid)
        assert analysis.spotify_profile["source"] == "spotify"
        assert "Spotify" in (analysis.sonic_summary or "")
        # Genre estimates must not be shown as measured audio
        assert analysis.audio_features["averages"] == {}
        assert analysis.audio_features["source"] == "unavailable"
        assert analysis.audience_profile.get("mood") is None
        brief = db.session.get(CampaignBrief, bid)
        assert brief.analysis_status == "complete"
        assert brief.spotify_monthly_listeners == 1500
