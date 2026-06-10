"""Rejected-site blacklist so discovery skips admin-rejected domains."""
from datetime import datetime

from app import db
from app.models import IntroRequest, Marketer, MatchFeedback, RejectedSite
from app.services.site_urls import canonical_homepage_url, domain_key


def is_blacklisted(url):
    key = domain_key(url)
    if not key:
        return False
    return RejectedSite.query.filter_by(domain_key=key).first() is not None


def add_rejected_site(marketer, reason="admin_reject", notes="", commit=True):
    key = domain_key(marketer.website or "")
    if not key:
        return None
    existing = RejectedSite.query.filter_by(domain_key=key).first()
    if existing:
        existing.reason = reason
        existing.notes = (notes or existing.notes or "")[:500]
        existing.brand_name = marketer.brand_name or marketer.name or existing.brand_name
        existing.website = canonical_homepage_url(marketer.website or "") or existing.website
        existing.rejected_at = datetime.utcnow()
    else:
        row = RejectedSite(
            domain_key=key,
            website=canonical_homepage_url(marketer.website or "") or marketer.website,
            brand_name=(marketer.brand_name or marketer.name or "")[:255],
            reason=reason,
            notes=(notes or "")[:500],
        )
        db.session.add(row)
        existing = row
    if commit:
        db.session.commit()
    return existing


def delete_marketer_cascade(marketer):
    """Remove marketer and related intro/feedback rows."""
    MatchFeedback.query.filter_by(marketer_id=marketer.id).delete()
    IntroRequest.query.filter_by(marketer_id=marketer.id).delete()
    db.session.delete(marketer)


def reject_and_remove_marketer(marketer, reason="admin_reject"):
    """Delete marketer from catalog and blacklist its domain."""
    add_rejected_site(marketer, reason=reason, commit=False)
    delete_marketer_cascade(marketer)
    db.session.commit()
