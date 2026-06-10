"""Platform marketplace helpers — enrolled marketers and packages only."""
from __future__ import annotations

import os

from sqlalchemy import or_

from app.models import Marketer, MarketerPackage, MarketplaceOrder


def is_platform_marketer(marketer: Marketer) -> bool:
    return (
        marketer.status == "approved"
        and bool(marketer.enrolled)
        and (marketer.provider_type or "agency") == "solo"
    )


def platform_marketers_query():
    """Approved enrolled solo marketers (user-facing catalog)."""
    return Marketer.query.filter_by(status="approved", enrolled=True, provider_type="solo")


def get_platform_marketer(marketer_id: int) -> Marketer | None:
    return platform_marketers_query().filter_by(id=marketer_id).first()


def active_packages_for_marketer(marketer_id: int) -> list[MarketerPackage]:
    return (
        MarketerPackage.query.filter_by(marketer_id=marketer_id, active=True)
        .order_by(MarketerPackage.price_cents.asc())
        .all()
    )


def packages_matching_brief(marketer_id: int, services_needed: list[str]) -> list[MarketerPackage]:
    needed = set(services_needed or [])
    packages = active_packages_for_marketer(marketer_id)
    if not needed:
        return packages
    matched = [p for p in packages if p.service in needed]
    return matched or packages


def cheapest_package_for_brief(marketer_id: int, services_needed: list[str]) -> MarketerPackage | None:
    packages = packages_matching_brief(marketer_id, services_needed)
    return packages[0] if packages else None


def fee_breakdown(price_cents: int) -> dict:
    platform_pct = float(os.environ.get("PLATFORM_FEE_PERCENT", "20"))
    buyer_pct = float(os.environ.get("BUYER_SERVICE_FEE_PERCENT", "5"))
    platform_fee = int(round(price_cents * platform_pct / 100))
    buyer_fee = int(round(price_cents * buyer_pct / 100))
    total_cents = price_cents + buyer_fee
    marketer_payout = max(0, price_cents - platform_fee)
    return {
        "price_cents": price_cents,
        "platform_fee_cents": platform_fee,
        "buyer_fee_cents": buyer_fee,
        "total_cents": total_cents,
        "marketer_payout_cents": marketer_payout,
    }


def marketers_with_active_packages():
    """Marketer IDs that have at least one active package."""
    rows = MarketerPackage.query.filter_by(active=True).with_entities(MarketerPackage.marketer_id).distinct().all()
    return {r[0] for r in rows}


def format_price_cents(cents: int | None) -> str:
    if cents is None:
        return "—"
    return f"${cents / 100:.0f}" if cents % 100 == 0 else f"${cents / 100:.2f}"


def require_connect_for_checkout() -> bool:
    return os.environ.get("REQUIRE_STRIPE_CONNECT", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def marketer_can_accept_payments(marketer: Marketer) -> bool:
    from app.services.payments import payments_dev_bypass, payments_enabled

    if payments_dev_bypass():
        return True
    if not payments_enabled():
        return False
    if not require_connect_for_checkout():
        return True
    return bool(marketer.stripe_connect_account_id and marketer.payouts_enabled)


def marketplace_gmv_stats() -> dict:
    from app.models import MarketplaceOrder

    paid_statuses = ("paid", "in_progress", "delivered", "completed")
    orders = MarketplaceOrder.query.filter(MarketplaceOrder.status.in_(paid_statuses)).all()
    gmv = sum(o.amount_cents or 0 for o in orders)
    fees = sum(o.platform_fee_cents or 0 for o in orders)
    completed = sum(1 for o in orders if o.status == "completed")
    return {
        "order_count": len(orders),
        "completed_count": completed,
        "gmv_cents": gmv,
        "platform_fee_cents": fees,
    }
