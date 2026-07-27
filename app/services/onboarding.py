"""Marketer provisioning and onboarding helpers."""
from __future__ import annotations

import os
import secrets
from typing import TYPE_CHECKING

from app import db
from app.models import Marketer
from app.services.catalog import catalog_marketers_query, is_catalog_marketer
from app.services.site_urls import sync_marketer_domain_fields

if TYPE_CHECKING:
    from app.models import MarketerApplication


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


def provision_catalog_marketer(
    *,
    brand_name: str,
    website: str,
    email: str = "",
    bio: str = "",
    services: list | None = None,
    genres: list | None = None,
    source: str = "onboarding",
    provider_type: str = "solo",
) -> Marketer:
    """Create approved marketer in the public catalog."""
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
        provider_type=provider_type,
        enrolled=False,
    )
    sync_marketer_domain_fields(marketer)
    db.session.add(marketer)
    return marketer


def provision_from_application(app_row: MarketerApplication) -> Marketer:
    return provision_catalog_marketer(
        brand_name=app_row.brand_name,
        website=app_row.website,
        email=app_row.email or "",
        bio=app_row.bio or "",
        services=app_row.services or [],
        genres=app_row.genres or [],
        source="onboarding",
        provider_type="solo",
    )


# Backward-compatible alias for admin routes
provision_platform_marketer = provision_catalog_marketer


def marketer_onboarding_status(marketer: Marketer) -> dict:
    """Summarize whether a marketer is ready for artist connections."""
    approved = is_catalog_marketer(marketer)
    has_profile = bool((marketer.bio or "").strip() and (marketer.services or []))
    has_contact = bool((marketer.email or "").strip())
    has_portal = bool((marketer.portal_token or "").strip())

    if approved and has_profile and has_contact:
        label = "Live"
        tone = "approved"
    elif approved and has_profile:
        label = "Needs contact email"
        tone = "pending"
    elif approved:
        label = "Needs profile"
        tone = "pending"
    else:
        label = marketer.status or "pending"
        tone = marketer.status or "pending"

    return {
        "label": label,
        "tone": tone,
        "live": approved and has_profile and has_contact,
        "has_portal": has_portal,
    }


def onboarding_email_body(marketer: Marketer) -> str:
    portal = marketer_portal_url(marketer)
    lines = [
        f"Hi {marketer.brand_name or marketer.name},",
        "",
        "You're listed on SoundMatch. Your profile portal:",
        portal,
        "",
        "Please complete:",
        "1. Update your bio, services, and genres",
        "2. Add a contact email so artists can reach you",
        "",
        "SoundMatch is a nonprofit connection engine — we match artists with marketers based on campaign fit, not bookings.",
        "",
        "Thanks,",
        "SoundMatch",
    ]
    return "\n".join(lines)


def catalog_stats() -> dict:
    count = catalog_marketers_query().count()
    return {"catalog_count": count}
