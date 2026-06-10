"""Tests for verification agent, classifier, scoring, and decisions."""
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.profile_classifier import classify_profile
from app.services.verification_decision import (
    DecisionTier,
    compute_risk_flags,
    decide_marketer,
    meets_auto_approve_threshold,
    score_candidate,
    should_auto_approve_marketer,
)
from app.services.verification_schema import ProfileExtractionResult, validate_profile_extraction

FIXTURES_PATH = Path(__file__).parent / "verification" / "fixtures.json"


def _load_fixtures():
    with open(FIXTURES_PATH, encoding="utf-8") as f:
        return json.load(f)


class TestClassifyProfileFixtures:
    def test_all_fixtures_have_expected_outcome(self):
        fixtures = _load_fixtures()
        assert len(fixtures) >= 25

    def test_classify_precision_on_fixtures(self):
        fixtures = _load_fixtures()
        false_positives = []
        false_negatives = []

        for case in fixtures:
            ok, _ = classify_profile(
                case["url"],
                title=case.get("title", ""),
                snippet=case.get("snippet", ""),
                text=case.get("text", ""),
            )
            expected = case["expected_classify"]
            if ok and not expected:
                false_positives.append(case["id"])
            if not ok and expected:
                false_negatives.append(case["id"])

        fpr = len(false_positives) / max(len(fixtures), 1)
        recall = 1 - (len(false_negatives) / max(
            sum(1 for c in fixtures if c["expected_classify"]), 1
        ))

        assert fpr < 0.05, f"FPR too high: {false_positives}"
        assert recall >= 0.90, f"Recall too low: {false_negatives}"


class TestScoreCandidate:
    def test_more_reviews_increase_proof(self):
        low_proof, _ = score_candidate(rating=4.0, review_count=0, services=["ads"], genres=["pop"])
        high_proof, _ = score_candidate(rating=4.0, review_count=50, services=["ads"], genres=["pop"])
        assert high_proof > low_proof

    def test_services_and_genres_increase_confidence(self):
        _, base_conf = score_candidate(rating=0, review_count=0, services=[], genres=[])
        _, full_conf = score_candidate(rating=0, review_count=0, services=["ads"], genres=["pop"])
        assert full_conf > base_conf


class TestRiskFlags:
    def test_llm_invalid_blocks_risk_flag(self):
        flags = compute_risk_flags(
            corpus_len=1000,
            llm_valid=False,
            llm_configured=True,
            review_count=10,
            rating=4.5,
            services=["ads"],
            genres=["pop"],
            price_source="extracted",
            proof_strength=80,
            llm_services=[],
            llm_genres=[],
        )
        assert "llm_invalid_json" in flags

    def test_thin_corpus_flag(self):
        flags = compute_risk_flags(
            corpus_len=50,
            llm_valid=True,
            llm_configured=True,
            review_count=10,
            rating=4.5,
            services=["ads"],
            genres=["pop"],
            price_source="extracted",
            proof_strength=80,
            llm_services=["ads"],
            llm_genres=["pop"],
        )
        assert "thin_corpus" in flags


class TestDecideMarketer:
    def _base_row(self, **overrides):
        row = {
            "is_service_profile": True,
            "confidence_score": 80,
            "proof_strength": 60,
            "services": ["ads"],
            "genres": ["pop"],
            "risk_flags": [],
        }
        row.update(overrides)
        return row

    @patch("app.services.automation_settings.is_automation_enabled", return_value=False)
    def test_reject_not_service_profile(self, _mock_toggle):
        tier, reasons = decide_marketer({"is_service_profile": False, "reject_reason": "blocked_domain"})
        assert tier == DecisionTier.REJECT
        assert "blocked_domain" in reasons

    @patch("app.services.automation_settings.is_automation_enabled", return_value=False)
    def test_reject_low_confidence(self, _mock_toggle):
        tier, reasons = decide_marketer(self._base_row(confidence_score=10))
        assert tier == DecisionTier.REJECT
        assert "below_min_confidence" in reasons

    @patch("app.services.automation_settings.is_automation_enabled", return_value=True)
    def test_pending_when_risk_flags_present(self, _mock_toggle):
        os.environ["VERIFICATION_BLOCK_AUTO_APPROVE_ON_RISK"] = "true"
        row = self._base_row(risk_flags=["llm_invalid_json"])
        tier, reasons = decide_marketer(row)
        assert tier == DecisionTier.PENDING
        assert "llm_invalid_json" in reasons

    @patch("app.services.automation_settings.is_automation_enabled", return_value=True)
    def test_auto_approve_when_clean(self, _mock_toggle):
        os.environ["VERIFICATION_BLOCK_AUTO_APPROVE_ON_RISK"] = "true"
        tier, reasons = decide_marketer(self._base_row())
        assert tier == DecisionTier.AUTO_APPROVE
        assert "auto_approve_threshold_met" in reasons

    @patch("app.services.automation_settings.is_automation_enabled", return_value=True)
    def test_llm_failure_never_auto_approves(self, _mock_toggle):
        os.environ["VERIFICATION_BLOCK_AUTO_APPROVE_ON_RISK"] = "true"
        row = self._base_row(risk_flags=["llm_invalid_json"])
        assert not should_auto_approve_marketer(row)
        tier, _ = decide_marketer(row)
        assert tier == DecisionTier.PENDING


class TestProfileExtractionSchema:
    def test_valid_extraction(self):
        result = validate_profile_extraction(
            {
                "name": "Test Agency",
                "brand_name": "Test Agency",
                "bio": "We help artists.",
                "email": "hello@test.com",
                "services": ["ads", "invalid_slug"],
                "genres": ["pop"],
                "evidence_citations": ["We offer ads"],
            }
        )
        assert result.valid
        assert result.services == ["ads"]
        assert result.genres == ["pop"]

    def test_missing_keys_invalid(self):
        result = validate_profile_extraction({"name": "Only Name"})
        assert not result.valid
        assert "missing_keys" in result.parse_error

    def test_empty_returns_invalid(self):
        result = validate_profile_extraction(None)
        assert not result.valid


class TestVerifyCandidateIntegration:
    @patch.dict(
        os.environ,
        {"DISCOVERY_LLM_API_URL": "https://api.example.com", "DISCOVERY_LLM_API_KEY": "test-key"},
    )
    @patch("app.services.automation_settings.is_automation_enabled", return_value=False)
    @patch("app.services.verification_agent.fetch_site_corpus", return_value="x" * 1000)
    @patch("app.services.verification_agent.extract_profile_llm")
    def test_verify_candidate_pending_on_llm_failure(self, mock_llm, _mock_fetch, _mock_auto):
        mock_llm.return_value = ProfileExtractionResult(valid=False, parse_error="no_json_object")
        from app.services.verification_agent import verify_candidate

        result = verify_candidate(
            {
                "url": "https://beatboostagency.com/",
                "title": "BeatBoost Music Marketing Agency",
                "snippet": "Contact us for pricing and playlist pitching services.",
                "source": "test",
            }
        )
        assert result["is_service_profile"] is True
        assert result["decision"] == DecisionTier.PENDING.value
        assert "llm_invalid_json" in result.get("risk_flags", [])
