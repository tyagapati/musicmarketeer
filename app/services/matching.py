"""Matching engine: rank platform marketers by fit to a campaign brief."""
import os

from app import db
from app.models import Marketer, MatchFeedback, MarketplaceOrder
from app.services.marketplace import (
    cheapest_package_for_brief,
    marketers_with_active_packages,
    packages_matching_brief,
    platform_marketers_query,
)

DEFAULT_WEIGHTS = {
    "genre": 0.20,
    "service": 0.20,
    "budget": 0.15,
    "goal": 0.10,
    "maturity": 0.10,
    "proof": 0.10,
    "timezone": 0.05,
    "language": 0.05,
    "confidence": 0.05,
}

GOAL_SERVICE_MAP = {
    "streams": ["playlist_pitching", "ads", "release_campaigns"],
    "stream": ["playlist_pitching", "ads"],
    "playlists": ["playlist_pitching"],
    "playlist": ["playlist_pitching"],
    "spotify": ["playlist_pitching", "ads"],
    "tiktok": ["social_media_strategy", "ads"],
    "instagram": ["social_media_strategy", "ads"],
    "social": ["social_media_strategy", "ads"],
    "press": ["pr"],
    "pr": ["pr"],
    "publicity": ["pr"],
    "release": ["release_campaigns", "pr"],
    "launch": ["release_campaigns", "ads"],
    "brand": ["identity_positioning", "social_media_strategy"],
    "branding": ["identity_positioning"],
    "analytics": ["analytics"],
    "data": ["analytics"],
    "growth": ["social_media_strategy", "ads", "analytics"],
    "followers": ["social_media_strategy", "ads"],
    "fanbase": ["social_media_strategy"],
}


def _weights():
    weights = {}
    for key, default in DEFAULT_WEIGHTS.items():
        env_key = f"MATCH_WEIGHT_{key.upper()}"
        raw = os.environ.get(env_key, "")
        try:
            weights[key] = float(raw) if raw else default
        except ValueError:
            weights[key] = default
    total = sum(weights.values()) or 1.0
    return {k: v / total for k, v in weights.items()}


def _marketer_payload(m, *, brief=None):
    cheapest = cheapest_package_for_brief(m.id, brief.services_needed if brief else []) if brief else None
    packages = packages_matching_brief(m.id, brief.services_needed if brief else []) if brief else []
    return {
        "id": m.id,
        "name": m.name,
        "brand_name": m.brand_name,
        "bio": m.bio,
        "website": m.website,
        "genres": m.genres or [],
        "services": m.services or [],
        "price_min": m.price_min,
        "price_max": m.price_max,
        "price_model": m.price_model,
        "price_verified": m.price_verified,
        "price_source": m.price_source or "estimated",
        "proof_strength": m.proof_strength or 0,
        "confidence_score": m.confidence_score or 0,
        "evidence_summary": m.evidence_summary,
        "provider_type": m.provider_type or "solo",
        "enrolled": bool(m.enrolled),
        "cheapest_package_cents": cheapest.price_cents if cheapest else None,
        "cheapest_package_id": cheapest.id if cheapest else None,
        "package_count": len(packages),
    }


def rank_marketers(brief, top_n=5):
    """Rank enrolled platform marketers with active packages only."""
    bookable_ids = marketers_with_active_packages()
    marketers = platform_marketers_query().filter(Marketer.id.in_(bookable_ids or [-1])).all()
    results = []
    for m in marketers:
        score, reasons = _score(m, brief)
        pkg = cheapest_package_for_brief(m.id, brief.services_needed or [])
        results.append(
            {
                "marketer": _marketer_payload(m, brief=brief),
                "match_score": round(score, 2),
                "top_reasons": reasons[:5],
                "featured_package_id": pkg.id if pkg else None,
            }
        )
    results.sort(key=lambda x: -x["match_score"])
    return results[:top_n]


def _expanded_goal_services(brief):
    services = set(brief.services_needed or [])
    for goal in brief.goals or []:
        token = str(goal).strip().lower().replace(" ", "_")
        if token in GOAL_SERVICE_MAP:
            services.update(GOAL_SERVICE_MAP[token])
        for key, mapped in GOAL_SERVICE_MAP.items():
            if key in token:
                services.update(mapped)
    return services


def _score(marketer, brief):
    w = _weights()
    reasons = []
    score = 0.0

    if set(marketer.genres or []) & set(brief.genres or []):
        score += w["genre"]
        reasons.append("Genre fit")

    matched_packages = packages_matching_brief(marketer.id, brief.services_needed or [])
    if matched_packages:
        score += w["service"]
        reasons.append("Bookable service match")

    goal_services = _expanded_goal_services(brief)
    if goal_services and any(p.service in goal_services for p in matched_packages):
        score += w["goal"]
        reasons.append("Goal fit")

    cheapest = matched_packages[0] if matched_packages else None
    if cheapest and brief.budget_max:
        pkg_dollars = cheapest.price_cents / 100
        if pkg_dollars <= brief.budget_max:
            score += w["budget"]
            reasons.append("Package fits budget")
        elif pkg_dollars <= brief.budget_max * 1.15:
            score += w["budget"] * 0.5
            reasons.append("Package near budget")

    if brief.maturity_tier in (marketer.preferred_maturity or []):
        score += w["maturity"]
        reasons.append("Maturity fit")
    elif not marketer.preferred_maturity:
        score += w["maturity"] * 0.35

    proof = marketer.proof_strength or 0
    score += w["proof"] * (proof / 100.0)
    if proof >= 50:
        reasons.append("Strong proof")

    if brief.timezone and marketer.timezone:
        if brief.timezone == marketer.timezone:
            score += w["timezone"]
            reasons.append("Timezone fit")
    elif not brief.timezone or not marketer.timezone:
        score += w["timezone"] * 0.5

    if set(marketer.languages or []) & set(brief.languages or []):
        score += w["language"]
        reasons.append("Language fit")
    elif "en" in (marketer.languages or []) and "en" in (brief.languages or []):
        score += w["language"]
        reasons.append("Language fit")

    confidence = marketer.confidence_score or 0
    score += w["confidence"] * (confidence / 100.0)
    if confidence >= 60:
        reasons.append("High confidence")

    completed_orders = MarketplaceOrder.query.filter_by(
        marketer_id=marketer.id, status="completed"
    ).count()
    if completed_orders:
        score += min(0.08, completed_orders * 0.02)
        reasons.append("Completed platform orders")

    hire_count = MatchFeedback.query.filter_by(marketer_id=marketer.id, hired=True).count()
    if hire_count:
        score += min(0.04, hire_count * 0.01)

    avg_rating = (
        db.session.query(db.func.avg(MarketplaceOrder.rating))
        .filter(
            MarketplaceOrder.marketer_id == marketer.id,
            MarketplaceOrder.rating.isnot(None),
            MarketplaceOrder.status == "completed",
        )
        .scalar()
    )
    if not avg_rating:
        avg_rating = (
            db.session.query(db.func.avg(MatchFeedback.rating))
            .filter(MatchFeedback.marketer_id == marketer.id, MatchFeedback.rating.isnot(None))
            .scalar()
        )
    if avg_rating and avg_rating >= 4:
        score += 0.04
        reasons.append("Strong artist ratings")

    return min(score, 1.0), reasons
