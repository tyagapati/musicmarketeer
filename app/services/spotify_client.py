"""Spotify Web API client (client-credentials flow).

Works with current Spotify Developer Mode limits:
- Artist profile (genres, followers, popularity) — primary signal
- Top tracks / audio-features — attempted; many new apps get 403 (deprecated)
- Album/track fallback when top-tracks is blocked
"""
from __future__ import annotations

import os
import re
import time
from urllib.parse import urlparse

import requests

_TOKEN_CACHE: dict = {"token": None, "expires_at": 0.0}

ARTIST_URL_RE = re.compile(
    r"(?:https?://)?(?:open\.)?spotify\.com/artist/([a-zA-Z0-9]+)",
    re.IGNORECASE,
)

# Genre → approximate audio signature when /audio-features is blocked
_GENRE_FEATURE_HINTS = {
    "dance": {"energy": 0.78, "danceability": 0.82, "valence": 0.68, "tempo": 124.0, "speechiness": 0.08},
    "edm": {"energy": 0.85, "danceability": 0.8, "valence": 0.62, "tempo": 128.0, "speechiness": 0.06},
    "electronic": {"energy": 0.7, "danceability": 0.72, "valence": 0.55, "tempo": 120.0, "speechiness": 0.07},
    "hip hop": {"energy": 0.68, "danceability": 0.74, "valence": 0.48, "tempo": 95.0, "speechiness": 0.28},
    "rap": {"energy": 0.7, "danceability": 0.72, "valence": 0.45, "tempo": 92.0, "speechiness": 0.32},
    "r&b": {"energy": 0.52, "danceability": 0.66, "valence": 0.5, "tempo": 98.0, "speechiness": 0.12},
    "pop": {"energy": 0.65, "danceability": 0.7, "valence": 0.62, "tempo": 118.0, "speechiness": 0.08},
    "indie": {"energy": 0.55, "danceability": 0.52, "valence": 0.48, "tempo": 112.0, "speechiness": 0.06},
    "folk": {"energy": 0.4, "danceability": 0.42, "valence": 0.45, "tempo": 105.0, "speechiness": 0.05},
    "rock": {"energy": 0.75, "danceability": 0.5, "valence": 0.5, "tempo": 130.0, "speechiness": 0.05},
    "metal": {"energy": 0.9, "danceability": 0.4, "valence": 0.35, "tempo": 140.0, "speechiness": 0.06},
    "jazz": {"energy": 0.4, "danceability": 0.45, "valence": 0.5, "tempo": 110.0, "speechiness": 0.04},
    "latin": {"energy": 0.72, "danceability": 0.78, "valence": 0.7, "tempo": 105.0, "speechiness": 0.1},
    "country": {"energy": 0.55, "danceability": 0.55, "valence": 0.55, "tempo": 108.0, "speechiness": 0.05},
}


class SpotifyAPIError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def spotify_configured() -> bool:
    return bool(
        os.environ.get("SPOTIFY_CLIENT_ID", "").strip()
        and os.environ.get("SPOTIFY_CLIENT_SECRET", "").strip()
    )


def resolve_artist_id(url_or_id: str) -> str | None:
    raw = (url_or_id or "").strip()
    if not raw:
        return None
    if re.fullmatch(r"[a-zA-Z0-9]{22}", raw):
        return raw
    match = ARTIST_URL_RE.search(raw)
    if match:
        return match.group(1)
    parsed = urlparse(raw)
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) >= 2 and parts[0].lower() == "artist":
        candidate = parts[1].split("?")[0]
        if re.fullmatch(r"[a-zA-Z0-9]{22}", candidate):
            return candidate
    return None


