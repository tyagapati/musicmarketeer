"""Platform marketer provisioning and onboarding helpers."""
from __future__ import annotations

import os
import secrets
from typing import TYPE_CHECKING

from app import db
from app.models import Marketer, MarketerPackage
from sqlalchemy import func

from app.services.marketplace import is_platform_marketer, marketer_can_accept_payments
from app.services.site_urls import sync_marketer_domain_fields

if TYPE_CHECKING:
    from app.models import MarketerApplication

DEFAULT_STARTER_PRICE_CENTS = 14900
DEFAULT_DELIVERY_DAYS = 14


def app_base_url() -> str:
    return os.environ.get("APP_URL", "http://127.0.0.1:8000").rstrip("/")


def marketer_portal_path(marketer: Marketer) -> str:
    token = (marketer.portal_token or "").strip()
    return f"/marketer/portal/{token}" if token else ""


def marketer_portal_url(marketer: Marketer) -> str:
    path = marketer_portal_path(marketer)
    return f"{app_base_url()}{path}" if path else ""


def marketer_apply_url() -> str:
    return f"{app_base_url()}/marketer/apply"


def _starter_package_title(brand_name: str, service: str) -> str:
    label = service.replace("_", " ").title()
    return f"{brand_name} — {label}"


def add_starter_package(
    marketer: Marketer,
    *,
    service: str | None = None,
    price_cents: int = DEFAULT_STARTER_PRICE_CENTS,
    delivery_days: int = DEFAULT_DELIVERY_DAYS,
    description: str | None = None,
) -> MarketerPackage:
    primary = service or (marketer.services or ["playlist_pitching"])[0]
    brand = marketer.brand_name or marketer.name or "Marketer"
    pkg = MarketerPackage(
        marketer_id=marketer.id,
        service=primary,
        title=_starter_package_title(brand, primary),
        description=description or marketer.bio or "Custom campaign support for independent artists.",
        price_cents=price_cents,
        delivery_days=delivery_days,
        active=True,
    )
    db.session.add(pkg)
    return pkg


def provision_platform_marketer(
    *,
    brand_name: str,
    website: str,
    email: str = "",
    bio: str = "",
    services: list | None = None,
    genres: list | None = None,
    source: str = "onboarding",
    price_cents: int = DEFAULT_STARTER_PRICE_CENTS,
    delivery_days: int = DEFAULT_DELIVERY_DAYS,
) -> Marketer:
    """Create enrolled solo marketer with portal token and starter package."""
    marketer = Marketer(
        name=brand_name,
        brand_name=brand_name,
        website=website,
        email=email,
        bio=bio,
        genres=genres or [],
        services=services or [],
        languages=["en"],
        status="approved",
        source=source,
        price_verified=False,
        price_source="estimated",
        affiliate_url=website,
        portal_token=secrets.token_urlsafe(24),
        provider_type="solo",
        enrolled=True,
    )
    sync_marketer_domain_fields(marketer)
    db.session.add(marketer)
    db.session.flush()
    add_starter_package(
        marketer,
        service=(services or ["playlist_pitching"])[0],
        price_cents=price_cents,
        delivery_days=delivery_days,
        description=bio or None,
    )
    return marketer


def provision_from_application(app_row: MarketerApplication) -> Marketer:
    return provision_platform_marketer(
        brand_name=app_row.brand_name,
        website=app_row.website,
        email=app_row.email or "",
        bio=app_row.bio or "",
        services=app_row.services or [],
        genres=app_row.genres or [],
        source="onboarding",
    )


def active_package_counts(marketer_ids: list[int]) -> dict[int, int]:
    if not marketer_ids:
        return {}
    rows = (
        db.session.query(MarketerPackage.marketer_id, func.count(MarketerPackage.id))
        .filter(MarketerPackage.marketer_id.in_(marketer_ids), MarketerPackage.active.is_(True))
        .group_by(MarketerPackage.marketer_id)
        .all()
    )
    return {mid: count for mid, count in rows}


def marketer_onboarding_status(marketer: Marketer, *, active_packages: int = 0) -> dict:
    """Summarize onboarding progress for admin UI."""
    approved = marketer.status == "approved"
    enrolled = bool(marketer.enrolled and marketer.provider_type == "solo")
    has_packages = active_packages > 0
    connect_ok = bool(marketer.payouts_enabled)
    has_connect_account = bool((marketer.stripe_connect_account_id or "").strip())
    bookable = marketer_can_accept_payments(marketer) if enrolled and has_packages else False
    in_catalog = is_platform_marketer(marketer) and has_packages

    steps = []
    if approved:
        steps.append("approved")
    if enrolled:
        steps.append("enrolled")
    if has_packages:
        steps.append("packages")
    if connect_ok:
        steps.append("connect")
    elif has_connect_account:
        steps.append("connect_pending")
    if bookable:
        steps.append("bookable")
    if in_catalog:
        steps.append("live")

    if in_catalog and bookable:
        label = "Live"
        tone = "approved"
    elif enrolled and has_packages:
        label = "Needs Connect" if not bookable else "Almost live"
        tone = "pending"
    elif approved and enrolled:
        label = "Needs packages"
        tone = "pending"
    elif approved:
        label = "Approved"
        tone = "pending"
    else:
        label = marketer.status or "pending"
        tone = marketer.status or "pending"

    return {
        "label": label,
        "tone": tone,
        "steps": steps,
        "active_packages": active_packages,
        "bookable": bookable,
        "live": in_catalog and bookable,
    }


def onboarding_email_body(marketer: Marketer, *, include_connect: bool = True) -> str:
    portal = marketer_portal_url(marketer)
    lines = [
        f"Hi {marketer.brand_name or marketer.name},",
        "",
        "You're approved on SoundMatch. Your private portal:",
        portal,
        "",
        "Please complete:",
        "1. Add 1–3 packages with your real prices and delivery times",
        "2. Update your bio and services",
    ]
    if include_connect:
        lines.append("3. Complete Connect payouts in the portal so you can receive bookings")
    else:
        lines.append("3. Payout setup will be shared when we go live with payments")
    lines.extend(["", "Thanks,", "SoundMatch"])
    return "\n".join(lines)
