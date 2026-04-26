"""Discovery -> vetting -> categorization pipeline for marketers."""
import os
import re
from urllib.parse import urlparse

import requests

from app import db
from app.connectors.base import RedditConnector, SearchApiConnector, WebDirectoryConnector
from app.constants.marketer_taxonomy import (
    CANONICAL_GENRES,
    CANONICAL_SERVICES,
    infer_genres_from_text,
    infer_services_from_text,
)
from app.models import Marketer


def run_discovery_cycle(max_candidates=None):
    """Discover candidates, score reliability, and store pending marketers."""
    limit = max_candidates or int(os.environ.get("DISCOVERY_MAX_CANDIDATES", "25"))
    underrepresented = _underrepresented_targets()
    query_plan = build_query_plan(underrepresented)
    candidates = _gather_candidates(limit=limit, queries=query_plan)

    created = 0
    skipped_existing = 0
    skipped_low_confidence = 0

    for candidate in candidates:
        website = _normalize_website(candidate["url"].strip())
        if not website:
            continue

        existing = _find_existing_by_website(website)
        if existing:
            # Refresh evidence for stale pending candidates.
            if existing.status == "pending":
                enriched = _enrich_candidate(candidate)
                existing.evidence_summary = enriched["evidence_summary"]
                existing.proof_strength = enriched["proof_strength"]
                existing.confidence_score = enriched["confidence_score"]
                existing.source = enriched["source"]
            skipped_existing += 1
            continue

        enriched = _enrich_candidate(candidate)
        if enriched["confidence_score"] < int(os.environ.get("DISCOVERY_MIN_CONFIDENCE", "30")):
            skipped_low_confidence += 1
            continue

        marketer = Marketer(
            name=enriched["name"],
            brand_name=enriched["brand_name"],
            website=website,
            email=enriched["email"],
            bio=enriched["bio"],
            genres=enriched["genres"],
            services=enriched["services"],
            languages=enriched["languages"],
            geography=enriched["geography"],
            portfolio_urls=enriched["portfolio_urls"],
            evidence_summary=enriched["evidence_summary"],
            proof_strength=enriched["proof_strength"],
            source=enriched["source"],
            status="pending",
            confidence_score=enriched["confidence_score"],
        )
        db.session.add(marketer)
        created += 1

    db.session.commit()
    return {
        "created": created,
        "skipped_existing": skipped_existing,
        "skipped_low_confidence": skipped_low_confidence,
        "considered": len(candidates),
        "query_plan": query_plan,
        "underrepresented": underrepresented,
    }


def build_query_plan(underrepresented):
    """Create discovery queries and bias toward underrepresented taxonomy targets."""
    base_queries = [
        "music marketing agency",
        "music marketing freelancer",
        "playlist pitching service for artists",
        "music PR agency independent artists",
        "tiktok ads music marketing",
    ]
    for service in underrepresented["services"]:
        base_queries.append(f"{service.replace('_', ' ')} music marketing")
    for genre in underrepresented["genres"]:
        base_queries.append(f"{genre} music marketing agency")
    # Preserve order while removing duplicates.
    return list(dict.fromkeys(base_queries))


def _gather_candidates(limit=25, queries=None):
    queries = queries or []
    connectors = [WebDirectoryConnector(), SearchApiConnector(), RedditConnector()]
    all_candidates = []
    seen_urls = set()

    for connector in connectors:
        try:
            discovered = connector.discover(queries)  # Search + Reddit signatures
        except TypeError:
            discovered = connector.discover()  # Seed connector signature
        for item in discovered:
            url = (item.get("url") or "").strip()
            if not _looks_like_web_url(url) or url in seen_urls:
                continue
            seen_urls.add(url)
            all_candidates.append(item)
            if len(all_candidates) >= limit:
                return all_candidates
    return all_candidates