def _get_token() -> str:
    if not spotify_configured():
        raise SpotifyAPIError("Spotify API credentials are not configured")
    now = time.time()
    if _TOKEN_CACHE["token"] and _TOKEN_CACHE["expires_at"] > now + 30:
        return _TOKEN_CACHE["token"]
    resp = requests.post(
        "https://accounts.spotify.com/api/token",
        data={"grant_type": "client_credentials"},
        auth=(os.environ["SPOTIFY_CLIENT_ID"].strip(), os.environ["SPOTIFY_CLIENT_SECRET"].strip()),
        timeout=15,
    )
    if resp.status_code >= 400:
        raise SpotifyAPIError(
            f"Spotify auth failed ({resp.status_code}): check SPOTIFY_CLIENT_ID / SECRET",
            status_code=resp.status_code,
        )
    payload = resp.json()
    _TOKEN_CACHE["token"] = payload["access_token"]
    _TOKEN_CACHE["expires_at"] = now + int(payload.get("expires_in", 3600))
    return _TOKEN_CACHE["token"]


def _api_get(path: str, *, params: dict | None = None, soft: bool = False) -> dict | None:
    token = _get_token()
    resp = requests.get(
        f"https://api.spotify.com/v1{path}",
        headers={"Authorization": f"Bearer {token}"},
        params=params or {},
        timeout=20,
    )
    if soft and resp.status_code in (403, 404):
        return None
    if resp.status_code >= 400:
        detail = ""
        try:
            detail = (resp.json().get("error") or {}).get("message") or ""
        except Exception:
            detail = (resp.text or "")[:200]
        raise SpotifyAPIError(
            f"Spotify {path} failed ({resp.status_code}){': ' + detail if detail else ''}",
            status_code=resp.status_code,
        )
    if not resp.content:
        return {}
    return resp.json()


def estimate_features_from_genres(genres: list[str]) -> dict:
    """Approximate audio averages from Spotify genre strings when audio-features is blocked."""
    matched: list[dict] = []
    for genre in genres or []:
        g = genre.lower()
        for key, feats in _GENRE_FEATURE_HINTS.items():
            if key in g:
                matched.append(feats)
                break
    if not matched:
        return {
            "energy": 0.55,
            "valence": 0.5,
            "danceability": 0.55,
            "tempo": 110.0,
            "speechiness": 0.08,
            "acousticness": 0.3,
            "instrumentalness": 0.1,
        }
    out: dict = {}
    for key in matched[0]:
        vals = [m[key] for m in matched if m.get(key) is not None]
        if vals:
            out[key] = round(sum(vals) / len(vals), 3)
    return out


def fetch_artist_profile(artist_id: str) -> dict:
    data = _api_get(f"/artists/{artist_id}") or {}
    return {
        "id": data.get("id") or artist_id,
        "name": data.get("name"),
        "genres": data.get("genres") or [],
        "popularity": data.get("popularity"),
        "followers": (data.get("followers") or {}).get("total"),
        "images": data.get("images") or [],
        "external_url": (data.get("external_urls") or {}).get("spotify"),
        "source": "spotify",
    }


def _tracks_from_payload(tracks_raw: list) -> list[dict]:
    tracks = []
    for t in tracks_raw or []:
        if not t or not t.get("id"):
            continue
        tracks.append(
            {
                "id": t.get("id"),
                "name": t.get("name"),
                "popularity": t.get("popularity"),
                "album": (t.get("album") or {}).get("name") if isinstance(t.get("album"), dict) else t.get("album"),
                "preview_url": t.get("preview_url"),
                "explicit": t.get("explicit"),
            }
        )
    return tracks


