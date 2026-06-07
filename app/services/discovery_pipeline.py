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
from app.services.marketer_display import (
    estimate_pricing_from_services,
    extract_pricing_from_text,
    infer_preferred_maturity,
    normalize_brand_name,
)
from app.services.profile_classifier import classify_profile


def run_discovery_cycle(max_candidates=None):
    """Discover candidates, score reliability, and store pending marketers."""
    limit = max_candidates or int(os.environ.get("DISCOVERY_MAX_CANDIDATES", "25"))
    underrepresented = _underrepresented_targets()
    query_plan = build_query_plan(underrepresented)
    candidates = _gather_candidates(limit=limit, queries=query_plan)

    created = 0
    skipped_existing = 0
    skipped_low_confidence = 0
    skipped_not_profile = 0

    for candidate in candidates:
        website = _normalize_website(candidate["url"].strip())
        if not website:
            continue

        prelim_ok, prelim_reason = classify_profile(
            website,
            title=candidate.get("title", ""),
            snippet=candidate.get("snippet", ""),
        )
        if not prelim_ok:
            skipped_not_profile += 1
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
                existing.name = enriched["name"]
                existing.brand_name = enriched["brand_name"]
                existing.price_min = enriched.get("price_min")
                existing.price_max = enriched.get("price_max")
                existing.price_model = enriched.get("price_model")
            skipped_existing += 1
            continue

        enriched = _enrich_candidate(candidate)
        if not enriched.get("is_service_profile"):
            skipped_not_profile += 1
            continue
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
            price_min=enriched.get("price_min"),
            price_max=enriched.get("price_max"),
            price_model=enriched.get("price_model"),
            price_verified=enriched.get("price_verified", False),
            preferred_maturity=enriched.get("preferred_maturity", []),
            affiliate_url=enriched.get("affiliate_url"),
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
        "skipped_not_profile": skipped_not_profile,
        "considered": len(candidates),
        "query_plan": query_plan,
        "underrepresented": underrepresented,
    }


