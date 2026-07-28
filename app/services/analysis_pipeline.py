"""Music analysis pipeline — prefer measured data; never present guesses as measurements."""
from __future__ import annotations

from statistics import mean

from app import db
from app.models import CampaignBrief, MusicAnalysis
from app.services.lastfm_client import (
    fetch_artist_profile as lastfm_profile,
    fetch_top_tracks as lastfm_top_tracks,
    lastfm_configured,
    search_artist as lastfm_search,
)
from app.services.lyrical_analysis import build_lyrical_essence, merge_lyrical_into_audience
from app.services.spotify_client import (
    SpotifyAPIError,
    analyze_artist,
    resolve_artist_id,
    spotify_configured,
)

REAL_AUDIO_SOURCES = frozenset({"spotify"})


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


def _mood_from_real_audio(averages: dict) -> str | None:
    """Mood only when energy/valence came from real audio-features."""
    if "energy" not in averages or "valence" not in averages:
        return None
    energy = averages["energy"]
    valence = averages["valence"]
    if energy >= 0.65 and valence >= 0.55:
        return "uplifting and high-energy"
    if energy >= 0.65 and valence < 0.45:
        return "intense and driven"
    if energy < 0.45 and valence >= 0.55:
        return "warm and reflective"
    if energy < 0.45 and valence < 0.45:
        return "moody and introspective"
    return "balanced"


def _platform_channels(brief: CampaignBrief) -> list[str]:
    """Channels backed by stated follower counts only (no invented defaults)."""
    channels: list[str] = []
    stats = {
        "streaming": brief.spotify_monthly_listeners or 0,
        "tiktok": brief.tiktok_followers or 0,
        "social": brief.ig_followers or 0,
        "video": brief.yt_subscribers or 0,
    }
    for channel, value in sorted(stats.items(), key=lambda item: -item[1]):
        if value > 0:
            if channel == "streaming":
                channels.extend(["playlist", "streaming"])
            else:
                channels.append(channel)
    return list(dict.fromkeys(channels))


def _maturity_tag(brief: CampaignBrief) -> str | None:
    if brief.maturity_tier == "early":
        return "early-stage (from stated reach)"
    if brief.maturity_tier == "mid":
        return "mid-stage (from stated reach)"
    if brief.maturity_tier == "advanced":
        return "established reach (from stated stats)"
    return None


def _build_audience(profile: dict, averages: dict, brief: CampaignBrief, *, audio_source: str) -> dict:
    tags: list[str] = []
    for g in (brief.genres or [])[:6]:
        tags.append(g)
    for g in (profile.get("genres") or [])[:6]:
        if g not in tags:
            tags.append(g)

    maturity = _maturity_tag(brief)
    if maturity:
        tags.append(maturity)

    # Real-audio-only tags
    if audio_source in REAL_AUDIO_SOURCES:
        if averages.get("danceability", 0) >= 0.65:
            tags.append("high-danceability (measured)")
        if averages.get("energy", 0) >= 0.6:
            tags.append("high-energy (measured)")
        if averages.get("speechiness", 0) >= 0.35:
            tags.append("speech-forward (measured)")
        if averages.get("valence", 0) >= 0.6:
            tags.append("high-valence (measured)")

    channels = _platform_channels(brief)
    for goal in brief.goals or []:
        token = str(goal).lower()
        if "playlist" in token or "stream" in token:
            channels.append("playlist")
        if "tiktok" in token or "social" in token:
            channels.append("tiktok")
        if "press" in token or "pr" in token:
            channels.append("press")

    mood = _mood_from_real_audio(averages) if audio_source in REAL_AUDIO_SOURCES else None

    return {
        "tags": list(dict.fromkeys(tags))[:16],
        "primary_channels": list(dict.fromkeys(channels)),
        "mood": mood,
        "maturity_tier": brief.maturity_tier,
        "listener_scale": _primary_listener_scale(brief, profile),
        "evidence": {
            "genres": list(brief.genres or []) or list(profile.get("genres") or [])[:6],
            "platform_stats": {
                "spotify_monthly_listeners": brief.spotify_monthly_listeners or 0,
                "tiktok_followers": brief.tiktok_followers or 0,
                "ig_followers": brief.ig_followers or 0,
                "yt_subscribers": brief.yt_subscribers or 0,
                "spotify_followers": profile.get("followers"),
            },
            "audio_source": audio_source,
        },
    }


def _primary_listener_scale(brief: CampaignBrief, profile: dict) -> int:
    scales = [
        brief.spotify_monthly_listeners or 0,
        brief.tiktok_followers or 0,
        brief.ig_followers or 0,
        brief.yt_subscribers or 0,
        profile.get("followers") or 0,
    ]
    return max(scales)


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
            (lyrical.get("note") or "")
            + " Genius links are real search hits for review — not lyric text analysis."
        ).strip()
    analysis.lyrical_analysis = lyrical
    analysis.audience_profile = merge_lyrical_into_audience(analysis.audience_profile or {}, lyrical)


