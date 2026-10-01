import os
import unittest
from tempfile import TemporaryDirectory

from app import create_app
from app.models.article import Article
from app.providers.base_provider import NewsProvider
from app.providers.multi_provider import MultiProvider
from app.services.cross_source_service import CrossSourceService
from app.services.search_orchestrator import SearchOrchestrator


class MockMultiProvider(NewsProvider):
    def __init__(self, batches, name="mock_provider"):
        super().__init__()
        self.name = name
        self.batches = list(batches)
        self.call_count = 0

    def search(self, query):
        idx = min(self.call_count, len(self.batches) - 1)
        self.call_count += 1
        return list(self.batches[idx])


class Step24CrossSourceVerificationSignalsTestCase(unittest.TestCase):
    """Test suite verifying Step 24: Real-time cross-source verification signals with mocked multi-provider data."""

    def setUp(self):
        self.cross_source = CrossSourceService()
        self.database_directory = TemporaryDirectory()
        self.db_path = os.path.join(self.database_directory.name, "step24_test.db")
        self.app = create_app(
            {
                "TESTING": True,
                "DATABASE_PATH": self.db_path,
                "NEWS_PROVIDERS": "mock",
            }
        )
        self.client = self.app.test_client()
        self.repository = self.app.extensions["article_repository"]

    def tearDown(self):
        self.database_directory.cleanup()

    def set_multi_provider(self, providers):
        multi = MultiProvider(providers=providers)
        orchestrator = SearchOrchestrator(
            multi,
            self.repository,
            ai_provider=self.app.extensions["ai_provider"],
        )
        self.app.extensions["search_orchestrator"] = orchestrator
        return orchestrator

    # 1. Compare normalized articles across different providers about the same story
    def test_compare_normalized_articles_across_providers(self):
        art_gdelt = Article(
            title="Clean Hydrogen Turbine Commercialized",
            url="https://gdelt.example.com/hydrogen-turbine",
            publisher="Energy Global Wire",
            publication_date="2026-09-01T08:00:00Z",
            description="First grid-scale 100% clean hydrogen turbine enters commercial operation.",
            source_provider="gdelt",
            article_id=1,
        )
        art_thenewsapi = Article(
            title="Power Grid Integrates Clean Hydrogen Turbine",
            url="https://thenewsapi.example.com/hydrogen-turbine-live",
            publisher="Power Systems Daily",
            publication_date="2026-09-01T09:30:00Z",
            description="Operators confirm successful synchronisation of the zero-emission turbine.",
            source_provider="thenewsapi",
            article_id=2,
        )

        verification = self.cross_source.verify_related_articles([art_gdelt, art_thenewsapi])

        # Requirement 2: Identify independent publishers and supporting reports
        self.assertEqual(verification["independent_source_count"], 2)
        self.assertEqual(verification["independent_publishers_count"], 2)
        self.assertEqual(verification["number_of_independent_publishers"], 2)
        self.assertEqual(verification["supporting_reports"], [1, 2])
        self.assertEqual(verification["supporting_reports_count"], 2)
        self.assertEqual(verification["number_of_supporting_reports"], 2)
        self.assertEqual(verification["conflicting_reports"], [])
        self.assertEqual(verification["conflicting_reports_count"], 0)
        self.assertFalse(verification["is_single_source"])
        self.assertFalse(verification["single_source_story"])

        # Requirement 2: Earliest and latest publication times
        self.assertEqual(verification["time_of_first_report"], "2026-09-01T08:00:00Z")
        self.assertEqual(verification["earliest_publication_time"], "2026-09-01T08:00:00Z")
        self.assertEqual(verification["time_of_latest_report"], "2026-09-01T09:30:00Z")
        self.assertEqual(verification["latest_publication_time"], "2026-09-01T09:30:00Z")

        # Requirement 3 & 4: Signals reference article IDs and display neutral label
        signals = verification["signals"]
        self.assertTrue(any(s.get("label") == "Multiple sources reporting" for s in signals))
        for sig in signals:
            self.assertTrue("supporting_article_ids" in sig or "article_ids" in sig)
            ids = sig.get("supporting_article_ids") or sig.get("article_ids")
            self.assertGreater(len(ids), 0)

    # 2. Identify single-source stories across providers
    def test_single_source_story_identification(self):
        art_single = Article(
            title="Unconfirmed Deep Space Signal Received",
            url="https://gdelt.example.com/signal",
            publisher="Astronomy Dispatch",
            publication_date="2026-09-05T10:00:00Z",
            description="Observatory logs anomalous narrow-band microwave signal.",
            source_provider="gdelt",
            article_id=10,
        )

        verification = self.cross_source.verify_related_articles([art_single])

        self.assertEqual(verification["independent_source_count"], 1)
        self.assertTrue(verification["is_single_source"])
        self.assertTrue(verification["single_source_story"])
        self.assertEqual(verification["single_source_stories"], [10])

        # Requirement 4: Neutral label "Single-source report"
        signals = verification["signals"]
        single_sig = next(s for s in signals if s.get("label") == "Single-source report" or s.get("type") == "single_source_report")
        self.assertEqual(single_sig["label"], "Single-source report")
        self.assertIn(10, single_sig.get("supporting_article_ids") or single_sig.get("article_ids"))

    # 3. Identify conflicting reports and preserve disagreements
    def test_conflicting_reports_identification_and_preservation(self):
        art_announce = Article(
            title="Biotech Firm Announces Successful Phase 3 Drug Trial",
            url="https://gdelt.example.com/trial-success",
            publisher="Medical Wire",
            publication_date="2026-09-10T12:00:00Z",
            description="Company announces candidate achieved primary clinical endpoints.",
            source_provider="gdelt",
            article_id=101,
        )
        art_dispute = Article(
            title="Independent Review Disputes Trial Methodology",
            url="https://thenewsapi.example.com/trial-dispute",
            publisher="Clinical Review",
            publication_date="2026-09-11T15:00:00Z",
            description="Biostatisticians dispute results and reject claims of broad efficacy.",
            source_provider="thenewsapi",
            article_id=102,
        )

        verification = self.cross_source.verify_related_articles([art_announce, art_dispute])

        # Requirement 2: Possible conflicting reports
        self.assertEqual(verification["conflicting_reports"], [102])
        self.assertEqual(verification["conflicting_reports_count"], 1)
        self.assertEqual(verification["possible_conflicting_reports"], [102])
        self.assertEqual(verification["supporting_reports"], [101])

        # Requirement 4: Neutral label "Conflicting reports detected"
        signals = verification["signals"]
        conflict_sig = next(s for s in signals if s.get("label") == "Conflicting reports detected")
        self.assertEqual(conflict_sig["label"], "Conflicting reports detected")
        self.assertEqual(conflict_sig["supporting_article_ids"], [102])

        # Requirement 6: Disagreements are preserved (both article IDs are tracked)
        all_ids = set(verification["supporting_reports"] + verification["conflicting_reports"])
        self.assertEqual(all_ids, {101, 102})

    # 4. Identify missing source metadata
    def test_missing_source_metadata_identification(self):
        art_incomplete = Article(
            title="Solar Farm Ribbon Cutting",
            url="https://example.com/solar",
            publisher=None,  # Missing publisher
            publication_date=None,  # Missing publication date
            description="New 50MW solar plant opens in desert region.",
            source_provider="gdelt",
            article_id=50,
        )

        verification = self.cross_source.verify_related_articles([art_incomplete])
        metadata = verification["source_metadata_completeness"]

        self.assertFalse(metadata["is_complete"])
        self.assertIn("publisher", metadata["missing_fields"])
        self.assertIn("publication_date", metadata["missing_fields"])
        self.assertIn(50, metadata["incomplete_article_ids"])

        # Requirement 4: Neutral label "Limited source information"
        signals = verification["signals"]
        meta_sig = next(s for s in signals if s.get("label") == "Limited source information")
        self.assertEqual(meta_sig["label"], "Limited source information")
        self.assertIn(50, meta_sig["supporting_article_ids"])

    # 5. Requirement 5: Strict neutrality guardrails (no credibility/bias scores or rankings)
    def test_neutrality_guardrails_no_scores_or_truth_labels(self):
        art1 = Article(
            title="Electric Aviation Prototype Flies",
            url="https://a.com/fly",
            publisher="Aero News",
            publication_date="2026-09-12T10:00:00Z",
            description="First all-electric commuter aircraft makes maiden flight.",
            source_provider="gdelt",
            article_id=1,
        )
        art2 = Article(
            title="Aviation Authority Denies Flight Approval Was Granted",
            url="https://b.com/fly-deny",
            publisher="Aero Bureau",
            publication_date="2026-09-12T14:00:00Z",
            description="Spokesperson denies flight had regulatory clearance.",
            source_provider="thenewsapi",
            article_id=2,
        )

        verification = self.cross_source.verify_related_articles([art1, art2])

        # Prohibited score keys
        prohibited_keys = [
            "credibility_score", "credibility", "bias_score", "bias",
            "publisher_ranking", "publisher_rank", "publisher_rankings",
            "fake_news_score", "truth_score", "trustworthy_score", "verdict"
        ]
        for key in prohibited_keys:
            self.assertNotIn(key, verification)

        # Prohibited words in any signal
        prohibited_words = ["fake", "hoax", "true", "false", "trustworthy", "untrustworthy", "debunked"]
        for sig in verification["signals"]:
            label = sig.get("label", "").lower()
            statement = sig.get("statement", "").lower()
            sig_name = sig.get("signal", "").lower()
            for word in prohibited_words:
                self.assertNotIn(word, label)
                self.assertNotIn(word, statement)
                self.assertNotIn(word, sig_name)

    # 6. Requirement 7: Real-time update of verification signals when new articles arrive
    def test_realtime_verification_signal_update_on_new_arrival(self):
        # Poll cycle 1: Only GDELT report exists (Single-source report)
        art_poll1 = Article(
            title="Solid State Battery Factory Breaks Ground",
            url="https://gdelt.example.com/battery-factory",
            publisher="EV Industry Today",
            publication_date="2026-09-15T09:00:00Z",
            description="Construction begins on 20GWh solid-state electrolyte facility.",
            source_provider="gdelt",
        )

        # Poll cycle 2: The News API brings second independent report (Multiple sources reporting)
        art_poll2 = Article(
            title="New Battery Plant Underway",
            url="https://thenewsapi.example.com/battery-plant-construction",
            publisher="Manufacturing Weekly",
            publication_date="2026-09-15T11:00:00Z",
            description="Suppliers confirm equipment orders for new solid-state battery gigafactory.",
            source_provider="thenewsapi",
        )

        p_gdelt = MockMultiProvider([[art_poll1], [art_poll1]], name="gdelt")
        p_thenewsapi = MockMultiProvider([[], [art_poll2]], name="thenewsapi")

        self.set_multi_provider([p_gdelt, p_thenewsapi])

        # Initial Search (Poll 1)
        res1 = self.client.post("/api/search", json={"query": "solid state battery"})
        self.assertEqual(res1.status_code, 200)
        data1 = res1.json

        # Dashboard in Poll 1: single publisher, single source
        dashboard1 = data1["verification_dashboard"]
        self.assertEqual(dashboard1["independent_source_count"], 1)
        self.assertTrue(dashboard1["is_single_source"])
        signals1 = dashboard1["neutral_signals"]
        self.assertTrue(any(s.get("label") == "Single-source report" for s in signals1))

        # Real-time update (Poll 2)
        res2 = self.client.post("/api/search", json={"query": "solid state battery"})
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json

        # Dashboard in Poll 2: 2 independent publishers, updated to multiple sources reporting
        dashboard2 = data2["verification_dashboard"]
        self.assertEqual(dashboard2["independent_source_count"], 2)
        self.assertFalse(dashboard2["is_single_source"])
        self.assertTrue(dashboard2["multiple_sources_found"])
        signals2 = dashboard2["neutral_signals"]
        self.assertTrue(any(s.get("label") == "Multiple sources reporting" for s in signals2))

    # 7. Real-time update when conflicting report arrives
    def test_realtime_conflicting_signal_update(self):
        art_initial = Article(
            title="Space Agency Confirms Discovery of Water Ice on Moon",
            url="https://gdelt.example.com/water-ice",
            publisher="Space Science Wire",
            publication_date="2026-09-18T08:00:00Z",
            description="Orbiter data indicates substantive subsurface water ice deposits.",
            source_provider="gdelt",
        )
        art_dispute = Article(
            title="Geologists Dispute Lunar Water Ice Interpretation",
            url="https://thenewsapi.example.com/water-ice-dispute",
            publisher="Planetary Geology Journal",
            publication_date="2026-09-18T12:00:00Z",
            description="Researchers reject water signature, attributing signal to surface roughness.",
            source_provider="thenewsapi",
        )

        p_gdelt = MockMultiProvider([[art_initial], [art_initial]], name="gdelt")
        p_thenewsapi = MockMultiProvider([[], [art_dispute]], name="thenewsapi")

        self.set_multi_provider([p_gdelt, p_thenewsapi])

        # Poll 1
        res1 = self.client.post("/api/search", json={"query": "lunar water ice"})
        self.assertFalse(res1.json["verification_dashboard"]["has_conflicting_reports"])

        # Poll 2 (Conflicting report arrives)
        res2 = self.client.post("/api/search", json={"query": "lunar water ice"})
        dashboard2 = res2.json["verification_dashboard"]
        self.assertTrue(dashboard2["has_conflicting_reports"])
        signals2 = dashboard2["neutral_signals"]
        self.assertTrue(any(s.get("label") == "Conflicting reports detected" for s in signals2))
        # Both articles are preserved
        self.assertEqual(len(res2.json["results"]), 2)


if __name__ == "__main__":
    unittest.main()