def _enrich_candidate(candidate):
    website = candidate["url"]
    title = candidate.get("title", "").strip()
    snippet = candidate.get("snippet", "").strip()
    text = _fetch_text(website)
    corpus = f"{title}\n{snippet}\n{text}".lower()

    llm = _extract_with_llm(title=title, snippet=snippet, text=text, url=website)
    services = llm.get("services") or infer_services_from_text(corpus)
    genres = llm.get("genres") or infer_genres_from_text(corpus)
    rating, review_count = _extract_review_signals(corpus)
    email = llm.get("email") or _extract_email(corpus)

    # Reliability-first scoring: prioritize independent review signals.
    proof = min(100, int((rating / 5.0) * 50) + min(review_count, 50))
    confidence = min(
        100,
        15
        + (20 if services else 0)
        + (15 if genres else 0)
        + (30 if review_count > 0 else 0)
        + (20 if rating >= 4.0 else 0),
    )

    domain = urlparse(website).netloc or "unknown"
    brand_name = llm.get("brand_name") or (title.split("|")[0].split("-")[0].strip() if title else domain)
    name = llm.get("name") or brand_name
    evidence = (
        f"Source={candidate.get('source', 'agent')}; rating={rating:.1f}; "
        f"reviews={review_count}; inferred_services={services}; inferred_genres={genres}"
    )

    return {
        "name": name[:255],
        "brand_name": brand_name[:255],
        "email": email,
        "bio": (llm.get("bio") or snippet[:800] or "Discovered by automated pipeline.")[:800],
        "genres": genres,
        "services": services,
        "languages": ["en"],
        "geography": None,
        "portfolio_urls": [website],
        "evidence_summary": evidence[:1500],
        "proof_strength": proof,
        "confidence_score": confidence,
        "source": candidate.get("source", "agent"),
    }


def _underrepresented_targets():
    """Return least-covered genres/services among approved+pending marketers."""
    service_counts = {name: 0 for name in CANONICAL_SERVICES}
    genre_counts = {name: 0 for name in CANONICAL_GENRES}

    marketers = Marketer.query.filter(Marketer.status.in_(("approved", "pending"))).all()
    for marketer in marketers:
        for service in marketer.services or []:
            if service in service_counts:
                service_counts[service] += 1
        for genre in marketer.genres or []:
            if genre in genre_counts:
                genre_counts[genre] += 1

    low_services = sorted(service_counts, key=lambda key: service_counts[key])[:3]
    low_genres = sorted(genre_counts, key=lambda key: genre_counts[key])[:3]
    return {"services": low_services, "genres": low_genres}


def _fetch_text(url):
    try:
        response = requests.get(url, timeout=6, headers={"User-Agent": "soundmatch-discovery/1.0"})
        response.raise_for_status()
        return response.text[:20000]
    except Exception:
        return ""


def _extract_review_signals(corpus):
    rating_match = re.search(r"([1-5](?:\.[0-9])?)\s*/\s*5", corpus)
    review_match = re.search(r"([0-9]{1,4})\s+reviews?", corpus)
    rating = float(rating_match.group(1)) if rating_match else 0.0
    reviews = int(review_match.group(1)) if review_match else 0
    return rating, reviews


def _extract_email(corpus):
    match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", corpus)
    if not match:
        return None
    return match.group(0)[:255]


def _looks_like_web_url(url):
    return url.startswith("http://") or url.startswith("https://")


def _normalize_website(url):
    url = (url or "").strip()
    if not url:
        return ""
    if not _looks_like_web_url(url):
        return ""
    return url.rstrip("/")


def _find_existing_by_website(website):
    existing = Marketer.query.filter_by(website=website).first()
    if existing:
        return existing
    # Backward compatibility for rows stored with a trailing slash variant.
    alt = website + "/" if not website.endswith("/") else website[:-1]
    return Marketer.query.filter_by(website=alt).first()


def _extract_with_llm(title, snippet, text, url):
    """
    Optional LLM extraction hook.

    Uses an OpenAI-compatible chat completion endpoint when configured.
    """
    api_url = os.environ.get("DISCOVERY_LLM_API_URL", "").strip()
    api_key = os.environ.get("DISCOVERY_LLM_API_KEY", "").strip()
    model = os.environ.get("DISCOVERY_LLM_MODEL", "gpt-4o-mini")
    if not (api_url and api_key):
        return {}

    system_prompt = (
        "Extract marketer profile JSON from provided webpage text. "
        "Return ONLY valid JSON with keys: name, brand_name, bio, email, services, genres. "
        "services and genres must be arrays of canonical slugs when known, else empty arrays."
    )
    user_prompt = (
        f"URL: {url}\n"
        f"TITLE: {title}\n"
        f"SNIPPET: {snippet}\n"
        f"TEXT:\n{text[:12000]}"
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.0,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        response = requests.post(api_url, json=payload, headers=headers, timeout=20)
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        # Extract first JSON object in case model wraps with prose.
        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if not json_match:
            return {}
        import json

        parsed = json.loads(json_match.group(0))
        parsed["services"] = [s for s in (parsed.get("services") or []) if s in CANONICAL_SERVICES]
        parsed["genres"] = [g for g in (parsed.get("genres") or []) if g in CANONICAL_GENRES]
        return parsed
    except Exception:
        return {}
