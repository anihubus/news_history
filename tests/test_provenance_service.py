import unittest

from app.models.article import Article
from app.services.provenance_service import ProvenanceService


class ProvenanceServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.service = ProvenanceService()
        self.article = Article(
            title="Technology report",
            url="https://example.com/source",
            publisher="Example News",
            publication_date="20260918090000",
            description="Reported description",
            source_provider="mock",
            article_id=12,
            retrieved_at="2026-09-24T10:00:00+00:00",
        )

    def test_article_reference_contains_required_source_fields(self):
        reference = self.service.article_reference(self.article)

        self.assertEqual(reference["article_id"], 12)
        self.assertEqual(reference["title"], "Technology report")
        self.assertEqual(reference["publisher"], "Example News")
        self.assertEqual(reference["url"], "https://example.com/source")
        self.assertEqual(reference["publication_date"], "20260918090000")
        self.assertEqual(reference["retrieved_at"], "2026-09-24T10:00:00+00:00")
        self.assertEqual(reference["source_provider"], "mock")

    def test_missing_source_fields_remain_none(self):
        article = Article("Unknown", "", None, None, None, "mock", 4, None)

        reference = self.service.article_reference(article)

        self.assertIsNone(reference["publisher"])
        self.assertIsNone(reference["publication_date"])
        self.assertIsNone(reference["retrieved_at"])
        self.assertEqual(reference["url"], "")

    def test_publication_date_and_retrieval_date_remain_separate(self):
        reference = self.service.article_reference(self.article)

        self.assertNotEqual(reference["publication_date"], reference["retrieved_at"])

    def test_group_and_timeline_sources_use_article_references(self):
        group = {"group_id": "3", "article_ids": [12], "article_count": 1}
        timeline = {"timeline_id": "article-12", "article_ids": [12]}

        enriched_group = self.service.enrich_groups([group], [self.article])[0]
        enriched_timeline = self.service.enrich_timeline([timeline], [self.article])[0]

        self.assertEqual(enriched_group["sources"][0]["url"], self.article.url)
        self.assertEqual(enriched_timeline["supporting_sources"][0]["article_id"], 12)

    def test_summary_sources_are_deduplicated_by_article_id(self):
        summary = {"summary": "", "supporting_article_ids": [12, 12]}

        enriched = self.service.enrich_summaries([summary], [self.article])[0]

        self.assertEqual(len(enriched["sources"]), 1)

    def test_answer_without_supported_ids_has_no_fabricated_sources(self):
        answer = {"success": True, "answer": "Insufficient information.", "supporting_article_ids": []}

        enriched = self.service.enrich_answer(answer, [self.article])

        self.assertEqual(enriched["sources"], [])


if __name__ == "__main__":
    unittest.main()
