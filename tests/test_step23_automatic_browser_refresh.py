import json
import os
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app import create_app
from app.models.article import Article
from app.providers.base_provider import NewsProvider, ProviderError, RateLimitError
from app.services.search_orchestrator import SearchOrchestrator


class MockStep23PollingProvider(NewsProvider):
    """Mock news provider simulating sequential polling cycles."""

    def __init__(self, batches, name="mock_polling"):
        super().__init__()
        self.name = name
        self.batches = list(batches)
        self.call_count = 0
        self.queries_received = []

    def search(self, query):
        self.queries_received.append(query)
        idx = min(self.call_count, len(self.batches) - 1)
        self.call_count += 1
        batch = self.batches[idx]
        if isinstance(batch, Exception):
            raise batch
        return list(batch)


class Step23AutomaticBrowserRefreshTestCase(unittest.TestCase):
    """Test suite verifying Step 23: Automatic real-time browser refresh requirements."""

    def setUp(self):
        self.database_directory = TemporaryDirectory()
        self.db_path = f"{self.database_directory.name}/test_step23_refresh.db"
        self.app = create_app(
            {
                "TESTING": True,
                "NEWS_PROVIDER": "mock",
                "DATABASE_PATH": self.db_path,
                "THENEWSAPI_API_KEY": "super_secret_thenewsapi_token_step23",
                "NEWSAPI_KEY": "super_secret_newsapi_key_step23",
            }
        )
        self.client = self.app.test_client()
        self.repository = self.app.extensions["article_repository"]

    def tearDown(self):
        self.database_directory.cleanup()

    def set_provider(self, provider):
        orchestrator = SearchOrchestrator(
            provider,
            self.repository,
            ai_provider=self.app.extensions["ai_provider"],
        )
        self.app.extensions["search_orchestrator"] = orchestrator
        return orchestrator

    # 1. Polling sends current search query to existing search API
    def test_polling_sends_active_query_to_search_api(self):
        art = Article(
            title="Fusion Energy Commercialization Roadmap",
            url="https://example.com/fusion-roadmap",
            publisher="Science Wire",
            publication_date="2026-09-01T12:00:00Z",
            description="Milestone reached in sustained plasma confinement.",
            source_provider="mock",
        )
        provider = MockStep23PollingProvider([[art], [art]])
        self.set_provider(provider)

        # Initial search
        res1 = self.client.post("/api/search", json={"query": "fusion energy"})
        self.assertEqual(res1.status_code, 200)
        data1 = res1.json
        self.assertTrue(data1["success"])
        self.assertEqual(data1["query"], "fusion energy")

        # Subsequent poll cycle with same active query
        res2 = self.client.post("/api/search", json={"query": "fusion energy"})
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json
        self.assertTrue(data2["success"])
        self.assertEqual(provider.queries_received, ["fusion energy", "fusion energy"])

    # 2. Sequential polling detects genuinely new articles and assigns article IDs
    def test_polling_detects_genuinely_new_articles_and_updates_timeline(self):
        art1 = Article(
            title="Quantum Chip Announcement",
            url="https://tech.example.com/quantum-1",
            publisher="Tech News",
            publication_date="2026-09-10T10:00:00Z",
            description="1000-qubit processor announced.",
            source_provider="mock",
        )
        art2 = Article(
            title="Independent Benchmark Validates Quantum Chip",
            url="https://journal.example.com/quantum-2",
            publisher="Physics Journal",
            publication_date="2026-09-15T14:00:00Z",
            description="Third-party laboratory confirms quantum advantage.",
            source_provider="mock",
        )

        provider = MockStep23PollingProvider([[art1], [art1, art2]])
        self.set_provider(provider)

        # Poll 1
        res1 = self.client.post("/api/search", json={"query": "quantum chip"})
        data1 = res1.json
        self.assertEqual(len(data1["results"]), 1)
        self.assertIsNotNone(data1["results"][0]["article_id"])
        first_id = data1["results"][0]["article_id"]

        # Poll 2 (New article arrives)
        res2 = self.client.post("/api/search", json={"query": "quantum chip"})
        data2 = res2.json
        self.assertEqual(len(data2["results"]), 2)

        # Verify article IDs are present and distinct
        returned_ids = {a["article_id"] for a in data2["results"]}
        self.assertIn(first_id, returned_ids)
        self.assertEqual(len(returned_ids), 2)

        # Timeline and repository updated
        self.assertEqual(len(data2["timeline"]), 2)
        self.assertEqual(self.repository.count_articles(), 2)

    # 3. Polling deduplicates by canonical URL and prevents duplicate cards/records
    def test_polling_deduplicates_by_canonical_url_preventing_duplicates(self):
        art_initial = Article(
            title="Autonomous Drone Delivery Launched",
            url="https://example.com/drone-delivery?utm_source=twitter&utm_medium=social",
            publisher="Aviation Today",
            publication_date="2026-09-05T08:00:00Z",
            description="Commercial drone delivery expands to three new metropolitan areas.",
            source_provider="mock",
        )
        art_poll = Article(
            title="Autonomous Drone Delivery Launched",
            url="https://EXAMPLE.com/drone-delivery#overview",
            publisher="Aviation Today",
            publication_date="2026-09-05T08:00:00Z",
            description="Commercial drone delivery expands to three new metropolitan areas.",
            source_provider="mock",
        )

        provider = MockStep23PollingProvider([[art_initial], [art_poll]])
        self.set_provider(provider)

        # Poll 1
        res1 = self.client.post("/api/search", json={"query": "drone delivery"})
        self.assertEqual(len(res1.json["results"]), 1)
        initial_id = res1.json["results"][0]["article_id"]

        # Poll 2
        res2 = self.client.post("/api/search", json={"query": "drone delivery"})
        self.assertEqual(len(res2.json["results"]), 1)
        # Deduplication preserves the single stored article without creating a duplicate
        self.assertEqual(self.repository.count_articles(), 1)
        self.assertEqual(res2.json["results"][0]["article_id"], initial_id)

    # 4. Empty response during polling preserves existing coverage without breaking
    def test_polling_empty_provider_response_preserves_existing_coverage(self):
        stored_art = Article(
            title="Space Telescope Captures Exoplanet Atmosphere",
            url="https://example.com/exoplanet",
            publisher="Cosmos Daily",
            publication_date="2026-09-12T16:00:00Z",
            description="Direct atmospheric spectroscopy of temperate terrestrial world.",
            source_provider="mock",
        )
        # First poll succeeds, second poll returns empty list []
        provider = MockStep23PollingProvider([[stored_art], []])
        self.set_provider(provider)

        # Poll 1
        self.client.post("/api/search", json={"query": "exoplanet"})

        # Poll 2 (empty response)
        res2 = self.client.post("/api/search", json={"query": "exoplanet"})
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json
        self.assertTrue(data2["success"])
        self.assertEqual(len(data2["results"]), 1)
        self.assertEqual(data2["results"][0]["title"], "Space Telescope Captures Exoplanet Atmosphere")

    # 5. Provider outage (HTTP 500 / ProviderError) during polling preserves existing coverage
    def test_polling_provider_failure_preserves_existing_results(self):
        stored_art = Article(
            title="Deep Sea Mapping Expedition Concluded",
            url="https://example.com/deep-sea",
            publisher="Oceanographic Institute",
            publication_date="2026-09-18T11:00:00Z",
            description="High-resolution bathymetric survey reveals extensive hydrothermal field.",
            source_provider="mock",
        )
        provider = MockStep23PollingProvider([[stored_art], ProviderError("500 Internal Server Error")])
        self.set_provider(provider)

        # Poll 1
        self.client.post("/api/search", json={"query": "deep sea"})

        # Poll 2 (provider fails)
        res2 = self.client.post("/api/search", json={"query": "deep sea"})
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json
        self.assertTrue(data2["success"])
        self.assertEqual(data2["provider_status"], "provider_unavailable")
        self.assertEqual(len(data2["results"]), 1)
        self.assertEqual(data2["results"][0]["title"], "Deep Sea Mapping Expedition Concluded")

    # 6. Provider rate-limiting (HTTP 429) during polling preserves existing coverage
    def test_polling_rate_limiting_preserves_existing_results(self):
        stored_art = Article(
            title="Grid-Scale Flow Battery Installed",
            url="https://example.com/flow-battery",
            publisher="Clean Energy Wire",
            publication_date="2026-09-22T09:00:00Z",
            description="100MWh vanadium redox system enters commercial service.",
            source_provider="mock",
        )
        provider = MockStep23PollingProvider([[stored_art], RateLimitError("Rate limit exceeded")])
        self.set_provider(provider)

        # Poll 1
        self.client.post("/api/search", json={"query": "flow battery"})

        # Poll 2 (rate limited)
        res2 = self.client.post("/api/search", json={"query": "flow battery"})
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json
        self.assertTrue(data2["success"])
        self.assertEqual(data2["provider_status"], "rate_limited")
        self.assertEqual(len(data2["results"]), 1)

    # 7. Polling with multi-provider integration (GDELT and The News API)
    def test_multi_provider_polling_cycle(self):
        from app.providers.multi_provider import MultiProvider

        art_gdelt = Article(
            title="Antarctic Ice Core Drilling Milestone",
            url="https://gdelt.example.com/ice-core",
            publisher="Polar Research",
            publication_date="2026-09-02T10:00:00Z",
            description="Core reaches 1.5 million year old ice stratum.",
            source_provider="gdelt",
        )
        art_thenewsapi = Article(
            title="Climate Scientists Analyze Oldest Ice Sample",
            url="https://thenewsapi.example.com/ice-core-analysis",
            publisher="International Science",
            publication_date="2026-09-03T15:00:00Z",
            description="Initial atmospheric gas measurements corroborate past CO2 models.",
            source_provider="thenewsapi",
        )

        p_gdelt = MockStep23PollingProvider([[art_gdelt], [art_gdelt]], name="gdelt")
        p_thenewsapi = MockStep23PollingProvider([[], [art_thenewsapi]], name="thenewsapi")

        multi = MultiProvider(providers=[p_gdelt, p_thenewsapi])
        self.set_provider(multi)

        # Poll 1
        res1 = self.client.post("/api/search", json={"query": "ice core"})
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(len(res1.json["results"]), 1)
        self.assertTrue(res1.json["providers"]["gdelt"]["success"])

        # Poll 2 (The News API returns new article)
        res2 = self.client.post("/api/search", json={"query": "ice core"})
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(len(res2.json["results"]), 2)
        self.assertTrue(res2.json["providers"]["gdelt"]["success"])
        self.assertTrue(res2.json["providers"]["thenewsapi"]["success"])

    # 8. Requirement 18: Never expose API keys in browser responses or payloads
    def test_no_api_keys_exposed_to_browser_during_polling(self):
        secret_thenewsapi = "super_secret_thenewsapi_token_step23"
        secret_newsapi = "super_secret_newsapi_key_step23"

        art = Article(
            title="Cybersecurity Advisory Issued",
            url="https://example.com/advisory",
            publisher="Security Alert",
            publication_date="2026-09-25T12:00:00Z",
            description="Critical advisory regarding firmware updates.",
            source_provider="mock",
        )
        provider = MockStep23PollingProvider([[art]])
        self.set_provider(provider)

        # Polling request to search API
        res = self.client.post("/api/search", json={"query": "cybersecurity"})
        self.assertEqual(res.status_code, 200)
        raw_response = res.data.decode("utf-8")

        self.assertNotIn(secret_thenewsapi, raw_response)
        self.assertNotIn(secret_newsapi, raw_response)

        # HTML page load
        res_html = self.client.get("/")
        raw_html = res_html.data.decode("utf-8")
        self.assertNotIn(secret_thenewsapi, raw_html)
        self.assertNotIn(secret_newsapi, raw_html)

    # 9. Verify UI and JS frontend contracts for Step 23
    def test_frontend_implements_step23_polling_contracts(self):
        with open("static/js/main.js", "r", encoding="utf-8") as f:
            js = f.read()

        # Requirement 1: Polling mechanism
        self.assertIn("triggerRefresh", js)
        self.assertIn("scheduleNextPoll", js)

        # Requirement 2 & 3: Default 60s configurable interval
        self.assertIn("60000", js)
        self.assertIn("refreshIntervalMs", js)

        # Requirement 4: No WebSockets
        self.assertNotIn("WebSocket(", js)
        self.assertNotIn("new WebSocket", js)

        # Requirement 5: No full page reload
        self.assertNotIn("location.reload()", js)

        # Requirement 6: Only poll when search query is active
        self.assertIn("currentQuery", js)

        # Requirement 7: Prevent overlapping requests
        self.assertIn("isRefreshing", js)

        # Requirement 8: Send current query to existing search API
        self.assertIn("JSON.stringify({ query: currentQuery })", js)

        # Requirement 9: Compare using article ID when available, canonical URL as fallback
        self.assertIn("knownArticleIds", js)
        self.assertIn("knownCanonicalUrls", js)

        # Requirement 12: Updates timeline, grouping, article list, and last updated
        self.assertIn("renderTimeline", js)
        self.assertIn("renderLegacyGroups", js)
        self.assertIn("renderVerificationDashboard", js)
        self.assertIn("updateLastUpdatedDisplay", js)

        # Requirement 13 & 14: "Last updated:" and "New articles available"
        self.assertIn("Last updated:", js)
        self.assertIn("New articles available", js)

        # Requirement 15: Manual Refresh button
        self.assertIn("manualRefreshBtn", js)

        # Requirement 17: Page Visibility API
        self.assertIn("visibilitychange", js)
        self.assertIn("document.hidden", js)


if __name__ == "__main__":
    unittest.main()
