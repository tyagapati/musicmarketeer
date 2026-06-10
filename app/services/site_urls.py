"""Canonical website URLs and domain-level deduplication."""
from urllib.parse import urlparse

from app import db
from app.models import IntroRequest, Marketer, MatchFeedback

_STATUS_RANK = {"approved": 3, "pending": 2, "rejected": 1}


def domain_key(url):
    """Normalized registrable host for dedup/blacklist (lowercase, no www)."""
    raw = (url or "").strip()
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw.lstrip("/")
    host = (urlparse(raw).netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host.split(":")[0]


def canonical_homepage_url(url):
    """Single homepage URL per domain (always https, no path)."""
    key = domain_key(url)
    if not key:
        return ""
    return f"https://{key}"


def _marketer_rank(marketer):
    status_score = _STATUS_RANK.get(marketer.status or "", 0)
    proof = marketer.proof_strength or 0
    confidence = marketer.confidence_score or 0
    return (status_score, proof, confidence, -(marketer.id or 0))


def _delete_marketer_rows(marketer):
    from app.services.site_blacklist import delete_marketer_cascade

    delete_marketer_cascade(marketer)


def dedupe_marketers_by_domain():
    """Keep one marketer per domain; normalize website to homepage."""
    groups = {}
    for marketer in Marketer.query.all():
        key = domain_key(marketer.website or "")
        if not key:
            continue
        groups.setdefault(key, []).append(marketer)

    removed = 0
    normalized = 0
    for key, rows in groups.items():
        homepage = canonical_homepage_url(rows[0].website or f"https://{key}")
        keeper = max(rows, key=_marketer_rank)
        if keeper.website != homepage:
            keeper.website = homepage
            keeper.domain_key = key
            if not keeper.affiliate_url or domain_key(keeper.affiliate_url) == key:
                keeper.affiliate_url = homepage
            normalized += 1
        elif keeper.domain_key != key:
            keeper.domain_key = key
            normalized += 1

        for marketer in rows:
            if marketer.id == keeper.id:
                continue
            _delete_marketer_rows(marketer)
            removed += 1

    if removed or normalized:
        db.session.commit()
    return {"removed": removed, "normalized": normalized}


def sync_marketer_domain_fields(marketer):
    """Set domain_key and canonical homepage on a marketer row."""
    homepage = canonical_homepage_url(marketer.website or "")
    key = domain_key(homepage)
    if homepage:
        marketer.website = homepage
        marketer.domain_key = key
        if not marketer.affiliate_url or domain_key(marketer.affiliate_url) == key:
            marketer.affiliate_url = homepage
