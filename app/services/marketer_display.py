"""Display helpers and enrichment for marketer cards."""
import re
from urllib.parse import urlparse

GENERIC_TITLES = {
    "who we are",
    "about us",
    "about",
    "home",
    "services",
    "pricing",
    "contact",
    "contact us",
    "award",
    "music marketing",
    "music promotion services",
    "music promotion service",
    "indie music promotion",
    "waves music marketing pricing",
}


def brand_from_website(website):
    """Derive a readable brand label from a website URL."""
    if not website:
        return "Unknown brand"
    host = (urlparse(website).netloc or "").lower().replace("www.", "")
    slug = host.split(".")[0] if host else "unknown"
    slug = re.sub(r"([a-z])([A-Z])", r"\1 \2", slug)
    slug = slug.replace("-", " ").replace("_", " ")
    words = [w for w in slug.split() if w]
    return " ".join(w.capitalize() for w in words) if words else "Unknown brand"


def _clean_candidate_label(value):
    cleaned = (value or "").strip()
    if not cleaned:
        return ""
    if ":" in cleaned:
        cleaned = cleaned.split(":", 1)[0].strip()
    cleaned = re.sub(r"\s*[|\u2013\u2014-]\s*music marketing.*$", "", cleaned, flags=re.I).strip()
    cleaned = re.sub(r"\s*[|\u2013\u2014-]\s*music promotion.*$", "", cleaned, flags=re.I).strip()
    cleaned = re.sub(r"\s*&\s*(music )?(promotion|pr services?).*$", "", cleaned, flags=re.I).strip()
    return cleaned


def normalize_brand_name(website="", title="", brand_name="", name=""):
    """Pick the best brand label, avoiding scraped page titles."""
    candidates = [_clean_candidate_label(brand_name), _clean_candidate_label(name), _clean_candidate_label(title)]
    for candidate in candidates:
        if not candidate:
            continue
        if any(ord(ch) > 127 for ch in candidate):
            continue
        key = candidate.lower()
        if key in GENERIC_TITLES:
            continue
        if len(candidate) <= 2:
            continue
        if re.search(r"\b(how to|best \d+|top \d+|what is|guide to)\b", key):
            continue
        if len(candidate) > 34:
            continue
        return candidate[:255]
    return brand_from_website(website)


SERVICE_PRICE_DEFAULTS = {
    "playlist_pitching": (75, 600),
    "ads": (300, 2500),
    "pr": (800, 5000),
    "release_campaigns": (500, 3500),
    "social_media_strategy": (400, 2200),
    "analytics": (200, 1200),
    "identity_positioning": (600, 4000),
}


def estimate_pricing_from_services(services):
    """Fallback pricing band when page extraction fails."""
    services = services or []
    if not services:
        return 200, 1500, "range"
    lows, highs = [], []
    for service in services:
        band = SERVICE_PRICE_DEFAULTS.get(service)
        if band:
            lows.append(band[0])
            highs.append(band[1])
    if not lows:
        return 200, 1500, "range"
    return min(lows), max(highs), "range"


def extract_pricing_from_text(text):
    """Extract (price_min, price_max, price_model) from page text."""
    corpus = (text or "").lower()
    price_model = "range"

    range_match = re.search(
        r"\$\s?(\d{1,3}(?:,\d{3})*|\d+)\s*(?:-|–|to)\s*\$?\s?(\d{1,3}(?:,\d{3})*|\d+)",
        corpus,
    )
    if range_match:
        low = int(range_match.group(1).replace(",", ""))
        high = int(range_match.group(2).replace(",", ""))
        if low <= high and high <= 100000:
            return low, high, price_model

    starting_match = re.search(
        r"(?:starting at|from|packages from|plans from)\s*\$?\s?(\d{1,3}(?:,\d{3})*|\d+)",
        corpus,
    )
    if starting_match:
        low = int(starting_match.group(1).replace(",", ""))
        if low <= 100000:
            return low, max(low * 3, low + 500), "starting_at"

    single_match = re.search(r"\$\s?(\d{1,3}(?:,\d{3})*|\d+)\s*/?\s*(?:month|mo|project|campaign)?", corpus)
    if single_match:
        value = int(single_match.group(1).replace(",", ""))
        if value <= 100000:
            return value, value, "fixed"

    return None, None, None


def format_price_range(price_min, price_max, price_model=None, price_verified=False):
    """Human-readable price badge text for cards."""
    prefix = "" if price_verified else "Est. "
    if price_min is None and price_max is None:
        return f"{prefix}Pricing on request".strip()
    low = price_min or 0
    high = price_max or low
    if low == 0 and high == 0:
        return f"{prefix}Pricing on request".strip()
    if price_model == "starting_at":
        return f"{prefix}From ${low:,}".strip()
    if low == high:
        return f"{prefix}${low:,}".strip()
    return f"{prefix}${low:,}–${high:,}".strip()


def infer_preferred_maturity(text):
    """Infer artist maturity tiers a marketer serves from page copy."""
    corpus = (text or "").lower()
    tiers = []
    if any(k in corpus for k in ("emerging artist", "independent artist", "indie artist", "new artist", "early stage")):
        tiers.append("early")
    if any(k in corpus for k in ("mid-level", "growing artist", "mid tier", "mid-career")):
        tiers.append("mid")
    if any(k in corpus for k in ("established artist", "major label", "advanced artist", "stadium", "arena")):
        tiers.append("advanced")
    if not tiers:
        tiers = ["early", "mid"]
    return sorted(set(tiers))
