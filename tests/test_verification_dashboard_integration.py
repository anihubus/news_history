import os
import unittest
from tempfile import TemporaryDirectory

from app import create_app
from app.models.article import Article


class StubProvider:
    name = "stub"

    def __init__(self, articles=None, error=None):
        self.articles = articles or []
        self.error = error

    def search(self, query):
        if self.error:
            raise self.error
        return self.articles


class VerificationDashboardIntegrationTestCase(unittest.TestCase):
    def setUp(self):
        self.database_directory = TemporaryDirectory()
        self.app = create_app({
            "TESTING": True,
            "DATABASE_PATH": os.path.join(self.database_directory.name, "news_history.db"),
            "NEWS_PROVIDERS": "mock",
            "AI_PROVIDER": "mock",
        })
        self.client = self.app.test_client()

    def tearDown(self):
        self.database_directory.cleanup()

    def set_provider(self, provider):
        self.app.extensions["news_provider"] = provider
        self.app.extensions["search_orchestrator"].retrieval_service.news_provider = provider

    def test_search_endpoint_returns_verification_dashboard(self):
        article = Article(
            title="Clean Energy Summit Opens",
            url="https://example.com/energy-1",
            publisher="Global Tribune",
            publication_date="2026-09-15",
            description="Leaders gather to discuss renewable grids.",
            source_provider="stub",
            article_id=1,
        )
        self.set_provider(StubProvider([article]))

        response = self.client.post("/api/search", json={"query": "energy"})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["success"])
        self.assertIn("verification_dashboard", response.json)

        dashboard = response.json["verification_dashboard"]
        self.assertIn("independent_source_count", dashboard)
        self.assertIn("total_sources", dashboard)
        self.assertIn("multiple_sources_found", dashboard)
        self.assertIn("has_conflicting_reports", dashboard)
        self.assertIn("warnings", dashboard)
        self.assertIn("sources", dashboard)
        self.assertIn("disclaimer", dashboard)
        self.assertIn("summary_statement", dashboard)

    def test_dashboard_multi_source_and_supporting_reports(self):
        art1 = Article(
            title="Global Treaty Signed",
            url="https://reuters.com/treaty",
            publisher="Reuters",
            publication_date="2026-09-01",
            description="Nations sign landmark treaty.",
            source_provider="stub",
            article_id=1,
        )
        art2 = Article(
            title="Treaty Ratified Globally",
            url="https://apnews.com/treaty",
            publisher="Associated Press",
            publication_date="2026-09-02",
            description="Delegates ratify international treaty.",
            source_provider="stub",
            article_id=2,
        )
        self.set_provider(StubProvider([art1, art2]))

        response = self.client.post("/api/search", json={"query": "treaty"})
        dashboard = response.json["verification_dashboard"]

        self.assertEqual(dashboard["independent_source_count"], 2)
        self.assertEqual(dashboard["total_sources"], 2)
        self.assertTrue(dashboard["multiple_sources_found"])
        self.assertFalse(dashboard["has_conflicting_reports"])
        self.assertEqual(dashboard["summary_statement"], "Reported by multiple sources.")

        # Check source items contain all required fields
        self.assertEqual(len(dashboard["sources"]), 2)
        for src in dashboard["sources"]:
            self.assertTrue(src["original_url"].startswith("http"))
            self.assertIn(src["publisher"], ["Reuters", "Associated Press"])
            self.assertTrue(src["publication_date"].startswith("2026-09"))
            self.assertEqual(src["source_provider"], "stub")
            self.assertEqual(src["independent_source_count"], 2)
            self.assertTrue(src["is_supporting"])
            self.assertFalse(src["is_conflicting"])
            self.assertEqual(src["reporting_status"], "Supporting report")
            self.assertFalse(src["has_warnings"])

    def test_dashboard_conflicting_reports_detection(self):
        art1 = Article(
            title="Agreement Concluded",
            url="https://source-a.com/deal",
            publisher="Source A",
            publication_date="2026-09-01",
            description="Officials announce deal concluded.",
            source_provider="stub",
            article_id=1,
        )
        art2 = Article(
            title="Agreement Denied",
            url="https://source-b.com/deal",
            publisher="Source B",
            publication_date="2026-09-02",
            description="Spokesperson denies agreement was reached.",
            source_provider="stub",
            article_id=2,
        )
        self.set_provider(StubProvider([art1, art2]))

        response = self.client.post("/api/search", json={"query": "agreement"})
        dashboard = response.json["verification_dashboard"]

        self.assertTrue(dashboard["has_conflicting_reports"])
        self.assertEqual(dashboard["summary_statement"], "Reports contain differing information.")
        self.assertGreaterEqual(dashboard["conflicting_reports_count"], 1)

        conflicting_sources = [s for s in dashboard["sources"] if s["is_conflicting"]]
        self.assertEqual(len(conflicting_sources), 1)
        self.assertEqual(conflicting_sources[0]["reporting_status"], "Conflicting report")

    def test_dashboard_missing_metadata_warnings_with_explanations(self):
        art = Article(
            title="Incomplete metadata report",
            url="",
            publisher="",
            publication_date="",
            description="Brief text without metadata.",
            source_provider="stub",
            article_id=1,
        )
        self.set_provider(StubProvider([art]))

        response = self.client.post("/api/search", json={"query": "incomplete"})
        dashboard = response.json["verification_dashboard"]

        self.assertTrue(dashboard["has_warnings"])
        warning_types = [w["type"] for w in dashboard["warnings"]]
        self.assertIn("missing_publisher", warning_types)
        self.assertIn("missing_publication_date", warning_types)
        self.assertIn("missing_original_url", warning_types)
        self.assertIn("incomplete_metadata", warning_types)

        # Verify every warning contains a neutral explanation
        for w in dashboard["warnings"]:
            self.assertIn("explanation", w)
            self.assertIsInstance(w["explanation"], str)
            self.assertGreater(len(w["explanation"]), 0)

        # Verify per-source warning exposure
        source_record = dashboard["sources"][0]
        self.assertTrue(source_record["has_warnings"])
        self.assertEqual(source_record["publisher"], "Publisher not identified")
        self.assertEqual(source_record["publication_date"], "Date unavailable")

    def test_dashboard_neutrality_guardrails(self):
        art = Article(
            title="Observational event",
            url="https://example.com/obs",
            publisher="Daily Press",
            publication_date="2026-09-01",
            description="Reported observation.",
            source_provider="stub",
            article_id=1,
        )
        self.set_provider(StubProvider([art]))

        response = self.client.post("/api/search", json={"query": "observation"})
        dashboard = response.json["verification_dashboard"]

        # Assert no prohibited scoring or subjective verdicts
        prohibited = [
            "fake news", "verified true", "hoax", "debunked", "credibility_score",
            "trust_rank", "political_bias", "bias_score"
        ]
        dashboard_str = str(dashboard).lower()
        for term in prohibited:
            self.assertNotIn(term, dashboard_str)

        # Assert disclaimer presence
        self.assertIn("observable verification signals", dashboard["disclaimer"].lower())
        self.assertIn("not definitive fact-checking", dashboard["disclaimer"].lower())

    def test_end_to_end_search_timeline_groups_qa_dashboard_integration(self):
        art1 = Article(
            title="Tech Summit Held",
            url="https://tech1.com/summit",
            publisher="Tech Times",
            publication_date="2026-09-10",
            description="Global tech summit kicks off.",
            source_provider="stub",
            article_id=1,
        )
        art2 = Article(
            title="Tech Summit Keynote",
            url="https://tech2.com/summit",
            publisher="Silicon Wire",
            publication_date="2026-09-11",
            description="Leaders deliver keynote speeches at tech summit.",
            source_provider="stub",
            article_id=2,
        )
        self.set_provider(StubProvider([art1, art2]))

        # 1. Search request
        search_res = self.client.post("/api/search", json={"query": "tech summit"})
        self.assertEqual(search_res.status_code, 200)
        data = search_res.json

        # Validate search, groups, timeline, summary, provenance, and verification dashboard
        self.assertTrue(data["success"])
        self.assertEqual(len(data["results"]), 2)
        self.assertIn("groups", data)
        self.assertIn("timeline", data)
        self.assertIn("summary", data)
        self.assertIn("provenance_signals", data)
        self.assertIn("verification_dashboard", data)
        self.assertEqual(data["verification_dashboard"]["independent_source_count"], 2)

        # 2. Q&A request on the same history
        qa_res = self.client.post("/api/question", json={
            "question": "How many sources reported this?",
            "query": "tech summit"
        })
        self.assertEqual(qa_res.status_code, 200)
        qa_data = qa_res.json
        self.assertTrue(qa_data["success"])
        self.assertIn("2 independent source(s)", qa_data["answer"])
        self.assertIn("sources", qa_data)
        self.assertEqual(len(qa_data["sources"]), 2)


if __name__ == "__main__":
    unittest.main()
