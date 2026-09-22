import unittest

from app.models.article import Article
from app.services.timeline_service import TimelineService, normalize_publication_date


class TimelineServiceTestCase(unittest.TestCase):
    def article(self, article_id, title, date=None, description=None):
        return Article(
            title=title,
            url=f"https://example.com/{article_id}",
            publisher="Example News",
            publication_date=date,
            description=description,
            source_provider="mock",
            article_id=article_id,
        )

    def test_entries_are_sorted_chronologically(self):
        articles = [
            self.article(1, "Later", "20260918090000"),
            self.article(2, "Earlier", "20260806T134500Z"),
        ]

        timeline = TimelineService().generate(articles, [])

        self.assertEqual([entry["title"] for entry in timeline], ["Earlier", "Later"])
        self.assertEqual(timeline[0]["date"], "2026-08-06")

    def test_missing_and_invalid_dates_are_sorted_last(self):
        articles = [
            self.article(1, "Valid", "20260918090000"),
            self.article(2, "Missing"),
            self.article(3, "Invalid", "not-a-date"),
        ]

        timeline = TimelineService().generate(articles, [])

        self.assertEqual([entry["title"] for entry in timeline], ["Valid", "Missing", "Invalid"])
        self.assertIsNone(timeline[1]["date"])
        self.assertIsNone(timeline[2]["date"])

    def test_retrieved_at_is_not_used_as_historical_date(self):
        article = self.article(1, "Retrieved later", None)

        timeline = TimelineService().generate([article], [])

        self.assertIsNone(timeline[0]["date"])

    def test_related_group_creates_one_shared_entry_with_supporting_ids(self):
        articles = [
            self.article(1, "Technology launch", "20260918000000", "Launch details"),
            self.article(2, "Technology launch review", "20260917000000", "Review details"),
        ]
        groups = [
            {
                "group_id": "7",
                "article_ids": [1, 2],
                "article_count": 2,
                "representative_title": "Technology launch",
            }
        ]

        timeline = TimelineService().generate(articles, groups)

        self.assertEqual(len(timeline), 1)
        self.assertEqual(timeline[0]["date"], "2026-09-17")
        self.assertEqual(timeline[0]["article_ids"], [1, 2])
        self.assertEqual(timeline[0]["group_id"], "7")
        self.assertTrue(timeline[0]["automatic"])
        self.assertEqual(timeline[0]["description"], "Launch details")

    def test_single_article_creates_individual_automatic_entry(self):
        timeline = TimelineService().generate([self.article(1, "One story", "20260918")], [])

        self.assertEqual(len(timeline), 1)
        self.assertEqual(timeline[0]["article_ids"], [1])
        self.assertIsNone(timeline[0]["group_id"])
        self.assertTrue(timeline[0]["automatic"])

    def test_empty_articles_returns_empty_timeline(self):
        self.assertEqual(TimelineService().generate([], []), [])

    def test_normalize_publication_date_accepts_provider_formats(self):
        self.assertEqual(normalize_publication_date("20260918090000"), "2026-09-18")
        self.assertEqual(normalize_publication_date("2026-09-18T09:00:00Z"), "2026-09-18")
        self.assertIsNone(normalize_publication_date("invalid"))


if __name__ == "__main__":
    unittest.main()
