"""Pytest fixtures for SoundMatch verification tests."""
import os

import pytest

os.environ.setdefault("SOUNDMATCH_SKIP_AUTO_SEED", "1")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app import create_app, db  # noqa: E402


@pytest.fixture
def app():
    application = create_app({"TESTING": True})
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def brief_with_spotify(app):
    with app.app_context():
        from app.models import CampaignBrief

        brief = CampaignBrief(
            artist_name="Test Artist",
            email="a@example.com",
            spotify_artist_url="https://open.spotify.com/artist/3TVXtAsR1Inumwj472S9r4",
            genres=["indie"],
            services_needed=["playlist_pitching"],
            budget_max=500,
        )
        brief.compute_maturity()
        db.session.add(brief)
        db.session.commit()
        yield brief
