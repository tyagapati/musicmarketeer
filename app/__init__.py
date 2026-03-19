"""Flask application factory."""
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

db = SQLAlchemy()
migrate = Migrate()


def _resolve_database_uri():
    """Build SQLAlchemy database URI for local dev and hosts like Render."""
    uri = (os.environ.get("DATABASE_URL") or "").strip()
    if not uri:
        return "sqlite:///soundmatch.db"
    # Render / Heroku historically used postgres://; SQLAlchemy expects postgresql://
    if uri.startswith("postgres://"):
        uri = "postgresql://" + uri[len("postgres://") :]
    # requirements.txt ships psycopg v3 only; plain postgresql:// would look for psycopg2
    if uri.startswith("postgresql://"):
        uri = "postgresql+psycopg://" + uri[len("postgresql://") :]
    return uri


def create_app(config_overrides=None):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key")
    app.config["SQLALCHEMY_DATABASE_URI"] = _resolve_database_uri()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    if config_overrides:
        app.config.update(config_overrides)

    db.init_app(app)
    migrate.init_app(app, db)

    from app.blueprints.main import main_bp
    app.register_blueprint(main_bp)

    from app.blueprints.artist import artist_bp
    app.register_blueprint(artist_bp, url_prefix="/artist")

    from app.blueprints.search import search_bp
    app.register_blueprint(search_bp, url_prefix="/search")

    from app.blueprints.admin import admin_bp
    app.register_blueprint(admin_bp, url_prefix="/admin")

    # No Alembic revisions are shipped yet; fresh Postgres (e.g. Render) has no tables.
    # create_all is idempotent and fixes "relation marketers does not exist" on first boot.
    from app import models  # noqa: F401 — register models on metadata before create_all

    with app.app_context():
        db.create_all()
        # Demo catalogue for empty DB (e.g. fresh Render Postgres). Set SOUNDMATCH_SKIP_AUTO_SEED=1 to disable.
        if os.environ.get("SOUNDMATCH_SKIP_AUTO_SEED", "").lower() not in (
            "1",
            "true",
            "yes",
        ):
            try:
                import importlib

                seed_mod = importlib.import_module("seed")
                seed_mod.ensure_demo_marketers_seeded()
            except Exception:
                db.session.rollback()
                app.logger.exception(
                    "SOUNDMATCH: auto-seed of demo marketers failed; catalogue may stay empty"
                )

    return app
