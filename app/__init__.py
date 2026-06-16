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
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        app.config.setdefault("SQLALCHEMY_ENGINE_OPTIONS", {"connect_args": {"timeout": 30}})
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

    from app.blueprints.marketer import marketer_bp
    app.register_blueprint(marketer_bp, url_prefix="/marketer")

    from app.services.marketer_display import format_price_range, normalize_brand_name

    def _marketer_field(marketer, key, default=None):
        if isinstance(marketer, dict):
            return marketer.get(key, default)
        return getattr(marketer, key, default)

    @app.template_filter("marketer_brand")
    def marketer_brand_filter(marketer):
        return normalize_brand_name(
            website=_marketer_field(marketer, "website", "") or "",
            title=_marketer_field(marketer, "name", "") or "",
            brand_name=_marketer_field(marketer, "brand_name", "") or "",
            name=_marketer_field(marketer, "name", "") or "",
        )

    @app.template_filter("marketer_price")
    def marketer_price_filter(marketer):
        return format_price_range(
            _marketer_field(marketer, "price_min"),
            _marketer_field(marketer, "price_max"),
            _marketer_field(marketer, "price_model"),
            bool(_marketer_field(marketer, "price_verified", False)),
            _marketer_field(marketer, "price_source", "estimated") or "estimated",
        )

    from app.constants.marketer_taxonomy import taxonomy_label

    @app.template_filter("taxonomy_label")
    def taxonomy_label_filter(value):
        return taxonomy_label(value)

    @app.template_filter("provider_badge")
    def provider_badge_filter(marketer):
        provider_type = _marketer_field(marketer, "provider_type", "agency") or "agency"
        enrolled = bool(_marketer_field(marketer, "enrolled", False))
        if enrolled and provider_type == "solo":
            return "Independent marketer"
        if provider_type == "solo":
            return "Solo marketer"
        return "Agency"

    from app.services.csrf import get_csrf_token, validate_csrf

    @app.context_processor
    def inject_csrf():
        return {"csrf_token": get_csrf_token}

    from app.services.onboarding import app_base_url as _app_base_url
    from app.services.onboarding import marketer_apply_url as _marketer_apply_url
    from app.services.onboarding import onboarding_email_body

    @app.context_processor
    def inject_onboarding_helpers():
        return {
            "app_base_url": _app_base_url(),
            "marketer_apply_url": _marketer_apply_url(),
            "onboarding_email": onboarding_email_body,
        }

    @app.before_request
    def check_csrf():
        validate_csrf()

    # No Alembic revisions are shipped yet; fresh Postgres (e.g. Render) has no tables.
    # create_all is idempotent and fixes "relation marketers does not exist" on first boot.
    from app import models  # noqa: F401 — register models on metadata before create_all

    with app.app_context():
        db.create_all()
        from app.services.schema import ensure_schema

        ensure_schema()
        from app.services.automation_settings import ensure_automation_defaults

        ensure_automation_defaults()
        from app.services.site_urls import dedupe_marketers_by_domain

        dedupe_marketers_by_domain()
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
