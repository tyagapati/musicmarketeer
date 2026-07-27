"""Lyrical essence from campaign brief and track metadata — no external lyrics API required."""
from __future__ import annotations

import json
import os
import re

import requests

from app.models import CampaignBrief

GENRE_THEMES = {
    "indie": ["introspection", "authenticity", "DIY spirit"],
    "pop": ["hooks", "relatability", "mainstream appeal"],
    "hip-hop": ["storytelling", "rhythm", "cultural commentary"],
    "rap": ["wordplay", "confidence", "street narrative"],
    "r&b": ["intimacy", "sensuality", "vocal expression"],
    "rock": ["rebellion", "raw energy", "anthemic"],
    "electronic": ["atmosphere", "movement", "nightlife"],
    "edm": ["euphoria", "drops", "festival energy"],
    "folk": ["storytelling", "acoustic warmth", "tradition"],
    "country": ["narrative", "heartland", "personal history"],
    "metal": ["intensity", "catharsis", "technical prowess"],
    "jazz": ["improvisation", "sophistication", "mood"],
    "latin": ["rhythm", "celebration", "cultural pride"],
    "afrobeats": ["dance", "joy", "global crossover"],
    "soul": ["emotion", "vocal power", "legacy"],
}

GOAL_VOICE = {
    "streams": "aspirational",
    "playlist": "aspirational",
    "tiktok": "playful",
    "social": "playful",
    "press": "confessional",
    "pr": "confessional",
    "release": "celebratory",
    "brand": "aspirational",
    "growth": "aspirational",
    "fanbase": "confessional",
}

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
    "city": "urban life",
}


def _tokenize(text: str) -> set[str]:
    return {t.lower() for t in re.findall(r"[a-zA-Z']+", text or "") if len(t) > 2}


def _themes_from_genres(genres: list[str]) -> list[str]:
    themes: list[str] = []
    for genre in genres or []:
        key = genre.lower().replace(" ", "-").replace("&", "")
        for tag, mapped in GENRE_THEMES.items():
            if tag in key or key in tag:
                themes.extend(mapped)
    return list(dict.fromkeys(themes))[:8]


def _themes_from_goals(goals: list[str]) -> list[str]:
    themes: list[str] = []
    for goal in goals or []:
        token = str(goal).lower()
        if "tiktok" in token or "viral" in token:
            themes.append("shareable hooks")
        if "playlist" in token or "stream" in token:
            themes.append("playlist-friendly")
        if "press" in token or "story" in token:
            themes.append("narrative depth")
        if "release" in token or "launch" in token:
            themes.append("campaign momentum")
    return list(dict.fromkeys(themes))[:6]


def _themes_from_titles(tracks: list[dict]) -> list[str]:
    themes: list[str] = []
    for track in tracks or []:
        title = (track.get("name") or "").lower()
        for keyword, theme in TITLE_KEYWORDS.items():
            if keyword in title:
                themes.append(theme)
    return list(dict.fromkeys(themes))[:6]


def _narrative_voice(brief: CampaignBrief, themes: list[str]) -> str:
    for goal in brief.goals or []:
        token = str(goal).lower()
        for key, voice in GOAL_VOICE.items():
            if key in token:
                return voice
    if "party" in themes or "celebration" in themes:
        return "celebratory"
    if "introspection" in themes or "vulnerability" in themes:
        return "confessional"
    if "rebellion" in themes or "intensity" in themes:
        return "defiant"
    return "aspirational"


def _cultural_signals(brief: CampaignBrief, themes: list[str]) -> list[str]:
    signals: list[str] = []
    langs = [lang.lower() for lang in (brief.languages or [])]
    if len(langs) > 1 or (langs and langs != ["en"]):
        signals.append("multilingual audience")
    for genre in brief.genres or []:
        g = genre.lower()
        if g in ("latin", "afrobeats", "k-pop", "reggaeton"):
            signals.append(f"{genre} cultural lane")
    if brief.tiktok_followers and brief.tiktok_followers > brief.spotify_monthly_listeners:
        signals.append("short-form native")
    if brief.yt_subscribers and brief.yt_subscribers > 1000:
        signals.append("video-first fandom")
    if "urban life" in themes:
        signals.append("city culture")
    return list(dict.fromkeys(signals))[:5]


def _llm_configured() -> bool:
    return bool(os.environ.get("ANALYSIS_LLM_API_URL", "").strip() and os.environ.get("ANALYSIS_LLM_API_KEY", "").strip())


