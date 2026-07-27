"""Music analysis pipeline — brief-first synthesis with optional external data."""
from __future__ import annotations

from statistics import mean

from app import db
from app.models import CampaignBrief, MusicAnalysis
from app.services.lastfm_client import (
    fetch_artist_profile as lastfm_profile,
    fetch_top_tracks as lastfm_top_tracks,
    lastfm_configured,
    search_artist as lastfm_search,
    _averages_from_tags,
)
from app.services.lyrical_analysis import build_lyrical_essence, merge_lyrical_into_audience
from app.services.spotify_client import (
    SpotifyAPIError,
    analyze_artist,
    resolve_artist_id,
    spotify_configured,
)

def _avg_features(features_by_track: dict[str, dict]) -> dict:
    if not features_by_track:
        return {}
    keys = ("danceability", "energy", "valence", "tempo", "acousticness", "instrumentalness", "speechiness")
    out = {}
    for key in keys:
        vals = [f[key] for f in features_by_track.values() if f.get(key) is not None]
        if vals:
            out[key] = round(mean(vals), 3)
    return out


def _mood_label(energy: float, valence: float) -> str:
    if energy >= 0.65 and valence >= 0.55:
        return "uplifting and high-energy"
    if energy >= 0.65 and valence < 0.45:
        return "intense and driven"
    if energy < 0.45 and valence >= 0.55:
        return "warm and reflective"
    if energy < 0.45 and valence < 0.45:
        return "moody and introspective"
    return "balanced and versatile"


def _infer_audience(profile: dict, averages: dict, brief: CampaignBrief) -> dict:
    energy = averages.get("energy", 0.5)
    valence = averages.get("valence", 0.5)
    dance = averages.get("danceability", 0.5)
    speech = averages.get("speechiness", 0.2)
    tags = []
    channels = []

    if dance >= 0.65:
        tags.extend(["dancefloor", "playlist-curators", "tiktok-native"])
        channels.append("tiktok")
    if speech >= 0.35:
        tags.extend(["lyric-forward", "storytelling", "hip-hop-rap"])
        channels.append("press")
    if energy >= 0.6:
        tags.append("high-energy-listeners")
    if valence >= 0.6:
        tags.append("feel-good")
    if brief.maturity_tier == "early":
        tags.append("emerging-listeners")
    elif brief.maturity_tier == "advanced":
        tags.append("established-fanbase")

    spotify_genres = profile.get("genres") or []
    channels = list(dict.fromkeys(channels + _platform_channels(brief)))
    return {
        "tags": list(dict.fromkeys(tags + spotify_genres[:6] + (brief.genres or [])[:4])),
        "primary_channels": channels or ["playlist", "social"],
        "mood": _mood_label(energy, valence),
        "maturity_tier": brief.maturity_tier,
        "listener_scale": _primary_listener_scale(brief, profile),
    }


def _primary_listener_scale(brief: CampaignBrief, profile: dict) -> int:
    scales = [
        brief.spotify_monthly_listeners or 0,
        brief.tiktok_followers or 0,
        brief.ig_followers or 0,
        (brief.yt_subscribers or 0) * 10,
        profile.get("followers") or 0,
    ]
    return max(scales)


def _platform_channels(brief: CampaignBrief) -> list[str]:
    """Bias discovery channels toward where the artist already has traction."""
    channels: list[str] = []
    stats = {
        "spotify": brief.spotify_monthly_listeners or 0,
        "tiktok": brief.tiktok_followers or 0,
        "instagram": brief.ig_followers or 0,
        "youtube": (brief.yt_subscribers or 0) * 10,
    }
    ranked = sorted(stats.items(), key=lambda item: -item[1])
    for platform, value in ranked:
        if value <= 0:
            continue
        if platform == "spotify":
            channels.extend(["playlist", "streaming"])
        elif platform == "tiktok":
            channels.append("tiktok")
        elif platform == "instagram":
            channels.append("social")
        elif platform == "youtube":
            channels.append("video")
    return list(dict.fromkeys(channels + ["playlist", "social"]))


