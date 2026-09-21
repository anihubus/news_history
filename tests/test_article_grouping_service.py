import unittest
from tempfile import TemporaryDirectory

from app.database import initialize_database
from app.models.article import Article
from app.repositories.article_repository import ArticleRepository
from app.services.article_grouping_service import ArticleGroupingService
from app.services.text_normalizer import normalize_text


class ArticleGroupingServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.database_directory = TemporaryDirectory()
        database_path = f"{self.database_directory.name}/grouping.db"
        initialize_database(database_path)
        self.repository = ArticleRepository(database_path)

    def tearDown(self):
        self.database_directory.cleanup()

    def save(self, articles):
        rows = self.repository.save_articles(articles)
        return [
            Article(
                title=row["title"],
                url=row["url"],
                publisher=row["publisher"],
                publication_date=row["publication_date"],
                description=row["description"],
                source_provider=row["source_provider"],
                article_id=row["id"],
            )
            for row in rows
        ]

    def article(self, title, url, description=None, date="20260918000000"):
        return Article(title, url, "Example", date, description, "mock")

    def test_text_normalization_removes_stop_words_and_short_tokens(self):
        self.assertEqual(normalize_text("The new AI is in a test!"), ["new", "test"])

    def test_related_articles_have_weighted_similarity_and_reason(self):
        articles = self.save(
            [
                self.article("Apple launches Vision Pro headset", "https://example.com/one", "Apple released a mixed reality headset."),
                self.article("Apple Vision Pro headset review", "https://example.com/two", "The mixed reality headset receives attention."),
            ]
        )

        result = ArticleGroupingService(self.repository, threshold=0.30).group_articles(articles)

        self.assertEqual(len(result["relationships"]), 1)
        self.assertGreaterEqual(result["relationships"][0]["similarity"], 0.30)
        self.assertEqual(result["relationships"][0]["reason"], "Shared weighted keywords")
        self.assertEqual(result["groups"][0]["article_count"], 2)

    def test_unrelated_articles_form_separate_groups(self):
        articles = self.save(
            [
                self.article("Apple launches headset", "https://example.com/apple"),
                self.article("Heavy rain reaches the coast", "https://example.com/weather"),
            ]
        )

        result = ArticleGroupingService(self.repository, threshold=0.30).group_articles(articles)

        self.assertEqual(result["relationships"], [])
        self.assertEqual(len(result["groups"]), 2)
        self.assertTrue(all(group["article_count"] == 1 for group in result["groups"]))

    def test_threshold_can_prevent_relationship(self):
        articles = self.save(
            [
                self.article("Apple launches headset", "https://example.com/one"),
                self.article("Apple reviews headset", "https://example.com/two"),
            ]
        )

        result = ArticleGroupingService(self.repository, threshold=1.0).group_articles(articles)

        self.assertEqual(result["relationships"], [])

    def test_duplicate_canonical_urls_do_not_create_relationship_identity(self):
        articles = self.save(
            [
                self.article("Apple headset launch", "https://example.com/story?utm_source=one"),
                self.article("Different title", "https://EXAMPLE.com/story#section"),
            ]
        )

        result = ArticleGroupingService(self.repository).group_articles(articles)

        self.assertEqual(len(articles), 2)
        self.assertEqual(self.repository.count_articles(), 1)
        self.assertLessEqual(len(result["relationships"]), 1)

    def test_relationships_and_groups_are_persisted(self):
        articles = self.save(
            [
                self.article("Technology launch", "https://example.com/one"),
                self.article("Technology launch review", "https://example.com/two"),
            ]
        )

        ArticleGroupingService(self.repository, threshold=0.30).group_articles(articles)

        self.assertEqual(len(self.repository.get_relationships()), 1)
        self.assertEqual(len(self.repository.get_groups()), 1)


if __name__ == "__main__":
    unittest.main()