def _llm_enrich(brief: CampaignBrief, tracks: list[dict], base: dict) -> dict | None:
    if not _llm_configured():
        return None
    track_names = ", ".join((t.get("name") or "") for t in (tracks or [])[:5])
    prompt = (
        f"Artist: {brief.artist_name}\n"
        f"Genres: {', '.join(brief.genres or [])}\n"
        f"Goals: {', '.join(brief.goals or [])}\n"
        f"Top tracks: {track_names or 'unknown'}\n"
        f"Draft themes: {', '.join(base.get('themes') or [])}\n\n"
        "Return JSON with keys: themes (list of 4-6 strings), narrative_voice (one word), "
        "emotional_arc (short phrase), hook_patterns (list of 2-3 strings), cultural_signals (list)."
    )
    url = os.environ.get("ANALYSIS_LLM_API_URL", "").rstrip("/")
    model = os.environ.get("ANALYSIS_LLM_MODEL", "gpt-4o-mini")
    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {os.environ.get('ANALYSIS_LLM_API_KEY', '')}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "You analyze music marketing positioning. Reply with JSON only."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
            },
            timeout=30,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(content[start:end])
    except Exception:
        return None
    return None


def build_lyrical_essence(brief: CampaignBrief, tracks: list[dict] | None = None) -> dict:
    """Derive lyrical marketing essence from brief + track titles (no lyrics API)."""
    tracks = tracks or []
    themes = _themes_from_genres(brief.genres or [])
    themes.extend(_themes_from_goals(brief.goals or []))
    themes.extend(_themes_from_titles(tracks))
    themes = list(dict.fromkeys(themes))[:10]

    voice = _narrative_voice(brief, themes)
    cultural = _cultural_signals(brief, themes)

    result = {
        "themes": themes or ["versatile storytelling"],
        "narrative_voice": voice,
        "emotional_arc": _emotional_arc(voice, themes),
        "hook_patterns": _hook_patterns(brief, themes),
        "cultural_signals": cultural,
        "source": "brief_heuristic",
        "note": "Themes inferred from your genres, goals, and track titles. Add ANALYSIS_LLM_* env vars for deeper synthesis.",
    }

    llm = _llm_enrich(brief, tracks, result)
    if llm:
        for key in ("themes", "narrative_voice", "emotional_arc", "hook_patterns", "cultural_signals"):
            if llm.get(key):
                result[key] = llm[key]
        result["source"] = "llm"
        result["note"] = "Synthesized from your campaign brief and track context."

    return result


def _emotional_arc(voice: str, themes: list[str]) -> str:
    if voice == "confessional":
        return "vulnerability → connection → loyalty"
    if voice == "celebratory":
        return "energy → participation → repeat listens"
    if voice == "defiant":
        return "tension → release → identity"
    if "introspection" in themes:
        return "reflection → resonance → word-of-mouth"
    return "curiosity → engagement → fandom"


def _hook_patterns(brief: CampaignBrief, themes: list[str]) -> list[str]:
    patterns: list[str] = []
    if brief.tiktok_followers or any("tiktok" in str(g).lower() for g in brief.goals or []):
        patterns.append("short-form hook in first 8 seconds")
    if "hooks" in themes or "shareable hooks" in themes:
        patterns.append("memorable chorus or phrase")
    if "storytelling" in themes or "narrative depth" in themes:
        patterns.append("verse-led narrative payoff")
    if not patterns:
        patterns.append("sonic identity over lyric density")
    return patterns[:3]


def merge_lyrical_into_audience(audience: dict, lyrical: dict) -> dict:
    """Blend lyrical essence into audience profile for matching."""
    merged = dict(audience or {})
    tags = list(merged.get("tags") or [])
    for theme in lyrical.get("themes") or []:
        tags.append(theme.replace(" ", "-"))
    voice = lyrical.get("narrative_voice")
    if voice:
        tags.append(f"voice-{voice}")
    for signal in lyrical.get("cultural_signals") or []:
        tags.append(signal.replace(" ", "-"))
    merged["tags"] = list(dict.fromkeys(tags))[:16]
    merged["lyrical_themes"] = lyrical.get("themes") or []
    merged["narrative_voice"] = lyrical.get("narrative_voice")
    merged["cultural_signals"] = lyrical.get("cultural_signals") or []
    return merged
