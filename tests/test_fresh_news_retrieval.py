import unittest
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from app import create_app
from app.models.article import Article
from app.providers.base_provider import NewsProvider, ProviderError, RateLimitError
from app.providers.gdelt_provider import GDELTProvider
from app.repositories.article_repository import ArticleRepository, canonicalize_url
from app.services.article_retrieval_service import ArticleRetrievalService
from app.services.search_orchestrator import SearchOrchestrator


class MockLiveProvider(NewsProvider):
    """Deterministic mock provider simulating live fresh news retrieval."""

    def __init__(self, responses=None):
        self.call_count = 0
        self.last_query = None
        self.responses = responses or []

    def search(self, query):
        self.call_count += 1
        self.last_query = query
        if isinstance(self.responses, Exception):
            raise self.responses
        if callable(self.responses):
            return self.responses(self.call_count, query)
        return list(self.responses)


class FreshNewsRetrievalTestCase(unittest.TestCase):
    def setUp(self):
        self.database_directory = TemporaryDirectory()
        self.db_path = f"{self.database_directory.name}/test_fresh_news.db"
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

    def test_task1_gdelt_is_default_live_provider(self):
        """Task 1: Verify GDELT is the default configured live news provider."""
        temp_dir = TemporaryDirectory()
        try:
            default_app = create_app(
                {
                    "TESTING": True,
                    "DATABASE_PATH": f"{temp_dir.name}/default.db",
                }
            )
            # Default provider config is gdelt
            self.assertEqual(default_app.config["NEWS_PROVIDER"], "gdelt")
            orchestrator = default_app.extensions["search_orchestrator"]
            multi_provider = orchestrator.search_service
            # MultiProvider wraps the GDELTProvider
            self.assertTrue(any(isinstance(p, GDELTProvider) for p in multi_provider.providers))
        finally:
            temp_dir.cleanup()

    def test_task2_requests_fresh_provider_results_on_every_user_search(self):
        """Task 2: On every user search, request fresh provider results."""
        provider = MockLiveProvider()
        self.set_provider(provider)

        # First search
        response1 = self.client.post("/api/search", json={"query": "renewable energy"})
        self.assertEqual(response1.status_code, 200)
        self.assertEqual(provider.call_count, 1)
        self.assertEqual(provider.last_query, "renewable energy")

        # Second search for different topic
        response2 = self.client.post("/api/search", json={"query": "quantum computing"})
        self.assertEqual(response2.status_code, 200)
        self.assertEqual(provider.call_count, 2)
        self.assertEqual(provider.last_query, "quantum computing")

        # Repeat search for same topic also requests fresh results
        response3 = self.client.post("/api/search", json={"query": "renewable energy"})
        self.assertEqual(response3.status_code, 200)
        self.assertEqual(provider.call_count, 3)

    def test_task3_and_task4_sqlite_persistence_and_no_replacement_of_database(self):
        """Tasks 3 & 4: Continue using SQLite for persistence; do not replace database with live calls."""
        # Pre-seed SQLite with a historical article
        historical = Article(
            title="Early Solar Breakthroughs",
            url="https://example.com/solar-history",
            publisher="Science Daily",
            publication_date="20240115000000",
            description="Initial solar panel efficiency record established.",
            source_provider="gdelt",
        )
        self.repository.save_article(historical)
        self.assertEqual(self.repository.count_articles(), 1)

        # Provider returns a brand new fresh article
        fresh_article = Article(
            title="Solar Milestone Reached",
            url="https://example.com/solar-latest",
            publisher="Tech Chronicle",
            publication_date="20260920000000",
            description="Next-generation perovskite cells reach commercial market.",
            source_provider="gdelt",
        )
        provider = MockLiveProvider([fresh_article])
        self.set_provider(provider)

        response = self.client.post("/api/search", json={"query": "solar"})
        self.assertEqual(response.status_code, 200)
        data = response.json
        self.assertTrue(data["success"])

        # Both the historical and fresh articles are returned
        urls = [item["url"] for item in data["results"]]
        self.assertIn("https://example.com/solar-history", urls)
        self.assertIn("https://example.com/solar-latest", urls)

        # Both articles are now persistently stored in SQLite
        self.assertEqual(self.repository.count_articles(), 2)

    def test_task5_store_newly_retrieved_articles_with_retrieved_at(self):
        """Task 5: Store newly retrieved articles with retrieved_at, and update on re-retrieval."""
        article = Article(
            title="Fusion Energy Test",
            url="https://example.com/fusion-test",
            publisher="Physics World",
            publication_date="20260915000000",
            description="Reactor maintains sustained plasma for record duration.",
            source_provider="gdelt",
        )
        provider = MockLiveProvider([article])
        self.set_provider(provider)

        # First retrieval
        response = self.client.post("/api/search", json={"query": "fusion"})
        self.assertEqual(response.status_code, 200)
        stored1 = self.repository.find_by_canonical_url("https://example.com/fusion-test")
        self.assertIsNotNone(stored1)
        self.assertIsNotNone(stored1["retrieved_at"])
        initial_retrieved_at = stored1["retrieved_at"]

        # Later retrieval with custom timestamp to verify update
        later_timestamp = "2026-09-30T22:00:00+00:00"
        self.repository.save_article(article, retrieved_at=later_timestamp)
        stored2 = self.repository.find_by_canonical_url("https://example.com/fusion-test")
        self.assertEqual(stored2["retrieved_at"], later_timestamp)
        self.assertNotEqual(stored2["retrieved_at"], initial_retrieved_at)

    def test_task6_deduplicate_using_canonical_url(self):
        """Task 6: Deduplicate articles using canonical_url across variations."""
        art1 = Article(
            title="Electric Aviation Test Flight",
            url="https://EXAMPLE.com/aviation?utm_source=twitter&utm_medium=social#flight1",
            publisher="Aviation Weekly",
            publication_date="20260910000000",
            description="First commercial electric aircraft completes test route.",
            source_provider="gdelt",
        )
        art2 = Article(
            title="Electric Aviation Test Flight",
            url="https://example.com/aviation?fbclid=12345",
            publisher="Aviation Weekly",
            publication_date="20260910000000",
            description="First commercial electric aircraft completes test route.",
            source_provider="gdelt",
        )
        provider = MockLiveProvider([art1, art2])
        self.set_provider(provider)

        response = self.client.post("/api/search", json={"query": "electric aviation"})
        self.assertEqual(response.status_code, 200)
        data = response.json
        # Only 1 unique article returned and stored
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(self.repository.count_articles(), 1)

    def test_task7_do_not_overwrite_existing_historical_articles_unnecessarily(self):
        """Task 7: Do not overwrite existing historical articles unnecessarily when re-retrieved."""
        # Pre-seed rich historical article with description and verified publication date
        historical = Article(
            title="Historical Exploration Mission",
            url="https://example.com/mission-report",
            publisher="Space Exploration Society",
            publication_date="20250601000000",
            description="Comprehensive mission archive with telemetry and ground samples.",
            source_provider="gdelt",
        )
        self.repository.save_article(historical)

        # Fresh provider retrieval returns the same article with description=None (typical GDELT payload)
        fresh_variant = Article(
            title="Mission Report Update",
            url="https://example.com/mission-report",
            publisher="Space Exploration Society",
            publication_date="20260930000000",
            description=None,  # Provider lacks description
            source_provider="gdelt",
        )
        provider = MockLiveProvider([fresh_variant])
        self.set_provider(provider)

        response = self.client.post("/api/search", json={"query": "exploration mission"})
        self.assertEqual(response.status_code, 200)
        data = response.json
        self.assertEqual(len(data["results"]), 1)
        result_item = data["results"][0]

        # The historical description is preserved, not wiped to None
        self.assertEqual(result_item["description"], "Comprehensive mission archive with telemetry and ground samples.")
        # SQLite still contains the preserved historical record
        stored = self.repository.find_by_canonical_url("https://example.com/mission-report")
        self.assertEqual(stored["description"], "Comprehensive mission archive with telemetry and ground samples.")
        self.assertEqual(stored["publication_date"], "20250601000000")

    def test_task8_preserve_publication_date_separately_from_retrieved_at(self):
        """Task 8: Preserve publication_date separately from retrieved_at."""
        article = Article(
            title="Historic Treaty Signed",
            url="https://example.com/treaty",
            publisher="Diplomatic Gazette",
            publication_date="20240401093000",
            description="Treaty signed by delegate nations.",
            source_provider="gdelt",
        )
        provider = MockLiveProvider([article])
        self.set_provider(provider)

        response = self.client.post("/api/search", json={"query": "treaty"})
        self.assertEqual(response.status_code, 200)
        res = response.json["results"][0]

        # publication_date and retrieved_at are distinct
        self.assertEqual(res["publication_date"], "20240401093000")
        self.assertIsNotNone(res["retrieved_at"])
        self.assertNotEqual(res["publication_date"], res["retrieved_at"])

        # Timeline service uses publication_date, not retrieved_at
        timeline_entry = response.json["timeline"][0]
        self.assertEqual(timeline_entry["date"], "2024-04-01")

    def test_task9_provider_failures_and_rate_limits_gracefully_handled(self):
        """Task 9: Keep provider failures and rate limits gracefully handled."""
        # 1. Rate limit with stored articles -> returns HTTP 200 with stored articles and provider_status
        stored = Article(
            title="Cached Climate Report",
            url="https://example.com/cached-climate",
            publisher="Climate Institute",
            publication_date="20260901000000",
            description="Cached climate summary.",
            source_provider="gdelt",
        )
        self.repository.save_article(stored)
        self.set_provider(MockLiveProvider(RateLimitError()))

        res_rate = self.client.post("/api/search", json={"query": "climate"})
        self.assertEqual(res_rate.status_code, 200)
        self.assertTrue(res_rate.json["success"])
        self.assertEqual(res_rate.json["provider_status"], "rate_limited")
        self.assertIn("temporarily rate-limited", res_rate.json["message"])
        self.assertEqual(len(res_rate.json["results"]), 1)

        # 2. Rate limit with NO stored articles -> returns controlled HTTP 429
        res_rate_empty = self.client.post("/api/search", json={"query": "nonexistent"})
        self.assertEqual(res_rate_empty.status_code, 429)
        self.assertFalse(res_rate_empty.json["success"])
        self.assertEqual(res_rate_empty.json["provider_status"], "rate_limited")

        # 3. Provider failure with stored articles -> returns HTTP 200 with stored articles
        self.set_provider(MockLiveProvider(ProviderError("Network unreachable")))
        res_fail = self.client.post("/api/search", json={"query": "climate"})
        self.assertEqual(res_fail.status_code, 200)
        self.assertTrue(res_fail.json["success"])
        self.assertEqual(res_fail.json["provider_status"], "provider_unavailable")
        self.assertIn("temporarily unavailable", res_fail.json["message"])
        self.assertEqual(len(res_fail.json["results"]), 1)

        # 4. Provider failure with NO stored articles -> returns controlled HTTP 502
        res_fail_empty = self.client.post("/api/search", json={"query": "nonexistent"})
        self.assertEqual(res_fail_empty.status_code, 502)
        self.assertFalse(res_fail_empty.json["success"])
        self.assertEqual(res_fail_empty.json["provider_status"], "provider_unavailable")

    def test_task10_provider_status_returned_to_frontend(self):
        """Task 10: Return provider status to the frontend in all API responses."""
        # Success response
        article = Article(
            title="Clean Tech Progress",
            url="https://example.com/clean-tech",
            publisher="Clean Energy News",
            publication_date="20260925000000",
            description="Advancements in energy storage.",
            source_provider="gdelt",
        )
        self.set_provider(MockLiveProvider([article]))

        response = self.client.post("/api/search", json={"query": "clean tech"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("provider_status", response.json)
        self.assertEqual(response.json["provider_status"], "ok")


if __name__ == "__main__":
    unittest.main()
