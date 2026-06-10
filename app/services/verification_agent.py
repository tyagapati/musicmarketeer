"""Verification agent: orchestrates vetting steps with deterministic guardrails."""
from __future__ import annotations

import json
import os
import re
from urllib.parse import urlparse

import requests

from app.constants.marketer_taxonomy import infer_genres_from_text, infer_services_from_text
from app.models import Marketer, VerificationDecision
from app.services.marketer_display import (
    estimate_pricing_from_services,
    extract_pricing_from_text,
    infer_preferred_maturity,
    normalize_brand_name,
)
from app.services.profile_classifier import classify_profile
from app.services.review_signals import extract_review_signals
from app.services.verification_decision import (
    DecisionTier,
    compute_risk_flags,
    decide_marketer,
    score_candidate,
)
from app.services.verification_schema import validate_profile_extraction

from app import db


def verify_candidate(candidate: dict) -> dict:
    """
    Run the full verification pipeline for one discovery candidate.

    Returns enriched marketer dict with decision tier, reason codes, and risk flags.
    """
    website = candidate["url"]
    title = candidate.get("title", "").strip()
    snippet = candidate.get("snippet", "").strip()

    text = fetch_site_corpus(website)
    corpus = f"{title}\n{snippet}\n{text}".lower()
    corpus_len = len(text.strip())

    is_service, reject_reason = classify_profile(
        website, title=title, snippet=snippet, text=text
    )
    if not is_service:
        result = _rejected_payload(
            candidate,
            website,
            title,
            snippet,
            reject_reason,
        )
        result["decision"] = DecisionTier.REJECT.value
        result["reason_codes"] = [reject_reason or "not_service_profile"]
        return result

    llm_configured = bool(
        os.environ.get("DISCOVERY_LLM_API_URL", "").strip()
        and os.environ.get("DISCOVERY_LLM_API_KEY", "").strip()
    )
    extraction = extract_profile_llm(
        title=title, snippet=snippet, text=text, url=website
    )

    services = extraction.services or infer_services_from_text(corpus)
    genres = extraction.genres or infer_genres_from_text(corpus)
    rating, review_count, review_source = extract_review_signals(corpus)
    email = extraction.email or _extract_email(corpus)

    proof_strength, confidence_score = score_candidate(
        rating=rating,
        review_count=review_count,
        services=services,
        genres=genres,
    )

    price_min, price_max, price_model = extract_pricing_from_text(text)
    if price_min is not None:
        price_source = "extracted"
        price_verified = False
    else:
        price_min, price_max, price_model = estimate_pricing_from_services(services)
        price_source = "estimated"
        price_verified = False

    preferred_maturity = infer_preferred_maturity(text)

    risk_flags = compute_risk_flags(
        corpus_len=corpus_len,
        llm_valid=extraction.valid,
        llm_configured=llm_configured,
        review_count=review_count,
        rating=rating,
        services=services,
        genres=genres,
        price_source=price_source,
        proof_strength=proof_strength,
        llm_services=extraction.services,
        llm_genres=extraction.genres,
    )

    domain = urlparse(website).netloc or "unknown"
    raw_brand = extraction.brand_name or (
        title.split("|")[0].split("-")[0].strip() if title else domain
    )
    raw_name = extraction.name or raw_brand
    brand_name = normalize_brand_name(
        website=website,
        title=title,
        brand_name=raw_brand,
        name=raw_name,
    )

    evidence = (
        f"Source={candidate.get('source', 'agent')}; profile=service; rating={rating:.1f}; "
        f"reviews={review_count}; review_source={review_source or 'none'}; "
        f"inferred_services={services}; inferred_genres={genres}; "
        f"preferred_maturity={preferred_maturity}; price_source={price_source}"
    )
    if extraction.evidence_citations:
        evidence += f"; llm_citations={extraction.evidence_citations[:3]}"
    if risk_flags:
        evidence += f"; risk_flags={risk_flags}"

    enriched = {
        "name": brand_name[:255],
        "brand_name": brand_name[:255],
        "email": email,
        "bio": (
            extraction.bio or snippet[:800] or "Discovered by automated pipeline."
        )[:800],
        "genres": genres,
        "services": services,
        "languages": ["en"],
        "geography": None,
        "price_min": price_min,
        "price_max": price_max,
        "price_model": price_model,
        "price_verified": price_verified,
        "price_source": price_source,
        "preferred_maturity": preferred_maturity,
        "affiliate_url": website,
        "portfolio_urls": [website],
        "evidence_summary": evidence[:1500],
        "proof_strength": proof_strength,
        "confidence_score": confidence_score,
        "source": candidate.get("source", "agent"),
        "is_service_profile": True,
        "risk_flags": risk_flags,
        "llm_valid": extraction.valid,
        "llm_raw_response": extraction.raw_response,
    }

    tier, reason_codes = decide_marketer(enriched)
    enriched["decision"] = tier.value
    enriched["reason_codes"] = reason_codes
    return enriched