def build_query_plan(underrepresented):
    """Create discovery queries and bias toward underrepresented taxonomy targets."""
    base_queries = [
        "music marketing agency contact pricing",
        "music promotion company for independent artists",
        "playlist pitching agency hire",
        "music PR firm services",
        "independent artist marketing agency -reddit -youtube -blog -tutorial",
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
            ok, _ = classify_profile(
                url,
                title=item.get("title", ""),
                snippet=item.get("snippet", ""),
            )
            if not ok:
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
    text = _fetch_site_corpus(website)
    corpus = f"{title}\n{snippet}\n{text}".lower()

    is_service, reject_reason = classify_profile(website, title=title, snippet=snippet, text=text)
    if not is_service:
        return {
            "name": title[:255] or "Unknown",
            "brand_name": title[:255] or "Unknown",
            "email": None,
            "bio": snippet[:800],
            "genres": [],
            "services": [],
            "languages": ["en"],
            "geography": None,
            "portfolio_urls": [website],
            "evidence_summary": f"Rejected: {reject_reason}",
            "proof_strength": 0,
            "confidence_score": 0,
            "source": candidate.get("source", "agent"),
            "is_service_profile": False,
        }

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
    raw_brand = llm.get("brand_name") or (title.split("|")[0].split("-")[0].strip() if title else domain)
    raw_name = llm.get("name") or raw_brand
    brand_name = normalize_brand_name(
        website=website,
        title=title,
        brand_name=raw_brand,
        name=raw_name,
    )
    name = brand_name
    price_min, price_max, price_model = extract_pricing_from_text(text)
    price_verified = price_min is not None
    if price_min is None:
        price_min, price_max, price_model = estimate_pricing_from_services(services)
        price_verified = False
    preferred_maturity = infer_preferred_maturity(text)
    if review_count > 0 or rating >= 4.0:
        proof = min(100, proof + 10)
    evidence = (
        f"Source={candidate.get('source', 'agent')}; profile=service; rating={rating:.1f}; "
        f"reviews={review_count}; inferred_services={services}; inferred_genres={genres}; "
        f"preferred_maturity={preferred_maturity}; price_verified={price_verified}"
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
        "price_min": price_min,
        "price_max": price_max,
        "price_model": price_model,
        "price_verified": price_verified,
        "preferred_maturity": preferred_maturity,
        "affiliate_url": website,
        "portfolio_urls": [website],
        "evidence_summary": evidence[:1500],
        "proof_strength": proof,
        "confidence_score": confidence,
        "source": candidate.get("source", "agent"),
        "is_service_profile": True,
    }


def cleanup_marketer_catalog():
    """Remove demo data and non-service profiles from the marketer catalog."""
    removed_demo = 0
    removed_non_profile = 0
    removed_duplicates = 0
    kept = 0

    marketers = Marketer.query.all()
    for marketer in marketers:
        if marketer.source == "manual":
            db.session.delete(marketer)
            removed_demo += 1
            continue

        text = _fetch_text(marketer.website or "")
        ok, reason = classify_profile(
            marketer.website or "",
            title=marketer.name or "",
            snippet=marketer.bio or "",
            text=text,
        )
        if not ok:
            db.session.delete(marketer)
            removed_non_profile += 1
        else:
            normalized = _normalize_website(marketer.website or "")
            if normalized:
                marketer.website = normalized
            if marketer.source == "search_api" and (marketer.confidence_score or 0) >= 30:
                marketer.status = "approved"

    db.session.flush()

    seen = {}
    for marketer in Marketer.query.all():
        key = _normalize_website(marketer.website or "")
        if not key:
            continue
        if key in seen:
            db.session.delete(marketer)
            removed_duplicates += 1
        else:
            seen[key] = marketer.id
            kept += 1

    db.session.commit()
    return {
        "removed_demo": removed_demo,
        "removed_non_profile": removed_non_profile,
        "removed_duplicates": removed_duplicates,
        "kept": kept,
    }


def backfill_marketer_card_fields():
    """Normalize brand labels and pricing for all marketers."""
    updated = 0
    for marketer in Marketer.query.all():
        text = _fetch_text(marketer.website or "")
        brand = normalize_brand_name(
            website=marketer.website or "",
            title=marketer.name or "",
            brand_name=marketer.brand_name or "",
            name=marketer.name or "",
        )
        changed = False
        if marketer.brand_name != brand or marketer.name != brand:
            marketer.brand_name = brand
            marketer.name = brand
            changed = True
        price_min, price_max, price_model = extract_pricing_from_text(text)
        if price_min is None:
            price_min, price_max, price_model = estimate_pricing_from_services(marketer.services)
        if price_min is not None and (
            marketer.price_min != price_min
            or marketer.price_max != price_max
            or marketer.price_model != price_model
        ):
            marketer.price_min = price_min
            marketer.price_max = price_max
            marketer.price_model = price_model
            changed = True
        if changed:
            updated += 1
        if not marketer.preferred_maturity:
            marketer.preferred_maturity = infer_preferred_maturity(text)
            changed = True
        if not marketer.affiliate_url and marketer.website:
            marketer.affiliate_url = marketer.website
            changed = True
    db.session.commit()
    return {"updated": updated}


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


def get_discovery_report():
    """Return coverage counts and underrepresented taxonomy targets."""
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
    under = _underrepresented_targets()
    return {
        "total": len(marketers),
        "approved": Marketer.query.filter_by(status="approved").count(),
        "pending": Marketer.query.filter_by(status="pending").count(),
        "service_counts": service_counts,
        "genre_counts": genre_counts,
        "underrepresented": under,
    }


def _fetch_site_corpus(base_url):
    chunks = [_fetch_text(base_url)]
    parsed = urlparse(base_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    for suffix in ("/pricing", "/services", "/packages"):
        chunks.append(_fetch_text(root + suffix))
    return "\n".join(chunks)[:40000]


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
    parsed = urlparse(url)
    normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"
    return normalized


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
