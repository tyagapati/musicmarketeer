"""Query rotation and SerpAPI budget helpers for discovery."""
from __future__ import annotations

import os

from app import db
from app.models import AppSetting, Marketer, RejectedSite
from app.services.site_urls import domain_key


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def known_catalog_domains() -> set[str]:
    """Domains already in the catalog or on the reject blacklist."""
    keys: set[str] = set()
    for marketer in Marketer.query.filter(Marketer.domain_key.isnot(None)).all():
        if marketer.domain_key:
            keys.add(marketer.domain_key)
        elif marketer.website:
            key = domain_key(marketer.website)
            if key:
                keys.add(key)
    for row in RejectedSite.query.all():
        if row.domain_key:
            keys.add(row.domain_key)
    return keys


def _get_setting(key: str, default: str = "0") -> str:
    row = AppSetting.query.get(key)
    if row is None:
        return default
    return row.value or default


def _set_setting(key: str, value: str) -> None:
    row = AppSetting.query.get(key)
    if row is None:
        db.session.add(AppSetting(key=key, value=value))
    else:
        row.value = value
    db.session.commit()


def select_queries_for_cycle(all_queries: list[str]) -> list[str]:
    """
    Rotate through the query plan so each cycle uses a small subset.

    Avoids firing the full query list (and burning SerpAPI quota) every run.
    """
    if not all_queries:
        return []
    per_cycle = max(1, _env_int("DISCOVERY_QUERIES_PER_CYCLE", 2))
    offset = int(_get_setting("discovery_query_offset", "0") or "0")
    selected = [all_queries[(offset + i) % len(all_queries)] for i in range(per_cycle)]
    _set_setting("discovery_query_offset", str((offset + per_cycle) % len(all_queries)))
    return selected


def next_serp_page_offset() -> int:
    """Rotate Google result page offset (0, 10, 20, ...) for fresher SerpAPI results."""
    step = max(1, _env_int("DISCOVERY_SEARCH_RESULTS_PER_QUERY", 5))
    max_pages = max(1, _env_int("DISCOVERY_SERP_MAX_PAGES", 5))
    page = int(_get_setting("discovery_serp_page", "0") or "0")
    start = (page % max_pages) * step
    _set_setting("discovery_serp_page", str(page + 1))
    return start


def serpapi_query_budget() -> int:
    """Max SerpAPI HTTP calls allowed per discovery cycle."""
    return max(0, _env_int("DISCOVERY_MAX_SERPAPI_QUERIES", 2))