def _sonic_summary(
    artist_name: str,
    profile: dict,
    averages: dict,
    audience: dict,
    *,
    audio_source: str,
    track_count: int,
) -> str:
    genres = ", ".join((profile.get("genres") or [])[:4]) or ", ".join(brief_genres(audience)) or "unspecified genres"
    parts = [f"{artist_name}: {genres}."]

    followers = profile.get("followers")
    if followers:
        parts.append(f"Spotify lists about {followers:,} followers.")
    popularity = profile.get("popularity")
    if popularity is not None:
        parts.append(f"Spotify popularity score {popularity}/100.")

    if audio_source in REAL_AUDIO_SOURCES and averages:
        mood = audience.get("mood")
        if mood:
            parts.append(f"Measured audio mood: {mood}.")
        if averages.get("energy") is not None:
            parts.append(f"Measured average energy {int(averages['energy'] * 100)}%.")
        if averages.get("tempo"):
            parts.append(f"Measured typical tempo ~{int(averages['tempo'])} BPM.")
    else:
        parts.append("Measured audio features are unavailable for this Spotify app, so no energy/tempo percentages are claimed.")

    if track_count:
        parts.append(f"{track_count} track title(s) loaded for title-word cues.")
    else:
        parts.append("No verified track list loaded yet.")

    channels = audience.get("primary_channels") or []
    if channels:
        parts.append(f"Reach so far is strongest toward: {', '.join(channels)} (from stats you entered).")

    return " ".join(parts)


def brief_genres(audience: dict) -> list[str]:
    evidence = audience.get("evidence") or {}
    return list(evidence.get("genres") or [])


def _heuristic_analysis(brief: CampaignBrief) -> MusicAnalysis:
    """Brief-only path: no invented tracks or fake audio percentages."""
    profile = {
        "name": brief.artist_name,
        "genres": brief.genres or [],
        "followers": brief.spotify_monthly_listeners or None,
        "source": "brief",
    }
    averages: dict = {}
    audience = _build_audience(profile, averages, brief, audio_source="none")
    summary = _sonic_summary(
        brief.artist_name,
        profile,
        averages,
        audience,
        audio_source="none",
        track_count=0,
    )
    summary += " Analysis uses only your campaign brief until Spotify/Last.fm return data."
    analysis = MusicAnalysis(
        brief_id=brief.id,
        spotify_profile=profile,
        top_tracks=[],
        audio_features={"averages": {}, "tracks": {}, "source": "none"},
        sonic_summary=summary,
        audience_profile=audience,
    )
    _apply_lyrical_enrichment(brief, analysis)
    return analysis


def _lastfm_analysis(brief: CampaignBrief) -> MusicAnalysis:
    search = lastfm_search(brief.artist_name) or {}
    artist_key = search.get("name") or brief.artist_name
    profile = lastfm_profile(artist_key)
    tracks = lastfm_top_tracks(artist_key)
    tags = profile.get("genres") or []

    if tags and not brief.genres:
        from app.constants.marketer_taxonomy import normalize_genre_list

        brief.genres = normalize_genre_list(tags[:5])

    profile["followers"] = profile.get("listeners")
    averages: dict = {}  # Last.fm tag→audio mapping is not measured audio — do not invent %
    audience = _build_audience(profile, averages, brief, audio_source="none")
    summary = _sonic_summary(
        brief.artist_name,
        profile,
        averages,
        audience,
        audio_source="none",
        track_count=len(tracks),
    )
    summary += " Tags and track titles sourced from Last.fm (not measured Spotify audio features)."

    analysis = MusicAnalysis(
        brief_id=brief.id,
        spotify_profile=profile,
        top_tracks=tracks,
        audio_features={"averages": {}, "tracks": {}, "source": "none", "track_source": "lastfm"},
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
                feature_source = spotify["feature_source"]

                # Only treat real Spotify audio-features as measured
                if feature_source == "spotify" and features:
                    averages = _avg_features(features)
                    audio_source = "spotify"
                else:
                    averages = {}
                    audio_source = "none"
                    feature_source = "unavailable"

                if profile.get("genres") and not brief.genres:
                    from app.constants.marketer_taxonomy import normalize_genre_list

                    brief.genres = normalize_genre_list(profile["genres"][:5])

                if profile.get("followers") and not brief.spotify_monthly_listeners:
                    brief.spotify_monthly_listeners = int(profile["followers"])
                    brief.compute_maturity()

                audience = _build_audience(profile, averages, brief, audio_source=audio_source)
                summary = _sonic_summary(
                    brief.artist_name,
                    profile,
                    averages,
                    audience,
                    audio_source=audio_source,
                    track_count=len(tracks),
                )
                summary += " Profile data sourced from Spotify."

                analysis.spotify_profile = profile
                analysis.top_tracks = tracks
                analysis.audio_features = {
                    "averages": averages,
                    "tracks": features if audio_source == "spotify" else {},
                    "source": feature_source if audio_source == "spotify" else "unavailable",
                    "track_source": spotify["track_source"],
                }
                analysis.audience_profile = audience
                analysis.sonic_summary = summary
                _apply_lyrical_enrichment(brief, analysis)

                warnings = [w for w in (spotify.get("warnings") or []) if "estimated sonic" not in w.lower()]
                if audio_source != "spotify":
                    warnings.append(
                        "Spotify audio-features unavailable — energy/tempo % bars are hidden rather than estimated."
                    )
                brief.analysis_error = " ".join(warnings) if warnings else None
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
                used_external = True
            except Exception as exc:
                brief.analysis_error = (
                    (brief.analysis_error + " ") if brief.analysis_error else ""
                ) + f"Last.fm lookup failed ({exc}) — using brief-only profile."

        if not used_external:
            if not artist_id:
                brief.analysis_error = "Could not parse Spotify artist URL — using brief-only profile."
            elif not spotify_configured():
                brief.analysis_error = (
                    "Spotify credentials not configured — using brief-only profile. "
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
