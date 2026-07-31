"""Marketing strategy from stated goals, services, and platform reach — not fake audio."""
from __future__ import annotations

from app import db
from app.models import CampaignBrief, CampaignStrategy, MusicAnalysis

CHANNEL_DEFS = [
    {
        "service": "playlist_pitching",
        "title": "Playlist pitching",
        "goal_keys": ("playlist", "stream", "spotify"),
        "platforms": ("playlist", "streaming"),
    },
    {
        "service": "social_media_strategy",
        "title": "TikTok / social content",
        "goal_keys": ("tiktok", "social", "follow", "viral", "instagram"),
        "platforms": ("tiktok", "social"),
    },
    {
        "service": "ads",
        "title": "Paid social & streaming ads",
        "goal_keys": ("ads", "growth", "stream", "follow"),
        "platforms": ("tiktok", "social", "streaming", "video"),
    },
    {
        "service": "pr",
        "title": "Press & narrative PR",
        "goal_keys": ("press", "pr", "story", "publicity"),
        "platforms": ("press",),
    },
    {
        "service": "release_campaigns",
        "title": "Release campaign",
        "goal_keys": ("release", "launch"),
        "platforms": ("playlist", "streaming", "tiktok", "social", "video"),
    },
    {
        "service": "identity_positioning",
        "title": "Brand & positioning",
        "goal_keys": ("brand", "identity", "position"),
        "platforms": (),
    },
    {
        "service": "analytics",
        "title": "Audience analytics",
        "goal_keys": ("analytic", "data", "insight"),
        "platforms": (),
    },
]


def _goal_blob(brief: CampaignBrief) -> str:
    return " ".join(str(g).lower() for g in (brief.goals or []))


def _score_channel(defn: dict, audience: dict, brief: CampaignBrief) -> tuple[float, str]:
    score = 0.0
    reasons: list[str] = []
    channels = set(audience.get("primary_channels") or [])
    goals = _goal_blob(brief)

    if defn["service"] in (brief.services_needed or []):
        score += 0.5
        reasons.append("you selected this service")

    for key in defn["goal_keys"]:
        if key in goals:
            score += 0.25
            reasons.append(f"goal mentions {key}")
            break

    platform_hits = [p for p in defn["platforms"] if p in channels]
    if platform_hits:
        score += 0.25
        reasons.append(f"stated reach on {platform_hits[0]}")

    # Early artists often need identity + social; advanced often need ads — from maturity formula
    if brief.maturity_tier == "early" and defn["service"] in ("identity_positioning", "social_media_strategy"):
        score += 0.1
        reasons.append("early-stage reach")
    if brief.maturity_tier == "advanced" and defn["service"] in ("ads", "analytics"):
        score += 0.1
        reasons.append("larger stated reach")

    if not reasons:
        return 0.0, "no direct match to your stated goals, services, or platform stats"

    return min(score, 1.0), ", ".join(reasons[:3])


def build_strategy(brief: CampaignBrief, analysis: MusicAnalysis) -> CampaignStrategy:
    audience = analysis.audience_profile or {}
    ranked = []
    for defn in CHANNEL_DEFS:
        score, rationale = _score_channel(defn, audience, brief)
        ranked.append(
            {
                "service": defn["service"],
                "title": defn["title"],
                "score": round(score, 2),
                "rationale": rationale,
            }
        )
    ranked.sort(key=lambda x: (-x["score"], x["title"]))

    # Drop zero-evidence channels from the top list unless nothing scored
    evidenced = [r for r in ranked if r["score"] > 0]
    display = evidenced[:5] if evidenced else ranked[:3]

    goals = ", ".join(brief.goals or []) or "your stated goals"
    services = ", ".join(brief.services_needed or []) or "no services selected yet"
    platforms = ", ".join(audience.get("primary_channels") or []) or "no platform stats entered"
    insights = (
        f"Recommendations are ranked from what you told us — goals ({goals}), "
        f"services ({services}), and platform reach ({platforms}). "
        f"They are not based on invented audio or lyric analysis."
    )
    actions = []
    for i, row in enumerate(display[:3], start=1):
        actions.append({"step": i, "action": f"Prioritize {row['title'].lower()}", "why": row["rationale"]})
    if not actions:
        actions = [
            {
                "step": 1,
                "action": "Add goals or services on intake for sharper channel ranking",
                "why": "strategy needs stated intent",
            }
        ]

    strategy = CampaignStrategy.query.filter_by(brief_id=brief.id).first()
    if not strategy:
        strategy = CampaignStrategy(brief_id=brief.id)
        db.session.add(strategy)
    strategy.recommended_channels = display
    strategy.audience_insights = insights
    strategy.priority_actions = actions
    if not strategy.artist_priorities:
        strategy.artist_priorities = [r["service"] for r in display[:3]]
    return strategy


def run_strategy(brief_id: int) -> CampaignStrategy:
    brief = CampaignBrief.query.get_or_404(brief_id)
    analysis = MusicAnalysis.query.filter_by(brief_id=brief.id).first()
    if not analysis:
        from app.services.analysis_pipeline import run_analysis

        analysis = run_analysis(brief.id)
    strategy = build_strategy(brief, analysis)
    brief.engine_stage = "strategy"
    db.session.commit()
    return strategy
