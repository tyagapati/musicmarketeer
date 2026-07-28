"""Campaign signals grounded in stated brief data and real track titles.

Unbacked inventiveness (fake energy %, emotional arcs, genre stereotypes as
\"lyrical themes\") is intentionally avoided. Matching may still use soft
genre labels the artist selected themselves.
"""
from __future__ import annotations

import re

from app.models import CampaignBrief

# Only used when a *real* track title contains the word — not genre stereotypes.
TITLE_KEYWORDS = {
    "love": "romance",
    "night": "nocturnal",
    "dream": "escapism",
    "home": "belonging",
    "fire": "intensity",
    "heart": "emotion",
    "lost": "longing",
    "free": "liberation",
    "party": "celebration",
    "pain": "vulnerability",
    "god": "spirituality",
    "money": "ambition",
    "city": "urban",
}


def _themes_from_titles(tracks: list[dict]) -> list[str]:
    themes: list[str] = []
    for track in tracks or []:
        name = track.get("name") or ""
        # Skip placeholder heuristic tracks
        if "estimated" in name.lower() or "—" in name and "top track" in name.lower():
            continue
        title = name.lower()
        for keyword, theme in TITLE_KEYWORDS.items():
            if re.search(rf"\b{re.escape(keyword)}\b", title):
                themes.append(theme)
    return list(dict.fromkeys(themes))[:6]


def _platform_signals(brief: CampaignBrief) -> list[str]:
    """Signals from stated follower counts (artist-provided facts)."""
    signals: list[str] = []
    spotify = brief.spotify_monthly_listeners or 0
    tiktok = brief.tiktok_followers or 0
    ig = brief.ig_followers or 0
    yt = brief.yt_subscribers or 0

    ranked = sorted(
        [("spotify", spotify), ("tiktok", tiktok), ("instagram", ig), ("youtube", yt)],
        key=lambda item: -item[1],
    )
    top_platform, top_value = ranked[0]
    if top_value > 0:
        signals.append(f"strongest-on-{top_platform}")
    if tiktok > 0 and tiktok >= spotify and tiktok >= ig:
        signals.append("short-form-led")
    if yt >= 1000 and yt * 10 >= max(spotify, tiktok, ig):
        signals.append("video-led")
    if spotify > 0 and spotify >= max(tiktok, ig, yt * 10):
        signals.append("streaming-led")
    return signals


def _goal_priorities(brief: CampaignBrief) -> list[str]:
    """Normalize stated goals into marketing priorities (not lyrical claims)."""
    out: list[str] = []
    for goal in brief.goals or []:
        token = str(goal).strip().lower()
        if not token:
            continue
        if any(k in token for k in ("tiktok", "viral", "short")):
            out.append("short-form growth")
        elif any(k in token for k in ("playlist", "stream")):
            out.append("streaming / playlists")
        elif any(k in token for k in ("press", "pr", "story")):
            out.append("press / narrative")
        elif any(k in token for k in ("release", "launch")):
            out.append("release push")
        elif any(k in token for k in ("brand", "identity")):
            out.append("brand / identity")
        elif any(k in token for k in ("follow", "fan", "growth")):
            out.append("audience growth")
        else:
            out.append(token)
    return list(dict.fromkeys(out))[:6]


def _cultural_signals(brief: CampaignBrief) -> list[str]:
    signals: list[str] = []
    langs = [lang.lower() for lang in (brief.languages or []) if lang]
    if len(langs) > 1 or (langs and set(langs) != {"en"}):
        signals.append("non-English or multilingual brief")
    for genre in brief.genres or []:
        g = genre.lower()
        if g in ("latin", "latin-pop", "afrobeats", "reggaeton"):
            signals.append(f"selected genre: {genre}")
    return list(dict.fromkeys(signals))[:5]


def build_lyrical_essence(brief: CampaignBrief, tracks: list[dict] | None = None) -> dict:
    """Build evidence-backed campaign cues — not invented lyrical analysis.

    Returns only:
    - title_themes: words found in real track titles
    - goal_priorities: restated from artist goals
    - platform_signals: from stated stats
    - cultural_signals: from languages / selected genres
    - genius_refs: attached separately by pipeline when configured
    """
    tracks = tracks or []
    real_tracks = [
        t
        for t in tracks
        if t.get("name")
        and "estimated" not in (t.get("name") or "").lower()
        and "top track (estimated)" not in (t.get("name") or "").lower()
    ]
    title_themes = _themes_from_titles(real_tracks)
    goals = _goal_priorities(brief)
    platforms = _platform_signals(brief)
    cultural = _cultural_signals(brief)

    notes = []
    if title_themes:
        notes.append("Title themes come from words in real track titles.")
    else:
        notes.append("No title-derived themes yet (need real track names from Spotify/Last.fm).")
    if goals:
        notes.append("Priorities restated from your stated goals.")
    if platforms:
        notes.append("Platform signals use the follower counts you entered.")

    return {
        # Keep `themes` as title themes only for matching compatibility
        "themes": title_themes,
        "title_themes": title_themes,
        "goal_priorities": goals,
        "platform_signals": platforms,
        "cultural_signals": cultural,
        # Explicitly removed: narrative_voice, emotional_arc, hook_patterns
        "source": "evidence",
        "note": " ".join(notes),
    }


def merge_lyrical_into_audience(audience: dict, lyrical: dict) -> dict:
    """Attach evidence tags only — no invented voice/arc labels."""
    merged = dict(audience or {})
    tags = list(merged.get("tags") or [])
    for theme in lyrical.get("title_themes") or lyrical.get("themes") or []:
        tags.append(f"title:{theme}")
    for sig in lyrical.get("platform_signals") or []:
        tags.append(sig)
    for sig in lyrical.get("cultural_signals") or []:
        tags.append(sig.replace(" ", "-"))
    for goal in lyrical.get("goal_priorities") or []:
        tags.append(f"goal:{goal.replace(' ', '-')}")
    merged["tags"] = list(dict.fromkeys(tags))[:20]
    merged["title_themes"] = lyrical.get("title_themes") or []
    merged["goal_priorities"] = lyrical.get("goal_priorities") or []
    merged["platform_signals"] = lyrical.get("platform_signals") or []
    merged["cultural_signals"] = lyrical.get("cultural_signals") or []
    return merged
