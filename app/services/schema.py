"""Ensure new columns/tables exist on SQLite/Postgres without Alembic revisions."""
from sqlalchemy import inspect, text

from app import db


def ensure_schema():
    inspector = inspect(db.engine)
    if "marketers" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("marketers")}
        if "price_verified" not in cols:
            db.session.execute(text("ALTER TABLE marketers ADD COLUMN price_verified BOOLEAN DEFAULT 0"))
        if "affiliate_url" not in cols:
            db.session.execute(text("ALTER TABLE marketers ADD COLUMN affiliate_url VARCHAR(500)"))
        db.session.commit()
