"""Matching engine: rank marketers by fit to a campaign brief."""
import os

from app import db
from app.models import Marketer, MatchFeedback

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


def rank_marketers(brief, top_n=5):
    marketers = Marketer.query.filter_by(status="approved").all()
    results = []
    for m in marketers:
        score, reasons = _score(m, brief)
        results.append(
            {
                "marketer": {
                    "id": m.id,
                    "name": m.name,
                    "brand_name": m.brand_name,
                    "genres": m.genres or [],
                    "services": m.services or [],
                    "price_min": m.price_min,
                    "price_max": m.price_max,
                    "price_verified": m.price_verified,
                },
                "match_score": round(score, 2),
                "top_reasons": reasons[:5],
            }
        )
    results.sort(key=lambda x: -x["match_score"])
    return results[:top_n]


def _score(marketer, brief):
    w = _weights()
    reasons = []
    score = 0.0

    if set(marketer.genres or []) & set(brief.genres or []):
        score += w["genre"]
        reasons.append("Genre fit")

    if set(marketer.services or []) & set(brief.services_needed or []):
        score += w["service"]
        reasons.append("Services match")

    if brief.budget_max and marketer.price_min is not None:
        if brief.budget_max >= marketer.price_min:
            if marketer.price_max and brief.budget_min and brief.budget_min > marketer.price_max:
                score += w["budget"] * 0.4
                reasons.append("Budget partially aligned")
            else:
                score += w["budget"]
                reasons.append("Budget fit")

    goal_keywords = set((brief.goals or []) + (brief.services_needed or []))
    service_keywords = set(marketer.services or [])
    if goal_keywords & service_keywords:
        score += w["goal"]
        reasons.append("Goal fit")

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

    hire_count = MatchFeedback.query.filter_by(marketer_id=marketer.id, hired=True).count()
    if hire_count:
        score += min(0.08, hire_count * 0.02)
        reasons.append("Prior hire feedback")

    avg_rating = (
        db.session.query(db.func.avg(MatchFeedback.rating))
        .filter(MatchFeedback.marketer_id == marketer.id, MatchFeedback.rating.isnot(None))
        .scalar()
    )
    if avg_rating and avg_rating >= 4:
        score += 0.04
        reasons.append("Strong artist ratings")

    return min(score, 1.0), reasons
