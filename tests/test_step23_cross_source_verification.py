import json
import os
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app import create_app
from app.database import initialize_database
from app.models.article import Article
from app.services.cross_source_service import CrossSourceService, parse_report_datetime


class CrossSourceVerificationTestCase(unittest.TestCase):
    """Test suite verifying Step 23: Real-Time Cross-Source Verification."""

    def setUp(self):
        self.service = CrossSourceService()
        self.temp_dir = TemporaryDirectory()
        self.database_path = os.path.join(self.temp_dir.name, "test_step23.db")
        initialize_database(self.database_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    # 1. Number of independent sources
    def test_calculate_number_of_independent_sources(self):
        # 3 articles, 2 distinct publishers
        articles = [
            Article(title="Breakthrough announced", url="https://a.com/1", publisher="Outlet Alpha", publication_date="2026-09-30T10:00:00Z", description="Report 1", source_provider="newsapi", article_id=101),
            Article(title="More on breakthrough", url="https://a.com/2", publisher="Outlet Alpha", publication_date="2026-09-30T10:15:00Z", description="Report 2", source_provider="newsapi", article_id=102),
            Article(title="Independent confirmation", url="https://b.com/3", publisher="Outlet Beta", publication_date="2026-09-30T11:00:00Z", description="Report 3", source_provider="gdelt", article_id=103),
        ]
        result = self.service.verify_related_articles(articles)
        self.assertEqual(result["independent_source_count"], 2)

    def test_single_publisher_has_independent_count_one(self):
        articles = [
            Article(title="Report 1", url="https://a.com/1", publisher="Single Publisher", publication_date="2026-09-30T10:00:00Z", description="Desc", source_provider="mock", article_id=1),
            Article(title="Report 2", url="https://a.com/2", publisher="Single Publisher", publication_date="2026-09-30T11:00:00Z", description="Desc", source_provider="mock", article_id=2),
        ]
        result = self.service.verify_related_articles(articles)
        self.assertEqual(result["independent_source_count"], 1)

    # 2. Supporting reports and conflicting reports
    def test_supporting_and_conflicting_reports_calculation(self):
        articles = [
            Article(title="Treaty signed in capital", url="https://a.com/1", publisher="Publisher A", publication_date="2026-09-30T09:00:00Z", description="Delegates signed agreement.", source_provider="newsapi", article_id=1),
            Article(title="Accord reached today", url="https://b.com/2", publisher="Publisher B", publication_date="2026-09-30T09:30:00Z", description="Pact successfully concluded.", source_provider="gdelt", article_id=2),
            Article(title="Opposition disputes agreement terms", url="https://c.com/3", publisher="Publisher C", publication_date="2026-09-30T10:00:00Z", description="Spokesperson denies treaty is valid.", source_provider="newsapi", article_id=3),
        ]
        result = self.service.verify_related_articles(articles)

        self.assertEqual(result["supporting_reports"], [1, 2])
        self.assertEqual(result["conflicting_reports"], [3])

        # Verify signals
        signal_types = [s["signal"] for s in result["signals"]]
        self.assertIn("supporting_reports", signal_types)
        self.assertIn("conflicting_reports", signal_types)

        conflicting_sig = next(s for s in result["signals"] if s["signal"] == "conflicting_reports")
        self.assertEqual(conflicting_sig["statement"], "Reports contain differing information.")
        self.assertEqual(conflicting_sig["supporting_article_ids"], [3])

        supporting_sig = next(s for s in result["signals"] if s["signal"] == "supporting_reports")
        self.assertEqual(supporting_sig["statement"], "Reported by multiple sources.")
        self.assertEqual(supporting_sig["supporting_article_ids"], [1, 2])

    # 3. Source metadata completeness
    def test_source_metadata_completeness_complete(self):
        articles = [
            Article(title="Clean Tech Launch", url="https://a.com/1", publisher="Publisher A", publication_date="2026-09-30T08:00:00Z", description="Desc 1", source_provider="newsapi", article_id=10),
            Article(title="Clean Tech Deployed", url="https://b.com/2", publisher="Publisher B", publication_date="2026-09-30T09:00:00Z", description="Desc 2", source_provider="gdelt", article_id=20),
        ]
        result = self.service.verify_related_articles(articles)
        completeness = result["source_metadata_completeness"]

        self.assertTrue(completeness["is_complete"])
        self.assertEqual(completeness["complete_article_count"], 2)
        self.assertEqual(completeness["total_article_count"], 2)
        self.assertEqual(completeness["incomplete_article_ids"], [])
        self.assertEqual(completeness["missing_fields"], [])

        # No incomplete metadata signal when all are complete
        signal_types = [s["signal"] for s in result["signals"]]
        self.assertNotIn("incomplete_metadata", signal_types)

    def test_source_metadata_completeness_incomplete(self):
        articles = [
            Article(title="Complete article", url="https://a.com/1", publisher="Publisher A", publication_date="2026-09-30T08:00:00Z", description="Desc 1", source_provider="newsapi", article_id=1),
            Article(title="Missing publisher & date", url="https://b.com/2", publisher=None, publication_date=None, description="Desc 2", source_provider="gdelt", article_id=2),
        ]
        result = self.service.verify_related_articles(articles)
        completeness = result["source_metadata_completeness"]

        self.assertFalse(completeness["is_complete"])
        self.assertEqual(completeness["complete_article_count"], 1)
        self.assertEqual(completeness["total_article_count"], 2)
        self.assertEqual(completeness["incomplete_article_ids"], [2])
        self.assertIn("publisher", completeness["missing_fields"])
        self.assertIn("publication_date", completeness["missing_fields"])

        # Generates neutral signal: "Source metadata is incomplete."
        signal_types = [s["signal"] for s in result["signals"]]
        self.assertIn("incomplete_metadata", signal_types)
        incomplete_sig = next(s for s in result["signals"] if s["signal"] == "incomplete_metadata")
        self.assertEqual(incomplete_sig["statement"], "Source metadata is incomplete.")
        self.assertEqual(incomplete_sig["supporting_article_ids"], [2])

    # 4. Time of first report and time of latest report
    def test_time_of_first_and_latest_report_iso_timestamps(self):
        articles = [
            Article(title="Latest report", url="https://b.com/2", publisher="Publisher B", publication_date="2026-09-30T14:30:00Z", description="Desc", source_provider="newsapi", article_id=2),
            Article(title="Earliest report", url="https://a.com/1", publisher="Publisher A", publication_date="2026-09-30T08:15:00Z", description="Desc", source_provider="newsapi", article_id=1),
            Article(title="Midday report", url="https://c.com/3", publisher="Publisher C", publication_date="2026-09-30T11:00:00Z", description="Desc", source_provider="newsapi", article_id=3),
        ]
        result = self.service.verify_related_articles(articles)
        self.assertEqual(result["time_of_first_report"], "2026-09-30T08:15:00Z")
        self.assertEqual(result["time_of_latest_report"], "2026-09-30T14:30:00Z")

    def test_time_of_first_and_latest_report_gdelt_timestamps(self):
        articles = [
            Article(title="Midday", url="https://b.com/2", publisher="Publisher B", publication_date="20260930113000", description="Desc", source_provider="gdelt", article_id=2),
            Article(title="Morning", url="https://a.com/1", publisher="Publisher A", publication_date="20260930090000", description="Desc", source_provider="gdelt", article_id=1),
        ]
        result = self.service.verify_related_articles(articles)
        self.assertEqual(result["time_of_first_report"], "20260930090000")
        self.assertEqual(result["time_of_latest_report"], "20260930113000")

    def test_time_of_first_and_latest_report_mixed_formats(self):
        articles = [
            Article(title="GDELT morning", url="https://a.com/1", publisher="Publisher A", publication_date="20260930090000", description="Desc", source_provider="gdelt", article_id=1),
            Article(title="NewsAPI afternoon", url="https://b.com/2", publisher="Publisher B", publication_date="2026-09-30T14:00:00Z", description="Desc", source_provider="newsapi", article_id=2),
        ]
        result = self.service.verify_related_articles(articles)
        self.assertEqual(result["time_of_first_report"], "20260930090000")
        self.assertEqual(result["time_of_latest_report"], "2026-09-30T14:00:00Z")

    def test_time_of_first_and_latest_report_missing_dates(self):
        articles = [
            Article(title="No date 1", url="https://a.com/1", publisher="Publisher A", publication_date=None, description="Desc", source_provider="mock", article_id=1),
            Article(title="No date 2", url="https://b.com/2", publisher="Publisher B", publication_date="", description="Desc", source_provider="mock", article_id=2),
        ]
        result = self.service.verify_related_articles(articles)
        self.assertIsNone(result["time_of_first_report"])
        self.assertIsNone(result["time_of_latest_report"])

    # 5. Display neutral signals referencing supporting article IDs
    def test_limited_independent_reporting_signal(self):
        articles = [
            Article(title="Exclusive report", url="https://a.com/1", publisher="Sole Source", publication_date="2026-09-30T10:00:00Z", description="Only source covering this.", source_provider="newsapi", article_id=42),
        ]
        result = self.service.verify_related_articles(articles)

        signal = next(s for s in result["signals"] if s["signal"] == "insufficient_cross_source_evidence")
        self.assertEqual(signal["statement"], "Limited independent reporting available.")
        self.assertEqual(signal["supporting_article_ids"], [42])

    def test_every_signal_references_supporting_article_ids(self):
        articles = [
            Article(title="Event occurs", url="https://a.com/1", publisher="Alpha Times", publication_date="2026-09-30T10:00:00Z", description="Desc", source_provider="mock", article_id=1),
            Article(title="Official denies report", url="", publisher=None, publication_date="2026-09-30T11:00:00Z", description="Denies it occurred.", source_provider="mock", article_id=2),
        ]
        result = self.service.verify_related_articles(articles)

        self.assertGreater(len(result["signals"]), 0)
        for sig in result["signals"]:
            self.assertIn("supporting_article_ids", sig)
            self.assertIsInstance(sig["supporting_article_ids"], list)
            self.assertGreater(len(sig["supporting_article_ids"]), 0)
            self.assertIn("statement", sig)

    # 6. Neutrality guardrails: Do NOT label articles as "fake" or "true", no credibility scores or rankings
    def test_neutrality_guardrails_no_fake_true_or_credibility_scores(self):
        articles = [
            Article(title="Sensational leak exposed", url="https://a.com/1", publisher="Tabloid A", publication_date="2026-09-30T10:00:00Z", description="Claims massive conspiracy.", source_provider="mock", article_id=1),
            Article(title="Spokesperson denies allegations", url="https://b.com/2", publisher="Government Daily", publication_date="2026-09-30T11:00:00Z", description="Officials reject and dispute claims.", source_provider="mock", article_id=2),
        ]
        result = self.service.verify_related_articles(articles)

        prohibited_words = {"fake", "hoax", "true", "false", "verified_true", "debunked", "credibility_score", "trust_rank", "bias"}
        for sig in result["signals"]:
            statement = sig["statement"].lower()
            sig_name = sig["signal"].lower()
            for word in prohibited_words:
                self.assertNotIn(word, statement)
                self.assertNotIn(word, sig_name)

        # Ensure no numerical credibility score or publisher ranking field is generated
        self.assertNotIn("credibility_score", result)
        self.assertNotIn("trust_score", result)
        self.assertNotIn("publisher_ranking", result)
        self.assertNotIn("publisher_rankings", result)

    # 7. Group analysis integration
    def test_analyze_groups_attaches_verification_and_metrics(self):
        articles = [
            Article(title="AI Model Released", url="https://a.com/ai", publisher="Tech Daily", publication_date="2026-09-30T09:00:00Z", description="New weights public.", source_provider="newsapi", article_id=1),
            Article(title="Open AI Model Released Today", url="https://b.com/ai", publisher="Wired World", publication_date="2026-09-30T10:30:00Z", description="Open access version out.", source_provider="gdelt", article_id=2),
        ]
        groups = [
            {
                "group_id": 1,
                "representative_title": "AI Model Released",
                "article_ids": [1, 2],
            }
        ]

        analyzed_groups = self.service.analyze_groups(groups, articles)
        group = analyzed_groups[0]

        self.assertIn("cross_source_verification", group)
        self.assertEqual(group["independent_source_count"], 2)
        self.assertEqual(group["supporting_reports"], [1, 2])
        self.assertEqual(group["conflicting_reports"], [])
        self.assertEqual(group["time_of_first_report"], "2026-09-30T09:00:00Z")
        self.assertEqual(group["time_of_latest_report"], "2026-09-30T10:30:00Z")
        self.assertTrue(group["source_metadata_completeness"]["is_complete"])

        # Check signals
        signals = group["cross_source_signals"]
        self.assertTrue(any(s["statement"] == "Reported by multiple sources." for s in signals))
        for s in signals:
            self.assertIn("supporting_article_ids", s)

    # 8. End-to-end integration via search endpoint
    def test_search_endpoint_returns_cross_source_verification_in_groups_and_dashboard(self):
        with patch.dict(os.environ, {"NEWS_PROVIDER": "mock"}):
            app = create_app({"DATABASE_PATH": self.database_path})
            client = app.test_client()
            response = client.post("/api/search", json={"query": "climate change"})

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["success"])

        # Check groups have verification calculations
        groups = data.get("groups", [])
        for group in groups:
            self.assertIn("cross_source_verification", group)
            self.assertIn("independent_source_count", group)
            self.assertIn("supporting_reports", group)
            self.assertIn("conflicting_reports", group)
            self.assertIn("source_metadata_completeness", group)
            self.assertIn("time_of_first_report", group)
            self.assertIn("time_of_latest_report", group)

            # Check signals reference supporting_article_ids
            signals = group.get("cross_source_signals", [])
            for sig in signals:
                self.assertIn("supporting_article_ids", sig)

        # Check verification dashboard includes calculated fields
        dashboard = data.get("verification_dashboard", {})
        self.assertIn("independent_source_count", dashboard)
        self.assertIn("supporting_reports", dashboard)
        self.assertIn("conflicting_reports", dashboard)
        self.assertIn("source_metadata_completeness", dashboard)
        self.assertIn("time_of_first_report", dashboard)
        self.assertIn("time_of_latest_report", dashboard)


if __name__ == "__main__":
    unittest.main()