def fetch_top_tracks(artist_id: str, *, market: str = "US") -> tuple[list[dict], str]:
    """Return (tracks, source). source is 'top_tracks' or 'albums_fallback' or 'none'."""
    data = _api_get(f"/artists/{artist_id}/top-tracks", params={"market": market}, soft=True)
    if data is not None:
        tracks = _tracks_from_payload(data.get("tracks") or [])
        if tracks:
            return tracks, "top_tracks"

    albums = _api_get(
        f"/artists/{artist_id}/albums",
        params={"include_groups": "album,single", "limit": 5, "market": market},
        soft=True,
    )
    if not albums:
        return [], "none"

    tracks: list[dict] = []
    seen: set[str] = set()
    for album in albums.get("items") or []:
        album_id = album.get("id")
        if not album_id:
            continue
        album_data = _api_get(f"/albums/{album_id}", params={"market": market}, soft=True)
        if not album_data:
            continue
        for item in (album_data.get("tracks") or {}).get("items") or []:
            tid = item.get("id")
            if not tid or tid in seen:
                continue
            seen.add(tid)
            tracks.append(
                {
                    "id": tid,
                    "name": item.get("name"),
                    "popularity": None,
                    "album": album_data.get("name"),
                    "preview_url": item.get("preview_url"),
                    "explicit": item.get("explicit"),
                }
            )
            if len(tracks) >= 5:
                return tracks, "albums_fallback"
    return tracks, "albums_fallback" if tracks else "none"


def fetch_audio_features(track_ids: list[str]) -> tuple[dict[str, dict], str]:
    """Return (features_by_id, source). source is 'spotify' or 'unavailable'."""
    if not track_ids:
        return {}, "unavailable"
    ids = [tid for tid in track_ids if tid][:100]
    data = _api_get("/audio-features", params={"ids": ",".join(ids)}, soft=True)
    if data is None:
        return {}, "unavailable"
    out = {}
    for item in data.get("audio_features") or []:
        if not item:
            continue
        tid = item.get("id")
        if tid:
            out[tid] = {
                "danceability": item.get("danceability"),
                "energy": item.get("energy"),
                "valence": item.get("valence"),
                "tempo": item.get("tempo"),
                "acousticness": item.get("acousticness"),
                "instrumentalness": item.get("instrumentalness"),
                "speechiness": item.get("speechiness"),
                "liveness": item.get("liveness"),
                "key": item.get("key"),
                "mode": item.get("mode"),
                "loudness": item.get("loudness"),
            }
    return out, "spotify" if out else "unavailable"


def analyze_artist(artist_id: str, *, market: str | None = None) -> dict:
    """Full Spotify ingest for one artist, with soft degradation for restricted endpoints."""
    market = (market or os.environ.get("SPOTIFY_MARKET", "US")).strip() or "US"
    warnings: list[str] = []
    profile = fetch_artist_profile(artist_id)
    tracks, track_source = fetch_top_tracks(artist_id, market=market)
    if track_source == "albums_fallback":
        warnings.append("Top-tracks endpoint unavailable — using recent album/single tracks.")
    elif track_source == "none":
        warnings.append("Could not load tracks from Spotify — lyrical cues use brief only.")

    features, feature_source = fetch_audio_features([t["id"] for t in tracks if t.get("id")])
    if feature_source == "unavailable":
        features = {}
        averages = estimate_features_from_genres(profile.get("genres") or [])
        warnings.append(
            "Audio features endpoint restricted for this Spotify app — estimated sonic profile from genres."
        )
        feature_source = "genre_estimate"
    else:
        from statistics import mean

        keys = ("danceability", "energy", "valence", "tempo", "acousticness", "instrumentalness", "speechiness")
        averages = {}
        for key in keys:
            vals = [f[key] for f in features.values() if f.get(key) is not None]
            if vals:
                averages[key] = round(mean(vals), 3)

    return {
        "profile": profile,
        "tracks": tracks,
        "features": features,
        "averages": averages,
        "track_source": track_source,
        "feature_source": feature_source,
        "warnings": warnings,
    }


def verify_spotify_credentials() -> dict:
    """Lightweight connectivity check for setup/docs."""
    if not spotify_configured():
        return {"ok": False, "error": "SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET not set"}
    try:
        _get_token()
        # Drake — stable public artist id for smoke test
        profile = fetch_artist_profile("3TVXtAsR1Inumwj472S9r4")
        return {
            "ok": True,
            "artist": profile.get("name"),
            "genres": (profile.get("genres") or [])[:3],
            "followers": profile.get("followers"),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}
