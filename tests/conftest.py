"""Pytest fixtures for SoundMatch verification tests."""
import os

import pytest

os.environ.setdefault("SOUNDMATCH_SKIP_AUTO_SEED", "1")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("PAYMENTS_DEV_BYPASS", "0")

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