def _apply_lyrical_enrichment(brief: CampaignBrief, analysis: MusicAnalysis) -> None:
    from app.services.genius_client import enrich_tracks_with_genius, genius_configured

    tracks = analysis.top_tracks or []
    if genius_configured():
        tracks = enrich_tracks_with_genius(tracks, brief.artist_name or "")
        analysis.top_tracks = tracks
    lyrical = build_lyrical_essence(brief, tracks)
    if genius_configured() and any(t.get("genius") for t in tracks):
        lyrical["genius_refs"] = [
            {"title": t.get("name"), "url": (t.get("genius") or {}).get("url")}
            for t in tracks
            if t.get("genius")
        ]
        lyrical["note"] = (
            "Themes inferred from brief + track titles; Genius links attached for lyrical review. "
            "Set ANALYSIS_LLM_* for deeper synthesis."
        )
        lyrical["source"] = "brief_heuristic+genius" if lyrical.get("source") != "llm" else lyrical["source"]
    analysis.lyrical_analysis = lyrical
    analysis.audience_profile = merge_lyrical_into_audience(analysis.audience_profile or {}, lyrical)
    voice = lyrical.get("narrative_voice", "distinct")
    themes = ", ".join((lyrical.get("themes") or [])[:3])
    if themes and analysis.sonic_summary:
        analysis.sonic_summary += f" Lyrical positioning leans {voice} around {themes}."


def _sonic_summary_text(artist_name: str, profile: dict, averages: dict, audience: dict) -> str:
    genres = ", ".join((profile.get("genres") or [])[:4]) or ", ".join(audience.get("tags", [])[:3]) or "eclectic"
    mood = audience.get("mood", "distinct")
    energy = averages.get("energy")
    tempo = averages.get("tempo")
    parts = [
        f"{artist_name} reads as {mood} with a {genres} lean.",
    ]
    if energy is not None:
        parts.append(f"Average energy sits around {int(energy * 100)}%.")
    if tempo:
        parts.append(f"Typical tempo lands near {int(tempo)} BPM.")
    parts.append("The sound appeals most to listeners who discover music through curated playlists and genre-specific communities.")
    return " ".join(parts)


def _heuristic_analysis(brief: CampaignBrief) -> MusicAnalysis:
    """Fallback when Spotify API is unavailable."""
    profile = {
        "name": brief.artist_name,
        "genres": brief.genres or [],
        "followers": brief.spotify_monthly_listeners,
        "source": "brief_heuristic",
    }
    tracks = [{"name": f"{brief.artist_name} — top track (estimated)", "popularity": 40}]
    averages = {"energy": 0.55, "valence": 0.5, "danceability": 0.5, "tempo": 110.0, "speechiness": 0.08}
    audience = _infer_audience(profile, averages, brief)
    summary = (
        f"{brief.artist_name} shows a {audience['mood']} profile across {', '.join(brief.genres or ['their'])} influences. "
        "Analysis is based on your campaign brief and stated audience stats."
    )
    analysis = MusicAnalysis(
        brief_id=brief.id,
        spotify_profile=profile,
        top_tracks=tracks,
        audio_features={"averages": averages, "tracks": {}, "source": "brief_heuristic"},
        sonic_summary=summary,
        audience_profile=audience,
    )
    _apply_lyrical_enrichment(brief, analysis)
    return analysis


def _lastfm_analysis(brief: CampaignBrief) -> MusicAnalysis:
    """Free Last.fm path — real tags, listeners, and top tracks without Spotify Web API."""
    search = lastfm_search(brief.artist_name) or {}
    artist_key = search.get("name") or brief.artist_name
    profile = lastfm_profile(artist_key)
    tracks = lastfm_top_tracks(artist_key)
    tags = profile.get("genres") or []
    averages = _averages_from_tags(tags + (brief.genres or []))

    if tags and not brief.genres:
        from app.constants.marketer_taxonomy import normalize_genre_list

        brief.genres = normalize_genre_list(tags[:5])

    profile["followers"] = profile.get("listeners")
    audience = _infer_audience(profile, averages, brief)
    summary = _sonic_summary_text(brief.artist_name, profile, averages, audience)
    summary += " Listener data sourced from Last.fm."

    analysis = MusicAnalysis(
        brief_id=brief.id,
        spotify_profile=profile,
        top_tracks=tracks,
        audio_features={"averages": averages, "tracks": {}, "source": "lastfm_tags"},
        sonic_summary=summary,
        audience_profile=audience,
    )
    _apply_lyrical_enrichment(brief, analysis)
    return analysis


