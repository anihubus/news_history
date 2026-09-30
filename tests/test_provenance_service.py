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


    def test_article_signals_complete_metadata(self):
        signals = self.service.source_signals(self.article)

        self.assertTrue(signals["publisher_identified"])
        self.assertTrue(signals["original_url_available"])
        self.assertTrue(signals["publication_date_available"])
        self.assertTrue(signals["source_provider_identified"])
        self.assertFalse(signals["multiple_sources_found"])
        self.assertEqual(signals["independent_source_count"], 1)
        self.assertFalse(signals["source_information_missing"])
        self.assertEqual(signals["missing_fields"], [])

    def test_article_signals_incomplete_metadata(self):
        incomplete_article = Article(
            title="Incomplete story",
            url="",
            publisher=None,
            publication_date=None,
            description="Lacks publisher, date, url, and provider",
            source_provider=None,
            article_id=99,
        )
        signals = self.service.source_signals(incomplete_article)

        self.assertFalse(signals["publisher_identified"])
        self.assertFalse(signals["original_url_available"])
        self.assertFalse(signals["publication_date_available"])
        self.assertFalse(signals["source_provider_identified"])
        self.assertTrue(signals["source_information_missing"])
        self.assertEqual(signals["independent_source_count"], 0)
        self.assertIn("publisher", signals["missing_fields"])
        self.assertIn("url", signals["missing_fields"])
        self.assertIn("publication_date", signals["missing_fields"])
        self.assertIn("source_provider", signals["missing_fields"])

    def test_original_url_and_publisher_remain_unmodified_without_fabrication(self):
        # Incomplete metadata should not invent publisher or alter URLs
        raw_url = "https://example.com/original-path?param=1#section"
        article = Article(
            title="No publisher article",
            url=raw_url,
            publisher=None,
            publication_date=None,
            description=None,
            source_provider="mock",
            article_id=44,
        )
        reference = self.service.article_reference(article)

        self.assertEqual(reference["url"], raw_url)
        self.assertIsNone(reference["publisher"])
        self.assertFalse(reference["publisher_identified"])
        self.assertTrue(reference["original_url_available"])

    def test_no_credibility_score_trust_ranking_or_bias_inferred(self):
        reference = self.service.article_reference(self.article)
        signals = reference["provenance_signals"]

        # Ensure no forbidden credibility, trust, or bias properties exist
        forbidden_keys = {
            "credibility", "credibility_score", "score", "trust_score",
            "trustworthy", "untrustworthy", "reliability", "bias", "political_bias",
            "rating", "rank"
        }
        for key in forbidden_keys:
            self.assertNotIn(key, reference)
            self.assertNotIn(key, signals)

    def test_collection_signals_multiple_sources_different_publishers(self):
        art1 = Article("Title 1", "https://a.com/1", "Publisher A", "2026-09-01", "Desc", "mock", 1)
        art2 = Article("Title 2", "https://b.com/2", "Publisher B", "2026-09-02", "Desc", "mock", 2)

        signals = self.service.collection_signals([art1, art2])

        self.assertTrue(signals["multiple_sources_found"])
        self.assertEqual(signals["independent_source_count"], 2)
        self.assertTrue(signals["publisher_identified"])
        self.assertTrue(signals["original_url_available"])
        self.assertTrue(signals["publication_date_available"])
        self.assertTrue(signals["source_provider_identified"])
        self.assertFalse(signals["source_information_missing"])

    def test_collection_signals_multiple_sources_same_publisher(self):
        art1 = Article("Title 1", "https://a.com/1", "Publisher A", "2026-09-01", "Desc", "mock", 1)
        art2 = Article("Title 2", "https://a.com/2", "Publisher A", "2026-09-02", "Desc", "mock", 2)

        signals = self.service.collection_signals([art1, art2])

        self.assertTrue(signals["multiple_sources_found"])
        # Same publisher means independent publisher count is 1
        self.assertEqual(signals["independent_source_count"], 1)
        self.assertFalse(signals["source_information_missing"])

    def test_collection_signals_incomplete_source_metadata(self):
        art1 = Article("Title 1", "https://a.com/1", "Publisher A", "2026-09-01", "Desc", "mock", 1)
        art2 = Article("Title 2", "", None, None, "Desc", "mock", 2)

        signals = self.service.collection_signals([art1, art2])

        self.assertTrue(signals["multiple_sources_found"])
        self.assertEqual(signals["independent_source_count"], 1)
        self.assertTrue(signals["source_information_missing"])

    def test_enrich_timeline_and_groups_contain_provenance_signals(self):
        group = {"group_id": "1", "article_ids": [12], "article_count": 1}
        timeline = {"timeline_id": "article-12", "article_ids": [12]}

        enriched_group = self.service.enrich_groups([group], [self.article])[0]
        enriched_timeline = self.service.enrich_timeline([timeline], [self.article])[0]

        self.assertIn("provenance_signals", enriched_group)
        self.assertIn("provenance_signals", enriched_timeline)
        self.assertEqual(enriched_timeline["provenance_signals"]["independent_source_count"], 1)
        self.assertFalse(enriched_timeline["provenance_signals"]["multiple_sources_found"])
        self.assertFalse(enriched_timeline["provenance_signals"]["source_information_missing"])


if __name__ == "__main__":
    unittest.main()

