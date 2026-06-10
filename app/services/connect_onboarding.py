"""Stripe Connect Express onboarding for platform marketers."""
from __future__ import annotations

import os

from app import db
from app.models import Marketer
from app.services.payments import payments_enabled, _stripe_client


def connect_configured() -> bool:
    return payments_enabled()


def ensure_connect_account(marketer: Marketer) -> str:
    """Create or return Stripe Connect Express account id."""
    if not connect_configured():
        raise RuntimeError("Stripe is not configured")
    existing = (marketer.stripe_connect_account_id or "").strip()
    if existing:
        return existing

    client = _stripe_client()
    account = client.Account.create(
        type="express",
        country=os.environ.get("STRIPE_CONNECT_COUNTRY", "US"),
        email=marketer.email or None,
        capabilities={
            "card_payments": {"requested": True},
            "transfers": {"requested": True},
        },
        business_type="individual",
        metadata={"marketer_id": str(marketer.id)},
    )
    marketer.stripe_connect_account_id = account.id
    db.session.commit()
    return account.id


def create_account_link(marketer: Marketer, *, return_url: str, refresh_url: str) -> str:
    """Return Stripe-hosted onboarding URL."""
    account_id = ensure_connect_account(marketer)
    client = _stripe_client()
    link = client.AccountLink.create(
        account=account_id,
        refresh_url=refresh_url,
        return_url=return_url,
        type="account_onboarding",
    )
    return link.url


def sync_account_from_stripe(account_id: str) -> Marketer | None:
    """Refresh payouts_enabled from Stripe account state."""
    if not connect_configured():
        return None
    marketer = Marketer.query.filter_by(stripe_connect_account_id=account_id).first()
    if not marketer:
        return None
    client = _stripe_client()
    account = client.Account.retrieve(account_id)
    charges_enabled = bool(account.get("charges_enabled"))
    payouts_enabled = bool(account.get("payouts_enabled"))
    details_submitted = bool(account.get("details_submitted"))
    marketer.payouts_enabled = charges_enabled and payouts_enabled and details_submitted
    db.session.commit()
    return marketer


def handle_account_updated_event(event: dict) -> dict:
    account = event.get("data", {}).get("object") or {}
    account_id = account.get("id")
    if not account_id:
        return {"handled": False}
    marketer = sync_account_from_stripe(account_id)
    if not marketer:
        return {"handled": False}
    return {"handled": True, "marketer_id": marketer.id, "payouts_enabled": marketer.payouts_enabled}
