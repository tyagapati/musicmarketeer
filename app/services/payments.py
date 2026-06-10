"""Stripe Checkout for premium match reports + concierge intro bundle."""
from __future__ import annotations

import os
from datetime import datetime

from app import db
from app.models import CampaignBrief

try:
    import stripe
except ImportError:
    stripe = None


def payments_enabled() -> bool:
    return bool(stripe and os.environ.get("STRIPE_SECRET_KEY", "").strip())


def payments_dev_bypass() -> bool:
    return os.environ.get("PAYMENTS_DEV_BYPASS", "").strip().lower() in ("1", "true", "yes", "on")


def brief_is_paid(brief: CampaignBrief) -> bool:
    if payments_dev_bypass():
        return True
    return (brief.payment_status or "unpaid") == "paid"


def concierge_intros_available(brief: CampaignBrief) -> bool:
    """True when the artist can request a concierge intro for this brief."""
    if (brief.concierge_intros_remaining or 0) > 0:
        return True
    return payments_dev_bypass()


def _stripe_client():
    if not stripe:
        raise RuntimeError("stripe package not installed")
    key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    if not key:
        raise RuntimeError("STRIPE_SECRET_KEY is not set")
    stripe.api_key = key
    return stripe


def create_checkout_session(brief: CampaignBrief, *, success_url: str, cancel_url: str) -> str:
    """Return Stripe Checkout URL for this brief."""
    client = _stripe_client()
    price_id = os.environ.get("STRIPE_PRICE_ID", "").strip()
    line_items = []
    if price_id:
        line_items.append({"price": price_id, "quantity": 1})
    else:
        amount = int(os.environ.get("STRIPE_AMOUNT_CENTS", "4900"))
        line_items.append(
            {
                "price_data": {
                    "currency": os.environ.get("STRIPE_CURRENCY", "usd"),
                    "unit_amount": amount,
                    "product_data": {
                        "name": "SoundMatch Premium Match + Concierge Intro",
                        "description": "Full match report and one warm intro sent by SoundMatch.",
                    },
                },
                "quantity": 1,
            }
        )

    session = client.checkout.Session.create(
        mode="payment",
        line_items=line_items,
        success_url=success_url,
        cancel_url=cancel_url,
        customer_email=brief.email or None,
        metadata={"brief_id": str(brief.id)},
    )
    brief.stripe_checkout_session_id = session.id
    db.session.commit()
    return session.url


def mark_brief_paid_from_session(brief: CampaignBrief, session_id: str | None = None) -> bool:
    """Idempotently mark brief paid and grant concierge intro credit."""
    if (brief.payment_status or "") == "paid" and brief.paid_at:
        return False
    if session_id and payments_enabled():
        client = _stripe_client()
        session = client.checkout.Session.retrieve(session_id)
        if session.payment_status != "paid":
            return False
        meta_brief = (session.metadata or {}).get("brief_id")
        if meta_brief and str(brief.id) != str(meta_brief):
            return False
        brief.stripe_checkout_session_id = session.id
    brief.payment_status = "paid"
    brief.paid_at = datetime.utcnow()
    brief.concierge_intros_remaining = max(brief.concierge_intros_remaining or 0, 1)
    db.session.commit()
    return True


def handle_stripe_webhook(payload: bytes, sig_header: str) -> dict:
    """Verify webhook and mark briefs paid."""
    client = _stripe_client()
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
    if not secret:
        raise RuntimeError("STRIPE_WEBHOOK_SECRET is not set")
    event = client.Webhook.construct_event(payload, sig_header, secret)
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        brief_id = (session.get("metadata") or {}).get("brief_id")
        if brief_id:
            brief = CampaignBrief.query.get(int(brief_id))
            if brief:
                mark_brief_paid_from_session(brief, session.get("id"))
                return {"handled": True, "brief_id": brief.id}
    return {"handled": False}
