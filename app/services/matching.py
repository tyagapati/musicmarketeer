"""Matching engine: rank catalog marketers by fit to a campaign brief."""
import os
import re

from app import db
from app.models import CampaignStrategy, Marketer, MatchFeedback, MusicAnalysis
from app.services.catalog import catalog_marketers_query

DEFAULT_WEIGHTS = {
    "genre": 0.22,
    "service": 0.20,
    "budget": 0.10,
    "goal": 0.08,
    "maturity": 0.08,
    "proof": 0.08,
    "timezone": 0.02,
    "language": 0.02,
    "confidence": 0.05,
    "audience_fit": 0.08,
    "channel_fit": 0.05,
    "lyrical_themes": 0.02,
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

CHANNEL_SERVICE_MAP = {
    "tiktok": ["social_media_strategy", "ads"],
    "social": ["social_media_strategy", "ads"],
    "playlist": ["playlist_pitching", "release_campaigns"],
    "streaming": ["playlist_pitching", "ads"],
    "video": ["social_media_strategy", "ads", "release_campaigns"],
    "press": ["pr"],
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


def _tokenize(text: str) -> set[str]:
    return {t.lower() for t in re.findall(r"[a-zA-Z']+", text or "") if len(t) > 2}


def _marketer_payload(m, *, brief=None):
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
        "provider_type": m.provider_type or "agency",
        "enrolled": bool(m.enrolled),
        "email": m.email,
    }


def rank_marketers(brief, top_n=5):
    """Rank all approved catalog marketers."""
    strategy = CampaignStrategy.query.filter_by(brief_id=brief.id).first()
    analysis = MusicAnalysis.query.filter_by(brief_id=brief.id).first()
    priority_services = set(strategy.artist_priorities or []) if strategy else set()
    recommended = {c.get("service") for c in (strategy.recommended_channels or []) if c.get("service")} if strategy else set()

    marketers = catalog_marketers_query().all()
    results = []
    for m in marketers:
        score, reasons = _score(
            m,
            brief,
            analysis=analysis,
            priority_services=priority_services,
            recommended_services=recommended,
        )
        results.append(
            {
                "marketer": _marketer_payload(m, brief=brief),
                "match_score": round(score, 2),
                "top_reasons": reasons[:5],
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


def _service_overlap(marketer, brief):
    needed = set(brief.services_needed or [])
    offered = set(marketer.services or [])
    if not needed:
        return bool(offered)
    return bool(needed & offered)


def _audience_tag_overlap(marketer: Marketer, analysis: MusicAnalysis | None) -> tuple[float, str | None]:
    if not analysis or not analysis.audience_profile:
        return 0.0, None
    audience_tags = {_normalize_tag(t) for t in (analysis.audience_profile.get("tags") or [])}
    marketer_tokens = _tokenize(marketer.bio or "")
    marketer_tokens |= {_normalize_tag(g) for g in (marketer.genres or [])}
    overlap = audience_tags & marketer_tokens
    if overlap:
        sample = next(iter(overlap)).replace("-", " ")
        return min(0.5 + len(overlap) * 0.1, 1.0), f"Audience overlap ({sample})"
    return 0.0, None


def _lyrical_theme_overlap(marketer: Marketer, analysis: MusicAnalysis | None) -> tuple[float, str | None]:
    if not analysis or not analysis.lyrical_analysis:
        return 0.0, None
    themes = {_normalize_tag(t) for t in (analysis.lyrical_analysis.get("themes") or [])}
    bio_tokens = _tokenize(marketer.bio or "")
    evidence_tokens = _tokenize(marketer.evidence_summary or "")
    pool = bio_tokens | evidence_tokens
    hits = [theme for theme in themes if any(tok in theme or theme in tok for tok in pool)]
    if hits:
        return min(0.4 + len(hits) * 0.15, 1.0), f"Lyrical theme fit ({hits[0].replace('-', ' ')})"
    return 0.0, None


def _channel_fit(marketer: Marketer, analysis: MusicAnalysis | None, recommended_services: set[str]) -> tuple[float, str | None]:
    offered = set(marketer.services or [])
    if recommended_services and offered & recommended_services:
        return 1.0, "Recommended channel specialist"
    if not analysis or not analysis.audience_profile:
        return 0.0, None
    channels = analysis.audience_profile.get("primary_channels") or []
    mapped: set[str] = set()
    for channel in channels:
        mapped.update(CHANNEL_SERVICE_MAP.get(channel, []))
    if mapped and offered & mapped:
        return 0.85, "Platform channel alignment"
    return 0.0, None


def _normalize_tag(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")


def _score(marketer, brief, *, analysis=None, priority_services=None, recommended_services=None):
    w = _weights()
    reasons = []
    score = 0.0
    priority_services = priority_services or set()
    recommended_services = recommended_services or set()

    if set(marketer.genres or []) & set(brief.genres or []):
        score += w["genre"]
        reasons.append("Genre fit")

    if _service_overlap(marketer, brief):
        score += w["service"]
        reasons.append("Service match")

    marketer_services = set(marketer.services or [])
    if priority_services and marketer_services & priority_services:
        score += 0.08
        reasons.append("Strategy priority match")
    elif recommended_services and marketer_services & recommended_services:
        score += 0.05
        reasons.append("Channel fit from analysis")

    goal_services = _expanded_goal_services(brief)
    if goal_services and set(marketer.services or []) & goal_services:
        score += w["goal"]
        reasons.append("Goal fit")

    if brief.budget_max and (marketer.price_min or marketer.price_max):
        floor = marketer.price_min or marketer.price_max or 0
        ceiling = marketer.price_max or marketer.price_min or floor
        if ceiling <= brief.budget_max:
            score += w["budget"]
            reasons.append("Fits budget")
        elif floor <= brief.budget_max * 1.15:
            score += w["budget"] * 0.5
            reasons.append("Near budget")

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

    audience_ratio, audience_reason = _audience_tag_overlap(marketer, analysis)
    if audience_ratio:
        score += w["audience_fit"] * audience_ratio
        if audience_reason:
            reasons.append(audience_reason)

    channel_ratio, channel_reason = _channel_fit(marketer, analysis, recommended_services)
    if channel_ratio:
        score += w["channel_fit"] * channel_ratio
        if channel_reason:
            reasons.append(channel_reason)

    lyrical_ratio, lyrical_reason = _lyrical_theme_overlap(marketer, analysis)
    if lyrical_ratio:
        score += w["lyrical_themes"] * lyrical_ratio
        if lyrical_reason:
            reasons.append(lyrical_reason)

    hire_count = MatchFeedback.query.filter_by(marketer_id=marketer.id, hired=True).count()
    if hire_count:
        score += min(0.04, hire_count * 0.01)
        reasons.append("Past hire feedback")

    avg_rating = (
        db.session.query(db.func.avg(MatchFeedback.rating))
        .filter(MatchFeedback.marketer_id == marketer.id, MatchFeedback.rating.isnot(None))
        .scalar()
    )
    if avg_rating and avg_rating >= 4:
        score += 0.04
        reasons.append("Strong artist ratings")

    preferred = (getattr(brief, "preferred_provider_type", None) or "either").strip().lower()
    marketer_type = (marketer.provider_type or "agency").strip().lower()
    if preferred in ("solo", "agency") and marketer_type == preferred:
        score += 0.07
        # Surface early so it is not truncated from top_reasons[:5]
        reasons.insert(0, f"Preferred {preferred} marketer")

    return min(score, 1.0), reasons
