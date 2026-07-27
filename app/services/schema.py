"""Ensure new columns/tables exist on SQLite/Postgres without Alembic revisions."""
from sqlalchemy import inspect, text

from app import db


def _add_column_if_missing(table, column, ddl):
    inspector = inspect(db.engine)
    if table not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns(table)}
    if column not in cols:
        db.session.execute(text(ddl))


def ensure_schema():
    inspector = inspect(db.engine)
    if "marketers" in inspector.get_table_names():
        _add_column_if_missing(
            "marketers",
            "price_verified",
            "ALTER TABLE marketers ADD COLUMN price_verified BOOLEAN DEFAULT 0",
        )
        _add_column_if_missing(
            "marketers",
            "affiliate_url",
            "ALTER TABLE marketers ADD COLUMN affiliate_url VARCHAR(500)",
        )
        _add_column_if_missing(
            "marketers",
            "price_source",
            "ALTER TABLE marketers ADD COLUMN price_source VARCHAR(50) DEFAULT 'estimated'",
        )
        _add_column_if_missing(
            "marketers",
            "booking_url",
            "ALTER TABLE marketers ADD COLUMN booking_url VARCHAR(500)",
        )
        _add_column_if_missing(
            "marketers",
            "portal_token",
            "ALTER TABLE marketers ADD COLUMN portal_token VARCHAR(128)",
        )
        _add_column_if_missing(
            "marketers",
            "domain_key",
            "ALTER TABLE marketers ADD COLUMN domain_key VARCHAR(255)",
        )
        _add_column_if_missing(
            "marketers",
            "provider_type",
            "ALTER TABLE marketers ADD COLUMN provider_type VARCHAR(20) DEFAULT 'agency'",
        )
        _add_column_if_missing(
            "marketers",
            "enrolled",
            "ALTER TABLE marketers ADD COLUMN enrolled BOOLEAN DEFAULT 0",
        )
        _add_column_if_missing(
            "marketers",
            "stripe_connect_account_id",
            "ALTER TABLE marketers ADD COLUMN stripe_connect_account_id VARCHAR(255)",
        )
        _add_column_if_missing(
            "marketers",
            "payouts_enabled",
            "ALTER TABLE marketers ADD COLUMN payouts_enabled BOOLEAN DEFAULT 0",
        )
        db.session.execute(
            text("UPDATE marketers SET provider_type='agency' WHERE provider_type IS NULL")
        )
        db.session.execute(text("UPDATE marketers SET enrolled=0 WHERE enrolled IS NULL"))
        db.session.commit()

    if "campaign_briefs" in inspector.get_table_names():
        _add_column_if_missing(
            "campaign_briefs",
            "payment_status",
            "ALTER TABLE campaign_briefs ADD COLUMN payment_status VARCHAR(50) DEFAULT 'unpaid'",
        )
        _add_column_if_missing(
            "campaign_briefs",
            "paid_at",
            "ALTER TABLE campaign_briefs ADD COLUMN paid_at DATETIME",
        )
        _add_column_if_missing(
            "campaign_briefs",
            "stripe_checkout_session_id",
            "ALTER TABLE campaign_briefs ADD COLUMN stripe_checkout_session_id VARCHAR(255)",
        )
        _add_column_if_missing(
            "campaign_briefs",
            "concierge_intros_remaining",
            "ALTER TABLE campaign_briefs ADD COLUMN concierge_intros_remaining INTEGER DEFAULT 0",
        )
        for col, ddl in (
            ("spotify_artist_url", "ALTER TABLE campaign_briefs ADD COLUMN spotify_artist_url VARCHAR(500)"),
            ("spotify_artist_id", "ALTER TABLE campaign_briefs ADD COLUMN spotify_artist_id VARCHAR(64)"),
            ("engine_stage", "ALTER TABLE campaign_briefs ADD COLUMN engine_stage VARCHAR(50) DEFAULT 'intake'"),
            ("analysis_status", "ALTER TABLE campaign_briefs ADD COLUMN analysis_status VARCHAR(50) DEFAULT 'pending'"),
            ("analysis_error", "ALTER TABLE campaign_briefs ADD COLUMN analysis_error TEXT"),
        ):
            _add_column_if_missing("campaign_briefs", col, ddl)
        db.session.commit()

    if "intro_requests" in inspector.get_table_names():
        _add_column_if_missing(
            "intro_requests",
            "brief_id",
            "ALTER TABLE intro_requests ADD COLUMN brief_id INTEGER",
        )
        _add_column_if_missing(
            "intro_requests",
            "intro_type",
            "ALTER TABLE intro_requests ADD COLUMN intro_type VARCHAR(50) DEFAULT 'self_serve'",
        )
        _add_column_if_missing(
            "intro_requests",
            "status",
            "ALTER TABLE intro_requests ADD COLUMN status VARCHAR(50) DEFAULT 'pending'",
        )
        db.session.commit()

    table_names = inspector.get_table_names()
    if "marketplace_orders" in inspector.get_table_names():
        _add_column_if_missing(
            "marketplace_orders",
            "rating",
            "ALTER TABLE marketplace_orders ADD COLUMN rating INTEGER",
        )
        _add_column_if_missing(
            "marketplace_orders",
            "review_notes",
            "ALTER TABLE marketplace_orders ADD COLUMN review_notes TEXT",
        )
        db.session.commit()

    if "verification_decisions" not in table_names or "marketer_packages" not in table_names or "music_analyses" not in table_names:
        db.create_all()
        db.session.commit()
