"""Decision tiers, scoring, and risk flags for marketer verification."""
from __future__ import annotations

import os
from enum import Enum
from typing import Any

from app.models import Marketer


class DecisionTier(str, Enum):
    REJECT = "reject"
    PENDING = "pending"
    AUTO_APPROVE = "auto_approve"


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def score_candidate(
    *,
    rating: float,
    review_count: int,
    services: list[str],
    genres: list[str],
) -> tuple[int, int]:
    """Return (proof_strength, confidence_score) using deterministic formulas."""
    proof = min(100, int((rating / 5.0) * 50) + min(review_count, 50))
    confidence = min(
        100,
        15
        + (20 if services else 0)
        + (15 if genres else 0)
        + (30 if review_count > 0 else 0)
        + (20 if rating >= 4.0 else 0),
    )
    if review_count > 0 or rating >= 4.0:
        proof = min(100, proof + 10)
    return proof, confidence


def compute_risk_flags(
    *,
    corpus_len: int,
    llm_valid: bool,
    llm_configured: bool,
    review_count: int,
    rating: float,
    services: list[str],
    genres: list[str],
    price_source: str,
    proof_strength: int,
    llm_services: list[str],
    llm_genres: list[str],
) -> list[str]:
    """Return risk flags that block auto-approve but allow manual review."""
    flags: list[str] = []
    min_corpus = _env_int("VERIFICATION_MIN_CORPUS_CHARS", 500)

    if corpus_len < min_corpus:
        flags.append("thin_corpus")

    if llm_configured and not llm_valid:
        flags.append("llm_invalid_json")
    elif not llm_configured:
        flags.append("llm_unavailable")

    if review_count == 0 and rating < 4.0:
        flags.append("no_review_signals")

    if not llm_services and not llm_genres and (services or genres):
        flags.append("inference_only_taxonomy")

    if price_source == "estimated":
        flags.append("price_estimated_only")
        min_proof_for_estimated = _env_int("VERIFICATION_MIN_PROOF_FOR_ESTIMATED_PRICE", 60)
        if proof_strength < min_proof_for_estimated:
            flags.append("weak_proof_with_estimated_price")

    return flags


def meets_auto_approve_threshold(row: dict[str, Any] | Marketer) -> bool:
    """True when score thresholds pass (ignores admin toggle and risk flags)."""
    min_conf = _env_int("AUTO_APPROVE_MIN_CONFIDENCE", 75)
    min_proof = _env_int("AUTO_APPROVE_MIN_PROOF", 50)

    if isinstance(row, Marketer):
        return (
            row.status == "pending"
            and (row.confidence_score or 0) >= min_conf
            and (row.proof_strength or 0) >= min_proof
            and bool(row.services)
            and bool(row.genres)
        )
    return (
        row.get("is_service_profile")
        and row.get("confidence_score", 0) >= min_conf
        and row.get("proof_strength", 0) >= min_proof
        and bool(row.get("services"))
        and bool(row.get("genres"))
    )


def would_auto_approve_if_enabled(row: dict[str, Any] | Marketer) -> bool:
    """True when thresholds pass and no blocking risk flags."""
    if isinstance(row, Marketer):
        data = {
            "is_service_profile": row.status != "rejected",
            "confidence_score": row.confidence_score or 0,
            "proof_strength": row.proof_strength or 0,
            "services": row.services or [],
            "genres": row.genres or [],
            "risk_flags": [],
        }
    else:
        data = row
    if data.get("risk_flags"):
        return False
    return meets_auto_approve_threshold(data)


def should_auto_approve_marketer(row: dict[str, Any] | Marketer) -> bool:
    """True when automation is enabled, thresholds met, and no risk flags."""
    from app.services.automation_settings import is_automation_enabled

    if not is_automation_enabled("auto_approve_marketers"):
        return False
    if isinstance(row, Marketer):
        data = {
            "is_service_profile": True,
            "confidence_score": row.confidence_score or 0,
            "proof_strength": row.proof_strength or 0,
            "services": row.services or [],
            "genres": row.genres or [],
            "risk_flags": [],
        }
    else:
        data = row
    if _env_bool("VERIFICATION_BLOCK_AUTO_APPROVE_ON_RISK", True) and data.get("risk_flags"):
        return False
    return meets_auto_approve_threshold(data)


def decide_marketer(row: dict[str, Any]) -> tuple[DecisionTier, list[str]]:
    """
    Return (decision_tier, reason_codes) for a verified candidate dict.

    Balanced autonomy: reject low confidence, auto-approve only when safe.
    """
    reasons: list[str] = []

    if not row.get("is_service_profile"):
        reasons.append(row.get("reject_reason") or "not_service_profile")
        return DecisionTier.REJECT, reasons

    min_conf = _env_int("DISCOVERY_MIN_CONFIDENCE", 30)
    confidence = row.get("confidence_score", 0)
    if confidence < min_conf:
        reasons.append("below_min_confidence")
        return DecisionTier.REJECT, reasons

    risk_flags = row.get("risk_flags") or []
    if risk_flags:
        reasons.extend(risk_flags)

    if should_auto_approve_marketer(row):
        reasons.append("auto_approve_threshold_met")
        return DecisionTier.AUTO_APPROVE, reasons

    if meets_auto_approve_threshold(row) and risk_flags:
        reasons.append("threshold_met_but_risk_flags")
    else:
        reasons.append("pending_manual_review")

    return DecisionTier.PENDING, reasons
