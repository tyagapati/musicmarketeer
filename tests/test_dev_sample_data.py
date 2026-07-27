"""Developer sample data for intake form."""
import pytest

from app.services.dev_sample_data import SAMPLE_PRESETS, dev_tools_enabled


def test_sample_presets_have_required_fields():
    required = {
        "artist_name",
        "email",
        "spotify_artist_url",
        "genres",
        "services_needed",
        "budget_max",
    }
    for key, preset in SAMPLE_PRESETS.items():
        missing = required - set(preset.keys())
        assert not missing, f"preset {key} missing {missing}"


def test_intake_shows_dev_bar_in_development(client, monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "development")
    resp = client.get("/artist/intake")
    assert resp.status_code == 200
    assert b'id="dev-sample-bar"' in resp.data
    assert b"Indie" in resp.data


def test_intake_hides_dev_bar_when_disabled(client, monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("DEV_SAMPLE_DATA", "0")
    resp = client.get("/artist/intake")
    assert resp.status_code == 200
    assert b'id="dev-sample-bar"' not in resp.data
