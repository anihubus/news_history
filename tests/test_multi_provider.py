import unittest
import os
from unittest.mock import patch

from app import create_app
from app.models.article import Article
from app.providers.base_provider import ProviderError, RateLimitError
from app.providers.gdelt_provider import GDELTProvider
from app.providers.mock_provider import MockNewsProvider
from app.providers.multi_provider import MultiProvider


class StubProvider:
    def __init__(self, articles=None, error=None):
        self.articles = articles or []
        self.error = error

    def search(self, query):
        if self.error:
            raise self.error
        return self.articles


class MultiProviderTestCase(unittest.TestCase):
    def article(self, title, url):
        return Article(
            title=title,
            url=url,
            publisher="Example News",
            publication_date="20260918000000",
            description=None,
            source_provider="stub",
        )

    def test_configuration_with_multiple_providers(self):
        with patch.dict(os.environ, {"NEWS_PROVIDERS": "mock,gdelt"}):
            app = create_app()

        provider = app.extensions["search_orchestrator"].search_service
        self.assertIsInstance(provider, MultiProvider)
        self.assertEqual(len(provider.providers), 2)
        self.assertIsInstance(provider.providers[0], MockNewsProvider)
        self.assertIsInstance(provider.providers[1], GDELTProvider)

    def test_provider_failure_isolation(self):
        successful_provider = StubProvider([self.article("Success", "https://example.com/success")])
        failed_provider = StubProvider(error=ProviderError("Failed"))

        multi_provider = MultiProvider([failed_provider, successful_provider])
        results = multi_provider.search("test")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "Success")

    def test_all_providers_failing_raises_error(self):
        failed_provider1 = StubProvider(error=ProviderError("Failed 1"))
        failed_provider2 = StubProvider(error=ProviderError("Failed 2"))

        multi_provider = MultiProvider([failed_provider1, failed_provider2])
        with self.assertRaises(ProviderError):
            multi_provider.search("test")

    def test_cross_provider_deduplication(self):
        provider1 = StubProvider([
            self.article("Duplicate", "https://example.com/duplicate?utm_source=1"),
            self.article("Unique 1", "https://example.com/unique1")
        ])
        provider2 = StubProvider([
            self.article("Duplicate", "https://example.com/duplicate#anchor"),
            self.article("Unique 2", "https://example.com/unique2")
        ])

        multi_provider = MultiProvider([provider1, provider2])
        results = multi_provider.search("test")

        self.assertEqual(len(results), 3)
        urls = [article.url for article in results]
        self.assertIn("https://example.com/duplicate?utm_source=1", urls)
        self.assertIn("https://example.com/unique1", urls)
        self.assertIn("https://example.com/unique2", urls)


if __name__ == "__main__":
    unittest.main()
