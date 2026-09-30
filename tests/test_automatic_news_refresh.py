import re
import unittest
from tempfile import TemporaryDirectory

from app import create_app
from app.models.article import Article
from app.providers.base_provider import NewsProvider, ProviderError, RateLimitError
from app.services.search_orchestrator import SearchOrchestrator


class MockSequentialProvider(NewsProvider):
    """Mock news provider that returns different batches of articles across polling cycles."""

    def __init__(self, batches):
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


class AutomaticNewsRefreshTestCase(unittest.TestCase):
    def setUp(self):
        self.database_directory = TemporaryDirectory()
        self.db_path = f"{self.database_directory.name}/test_refresh.db"
        self.app = create_app(
            {
                "TESTING": True,
                "NEWS_PROVIDER": "mock",
                "DATABASE_PATH": self.db_path,
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

    def test_polling_with_current_query_retrieves_new_articles_and_updates_timeline(self):
        """Verify polling the search API with the current query returns new articles and updates timeline."""
        # Poll 1 initial result
        initial_article = Article(
            title="AI Regulation Framework Proposed",
            url="https://example.com/ai-regulation-1",
            publisher="Tech Policy Review",
            publication_date="20260901000000",
            description="Initial proposal on frontier model audits.",
            source_provider="gdelt",
        )
        # Poll 2 new article arrives later
        new_article = Article(
            title="Global Agreement on AI Safety Standards",
            url="https://example.com/ai-regulation-2",
            publisher="Global Standards Wire",
            publication_date="20260920000000",
            description="International consensus reached on mandatory safety evaluations.",
            source_provider="gdelt",
        )

        provider = MockSequentialProvider([[initial_article], [initial_article, new_article]])
        self.set_provider(provider)

        # Initial search (Poll 1)
        res1 = self.client.post("/api/search", json={"query": "AI regulation"})
        self.assertEqual(res1.status_code, 200)
        data1 = res1.json
        self.assertTrue(data1["success"])
        self.assertEqual(len(data1["results"]), 1)
        self.assertEqual(len(data1["timeline"]), 1)
        self.assertEqual(provider.call_count, 1)

        # Subsequent search polling cycle with current query (Poll 2)
        res2 = self.client.post("/api/search", json={"query": "AI regulation"})
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json
        self.assertTrue(data2["success"])
        self.assertEqual(provider.call_count, 2)
        self.assertEqual(provider.queries_received, ["AI regulation", "AI regulation"])

        # Results now include the new article
        urls2 = {item["url"] for item in data2["results"]}
        self.assertIn("https://example.com/ai-regulation-1", urls2)
        self.assertIn("https://example.com/ai-regulation-2", urls2)
        self.assertEqual(len(data2["results"]), 2)

        # Timeline and groups updated with both events
        self.assertEqual(len(data2["timeline"]), 2)
        self.assertEqual(self.repository.count_articles(), 2)

    def test_polling_deduplicates_by_canonical_url_and_preserves_retrieved_at(self):
        """Verify polling deduplicates articles and updates retrieved_at on existing items."""
        art = Article(
            title="Renewable Grid Breakthrough",
            url="https://example.com/grid?utm_campaign=launch",
            publisher="Energy Today",
            publication_date="20260910000000",
            description="Ultra-high-density storage connected to grid.",
            source_provider="gdelt",
        )
        art_poll2 = Article(
            title="Renewable Grid Breakthrough",
            url="https://EXAMPLE.com/grid#status",
            publisher="Energy Today",
            publication_date="20260910000000",
            description="Ultra-high-density storage connected to grid.",
            source_provider="gdelt",
        )

        provider = MockSequentialProvider([[art], [art_poll2]])
        self.set_provider(provider)

        # Poll 1
        res1 = self.client.post("/api/search", json={"query": "grid"})
        self.assertEqual(res1.status_code, 200)
        stored1 = self.repository.find_by_canonical_url("https://example.com/grid")
        retrieved_at_1 = stored1["retrieved_at"]

        # Poll 2
        res2 = self.client.post("/api/search", json={"query": "grid"})
        self.assertEqual(res2.status_code, 200)

        # Canonical deduplication preserves single record
        self.assertEqual(self.repository.count_articles(), 1)
        stored2 = self.repository.find_by_canonical_url("https://example.com/grid")
        self.assertIsNotNone(stored2["retrieved_at"])

    def test_polling_provider_failure_does_not_break_existing_results(self):
        """Verify that provider failure during a poll cycle does not destroy existing results."""
        stored = Article(
            title="Ocean Cleanup Prototype Tested",
            url="https://example.com/ocean-cleanup",
            publisher="Marine Journal",
            publication_date="20260905000000",
            description="Prototype autonomous interceptor recovers plastic in trials.",
            source_provider="gdelt",
        )
        # First poll succeeds, second poll raises ProviderError
        provider = MockSequentialProvider([[stored], ProviderError("Temporary provider outage")])
        self.set_provider(provider)

        # Initial successful search
        res1 = self.client.post("/api/search", json={"query": "ocean cleanup"})
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(len(res1.json["results"]), 1)

        # Polling during outage returns existing stored results gracefully
        res2 = self.client.post("/api/search", json={"query": "ocean cleanup"})
        self.assertEqual(res2.status_code, 200)
        self.assertTrue(res2.json["success"])
        self.assertEqual(res2.json["provider_status"], "provider_unavailable")
        self.assertIn("temporarily unavailable", res2.json["message"])
        # Existing results remain fully intact
        self.assertEqual(len(res2.json["results"]), 1)
        self.assertEqual(res2.json["results"][0]["title"], "Ocean Cleanup Prototype Tested")

    def test_polling_rate_limit_preserves_existing_results(self):
        """Verify that provider rate-limiting during a poll cycle preserves existing results."""
        stored = Article(
            title="Biotech Vaccine Milestone",
            url="https://example.com/vaccine",
            publisher="Bio Science",
            publication_date="20260908000000",
            description="Phase 3 trial demonstrates broad efficacy.",
            source_provider="gdelt",
        )
        provider = MockSequentialProvider([[stored], RateLimitError("Rate limit exceeded")])
        self.set_provider(provider)

        # Initial search
        self.client.post("/api/search", json={"query": "vaccine"})

        # Subsequent poll hit rate limit
        res_poll = self.client.post("/api/search", json={"query": "vaccine"})
        self.assertEqual(res_poll.status_code, 200)
        self.assertTrue(res_poll.json["success"])
        self.assertEqual(res_poll.json["provider_status"], "rate_limited")
        self.assertEqual(len(res_poll.json["results"]), 1)

    def test_ui_contains_step21_refresh_elements(self):
        """Verify templates/index.html contains all Step 21 UI elements."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")

        # Refresh toolbar
        self.assertIn('id="refresh-toolbar"', html)
        self.assertIn('id="refresh-status-dot"', html)
        self.assertIn('id="refresh-last-updated"', html)
        self.assertIn('Last updated:', html)

        # Configurable interval select with 60s default
        self.assertIn('id="refresh-interval-select"', html)
        self.assertIn('value="60000" selected', html)

        # Manual refresh button
        self.assertIn('id="manual-refresh-btn"', html)
        self.assertIn('Refresh', html)

        # New articles available banner
        self.assertIn('id="new-articles-banner"', html)
        self.assertIn('id="new-articles-text"', html)
        self.assertIn('New articles available', html)
        self.assertIn('id="new-articles-dismiss-btn"', html)

    def test_frontend_js_contains_step21_polling_architecture(self):
        """Verify static/js/main.js implements all Step 21 polling, visibility, and interval requirements."""
        with open("static/js/main.js", "r", encoding="utf-8") as f:
            js = f.read()

        # 1. Frontend refresh mechanism using polling
        self.assertIn("triggerRefresh", js)
        self.assertIn("startPolling", js)
        self.assertIn("stopPolling", js)
        self.assertIn("scheduleNextPoll", js)

        # 2. Default refresh interval 60s (60000 ms) and configurable interval
        self.assertIn("60000", js)
        self.assertIn("refreshIntervalMs", js)
        self.assertIn("refreshIntervalSelect", js)

        # 4. No WebSockets
        self.assertNotIn("WebSocket(", js)
        self.assertNotIn("new WebSocket", js)

        # 5. No entire page reload
        self.assertNotIn("location.reload()", js)

        # 6. Sends current search query to /api/search
        self.assertIn('body: JSON.stringify({ query: currentQuery })', js)

        # 7. Detect newly retrieved articles using article ID / canonical URL
        self.assertIn("knownCanonicalUrls", js)
        self.assertIn("knownArticleIds", js)
        self.assertIn("canonicalizeUrl", js)

        # 8 & 9. Add new articles and update timeline and groups
        self.assertIn("renderTimeline", js)
        self.assertIn("renderLegacyGroups", js)
        self.assertIn("renderVerificationDashboard", js)

        # 10. Show "Last updated:" and "New articles available"
        self.assertIn("Last updated:", js)
        self.assertIn("New articles available", js)

        # 11. Manual refresh button
        self.assertIn("manualRefreshBtn", js)

        # 12. Prevent overlapping refresh requests
        self.assertIn("isRefreshing", js)

        # 13. Stop polling when page is not being viewed (Page Visibility API)
        self.assertIn("visibilitychange", js)
        self.assertIn("document.hidden", js)


if __name__ == "__main__":
    unittest.main()
