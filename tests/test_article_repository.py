import sqlite3
import unittest
from tempfile import TemporaryDirectory

from app.database import initialize_database
from app.models.article import Article
from app.repositories.article_repository import ArticleRepository, canonicalize_url


class ArticleRepositoryTestCase(unittest.TestCase):
    def setUp(self):
        self.database_directory = TemporaryDirectory()
        self.database_path = f"{self.database_directory.name}/nested/news.db"
        initialize_database(self.database_path)
        self.repository = ArticleRepository(self.database_path)

    def tearDown(self):
        self.database_directory.cleanup()

    def article(self, url="https://example.com/article"):
        return Article(
            title="Example article",
            url=url,
            publisher="Example News",
            publication_date="20260918090000",
            description=None,
            source_provider="mock",
        )

    def test_database_initialization_creates_articles_table(self):
        connection = sqlite3.connect(self.database_path)
        try:
            table = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'articles'"
            ).fetchone()
        finally:
            connection.close()

        self.assertIsNotNone(table)

    def test_save_and_retrieve_one_article(self):
        saved = self.repository.save_article(self.article())
        retrieved = self.repository.find_by_canonical_url("https://example.com/article")

        self.assertEqual(saved["title"], "Example article")
        self.assertEqual(retrieved["url"], "https://example.com/article")
        self.assertEqual(self.repository.count_articles(), 1)

    def test_save_multiple_articles(self):
        saved = self.repository.save_articles(
            [self.article(), self.article("https://example.com/second")]
        )

        self.assertEqual(len(saved), 2)
        self.assertEqual(self.repository.count_articles(), 2)
        self.assertEqual(len(self.repository.get_articles()), 2)

    def test_duplicate_canonical_url_does_not_create_second_record(self):
        self.repository.save_article(
            self.article("https://EXAMPLE.com/article?utm_source=newsletter#section")
        )
        self.repository.save_article(self.article("https://example.com/article"))

        self.assertEqual(self.repository.count_articles(), 1)
        self.assertEqual(
            canonicalize_url("https://EXAMPLE.com/article?utm_source=newsletter#section"),
            "https://example.com/article",
        )

    def test_different_canonical_urls_create_separate_records(self):
        self.repository.save_article(self.article("https://example.com/one"))
        self.repository.save_article(self.article("https://example.com/two"))

        self.assertEqual(self.repository.count_articles(), 2)

    def test_retrieved_at_is_stored_separately_from_publication_date(self):
        saved = self.repository.save_article(self.article())

        self.assertIsNotNone(saved["retrieved_at"])
        self.assertIsNotNone(saved["created_at"])
        self.assertEqual(saved["publication_date"], "20260918090000")
        self.assertNotEqual(saved["retrieved_at"], saved["publication_date"])


if __name__ == "__main__":
    unittest.main()
