"""Public marketer catalog — all approved agencies and solos."""
from __future__ import annotations

from app.models import Marketer


def catalog_marketers_query():
    """Approved marketers visible to artists (agencies and solos)."""
    return Marketer.query.filter_by(status="approved")


def get_catalog_marketer(marketer_id: int) -> Marketer | None:
    return catalog_marketers_query().filter_by(id=marketer_id).first()


def is_catalog_marketer(marketer: Marketer) -> bool:
    return marketer.status == "approved"


def format_price_range(marketer: Marketer) -> str:
    """Human-readable estimated price range from catalog metadata."""
    if marketer.price_min and marketer.price_max:
        if marketer.price_min == marketer.price_max:
            return f"${marketer.price_min}"
        return f"${marketer.price_min}–${marketer.price_max}"
    if marketer.price_min:
        return f"from ${marketer.price_min}"
    if marketer.price_max:
        return f"up to ${marketer.price_max}"
    return "Contact for pricing"
