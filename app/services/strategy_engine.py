"""Marketing strategy recommendations from music analysis."""
from __future__ import annotations

from app import db
from app.models import CampaignBrief, CampaignStrategy, MusicAnalysis

CHANNEL_DEFS = [
    {
        "service": "playlist_pitching",
        "title": "Playlist pitching",
        "signals": ("playlist", "playlist-curators", "feel-good", "emerging-listeners"),
    },
    {
        "service": "social_media_strategy",
        "title": "TikTok / social content",
        "signals": ("tiktok", "tiktok-native", "dancefloor", "high-energy-listeners"),
    },
    {
        "service": "ads",
        "title": "Paid social & streaming ads",
        "signals": ("high-energy-listeners", "established-fanbase", "dancefloor"),
    },
    {
        "service": "pr",
        "title": "Press & narrative PR",
        "signals": ("press", "lyric-forward", "storytelling", "introspection"),
    },
    {
        "service": "release_campaigns",
        "title": "Release campaign",
        "signals": ("emerging-listeners", "playlist", "celebration"),
    },
    {
        "service": "identity_positioning",
        "title": "Brand & positioning",
        "signals": ("personal storytelling", "introspection", "moody"),
    },
    {
        "service": "analytics",
        "title": "Audience analytics",
        "signals": ("established-fanbase", "emerging-listeners"),
    },
]


def _score_channel(defn: dict, audience: dict, averages: dict, brief: CampaignBrief) -> tuple[float, str]:
    tags = set(audience.get("tags") or [])
    channels = set(audience.get("primary_channels") or [])
    score = 0.0
    reasons = []
    for sig in defn["signals"]:
        if sig in tags or sig in channels:
            score += 0.22
            reasons.append(sig.replace("-", " "))
    if defn["service"] in (brief.services_needed or []):
        score += 0.35
        reasons.append("you requested this")
    energy = averages.get("energy", 0.5)
    if defn["service"] == "social_media_strategy" and energy >= 0.6:
        score += 0.15
        reasons.append("high energy sound")
    if defn["service"] == "playlist_pitching" and averages.get("danceability", 0) >= 0.55:
        score += 0.12
        reasons.append("playlist-friendly production")
    rationale = ", ".join(reasons[:3]) or "general fit for your campaign stage"
    return min(score, 1.0), rationale


def build_strategy(brief: CampaignBrief, analysis: MusicAnalysis) -> CampaignStrategy:
    audience = analysis.audience_profile or {}
    averages = (analysis.audio_features or {}).get("averages") or {}
    ranked = []
    for defn in CHANNEL_DEFS:
        score, rationale = _score_channel(defn, audience, averages, brief)
        ranked.append(
            {
                "service": defn["service"],
                "title": defn["title"],
                "score": round(score, 2),
                "rationale": rationale,
            }
        )
    ranked.sort(key=lambda x: -x["score"])

    mood = audience.get("mood", "distinct")
    insights = (
        f"Your music comes across as {mood}. "
        f"Listeners who respond to this sound often discover artists through "
        f"{ranked[0]['title'].lower()} and {ranked[1]['title'].lower()} before deeper fan conversion."
    )
    actions = [
        {"step": 1, "action": f"Prioritize {ranked[0]['title'].lower()}", "why": ranked[0]["rationale"]},
        {"step": 2, "action": f"Layer in {ranked[1]['title'].lower()}", "why": ranked[1]["rationale"]},
        {"step": 3, "action": "Connect with a marketer who has executed this playbook", "why": "human expertise accelerates fit"},
    ]

    strategy = CampaignStrategy.query.filter_by(brief_id=brief.id).first()
    if not strategy:
        strategy = CampaignStrategy(brief_id=brief.id)
        db.session.add(strategy)
    strategy.recommended_channels = ranked[:5]
    strategy.audience_insights = insights
    strategy.priority_actions = actions
    if not strategy.artist_priorities:
        strategy.artist_priorities = [r["service"] for r in ranked[:3]]
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
