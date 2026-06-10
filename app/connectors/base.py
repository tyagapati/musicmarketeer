"""Connectors for discovering marketers from external sources."""
import os
import re

import requests

from app.services.site_urls import domain_key


def _split_env_list(name):
    raw = os.environ.get(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


class SearchApiConnector:
    """Search API connector using SerpAPI (optional)."""

    def __init__(self):
        self.api_key = os.environ.get("SERPAPI_API_KEY", "")
        self.engine = os.environ.get("DISCOVERY_SEARCH_ENGINE", "google")
        self.country = os.environ.get("DISCOVERY_SEARCH_COUNTRY", "us")
        self.language = os.environ.get("DISCOVERY_SEARCH_LANGUAGE", "en")
        self.max_results = int(os.environ.get("DISCOVERY_SEARCH_RESULTS_PER_QUERY", "5"))

    def discover(
        self,
        queries,
        *,
        known_domains=None,
        max_queries=None,
        page_offset=0,
    ):
        """
        Run up to max_queries SerpAPI searches, skipping known catalog domains.

        Yields candidates one query at a time so the pipeline can stop early.
        """
        if not self.api_key:
            return []

        known_domains = known_domains or set()
        max_queries = max_queries if max_queries is not None else len(queries)
        out = []
        self.queries_run = 0

        for query in queries:
            if self.queries_run >= max_queries:
                break
            self.queries_run += 1
            params = {
                "engine": self.engine,
                "q": query,
                "api_key": self.api_key,
                "gl": self.country,
                "hl": self.language,
                "num": self.max_results,
            }
            if page_offset and self.engine == "google":
                params["start"] = page_offset
            try:
                response = requests.get(
                    "https://serpapi.com/search.json",
                    params=params,
                    timeout=12,
                )
                response.raise_for_status()
                data = response.json()
            except Exception:
                continue

            for item in data.get("organic_results", []):
                link = (item.get("link") or "").strip()
                if not link:
                    continue
                key = domain_key(link)
                if key and key in known_domains:
                    continue
                out.append(
                    {
                        "url": link,
                        "title": (item.get("title") or "").strip(),
                        "snippet": (item.get("snippet") or "").strip(),
                        "source": "search_api",
                        "query": query,
                    }
                )
        return out


class RedditConnector:
    def __init__(self):
        self.client_id = os.environ.get("REDDIT_CLIENT_ID", "")
        self.client_secret = os.environ.get("REDDIT_CLIENT_SECRET", "")
        self.user_agent = os.environ.get("REDDIT_USER_AGENT", "soundmatch/1.0")

    def discover(self, queries, *, known_domains=None):
        known_domains = known_domains or set()
        discovered = []
        discovered.extend(self._discover_from_env(known_domains))
        discovered.extend(self._discover_from_praw(queries, known_domains))
        return discovered

    def _discover_from_env(self, known_domains):
        urls = _split_env_list("REDDIT_DISCOVERY_URLS")
        out = []
        for url in urls:
            key = domain_key(url)
            if key and key in known_domains:
                continue
            out.append(
                {
                    "url": url,
                    "title": "Reddit discovery candidate",
                    "snippet": "Seeded from REDDIT_DISCOVERY_URLS",
                    "source": "reddit_seed",
                    "query": "seed",
                }
            )
        return out

    def _discover_from_praw(self, queries, known_domains):
        if not (self.client_id and self.client_secret):
            return []
        try:
            import praw
        except Exception:
            return []

        subreddits = os.environ.get("REDDIT_DISCOVERY_SUBREDDITS", "musicmarketing,wearethemusicmakers")
        subreddit = "+".join([s.strip() for s in subreddits.split(",") if s.strip()])
        limit = int(os.environ.get("REDDIT_DISCOVERY_LIMIT", "25"))
        reddit = praw.Reddit(
            client_id=self.client_id,
            client_secret=self.client_secret,
            user_agent=self.user_agent,
        )
        found = []
        for query in queries:
            try:
                results = reddit.subreddit(subreddit).search(query, limit=limit, sort="new")
            except Exception:
                continue
            for post in results:
                urls = []
                if getattr(post, "url", ""):
                    urls.append(post.url)
                urls.extend(re.findall(r"https?://[^\s)]+", (getattr(post, "selftext", "") or "")))
                for url in urls:
                    key = domain_key(url)
                    if key and key in known_domains:
                        continue
                    found.append(
                        {
                            "url": url,
                            "title": getattr(post, "title", ""),
                            "snippet": (getattr(post, "selftext", "") or "")[:300],
                            "source": "reddit_api",
                            "query": query,
                        }
                    )
        return found


class WebDirectoryConnector:
    def discover(self, *, known_domains=None):
        known_domains = known_domains or set()
        urls = _split_env_list("DISCOVERY_SEED_URLS")
        out = []
        for url in urls:
            key = domain_key(url)
            if key and key in known_domains:
                continue
            out.append(
                {
                    "url": url,
                    "title": "Directory discovery candidate",
                    "snippet": "Seeded from DISCOVERY_SEED_URLS",
                    "source": "directory_seed",
                    "query": "seed",
                }
            )
        return out
