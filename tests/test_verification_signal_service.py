import unittest

from app.models.article import Article
from app.services.verification_signal_service import VerificationSignalService


class VerificationSignalServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.service = VerificationSignalService()

    def test_signal_structure_contains_required_fields(self):
        article = Article(
            title="Single source story",
            url="https://example.com/single",
            publisher="Example News",
            publication_date="2026-09-01",
            description="A reported event.",
            source_provider="mock",
            article_id=1,
        )
        signals = self.service.analyze_articles([article])

        self.assertGreater(len(signals), 0)
        for sig in signals:
            self.assertIn("type", sig)
            self.assertIn("severity", sig)
            self.assertIn("explanation", sig)
            self.assertIn("supporting_article_ids", sig)
            self.assertIsInstance(sig["type"], str)
            self.assertIsInstance(sig["severity"], str)
            self.assertIsInstance(sig["explanation"], str)
            self.assertIsInstance(sig["supporting_article_ids"], list)

    def test_single_source_only_signal(self):
        article = Article(
            title="Isolated event",
            url="https://example.com/one",
            publisher="News Outlet A",
            publication_date="2026-09-01",
            description="Reported on the ground.",
            source_provider="mock",
            article_id=10,
        )
        signals = self.service.analyze_articles([article])
        signal_types = [s["type"] for s in signals]

        self.assertIn("single_source_only", signal_types)
        single_sig = next(s for s in signals if s["type"] == "single_source_only")
        self.assertEqual(single_sig["explanation"], "Limited independent reporting is currently available.")
        self.assertEqual(single_sig["supporting_article_ids"], [10])

    def test_no_independent_supporting_reports_signal(self):
        # Multiple articles but all from the exact same publisher
        art1 = Article("Story part 1", "https://example.com/1", "Sole Publisher", "2026-09-01", "Desc", "mock", 1)
        art2 = Article("Story part 2", "https://example.com/2", "Sole Publisher", "2026-09-02", "Desc", "mock", 2)

        signals = self.service.analyze_articles([art1, art2])
        signal_types = [s["type"] for s in signals]

        self.assertIn("no_independent_supporting_reports", signal_types)
        self.assertNotIn("single_source_only", signal_types)
        sig = next(s for s in signals if s["type"] == "no_independent_supporting_reports")
        self.assertEqual(sig["explanation"], "Limited independent reporting is currently available.")
        self.assertIn(1, sig["supporting_article_ids"])
        self.assertIn(2, sig["supporting_article_ids"])

    def test_conflicting_reports_signal(self):
        art1 = Article("Event announced", "https://a.com/1", "Publisher A", "2026-09-01", "Officials announce event.", "mock", 1)
        art2 = Article("Event denied", "https://b.com/2", "Publisher B", "2026-09-02", "Spokesperson denies the event occurred.", "mock", 2)

        signals = self.service.analyze_articles([art1, art2])
        signal_types = [s["type"] for s in signals]

        self.assertIn("conflicting_reports", signal_types)
        conflict_sig = next(s for s in signals if s["type"] == "conflicting_reports")
        self.assertEqual(conflict_sig["explanation"], "Some reports contain differing information.")
        self.assertEqual(conflict_sig["supporting_article_ids"], [2])

    def test_missing_publisher_signal(self):
        article = Article("No publisher story", "https://a.com/1", None, "2026-09-01", "Desc", "mock", 5)
        signals = self.service.analyze_article(article)
        signal_types = [s["type"] for s in signals]

        self.assertIn("missing_publisher", signal_types)
        sig = next(s for s in signals if s["type"] == "missing_publisher")
        self.assertEqual(sig["explanation"], "Publisher information is missing from the source record.")
        self.assertEqual(sig["supporting_article_ids"], [5])

    def test_missing_publication_date_signal(self):
        article = Article("No date story", "https://a.com/1", "Publisher A", None, "Desc", "mock", 7)
        signals = self.service.analyze_article(article)
        signal_types = [s["type"] for s in signals]

        self.assertIn("missing_publication_date", signal_types)
        sig = next(s for s in signals if s["type"] == "missing_publication_date")
        self.assertEqual(sig["explanation"], "Publication date is unavailable in the source metadata.")
        self.assertEqual(sig["supporting_article_ids"], [7])

    def test_missing_original_url_signal(self):
        article = Article("No url story", "", "Publisher A", "2026-09-01", "Desc", "mock", 9)
        signals = self.service.analyze_article(article)
        signal_types = [s["type"] for s in signals]

        self.assertIn("missing_original_url", signal_types)
        sig = next(s for s in signals if s["type"] == "missing_original_url")
        self.assertEqual(sig["explanation"], "Original source URL is unavailable.")
        self.assertEqual(sig["supporting_article_ids"], [9])

    def test_incomplete_metadata_signal(self):
        article = Article("Incomplete story", "", None, None, "Desc", "mock", 11)
        signals = self.service.analyze_article(article)
        signal_types = [s["type"] for s in signals]

        self.assertIn("incomplete_metadata", signal_types)
        self.assertIn("unusually_incomplete_metadata", signal_types)
        sig = next(s for s in signals if s["type"] == "incomplete_metadata")
        self.assertEqual(sig["explanation"], "Source metadata is incomplete.")
        self.assertEqual(sig["supporting_article_ids"], [11])

    def test_complete_corroborated_reporting_has_no_warning_signals(self):
        art1 = Article("Conference opens", "https://a.com/1", "Publisher A", "2026-09-01", "Leaders assemble today.", "mock", 1)
        art2 = Article("Conference begins", "https://b.com/2", "Publisher B", "2026-09-01", "Global leaders gathered today.", "mock", 2)

        signals = self.service.analyze_articles([art1, art2])
        self.assertEqual(signals, [])

    def test_neutrality_guardrails_no_truth_bias_or_credibility_determination(self):
        art = Article("Sample story", "https://a.com/1", "Publisher A", "2026-09-01", "Desc", "mock", 1)
        signals = self.service.analyze_articles([art])

        # Verify signals do not declare articles fake/true, assign political bias, or assign credibility scores
        prohibited_words = {"fake", "hoax", "true", "false", "verified_true", "debunked", "bias", "credibility_score", "trust_rank"}
        for sig in signals:
            explanation = sig["explanation"].lower()
            sig_type = sig["type"].lower()
            for word in prohibited_words:
                self.assertNotIn(word, explanation)
                self.assertNotIn(word, sig_type)

    def test_enrich_groups_and_timeline_attaches_verification_signals(self):
        art = Article("Event", "https://a.com/1", "Publisher A", "2026-09-01", "Desc", "mock", 1)
        groups = [{"group_id": "1", "article_ids": [1]}]
        timeline = [{"timeline_id": "art-1", "article_ids": [1]}]

        enriched_groups = self.service.enrich_groups(groups, [art])
        enriched_timeline = self.service.enrich_timeline(timeline, [art])

        self.assertIn("verification_signals", enriched_groups[0])
        self.assertIn("warning_signals", enriched_groups[0])
        self.assertIn("verification_signals", enriched_timeline[0])
        self.assertIn("warning_signals", enriched_timeline[0])
        self.assertEqual(enriched_timeline[0]["verification_signals"][0]["type"], "single_source_only")


if __name__ == "__main__":
    unittest.main()
