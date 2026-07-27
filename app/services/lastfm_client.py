"""Last.fm API client — free alternative when Spotify Web API is unavailable."""
from __future__ import annotations

import os

import requests

BASE = "https://ws.audioscrobbler.com/2.0/"


def lastfm_configured() -> bool:
    return bool(os.environ.get("LASTFM_API_KEY", "").strip())


def _api(params: dict) -> dict:
    key = os.environ.get("LASTFM_API_KEY", "").strip()
    if not key:
        raise RuntimeError("LASTFM_API_KEY is not configured")
    resp = requests.get(
        BASE,
        params={**params, "api_key": key, "format": "json"},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


def search_artist(name: str) -> dict | None:
    data = _api({"method": "artist.search", "artist": name, "limit": 1})
    items = (data.get("results") or {}).get("artistmatches", {}).get("artist") or []
    if not items:
        return None
    hit = items[0] if isinstance(items, list) else items
    return {"name": hit.get("name"), "mbid": hit.get("mbid"), "listeners": hit.get("listeners")}


def fetch_artist_profile(artist_name: str) -> dict:
    data = _api({"method": "artist.getInfo", "artist": artist_name})
    artist = data.get("artist") or {}
    tags = [t.get("name") for t in (artist.get("tags") or {}).get("tag") or [] if t.get("name")]
    stats = artist.get("stats") or {}
    return {
        "name": artist.get("name") or artist_name,
        "genres": tags[:8],
        "listeners": int(stats.get("listeners") or 0),
        "playcount": int(stats.get("playcount") or 0),
        "mbid": artist.get("mbid"),
        "url": artist.get("url"),
        "source": "lastfm",
    }


def fetch_top_tracks(artist_name: str, *, limit: int = 5) -> list[dict]:
    data = _api({"method": "artist.getTopTracks", "artist": artist_name, "limit": limit})
    tracks = (data.get("toptracks") or {}).get("track") or []
    if isinstance(tracks, dict):
        tracks = [tracks]
    out = []
    for t in tracks:
        out.append(
            {
                "name": t.get("name"),
                "playcount": int(t.get("playcount") or 0),
                "listeners": int((t.get("listeners") or 0) or 0),
                "mbid": t.get("mbid"),
            }
        )
    return out


def _averages_from_tags(tags: list[str]) -> dict:
    """Estimate sonic averages from Last.fm community tags (no audio-features API)."""
    joined = " ".join(tags).lower()
    energy = 0.55
    valence = 0.5
    dance = 0.5
    speech = 0.1
    tempo = 110.0

    if any(w in joined for w in ("electronic", "dance", "edm", "house", "techno", "club")):
        energy, dance, tempo = 0.75, 0.72, 124.0
    if any(w in joined for w in ("hip hop", "hip-hop", "rap", "trap")):
        speech, energy = 0.38, 0.62
    if any(w in joined for w in ("acoustic", "folk", "singer-songwriter", "ambient")):
        energy, dance, valence = 0.35, 0.38, 0.55
    if any(w in joined for w in ("sad", "melancholy", "dark")):
        valence = 0.32
    if any(w in joined for w in ("happy", "uplifting", "summer", "pop")):
        valence = 0.68

    return {
        "energy": round(energy, 3),
        "valence": round(valence, 3),
        "danceability": round(dance, 3),
        "tempo": tempo,
        "speechiness": round(speech, 3),
        "source": "lastfm_tags",
    }
