import io
import json
import os
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from app import create_app
from app.database import initialize_database
from app.models.article import Article
from app.providers.base_provider import NewsProvider, ProviderError, RateLimitError
from app.providers.gdelt_provider import GDELTProvider
from app.providers.newsapi_provider import NewsAPIProvider
from app.providers.multi_provider import MultiProvider
from app.repositories.article_repository import ArticleRepository
from app.services.article_retrieval_service import ArticleRetrievalService
from app.services.search_orchestrator import SearchOrchestrator


class MockHTTPResponse:
    def __init__(self, data: dict, status: int = 200):
        self.data = data
        self.status = status

    def read(self):
        return json.dumps(self.data).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class MultipleRealTimeNewsSourcesTestCase(unittest.TestCase):
    """Test suite verifying Step 22: Multiple Real-Time News Sources."""

    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.database_path = os.path.join(self.temp_dir.name, "test_news.db")
        initialize_database(self.database_path)
        self.repository = ArticleRepository(self.database_path)

        self.gdelt_sample_response = {
            "articles": [
                {
                    "title": "Quantum Computing Breakthrough Unveiled",
                    "url": "https://technews.org/quantum-breakthrough?utm_source=gdelt",
                    "domain": "technews.org",
                    "seendate": "20260930100000",
                },
                {
                    "title": "Global Climate Conference Concludes",
                    "url": "https://worldnews.org/climate-summit",
                    "domain": "worldnews.org",
                    "seendate": "20260930090000",
                },
            ]
        }

        self.newsapi_sample_response = {
            "status": "ok",
            "totalResults": 2,
            "articles": [
                {
                    "title": "Quantum Computing Breakthrough Unveiled",
                    "url": "https://technews.org/quantum-breakthrough",
                    "source": {"id": "tech-news", "name": "TechNews"},
                    "publishedAt": "2026-09-30T10:00:00Z",
                    "description": "Researchers announce major coherence milestone in quantum systems.",
                },
                {
                    "title": "Autonomous Drone Fleet Launched",
                    "url": "https://aeronews.com/drone-fleet",
                    "source": {"id": "aero-news", "name": "AeroNews"},
                    "publishedAt": "2026-09-30T08:30:00Z",
                    "description": "Commercial delivery drones deployed in metropolitan area.",
                },
            ],
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    # Task 1 & 2 & 3: Adapter architecture with GDELT and NewsAPI
    def test_providers_implement_base_adapter_interface(self):
        gdelt = GDELTProvider(base_url="https://api.gdeltproject.org/api/v2/doc/doc")
        newsapi = NewsAPIProvider(api_key="env_key", base_url="https://newsapi.org/v2/everything")
        multi = MultiProvider([gdelt, newsapi])

        self.assertIsInstance(gdelt, NewsProvider)
        self.assertIsInstance(newsapi, NewsProvider)
        self.assertIsInstance(multi, NewsProvider)

    # Task 4: Store API keys only in environment variables
    def test_newsapi_key_read_from_environment_variables(self):
        provider_no_key = NewsAPIProvider(api_key=None)
        with self.assertRaises(ProviderError) as ctx:
            provider_no_key.search("quantum")
        self.assertIn("key is missing", str(ctx.exception).lower())

        with patch.dict(os.environ, {"NEWSAPI_KEY": "env_secret_key_123", "NEWS_PROVIDERS": "newsapi"}):
            app = create_app({"DATABASE_PATH": self.database_path})
            provider = app.extensions["search_orchestrator"].search_service.providers[0]
            self.assertEqual(provider.api_key, "env_secret_key_123")

    # Task 5: Normalize all provider responses into existing Article model
    def test_responses_normalized_into_article_model(self):
        gdelt = GDELTProvider(base_url="https://api.gdeltproject.org/api/v2/doc/doc")
        newsapi = NewsAPIProvider(api_key="env_key")

        with patch("app.providers.gdelt_provider.urlopen", return_value=MockHTTPResponse(self.gdelt_sample_response)):
            gdelt_articles = gdelt.search("quantum")

        with patch("app.providers.newsapi_provider.urlopen", return_value=MockHTTPResponse(self.newsapi_sample_response)):
            newsapi_articles = newsapi.search("quantum")

        self.assertTrue(all(isinstance(a, Article) for a in gdelt_articles))
        self.assertTrue(all(isinstance(a, Article) for a in newsapi_articles))

        # Check normalization fields
        g0 = gdelt_articles[0]
        self.assertEqual(g0.title, "Quantum Computing Breakthrough Unveiled")
        self.assertEqual(g0.publisher, "technews.org")
        self.assertEqual(g0.publication_date, "20260930100000")
        self.assertEqual(g0.source_provider, "gdelt")

        n0 = newsapi_articles[0]
        self.assertEqual(n0.title, "Quantum Computing Breakthrough Unveiled")
        self.assertEqual(n0.publisher, "TechNews")
        self.assertEqual(n0.publication_date, "2026-09-30T10:00:00Z")
        self.assertEqual(n0.description, "Researchers announce major coherence milestone in quantum systems.")
        self.assertEqual(n0.source_provider, "newsapi")

    # Task 6: Preserve publisher, original URL, publication date, provider, and retrieved_at
    def test_preserves_all_metadata_fields_in_repository(self):
        repo = self.repository
        article = Article(
            title="Clean Energy Transition",
            url="https://energy.org/transition?ref=twitter",
            publisher="Energy Journal",
            publication_date="2026-09-30T12:00:00Z",
            description="Analysis of solar and wind adoption rates.",
            source_provider="newsapi",
        )

        saved = repo.save_article(article, retrieved_at="2026-09-30T12:05:00+00:00")
        self.assertEqual(saved["publisher"], "Energy Journal")
        self.assertEqual(saved["url"], "https://energy.org/transition?ref=twitter")
        self.assertEqual(saved["publication_date"], "2026-09-30T12:00:00Z")
        self.assertEqual(saved["source_provider"], "newsapi")
        self.assertEqual(saved["retrieved_at"], "2026-09-30T12:05:00+00:00")
        self.assertEqual(saved["description"], "Analysis of solar and wind adoption rates.")

    # Task 7 & 8: Independent failure and rate limit handling; combine successful results
    def test_gdelt_fails_newsapi_succeeds_combined_gracefully(self):
        gdelt = GDELTProvider(base_url="https://api.gdeltproject.org")
        newsapi = NewsAPIProvider(api_key="valid_key")

        with patch("app.providers.gdelt_provider.urlopen", side_effect=HTTPError("url", 500, "Server Error", None, None)), \
             patch("app.providers.newsapi_provider.urlopen", return_value=MockHTTPResponse(self.newsapi_sample_response)):
            multi = MultiProvider([gdelt, newsapi])
            results = multi.search("quantum")

        self.assertEqual(len(results), 2)
        self.assertTrue(all(a.source_provider == "newsapi" for a in results))

    def test_newsapi_rate_limits_gdelt_succeeds_combined_gracefully(self):
        gdelt = GDELTProvider(base_url="https://api.gdeltproject.org")
        newsapi = NewsAPIProvider(api_key="valid_key")

        with patch("app.providers.gdelt_provider.urlopen", return_value=MockHTTPResponse(self.gdelt_sample_response)), \
             patch("app.providers.newsapi_provider.urlopen", side_effect=HTTPError("url", 429, "Too Many Requests", None, None)):
            multi = MultiProvider([gdelt, newsapi])
            results = multi.search("quantum")

        self.assertEqual(len(results), 2)
        self.assertTrue(all(a.source_provider == "gdelt" for a in results))

    def test_both_providers_fail_surfaces_most_relevant_error(self):
        gdelt = GDELTProvider(base_url="https://api.gdeltproject.org")
        newsapi = NewsAPIProvider(api_key="valid_key")

        with patch("app.providers.gdelt_provider.urlopen", side_effect=HTTPError("url", 500, "Server Error", None, None)), \
             patch("app.providers.newsapi_provider.urlopen", side_effect=HTTPError("url", 429, "Too Many Requests", None, None)):
            multi = MultiProvider([gdelt, newsapi])
            with self.assertRaises(RateLimitError):
                multi.search("quantum")

    # Task 9: Deduplicate cross-provider articles using canonical URLs
    def test_cross_provider_deduplication_merges_canonical_urls_and_providers(self):
        gdelt = GDELTProvider(base_url="https://api.gdeltproject.org")
        newsapi = NewsAPIProvider(api_key="valid_key")

        with patch("app.providers.gdelt_provider.urlopen", return_value=MockHTTPResponse(self.gdelt_sample_response)), \
             patch("app.providers.newsapi_provider.urlopen", return_value=MockHTTPResponse(self.newsapi_sample_response)):
            multi = MultiProvider([gdelt, newsapi])
            results = multi.search("quantum")

        # 3 unique articles total (1 shared canonical URL: technews.org/quantum-breakthrough)
        self.assertEqual(len(results), 3)

        shared = next(a for a in results if "quantum-breakthrough" in a.url)
        # Verify provider names merged
        self.assertIn("gdelt", shared.source_provider)
        self.assertIn("newsapi", shared.source_provider)
        # Richer description from NewsAPI preserved
        self.assertEqual(shared.description, "Researchers announce major coherence milestone in quantum systems.")
        # Publisher and publication date preserved
        self.assertTrue(bool(shared.publisher))
        self.assertTrue(bool(shared.publication_date))

    # Task 10: Keep provider names visible in provenance data
    def test_provider_names_visible_in_provenance_data_and_dashboard(self):
        with patch.dict(os.environ, {"NEWS_PROVIDERS": "gdelt,newsapi", "NEWSAPI_KEY": "test_key"}):
            app = create_app({"DATABASE_PATH": self.database_path})

        with patch("app.providers.gdelt_provider.urlopen", return_value=MockHTTPResponse(self.gdelt_sample_response)), \
             patch("app.providers.newsapi_provider.urlopen", return_value=MockHTTPResponse(self.newsapi_sample_response)):
            client = app.test_client()
            response = client.post("/api/search", json={"query": "quantum"})

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["provider_status"], "ok")

        results = data["results"]
        self.assertEqual(len(results), 3)

        # Check provenance signals in each article payload
        for article in results:
            self.assertIn("source_provider", article)
            self.assertTrue(bool(article["source_provider"]))
            self.assertTrue(article["provenance_signals"]["source_provider_identified"])

        # Check shared article shows merged providers in provenance data
        shared = next(a for a in results if "quantum-breakthrough" in a["url"])
        self.assertIn("gdelt", shared["source_provider"])
        self.assertIn("newsapi", shared["source_provider"])

        # Check verification dashboard sources include source provider
        dashboard = data["verification_dashboard"]
        self.assertIn("sources", dashboard)
        providers_in_sources = [s.get("source_provider") for s in dashboard["sources"]]
        self.assertTrue(any("newsapi" in str(p) for p in providers_in_sources))
        self.assertTrue(any("gdelt" in str(p) for p in providers_in_sources))

    # Cross-retrieval persistence and deduplication in database
    def test_database_merges_providers_on_subsequent_retrievals(self):
        repo = self.repository
        art_gdelt = Article(
            title="First Report",
            url="https://sample.com/story?utm_campaign=feed",
            publisher="sample.com",
            publication_date="20260930100000",
            description=None,
            source_provider="gdelt",
        )
        saved1 = repo.save_article(art_gdelt, retrieved_at="2026-09-30T10:00:00Z")
        self.assertEqual(saved1["source_provider"], "gdelt")

        # Later, NewsAPI returns the same canonical article with description
        art_newsapi = Article(
            title="First Report Updated",
            url="https://sample.com/story",
            publisher="Sample News",
            publication_date="2026-09-30T10:00:00Z",
            description="Detailed reporting from second source.",
            source_provider="newsapi",
        )
        saved2 = repo.save_article(art_newsapi, retrieved_at="2026-09-30T10:15:00Z")
        self.assertEqual(saved2["id"], saved1["id"])
        self.assertIn("gdelt", saved2["source_provider"])
        self.assertIn("newsapi", saved2["source_provider"])
        self.assertEqual(saved2["description"], "Detailed reporting from second source.")
        self.assertEqual(repo.count_articles(), 1)


if __name__ == "__main__":
    unittest.main()
