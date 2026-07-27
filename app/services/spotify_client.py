"""Spotify Web API client (client-credentials flow)."""
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


def spotify_configured() -> bool:
    return bool(os.environ.get("SPOTIFY_CLIENT_ID", "").strip() and os.environ.get("SPOTIFY_CLIENT_SECRET", "").strip())


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
        return parts[1]
    return None


def _get_token() -> str:
    if not spotify_configured():
        raise RuntimeError("Spotify API credentials are not configured")
    now = time.time()
    if _TOKEN_CACHE["token"] and _TOKEN_CACHE["expires_at"] > now + 30:
        return _TOKEN_CACHE["token"]
    resp = requests.post(
        "https://accounts.spotify.com/api/token",
        data={"grant_type": "client_credentials"},
        auth=(os.environ["SPOTIFY_CLIENT_ID"].strip(), os.environ["SPOTIFY_CLIENT_SECRET"].strip()),
        timeout=15,
    )
    resp.raise_for_status()
    payload = resp.json()
    _TOKEN_CACHE["token"] = payload["access_token"]
    _TOKEN_CACHE["expires_at"] = now + int(payload.get("expires_in", 3600))
    return _TOKEN_CACHE["token"]


def _api_get(path: str, *, params: dict | None = None) -> dict:
    token = _get_token()
    resp = requests.get(
        f"https://api.spotify.com/v1{path}",
        headers={"Authorization": f"Bearer {token}"},
        params=params or {},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_artist_profile(artist_id: str) -> dict:
    data = _api_get(f"/artists/{artist_id}")
    return {
        "id": data.get("id"),
        "name": data.get("name"),
        "genres": data.get("genres") or [],
        "popularity": data.get("popularity"),
        "followers": (data.get("followers") or {}).get("total"),
        "images": data.get("images") or [],
        "external_url": (data.get("external_urls") or {}).get("spotify"),
    }


def fetch_top_tracks(artist_id: str, *, market: str = "US") -> list[dict]:
    data = _api_get(f"/artists/{artist_id}/top-tracks", params={"market": market})
    tracks = []
    for t in data.get("tracks") or []:
        tracks.append(
            {
                "id": t.get("id"),
                "name": t.get("name"),
                "popularity": t.get("popularity"),
                "album": (t.get("album") or {}).get("name"),
                "preview_url": t.get("preview_url"),
                "explicit": t.get("explicit"),
            }
        )
    return tracks


def fetch_audio_features(track_ids: list[str]) -> dict[str, dict]:
    if not track_ids:
        return {}
    ids = [tid for tid in track_ids if tid][:100]
    data = _api_get("/audio-features", params={"ids": ",".join(ids)})
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
    return out
