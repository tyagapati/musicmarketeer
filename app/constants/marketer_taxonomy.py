"""Canonical taxonomy used by discovery and matching."""

CANONICAL_SERVICES = (
    "playlist_pitching",
    "ads",
    "pr",
    "release_campaigns",
    "social_media_strategy",
    "analytics",
    "identity_positioning",
)

CANONICAL_GENRES = (
    "indie",
    "indie-pop",
    "pop",
    "hip-hop",
    "r&b",
    "afrobeats",
    "latin-pop",
    "reggaeton",
    "electronic",
)

SERVICE_ALIASES = {
    "playlist pitching": "playlist_pitching",
    "playlist pitch": "playlist_pitching",
    "spotify playlist": "playlist_pitching",
    "ads": "ads",
    "paid ads": "ads",
    "meta ads": "ads",
    "tiktok ads": "ads",
    "youtube ads": "ads",
    "pr": "pr",
    "public relations": "pr",
    "press": "pr",
    "release campaigns": "release_campaigns",
    "release campaign": "release_campaigns",
    "social media strategy": "social_media_strategy",
    "social strategy": "social_media_strategy",
    "analytics": "analytics",
    "identity positioning": "identity_positioning",
    "brand strategy": "identity_positioning",
    "content": "social_media_strategy",
    "social media": "social_media_strategy",
    "social": "social_media_strategy",
}

GENRE_ALIASES = {
    "indie": "indie",
    "indie pop": "indie-pop",
    "indie-pop": "indie-pop",
    "pop": "pop",
    "hip hop": "hip-hop",
    "hip-hop": "hip-hop",
    "r&b": "r&b",
    "afrobeats": "afrobeats",
    "latin pop": "latin-pop",
    "latin-pop": "latin-pop",
    "reggaeton": "reggaeton",
    "electronic": "electronic",
}

MATURITY_TIERS = ("early", "mid", "advanced")


def canonicalize_service(value):
    """Map free-form service text to canonical service slug."""
    if not value:
        return None
    key = value.strip().lower()
    return SERVICE_ALIASES.get(key)


def canonicalize_genre(value):
    """Map free-form genre text to canonical genre slug."""
    if not value:
        return None
    key = value.strip().lower()
    return GENRE_ALIASES.get(key)


def infer_services_from_text(text):
    """Infer canonical services from free-form text."""
    corpus = (text or "").lower()
    found = set()
    for phrase, canonical in SERVICE_ALIASES.items():
        if phrase in corpus and canonical in CANONICAL_SERVICES:
            found.add(canonical)
    return sorted(found)


def infer_genres_from_text(text):
    """Infer canonical genres from free-form text."""
    corpus = (text or "").lower()
    found = set()
    for phrase, canonical in GENRE_ALIASES.items():
        if phrase in corpus and canonical in CANONICAL_GENRES:
            found.add(canonical)
    return sorted(found)


def _tokenize_csv(value):
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [part.strip() for part in str(value).split(",") if part.strip()]


def normalize_genre_list(value):
    """Turn comma-separated genre text into canonical slugs."""
    found = []
    seen = set()
    for part in _tokenize_csv(value):
        slug = canonicalize_genre(part)
        if not slug:
            key = part.strip().lower().replace("_", "-")
            if key in CANONICAL_GENRES:
                slug = key
        if slug and slug not in seen:
            seen.add(slug)
            found.append(slug)
    if not found and isinstance(value, str):
        for slug in infer_genres_from_text(value):
            if slug not in seen:
                seen.add(slug)
                found.append(slug)
    return found


def normalize_service_list(value):
    """Turn comma-separated service text into canonical slugs."""
    found = []
    seen = set()
    for part in _tokenize_csv(value):
        slug = canonicalize_service(part)
        if not slug:
            key = part.strip().lower().replace("-", "_").replace(" ", "_")
            if key in CANONICAL_SERVICES:
                slug = key
        if slug and slug not in seen:
            seen.add(slug)
            found.append(slug)
    if not found and isinstance(value, str):
        for slug in infer_services_from_text(value):
            if slug not in seen:
                seen.add(slug)
                found.append(slug)
    return found


def taxonomy_label(slug):
    """Human-readable label for a taxonomy slug."""
    return (slug or "").replace("_", " ").replace("-", " ").title()
