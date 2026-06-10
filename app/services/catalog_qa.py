"""Catalog quality-assurance helpers for admin."""
import secrets

from app import db
from app.models import Marketer


def verify_top_approved_prices(limit=10):
    """Mark prices verified for top approved marketers by proof score."""
    marketers = (
        Marketer.query.filter_by(status="approved")
        .order_by(Marketer.proof_strength.desc(), Marketer.confidence_score.desc())
        .limit(limit)
        .all()
    )
    updated = 0
    for marketer in marketers:
        if not marketer.price_verified:
            marketer.price_verified = True
            marketer.price_source = "verified"
            updated += 1
    db.session.commit()
    return {"verified": updated, "considered": len(marketers)}


def auto_approve_high_confidence_pending():
    """Approve pending marketers that pass auto-approve thresholds."""
    from app.services.automation_settings import is_automation_enabled
    from app.services.discovery_pipeline import meets_auto_approve_threshold

    if not is_automation_enabled("auto_approve_marketers"):
        return {"approved": 0, "considered": 0, "disabled": True}

    pending = Marketer.query.filter_by(status="pending").all()
    approved = 0
    for marketer in pending:
        if meets_auto_approve_threshold(marketer):
            marketer.status = "approved"
            if not marketer.portal_token:
                marketer.portal_token = secrets.token_urlsafe(24)
            approved += 1
    db.session.commit()
    return {"approved": approved, "considered": len(pending)}
