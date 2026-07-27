"""Optional Genius API client for track metadata (lyrics body not in public API)."""
from __future__ import annotations

import os

import requests

BASE = "https://api.genius.com"


def genius_configured() -> bool:
    return bool(os.environ.get("GENIUS_ACCESS_TOKEN", "").strip())


def _headers() -> dict:
    token = os.environ.get("GENIUS_ACCESS_TOKEN", "").strip()
    return {"Authorization": f"Bearer {token}"}


def search_song(title: str, artist: str = "") -> dict | None:
    """Return the top Genius hit for a track title (+ optional artist)."""
    if not genius_configured():
        return None
    query = f"{title} {artist}".strip()
    if not query:
        return None
    try:
        resp = requests.get(
            f"{BASE}/search",
            headers=_headers(),
            params={"q": query},
            timeout=15,
        )
        resp.raise_for_status()
        hits = (resp.json().get("response") or {}).get("hits") or []
        if not hits:
            return None
        result = hits[0].get("result") or {}
        return {
            "id": result.get("id"),
            "title": result.get("title"),
            "url": result.get("url"),
            "primary_artist": ((result.get("primary_artist") or {}).get("name")),
            "stats": result.get("stats") or {},
        }
    except Exception:
        return None


def enrich_tracks_with_genius(tracks: list[dict], artist_name: str = "") -> list[dict]:
    """Attach Genius metadata URLs to top tracks when the API key is configured."""
    if not genius_configured():
        return tracks
    out = []
    for track in tracks[:5]:
        row = dict(track)
        hit = search_song(track.get("name") or "", artist_name)
        if hit:
            row["genius"] = hit
        out.append(row)
    return out
