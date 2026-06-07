"""Classify URLs/content as actual marketer services vs articles/tutorials."""
import re
from urllib.parse import urlparse

# Domains that are never marketer service profiles.
BLOCKED_DOMAINS = {
    "reddit.com",
    "www.reddit.com",
    "youtube.com",
    "www.youtube.com",
    "youtu.be",
    "medium.com",
    "www.medium.com",
    "wikipedia.org",
    "www.wikipedia.org",
    "quora.com",
    "www.quora.com",
    "linkedin.com",
    "www.linkedin.com",
    "facebook.com",
    "www.facebook.com",
    "twitter.com",
    "x.com",
    "tiktok.com",
    "www.tiktok.com",
    "instagram.com",
    "www.instagram.com",
    "spotify.com",
    "open.spotify.com",
    "musicbusinessworldwide.com",
    "hypebot.com",
    "digitalmusicnews.com",
    "topagency.com",
    "www.topagency.com",
}

# URL path segments that usually indicate articles, not service providers.
BLOCKED_PATH_PATTERNS = (
    r"/blog/",
    r"/blogs/",
    r"/articles?/",
    r"/news/",
    r"/post/",
    r"/posts/",
    r"/tutorial",
    r"/tutorials/",
    r"/guide/",
    r"/guides/",
    r"/learn/",
    r"/resources/",
    r"/tips/",
    r"/how-to",
    r"/howto",
    r"/best-",
    r"/top-\d",
    r"/list/",
    r"/glossary/",
    r"/definition",
    r"/wiki/",
    r"/comments/",
    r"/watch\?",
    r"/r/",
)

# Title/snippet phrases that indicate listicles, tutorials, or editorial content.
BLOCKED_TITLE_PATTERNS = (
    r"\bbest\b.*\b(companies|agencies|services|tools)\b",
    r"\btop\s+\d+\b",
    r"\bhow to\b",
    r"\bhow i\b",
    r"\btutorial\b",
    r"\bguide\b",
    r"\btips for\b",
    r"\bwhat is\b",
    r"\bwhy you should\b",
    r"\brecommendations for\b",
    r"\bcompare\b",
    r"\breview of\b",
    r"\bvs\.?\b",
    r"\b\d+\s+best\b",
    r"\bstarted a music marketing agency\b",
    r"\binterview with\b",
    r"\bpodcast\b",
)

# Signals that a page is an actual service provider.
SERVICE_SIGNALS = (
    "contact us",
    "get in touch",
    "book a call",
    "schedule a call",
    "request a quote",
    "our services",
    "our clients",
    "case stud",
    "portfolio",
    "pricing",
    "hire us",
    "work with us",
    "music marketing agency",
    "music promotion service",
    "we help artists",
    "we help musicians",
    "full-service",
    "promotion package",
    "campaign",
)


def classify_profile(url, title="", snippet="", text=""):
    """
    Return (is_service_profile, rejection_reason).

    rejection_reason is empty when is_service_profile is True.
    """
    url = (url or "").strip()
    if not url:
        return False, "missing_url"

    parsed = urlparse(url)
    domain = (parsed.netloc or "").lower().replace("www.", "")
    full_domain = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    combined = f"{title}\n{snippet}\n{text}".lower()

    if full_domain in BLOCKED_DOMAINS or domain in {d.replace("www.", "") for d in BLOCKED_DOMAINS}:
        return False, "blocked_domain"

    for pattern in BLOCKED_PATH_PATTERNS:
        if re.search(pattern, path, re.I):
            return False, f"blocked_path:{pattern}"

    title_snippet = f"{title}\n{snippet}".lower()
    for pattern in BLOCKED_TITLE_PATTERNS:
        if re.search(pattern, title_snippet, re.I):
            return False, f"blocked_title:{pattern}"

    # Editorial/blog-heavy pages without service intent.
    editorial_hits = sum(
        1
        for phrase in (
            "read more",
            "published on",
            "written by",
            "in this article",
            "this blog post",
            "step-by-step guide",
            "ultimate guide",
        )
        if phrase in combined
    )
    service_hits = sum(1 for phrase in SERVICE_SIGNALS if phrase in combined)

    if editorial_hits >= 2 and service_hits == 0:
        return False, "editorial_content"

    if service_hits >= 1:
        return True, ""

    # Homepage or short marketing site paths are often agencies.
    if path in ("", "/") and service_hits == 0:
        agency_words = ("agency", "marketing", "promotion", "pr", "promo")
        if any(w in combined for w in agency_words) and "how to" not in title_snippet:
            return True, ""

    if service_hits == 0 and editorial_hits >= 1:
        return False, "insufficient_service_signals"

    return False, "not_a_service_profile"
