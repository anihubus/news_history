import unittest
from tempfile import TemporaryDirectory

from app.database import initialize_database
from app.models.article import Article
from app.providers.base_provider import ProviderError, RateLimitError
from app.repositories.article_repository import ArticleRepository
from app.services.article_retrieval_service import ArticleRetrievalService


class StubProvider:
    def __init__(self, articles=None, error=None):
        self.articles = articles or []
        self.error = error

    def search(self, query):
        if self.error:
            raise self.error
        return self.articles


class ArticleRetrievalServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.database_directory = TemporaryDirectory()
        database_path = f"{self.database_directory.name}/articles.db"
        initialize_database(database_path)
        self.repository = ArticleRepository(database_path)

    def tearDown(self):
        self.database_directory.cleanup()

    def article(self, title, url, publication_date=None, description=None, publisher="Example News"):
        return Article(
            title=title,
            url=url,
            publisher=publisher,
            publication_date=publication_date,
            description=description,
            source_provider="mock",
        )

    def service(self, provider, result_limit=20):
        return ArticleRetrievalService(self.repository, provider, result_limit=result_limit)

    def test_searches_stored_articles_by_title_description_and_publisher(self):
        self.repository.save_articles(
            [
                self.article("Technology policy", "https://example.com/title"),
                self.article("Other story", "https://example.com/description", description="Technology report"),
                self.article("Other story", "https://example.com/publisher", publisher="Technology Daily"),
            ]
        )
        provider = StubProvider()
        service = self.service(provider)

        self.assertEqual(len(service.search("technology").articles), 3)
        self.assertEqual(len(service.search(" TECHNOLOGY ").articles), 3)

    def test_no_matching_stored_articles_returns_empty_result(self):
        self.repository.save_article(self.article("Unrelated", "https://example.com/unrelated"))

        result = self.service(StubProvider()).search("missing")

        self.assertEqual(result.articles, [])
        self.assertEqual(result.provider_status, "ok")

    def test_combines_stored_and_provider_articles_and_removes_duplicates(self):
        stored = self.article("Stored story", "https://example.com/story?utm_source=email", "20260917000000")
        provider_duplicate = self.article("Provider article", "https://EXAMPLE.com/story#section", "20260918000000")
        provider_new = self.article("New article", "https://example.com/new", "20260916000000")
        self.repository.save_article(stored)

        result = self.service(StubProvider([provider_duplicate, provider_new])).search("story")

        self.assertEqual(len(result.articles), 2)
        self.assertEqual({article.url for article in result.articles}, {provider_duplicate.url, provider_new.url})

    def test_results_are_sorted_newest_first_and_missing_dates_last(self):
        provider = StubProvider(
            [
                self.article("Old", "https://example.com/old", "20260901000000"),
                self.article("Missing", "https://example.com/missing"),
                self.article("New", "https://example.com/new", "20260918000000"),
            ]
        )

        result = self.service(provider).search("topic")

        self.assertEqual([article.title for article in result.articles], ["New", "Old", "Missing"])

    def test_result_limit_is_configurable(self):
        provider = StubProvider(
            [self.article(f"Article {index}", f"https://example.com/{index}", "20260918000000") for index in range(3)]
        )

        result = self.service(provider, result_limit=2).search("topic")

        self.assertEqual(len(result.articles), 2)

    def test_provider_failure_preserves_matching_stored_articles(self):
        stored = self.article("Technology report", "https://example.com/stored", "20260918000000")
        self.repository.save_article(stored)

        result = self.service(StubProvider(error=ProviderError())).search("technology")

        self.assertEqual(result.provider_status, "provider_unavailable")
        self.assertEqual([article.title for article in result.articles], [stored.title])

    def test_rate_limit_preserves_matching_stored_articles(self):
        stored = self.article("Technology report", "https://example.com/stored", "20260918000000")
        self.repository.save_article(stored)

        result = self.service(StubProvider(error=RateLimitError())).search("technology")

        self.assertEqual(result.provider_status, "rate_limited")
        self.assertEqual(len(result.articles), 1)

    def test_provider_failure_without_stored_articles_is_controlled(self):
        result = self.service(StubProvider(error=ProviderError())).search("technology")

        self.assertEqual(result.provider_status, "provider_unavailable")
        self.assertEqual(result.articles, [])
        self.assertIsNotNone(result.provider_error)


if __name__ == "__main__":
    unittest.main()
