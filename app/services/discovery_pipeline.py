"""Discovery -> vetting -> categorization pipeline for marketers."""
import os
import re
import secrets

import requests

from app import db
from app.connectors.base import RedditConnector, SearchApiConnector, WebDirectoryConnector
from app.constants.marketer_taxonomy import (
    CANONICAL_GENRES,
    CANONICAL_SERVICES,
)
from app.models import Marketer
from app.services.marketer_display import (
    estimate_pricing_from_services,
    extract_pricing_from_text,
    infer_preferred_maturity,
    normalize_brand_name,
)
from app.services.profile_classifier import classify_profile
from app.services.site_blacklist import is_blacklisted
from app.services.site_urls import canonical_homepage_url, dedupe_marketers_by_domain, domain_key, sync_marketer_domain_fields
from app.services.discovery_search import (
    known_catalog_domains,
    next_serp_page_offset,
    select_queries_for_cycle,
    serpapi_query_budget,
)
from app.services.verification_agent import log_verification_decision, verify_candidate
from app.services.verification_decision import (
    DecisionTier,
    meets_auto_approve_threshold,
    should_auto_approve_marketer,
)

__all__ = [
    "meets_auto_approve_threshold",
    "should_auto_approve_marketer",
    "run_discovery_cycle",
    "build_query_plan",
    "cleanup_marketer_catalog",
    "backfill_marketer_card_fields",
    "get_discovery_report",
]


def run_discovery_cycle(max_candidates=None):
    """Discover candidates, score reliability, and store pending marketers."""
    limit = max_candidates or int(os.environ.get("DISCOVERY_MAX_CANDIDATES", "25"))
    underrepresented = _underrepresented_targets()
    full_query_plan = build_query_plan(underrepresented)
    query_plan = select_queries_for_cycle(full_query_plan)
    gather_stats = {}
    candidates = _gather_candidates(limit=limit, queries=query_plan, stats=gather_stats)

    created = 0
    skipped_existing = 0
    skipped_low_confidence = 0
    skipped_not_profile = 0
    skipped_blacklisted = 0

    for candidate in candidates:
        website = canonical_homepage_url(candidate["url"].strip())
        if not website:
            continue

        if is_blacklisted(website):
            skipped_blacklisted += 1
            continue

        prelim_ok, prelim_reason = classify_profile(
            website,
            title=candidate.get("title", ""),
            snippet=candidate.get("snippet", ""),
        )
        if not prelim_ok:
            skipped_not_profile += 1
            log_verification_decision(
                {
                    "decision": DecisionTier.REJECT.value,
                    "reason_codes": [prelim_reason or "prelim_classify_failed"],
                    "evidence_summary": f"Pre-filter rejected: {prelim_reason}",
                    "proof_strength": 0,
                    "confidence_score": 0,
                    "risk_flags": [],
                    "llm_valid": False,
                },
                url=website,
            )
            continue

        existing = _find_existing_by_website(website)
        if existing:
            if existing.status == "pending":
                enriched = verify_candidate({**candidate, "url": website})
                _apply_enriched_to_marketer(existing, enriched, website)
                log_verification_decision(enriched, marketer_id=existing.id, url=website)
                if enriched.get("decision") == DecisionTier.AUTO_APPROVE.value:
                    existing.status = "approved"
                    if not existing.portal_token:
                        existing.portal_token = secrets.token_urlsafe(24)
            skipped_existing += 1
            continue

        enriched = verify_candidate({**candidate, "url": website})

        if not enriched.get("is_service_profile"):
            log_verification_decision(enriched, url=website)
            skipped_not_profile += 1
            continue
        if enriched["confidence_score"] < int(os.environ.get("DISCOVERY_MIN_CONFIDENCE", "30")):
            log_verification_decision(enriched, url=website)
            skipped_low_confidence += 1
            continue

        status = (
            "approved"
            if enriched.get("decision") == DecisionTier.AUTO_APPROVE.value
            else "pending"
        )
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
            price_source=enriched.get("price_source", "estimated"),
            preferred_maturity=enriched.get("preferred_maturity", []),
            affiliate_url=enriched.get("affiliate_url"),
            portfolio_urls=enriched["portfolio_urls"],
            evidence_summary=enriched["evidence_summary"],
            proof_strength=enriched["proof_strength"],
            source=enriched["source"],
            status=status,
            confidence_score=enriched["confidence_score"],
            provider_type="agency",
            enrolled=False,
        )
        if status == "approved":
            marketer.portal_token = secrets.token_urlsafe(24)
        sync_marketer_domain_fields(marketer)
        db.session.add(marketer)
        db.session.flush()
        log_verification_decision(enriched, marketer_id=marketer.id, url=website)
        created += 1

    dedupe_marketers_by_domain()
    db.session.commit()
    return {
        "created": created,
        "skipped_existing": skipped_existing,
        "skipped_low_confidence": skipped_low_confidence,
        "skipped_not_profile": skipped_not_profile,
        "skipped_blacklisted": skipped_blacklisted,
        "considered": len(candidates),
        "query_plan": query_plan,
        "full_query_plan_size": len(full_query_plan),
        "underrepresented": underrepresented,
        "serpapi_queries_used": gather_stats.get("serpapi_queries_used", 0),
        "skipped_known_catalog": gather_stats.get("skipped_known_catalog", 0),
        "new_candidates_found": gather_stats.get("new_candidates_found", len(candidates)),
    }