def log_verification_decision(
    enriched: dict,
    *,
    marketer_id: int | None = None,
    url: str = "",
) -> VerificationDecision:
    """Persist an auditable verification decision record."""
    scores = {
        "proof_strength": enriched.get("proof_strength", 0),
        "confidence_score": enriched.get("confidence_score", 0),
        "risk_flags": enriched.get("risk_flags", []),
        "llm_valid": enriched.get("llm_valid", False),
    }
    row = VerificationDecision(
        marketer_id=marketer_id,
        url=url or enriched.get("affiliate_url", ""),
        decision=enriched.get("decision", DecisionTier.PENDING.value),
        reason_codes=enriched.get("reason_codes", []),
        scores=scores,
        evidence_summary=enriched.get("evidence_summary", "")[:1500],
        llm_raw_response=(enriched.get("llm_raw_response") or "")[:2000],
    )
    db.session.add(row)
    return row


def fetch_site_corpus(base_url: str) -> str:
    """Fetch homepage plus common service/pricing paths."""
    chunks = [_fetch_text(base_url)]
    parsed = urlparse(base_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    for suffix in ("/pricing", "/services", "/packages"):
        chunks.append(_fetch_text(root + suffix))
    return "\n".join(chunks)[:40000]


def extract_profile_llm(*, title: str, snippet: str, text: str, url: str):
    """
    Structured LLM extraction with schema validation.

    Returns ProfileExtractionResult; invalid JSON yields valid=False (fail-safe).
    """
    from app.services.verification_schema import ProfileExtractionResult

    api_url = os.environ.get("DISCOVERY_LLM_API_URL", "").strip()
    api_key = os.environ.get("DISCOVERY_LLM_API_KEY", "").strip()
    model = os.environ.get("DISCOVERY_LLM_MODEL", "gpt-4o-mini")

    if not (api_url and api_key):
        return ProfileExtractionResult(valid=False, parse_error="llm_unconfigured")

    system_prompt = (
        "Extract marketer profile JSON from provided webpage text. "
        "Return ONLY valid JSON with keys: name, brand_name, bio, email, services, genres, "
        "evidence_citations (array of short quoted snippets from the page supporting your fields), "
        "confidence_notes (brief string). "
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

    content = ""
    try:
        response = requests.post(api_url, json=payload, headers=headers, timeout=20)
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if not json_match:
            return ProfileExtractionResult(
                valid=False,
                parse_error="no_json_object",
                raw_response=content[:2000],
            )
        parsed = json.loads(json_match.group(0))
        return validate_profile_extraction(parsed, raw_response=content)
    except json.JSONDecodeError as exc:
        return ProfileExtractionResult(
            valid=False,
            parse_error=f"json_decode:{exc}",
            raw_response=content[:2000],
        )
    except Exception as exc:
        return ProfileExtractionResult(
            valid=False,
            parse_error=f"request_error:{type(exc).__name__}",
            raw_response=content[:2000],
        )


def _fetch_text(url: str) -> str:
    try:
        response = requests.get(
            url, timeout=6, headers={"User-Agent": "soundmatch-discovery/1.0"}
        )
        response.raise_for_status()
        return response.text[:20000]
    except Exception:
        return ""


def _extract_email(corpus: str) -> str | None:
    match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", corpus)
    if not match:
        return None
    return match.group(0)[:255]


def _rejected_payload(candidate, website, title, snippet, reject_reason):
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
        "reject_reason": reject_reason,
        "risk_flags": [],
        "decision": DecisionTier.REJECT.value,
        "reason_codes": [reject_reason or "not_service_profile"],
    }
