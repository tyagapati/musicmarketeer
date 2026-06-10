"""Structured profile extraction schema and validators for the verification agent."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.constants.marketer_taxonomy import CANONICAL_GENRES, CANONICAL_SERVICES

REQUIRED_LLM_KEYS = frozenset(
    {"name", "brand_name", "bio", "email", "services", "genres", "evidence_citations"}
)
OPTIONAL_LLM_KEYS = frozenset({"confidence_notes"})


@dataclass
class ProfileExtractionResult:
    """Validated LLM or fallback profile extraction."""

    name: str = ""
    brand_name: str = ""
    bio: str = ""
    email: str | None = None
    services: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    evidence_citations: list[str] = field(default_factory=list)
    confidence_notes: str = ""
    valid: bool = False
    parse_error: str = ""
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "brand_name": self.brand_name,
            "bio": self.bio,
            "email": self.email,
            "services": self.services,
            "genres": self.genres,
            "evidence_citations": self.evidence_citations,
            "confidence_notes": self.confidence_notes,
            "valid": self.valid,
            "parse_error": self.parse_error,
        }


def _coerce_str(value: Any, max_len: int = 0) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if max_len and len(text) > max_len:
        return text[:max_len]
    return text


def _coerce_str_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def validate_profile_extraction(
    parsed: dict[str, Any] | None,
    *,
    raw_response: str = "",
) -> ProfileExtractionResult:
    """Validate LLM JSON against schema; filter slugs to canonical taxonomy."""
    if not parsed or not isinstance(parsed, dict):
        return ProfileExtractionResult(
            valid=False,
            parse_error="empty_or_non_object",
            raw_response=raw_response[:2000],
        )

    missing = REQUIRED_LLM_KEYS - set(parsed.keys())
    if missing:
        return ProfileExtractionResult(
            valid=False,
            parse_error=f"missing_keys:{','.join(sorted(missing))}",
            raw_response=raw_response[:2000],
        )

    services = [s for s in _coerce_str_list(parsed.get("services")) if s in CANONICAL_SERVICES]
    genres = [g for g in _coerce_str_list(parsed.get("genres")) if g in CANONICAL_GENRES]
    citations = _coerce_str_list(parsed.get("evidence_citations"))[:10]

    email_raw = parsed.get("email")
    email = _coerce_str(email_raw, 255) or None
    if email and "@" not in email:
        email = None

    return ProfileExtractionResult(
        name=_coerce_str(parsed.get("name"), 255),
        brand_name=_coerce_str(parsed.get("brand_name"), 255),
        bio=_coerce_str(parsed.get("bio"), 800),
        email=email,
        services=services,
        genres=genres,
        evidence_citations=citations,
        confidence_notes=_coerce_str(parsed.get("confidence_notes"), 500),
        valid=True,
        raw_response=raw_response[:2000],
    )
