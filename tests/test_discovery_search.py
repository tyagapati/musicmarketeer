"""Tests for discovery search budget and catalog-aware filtering."""
import json
from unittest.mock import patch

from app.models import Marketer
from app.services.discovery_pipeline import _gather_candidates, build_query_plan
from app.services.discovery_search import select_queries_for_cycle, serpapi_query_budget
from app.services.site_urls import domain_key, sync_marketer_domain_fields


class TestQueryRotation:
    def test_select_queries_rotates(self, app):
        with app.app_context():
            plan = ["q1", "q2", "q3", "q4", "q5"]
            first = select_queries_for_cycle(plan)
            second = select_queries_for_cycle(plan)
            assert len(first) == 2
            assert first != second or first[0] != plan[0]


class TestCatalogAwareGather:
    def test_skips_known_catalog_domains(self, app):
        with app.app_context():
            from app import db

            marketer = Marketer(
                name="Existing Agency",
                brand_name="Existing Agency",
                website="https://existing-agency.example.com",
                status="approved",
                source="manual",
                genres=["pop"],
                services=["ads"],
            )
            sync_marketer_domain_fields(marketer)
            db.session.add(marketer)
            db.session.commit()
            key = domain_key("https://existing-agency.example.com")

            with patch("app.services.discovery_pipeline.WebDirectoryConnector") as seed_mock:
                seed_mock.return_value.discover.return_value = [
                    {
                        "url": "https://existing-agency.example.com",
                        "title": "Existing Agency",
                        "snippet": "contact us pricing music marketing agency",
                        "source": "directory_seed",
                    },
                    {
                        "url": "https://brand-new-agency.example.com",
                        "title": "Brand New Agency",
                        "snippet": "contact us pricing music marketing agency",
                        "source": "directory_seed",
                    },
                ]
                with patch("app.services.discovery_pipeline.SearchApiConnector") as serp_mock:
                    serp_mock.return_value.api_key = ""
                    with patch("app.services.discovery_pipeline.RedditConnector") as reddit_mock:
                        reddit_mock.return_value.discover.return_value = []
                        stats = {}
                        results = _gather_candidates(limit=10, queries=[], stats=stats)
                        urls = [r["url"] for r in results]
                        assert "https://existing-agency.example.com" not in urls
                        assert any("brand-new-agency" in u for u in urls)
                        assert stats.get("skipped_known_catalog", 0) >= 1


class TestSerpBudget:
    def test_default_budget_is_small(self):
        assert serpapi_query_budget() <= 3