def run_analysis(brief_id: int) -> MusicAnalysis:
    brief = CampaignBrief.query.get_or_404(brief_id)
    brief.analysis_status = "running"
    brief.engine_stage = "analyzing"
    brief.analysis_error = None
    db.session.commit()

    analysis = MusicAnalysis.query.filter_by(brief_id=brief.id).first()
    if not analysis:
        analysis = MusicAnalysis(brief_id=brief.id)
        db.session.add(analysis)

    try:
        artist_id = resolve_artist_id(brief.spotify_artist_url or brief.spotify_artist_id or "")
        if artist_id:
            brief.spotify_artist_id = artist_id

        used_external = False
        if artist_id and spotify_configured():
            try:
                spotify = analyze_artist(artist_id)
                profile = spotify["profile"]
                tracks = spotify["tracks"]
                features = spotify["features"]
                averages = spotify["averages"] or _avg_features(features)

                if profile.get("genres") and not brief.genres:
                    from app.constants.marketer_taxonomy import normalize_genre_list

                    brief.genres = normalize_genre_list(profile["genres"][:5])

                # Prefer Spotify follower count when artist left monthly listeners blank
                if profile.get("followers") and not brief.spotify_monthly_listeners:
                    brief.spotify_monthly_listeners = int(profile["followers"])
                    brief.compute_maturity()

                audience = _infer_audience(profile, averages, brief)
                summary = _sonic_summary_text(brief.artist_name, profile, averages, audience)
                summary += " Profile data sourced from Spotify."
                if spotify["feature_source"] == "genre_estimate":
                    summary += " Sonic averages estimated from Spotify genres."

                analysis.spotify_profile = profile
                analysis.top_tracks = tracks
                analysis.audio_features = {
                    "averages": averages,
                    "tracks": features,
                    "source": spotify["feature_source"],
                    "track_source": spotify["track_source"],
                }
                analysis.audience_profile = audience
                analysis.sonic_summary = summary
                _apply_lyrical_enrichment(brief, analysis)
                if spotify["warnings"]:
                    brief.analysis_error = " ".join(spotify["warnings"])
                else:
                    brief.analysis_error = None
                used_external = True
            except SpotifyAPIError as exc:
                brief.analysis_error = f"Spotify lookup failed ({exc}) — trying fallback."

        if not used_external and lastfm_configured():
            try:
                lastfm = _lastfm_analysis(brief)
                analysis.spotify_profile = lastfm.spotify_profile
                analysis.top_tracks = lastfm.top_tracks
                analysis.audio_features = lastfm.audio_features
                analysis.lyrical_analysis = lastfm.lyrical_analysis
                analysis.audience_profile = lastfm.audience_profile
                analysis.sonic_summary = lastfm.sonic_summary
                if not brief.analysis_error:
                    brief.analysis_error = None
                used_external = True
            except Exception as exc:
                brief.analysis_error = (
                    (brief.analysis_error + " ") if brief.analysis_error else ""
                ) + f"Last.fm lookup failed ({exc}) — using estimated profile."

        if not used_external:
            if not artist_id:
                brief.analysis_error = "Could not parse Spotify artist URL — using estimated profile."
            elif not spotify_configured():
                brief.analysis_error = (
                    "Spotify credentials not configured — using estimated profile. "
                    "Add SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET to .env."
                )
            heuristic = _heuristic_analysis(brief)
            analysis.spotify_profile = heuristic.spotify_profile
            analysis.top_tracks = heuristic.top_tracks
            analysis.audio_features = heuristic.audio_features
            analysis.lyrical_analysis = heuristic.lyrical_analysis
            analysis.audience_profile = heuristic.audience_profile
            analysis.sonic_summary = heuristic.sonic_summary

        brief.analysis_status = "complete"
        brief.engine_stage = "analysis"
        db.session.commit()
        return analysis
    except Exception as exc:
        brief.analysis_status = "failed"
        brief.analysis_error = str(exc)[:500]
        db.session.commit()
        raise
