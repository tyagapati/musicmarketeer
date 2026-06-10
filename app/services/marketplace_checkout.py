"""Per-order marketplace checkout (Stripe Connect ready; dev bypass for local)."""
from __future__ import annotations

import os
from datetime import datetime

from app import db
from app.models import CampaignBrief, MarketerPackage, MarketplaceOrder
from app.services.marketplace import fee_breakdown, get_platform_marketer
from app.services.payments import payments_dev_bypass, payments_enabled, _stripe_client

try:
    import stripe
except ImportError:
    stripe = None


def create_order_for_package(
    *,
    brief: CampaignBrief,
    package: MarketerPackage,
) -> MarketplaceOrder:
    marketer = get_platform_marketer(package.marketer_id)
    if not marketer:
        raise ValueError("Marketer is not on the platform marketplace")
    if not package.active:
        raise ValueError("Package is not available")

    fees = fee_breakdown(package.price_cents)
    order = MarketplaceOrder(
        brief_id=brief.id,
        marketer_id=marketer.id,
        package_id=package.id,
        artist_name=brief.artist_name,
        artist_email=brief.email or "",
        amount_cents=fees["total_cents"],
        platform_fee_cents=fees["platform_fee_cents"],
        marketer_payout_cents=fees["marketer_payout_cents"],
        status="pending_payment",
    )
    db.session.add(order)
    db.session.commit()
    return order


def mark_order_paid(order: MarketplaceOrder, *, session_id: str | None = None) -> bool:
    if order.status in ("in_progress", "paid", "delivered", "completed"):
        return False
    if order.status != "pending_payment":
        return False
    if session_id and payments_enabled():
        client = _stripe_client()
        session = client.checkout.Session.retrieve(session_id)
        if session.payment_status != "paid":
            return False
        meta_order = (session.metadata or {}).get("order_id")
        if meta_order and str(order.id) != str(meta_order):
            return False
        order.stripe_checkout_session_id = session.id
        if session.payment_intent:
            order.stripe_payment_intent_id = str(session.payment_intent)
    order.status = "in_progress"
    order.paid_at = datetime.utcnow()
    db.session.commit()
    from app.services.notifications import notify_order_paid

    notify_order_paid(order)
    return True


def start_checkout(order: MarketplaceOrder, *, success_url: str, cancel_url: str) -> str:
    """Return checkout URL. Dev bypass marks paid immediately."""
    if payments_dev_bypass():
        mark_order_paid(order)
        return success_url.replace("{CHECKOUT_SESSION_ID}", "dev_bypass")

    if not payments_enabled():
        raise RuntimeError("Stripe is not configured")

    package = MarketerPackage.query.get(order.package_id)
    marketer = get_platform_marketer(order.marketer_id)
    if not package or not marketer:
        raise ValueError("Invalid order")

    client = _stripe_client()
    line_items = [
        {
            "price_data": {
                "currency": os.environ.get("STRIPE_CURRENCY", "usd"),
                "unit_amount": order.amount_cents,
                "product_data": {
                    "name": package.title,
                    "description": package.description or f"SoundMatch booking — {package.delivery_days} day delivery",
                },
            },
            "quantity": 1,
        }
    ]

    session_kwargs = {
        "mode": "payment",
        "line_items": line_items,
        "success_url": success_url,
        "cancel_url": cancel_url,
        "customer_email": order.artist_email or None,
        "metadata": {"order_id": str(order.id), "brief_id": str(order.brief_id)},
    }

    connect_id = (marketer.stripe_connect_account_id or "").strip()
    if connect_id and marketer.payouts_enabled:
        session_kwargs["payment_intent_data"] = {
            "application_fee_amount": order.platform_fee_cents,
            "transfer_data": {"destination": connect_id},
        }

    session = client.checkout.Session.create(**session_kwargs)
    order.stripe_checkout_session_id = session.id
    db.session.commit()
    return session.url


def handle_marketplace_webhook_event(event: dict) -> dict:
    if event.get("type") != "checkout.session.completed":
        return {"handled": False}
    session = event["data"]["object"]
    order_id = (session.get("metadata") or {}).get("order_id")
    if not order_id:
        return {"handled": False}
    order = MarketplaceOrder.query.get(int(order_id))
    if not order:
        return {"handled": False}
    mark_order_paid(order, session_id=session.get("id"))
    return {"handled": True, "order_id": order.id}