def _apply_enriched_to_marketer(marketer, enriched, website):
    marketer.evidence_summary = enriched["evidence_summary"]
    marketer.proof_strength = enriched["proof_strength"]
    marketer.confidence_score = enriched["confidence_score"]
    marketer.source = enriched["source"]
    marketer.name = enriched["name"]
    marketer.brand_name = enriched["brand_name"]
    marketer.price_min = enriched.get("price_min")
    marketer.price_max = enriched.get("price_max")
    marketer.price_model = enriched.get("price_model")
    marketer.price_source = enriched.get("price_source", "estimated")
    sync_marketer_domain_fields(marketer)


def build_query_plan(underrepresented):
    """Create discovery queries and bias toward underrepresented taxonomy targets."""
    base_queries = [
        "music marketing agency contact pricing",
        "music promotion company for independent artists",
        "playlist pitching agency hire",
        "music PR firm services",
        "independent artist marketing agency -reddit -youtube -blog -tutorial",
        "music marketing freelancer for independent artists",
        "independent playlist pitching consultant",
        "solo music promotion specialist hire",
    ]
    for service in underrepresented["services"]:
        base_queries.append(f"{service.replace('_', ' ')} music marketing")
    for genre in underrepresented["genres"]:
        base_queries.append(f"{genre} music marketing agency")
    return list(dict.fromkeys(base_queries))


def _gather_candidates(limit=25, queries=None, stats=None):
    queries = queries or []
    stats = stats if stats is not None else {}
    catalog_domains = known_catalog_domains()
    seen_domains = set(catalog_domains)
    all_candidates = []
    skipped_known_catalog = 0

    def _try_add(item):
        nonlocal skipped_known_catalog
        url = (item.get("url") or "").strip()
        if not _looks_like_web_url(url):
            return False
        key = domain_key(url)
        if not key:
            return False
        if key in catalog_domains:
            skipped_known_catalog += 1
            return False
        if key in seen_domains:
            return False
        if is_blacklisted(url):
            return False
        ok, _ = classify_profile(
            url,
            title=item.get("title", ""),
            snippet=item.get("snippet", ""),
        )
        if not ok:
            return False
        seen_domains.add(key)
        row = dict(item)
        row["url"] = canonical_homepage_url(url)
        all_candidates.append(row)
        return True

    # Free sources first: seeds
    for item in WebDirectoryConnector().discover(known_domains=catalog_domains):
        _try_add(item)
        if len(all_candidates) >= limit:
            break

    stats["skipped_known_catalog"] = skipped_known_catalog

    # SerpAPI only when we still need new candidates and budget allows
    serp_budget = serpapi_query_budget()
    serp_used = 0
    if len(all_candidates) < limit and serp_budget > 0:
        page_offset = next_serp_page_offset()
        search = SearchApiConnector()
        if search.api_key:
            discovered = search.discover(
                queries,
                known_domains=catalog_domains,
                max_queries=serp_budget,
                page_offset=page_offset,
            )
            serp_used = getattr(search, "queries_run", 0)
            for item in discovered:
                if _try_add(item) and len(all_candidates) >= limit:
                    break
    stats["serpapi_queries_used"] = serp_used

    # Reddit last (optional)
    if len(all_candidates) < limit:
        for item in RedditConnector().discover(queries, known_domains=catalog_domains):
            _try_add(item)
            if len(all_candidates) >= limit:
                break

    stats["new_candidates_found"] = len(all_candidates)
    stats["skipped_known_catalog"] = skipped_known_catalog
    return all_candidates


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
            normalized = canonical_homepage_url(marketer.website or "")
            if normalized:
                marketer.website = normalized
                marketer.domain_key = domain_key(normalized)
            if should_auto_approve_marketer(marketer):
                marketer.status = "approved"
                if not marketer.portal_token:
                    marketer.portal_token = secrets.token_urlsafe(24)

    db.session.flush()

    seen = {}
    for marketer in Marketer.query.all():
        key = domain_key(marketer.website or "")
        if not key:
            continue
        if key in seen:
            from app.services.site_blacklist import delete_marketer_cascade

            delete_marketer_cascade(marketer)
            removed_duplicates += 1
        else:
            seen[key] = marketer.id
            marketer.domain_key = key
            marketer.website = canonical_homepage_url(marketer.website or "")
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
        if price_min is not None:
            price_source = "extracted"
        else:
            price_min, price_max, price_model = estimate_pricing_from_services(marketer.services)
            price_source = marketer.price_source or "estimated"
        if price_min is not None and (
            marketer.price_min != price_min
            or marketer.price_max != price_max
            or marketer.price_model != price_model
        ):
            marketer.price_min = price_min
            marketer.price_max = price_max
            marketer.price_model = price_model
            changed = True
        if marketer.price_source != price_source and marketer.price_source != "verified":
            marketer.price_source = price_source
            changed = True
        if changed:
            updated += 1
        if not marketer.preferred_maturity:
            marketer.preferred_maturity = infer_preferred_maturity(text)
            changed = True
        if not marketer.affiliate_url and marketer.website:
            marketer.affiliate_url = marketer.website
            changed = True
        if marketer.status == "approved" and not marketer.portal_token:
            marketer.portal_token = secrets.token_urlsafe(24)
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


def _fetch_text(url):
    try:
        response = requests.get(url, timeout=6, headers={"User-Agent": "soundmatch-discovery/1.0"})
        response.raise_for_status()
        return response.text[:20000]
    except Exception:
        return ""


def _looks_like_web_url(url):
    return url.startswith("http://") or url.startswith("https://")


def _find_existing_by_website(website):
    key = domain_key(website)
    if not key:
        return None
    existing = Marketer.query.filter_by(domain_key=key).first()
    if existing:
        return existing
    for marketer in Marketer.query.filter(Marketer.website.isnot(None)).all():
        if domain_key(marketer.website) == key:
            return marketer
    return None
