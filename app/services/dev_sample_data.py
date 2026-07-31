"""Developer sample data for the campaign builder intake form."""
from __future__ import annotations

import os

SAMPLE_PRESETS: dict[str, dict] = {
    "indie_tiktok": {
        "label": "Indie · TikTok-first",
        "artist_name": "Luna Ridge",
        "email": "luna.ridge@example.com",
        "spotify_artist_url": "https://open.spotify.com/artist/3TVXtAsR1Inumwj472S9r4",
        "genres": ["indie", "indie-pop"],
        "goals": "grow on tiktok, playlist adds, build fanbase",
        "services_needed": ["social_media_strategy", "playlist_pitching"],
        "budget_min": 200,
        "budget_max": 800,
        "spotify_monthly_listeners": 1200,
        "tiktok_followers": 18500,
        "ig_followers": 4200,
        "yt_subscribers": 350,
        "timeline": "1_month",
        "past_marketing_exp": "diy",
        "preferred_provider_type": "solo",
    },
    "hiphop_streams": {
        "label": "Hip-hop · Streams push",
        "artist_name": "Kairo Nova",
        "email": "kairo@example.com",
        "spotify_artist_url": "https://open.spotify.com/artist/3TVXtAsR1Inumwj472S9r4",
        "genres": ["hip-hop", "r&b"],
        "goals": "streams, playlist placement, press",
        "services_needed": ["playlist_pitching", "pr", "ads"],
        "budget_min": 500,
        "budget_max": 2500,
        "spotify_monthly_listeners": 8200,
        "tiktok_followers": 2400,
        "ig_followers": 6100,
        "yt_subscribers": 900,
        "timeline": "asap",
        "past_marketing_exp": "hired_before",
        "preferred_provider_type": "either",
    },
    "pop_release": {
        "label": "Pop · Release campaign",
        "artist_name": "Mira Sol",
        "email": "mira@example.com",
        "spotify_artist_url": "https://open.spotify.com/artist/3TVXtAsR1Inumwj472S9r4",
        "genres": ["pop", "electronic"],
        "goals": "release launch, brand building, followers",
        "services_needed": ["release_campaigns", "social_media_strategy", "identity_positioning"],
        "budget_min": 1000,
        "budget_max": 5000,
        "spotify_monthly_listeners": 22000,
        "tiktok_followers": 45000,
        "ig_followers": 18000,
        "yt_subscribers": 3200,
        "timeline": "3_months",
        "past_marketing_exp": "agency",
        "preferred_provider_type": "agency",
    },
}

DEFAULT_PRESET = "indie_tiktok"


def dev_tools_enabled() -> bool:
    raw = os.environ.get("DEV_SAMPLE_DATA", "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    return os.environ.get("FLASK_ENV", "").strip().lower() == "development"
