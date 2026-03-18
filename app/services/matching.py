"""Matching engine: rank marketers by fit to a campaign brief."""
from app.models import Marketer


def rank_marketers(brief, top_n=5):
    marketers = Marketer.query.filter_by(status="approved").all()
    results = []
    for m in marketers:
        score, reasons = _score(m, brief)
        results.append({
            "marketer": {
                "id": m.id,
                "name": m.name,
                "brand_name": m.brand_name,
                "genres": m.genres or [],
                "services": m.services or [],
                "price_min": m.price_min,
                "price_max": m.price_max,
            },
            "match_score": round(score, 2),
            "top_reasons": reasons[:5],
        })
    results.sort(key=lambda x: -x["match_score"])
    return results[:top_n]


def _score(marketer, brief):
    reasons = []
    score = 0.0
    if set(marketer.genres or []) & set(brief.genres or []):
        score += 0.3
        reasons.append("Genre fit")
    if brief.budget_max and marketer.price_min is not None:
        if brief.budget_max >= marketer.price_min:
            score += 0.25
            reasons.append("Budget fit")
    if set(marketer.services or []) & set(brief.services_needed or []):
        score += 0.25
        reasons.append("Services match")
    if brief.maturity_tier in (marketer.preferred_maturity or []):
        score += 0.2
        reasons.append("Maturity fit")
    return min(score, 1.0), reasons
