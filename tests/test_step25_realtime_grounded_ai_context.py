import unittest
from tempfile import TemporaryDirectory

from app import create_app
from app.models.article import Article
from app.providers.ai_provider import AIProvider, MockAIProvider
from app.repositories.article_repository import ArticleRepository
from app.services.context_builder import ContextBuilder
from app.services.provenance_service import ProvenanceService
from app.services.question_answer_service import QuestionAnswerService
from app.services.search_orchestrator import SearchOrchestrator
from app.services.summary_service import SummaryService
from app.services.timeline_service import TimelineService


class FabricatingAllSourcesProvider(AIProvider):
    name = "fabricated_mock"

    def summarize(self, instruction, context):
        return "Summary"

    def answer(self, instruction, context, question):
        return {
            "answer": "Fabricated breaking news without valid grounding.",
            "supporting_article_ids": [8888, 9999],
        }


class RealTimeGroundedAIContextTestCase(unittest.TestCase):
    def setUp(self):
        self.context_builder = ContextBuilder()
        self.provenance_service = ProvenanceService()
        self.timeline_service = TimelineService()
        self.mock_ai = MockAIProvider()
        self.qa_service = QuestionAnswerService(self.mock_ai)
        self.summary_service = SummaryService(self.mock_ai)

    def make_article(
        self,
        article_id,
        title,
        publication_date=None,
        url=None,
        publisher="Reuters",
        source_provider="gdelt",
        retrieved_at="2026-09-30T21:00:00Z",
        description=None,
    ):
        return Article(
            article_id=article_id,
            title=title,
            url=url or f"https://example.com/article/{article_id}",
            publisher=publisher,
            publication_date=publication_date,
            source_provider=source_provider,
            retrieved_at=retrieved_at,
            description=description or f"Reporting details for {title}",
        )

    def test_newly_retrieved_article_appearing_in_context(self):
        """When new articles arrive, grounded context is rebuilt and includes the new sources with full provenance."""
        art1 = self.make_article(1, "Initial Story", "2026-09-10", publisher="Associated Press", source_provider="gdelt")
        initial_context = self.context_builder.build("climate", [art1])

        self.assertEqual(len(initial_context["articles"]), 1)
        self.assertEqual(initial_context["supporting_article_ids"], [1])

        # Fresh article retrieved from live provider
        art2 = self.make_article(
            2,
            "Fresh Corroborating Evidence",
            "2026-09-12",
            publisher="Bloomberg",
            source_provider="newsapi",
            retrieved_at="2026-09-30T21:15:00Z",
        )

        rebuilt_context = self.context_builder.rebuild("climate", [art1, art2])

        # Verify newly retrieved article appears in articles and supporting_references
        self.assertEqual(len(rebuilt_context["articles"]), 2)
        article_ids = [a["article_id"] for a in rebuilt_context["articles"]]
        self.assertIn(1, article_ids)
        self.assertIn(2, article_ids)

        # Supporting references and IDs must include the newly retrieved article
        self.assertIn(2, rebuilt_context["supporting_article_ids"])
        supporting_refs = rebuilt_context["supporting_references"]
        fresh_ref = next(r for r in supporting_refs if r["article_id"] == 2)
        self.assertEqual(fresh_ref["publisher"], "Bloomberg")
        self.assertEqual(fresh_ref["source_provider"], "newsapi")
        self.assertEqual(fresh_ref["retrieved_at"], "2026-09-30T21:15:00Z")
        self.assertEqual(fresh_ref["publication_date"], "2026-09-12")

    def test_updated_timeline_context(self):
        """Summary and grounded context reflect timeline changes after newly retrieved articles arrive."""
        art1 = self.make_article(1, "Historical Development 1", "2026-01-10")
        initial_timeline = self.timeline_service.generate([art1], [])
        self.assertEqual(len(initial_timeline), 1)

        # Generate initial summaries
        initial_summaries = self.summary_service.generate("history", [art1], [], initial_timeline)
        init_timeline_summary = next(s for s in initial_summaries if s["summary_type"] == "timeline")
        self.assertEqual(init_timeline_summary["supporting_article_ids"], [1])

        # New article arrives and updates timeline
        art2 = self.make_article(2, "Recent Development 2", "2026-02-15")
        updated_timeline = self.timeline_service.update_timeline(initial_timeline, [art2])
        self.assertEqual(len(updated_timeline), 2)
        self.assertTrue(updated_timeline[1]["updated"])

        # Rebuild grounded context with the updated timeline
        updated_context = self.context_builder.rebuild(
            "history",
            [art1, art2],
            timeline=updated_timeline,
        )
        self.assertEqual(len(updated_context["timeline"]), 2)
        self.assertTrue(any(e.get("updated") for e in updated_context["timeline"]))

        # Generate updated summaries after timeline changes
        updated_summaries = self.summary_service.generate("history", [art1, art2], [], updated_timeline)
        updated_timeline_summary = next(s for s in updated_summaries if s["summary_type"] == "timeline")

        # Summary context now includes both article IDs from the updated timeline
        self.assertEqual(updated_timeline_summary["supporting_article_ids"], [1, 2])
        self.assertIn("Timeline covers 2 chronological development(s)", updated_timeline_summary["summary"])

    def test_source_attribution(self):
        """Every grounded answer exposes supporting article IDs and full provenance source references."""
        art1 = self.make_article(1, "Breakthrough in AI", "2026-09-01", publisher="Nature", source_provider="gdelt")
        art2 = self.make_article(2, "AI Safety Standard Adopted", "2026-09-05", publisher="Science Daily", source_provider="newsapi")
        context = self.context_builder.build("artificial intelligence", [art1, art2])

        # Ask question requiring source attribution
        result = self.qa_service.answer("How many sources reported this?", context)

        self.assertTrue(result["success"])
        # Every answer must expose supporting article IDs
        self.assertEqual(sorted(result["supporting_article_ids"]), [1, 2])
        self.assertIn("Nature", result["answer"])
        self.assertIn("Science Daily", result["answer"])

        # Enrich answer with provenance service
        enriched = self.provenance_service.enrich_answer(result, [art1, art2])
        self.assertIn("sources", enriched)
        self.assertEqual(len(enriched["sources"]), 2)
        publishers = [s["publisher"] for s in enriched["sources"]]
        self.assertIn("Nature", publishers)
        self.assertIn("Science Daily", publishers)
        providers = [s["source_provider"] for s in enriched["sources"]]
        self.assertIn("gdelt", providers)
        self.assertIn("newsapi", providers)

    def test_insufficient_evidence(self):
        """If fresh evidence or information is unavailable, the system says so and never invents breaking news."""
        art = self.make_article(1, "Local City Hall Renovation", "2026-05-01", description="City hall repairs commence.")
        context = self.context_builder.build("city hall", [art])

        # 1. Ask about breaking news on an unrelated topic not in context
        res1 = self.qa_service.answer("What is the breaking news on the lunar space station?", context)
        self.assertTrue(res1["success"])
        self.assertIn("unavailable", res1["answer"].lower())
        self.assertEqual(res1["supporting_article_ids"], [])

        # 2. Ask with completely empty context
        empty_context = self.context_builder.build("unknown", [])
        res2 = self.qa_service.answer("What are the latest updates?", empty_context)
        self.assertTrue(res2["success"])
        self.assertTrue(
            "unavailable" in res2["answer"].lower() or "do not provide enough information" in res2["answer"].lower()
        )
        self.assertEqual(res2["supporting_article_ids"], [])

        # 3. Check breaking news on matching topic with grounded reporting
        res3 = self.qa_service.answer("What is the latest breaking news on city hall renovation?", context)
        self.assertTrue(res3["success"])
        self.assertIn("City Hall Renovation", res3["answer"])
        self.assertEqual(res3["supporting_article_ids"], [1])

    def test_fabricated_source_prevention(self):
        """Fabricated sources are stripped, and answers based solely on nonexistent articles are rejected."""
        valid_art = self.make_article(10, "Verified Grounded Article", publisher="Legit Media")
        context = self.context_builder.build("grounded topic", [valid_art])

        # Provider that fabricates nonexistent sources 8888 and 9999
        hallucinating_service = QuestionAnswerService(FabricatingAllSourcesProvider())
        result = hallucinating_service.answer("What happened?", context)

        self.assertTrue(result["success"])
        # All fabricated sources must be stripped, leaving no valid sources
        self.assertEqual(result["supporting_article_ids"], [])
        self.assertNotIn(8888, result["supporting_article_ids"])
        self.assertNotIn(9999, result["supporting_article_ids"])
        # Claims from unsupported / fabricated information must not be generated
        self.assertIn("do not provide enough information", result["answer"])

    def test_search_orchestrator_answer_question_integration(self):
        """Integration test: SearchOrchestrator answer_question rebuilds context with newly stored articles."""
        temp_dir = TemporaryDirectory()
        db_path = f"{temp_dir.name}/test_step25.db"
        app = create_app({
            "TESTING": True,
            "NEWS_PROVIDER": "mock",
            "DATABASE_PATH": db_path,
        })
        client = app.test_client()

        with app.app_context():
            repo = app.extensions["article_repository"]
            orchestrator = app.extensions["search_orchestrator"]

            # Save initial article
            repo.save_article(self.make_article(1, "Initial Discovery", "2026-01-01", publisher="Outlet A"))

            ans1 = orchestrator.answer_question("How many sources reported this?", "Discovery")
            self.assertTrue(ans1["success"])
            self.assertEqual(len(ans1["supporting_article_ids"]), 1)
            self.assertEqual(ans1["sources"][0]["publisher"], "Outlet A")

            # Newly retrieved article arrives into database
            repo.save_article(self.make_article(2, "Second Corroborating Discovery", "2026-01-05", publisher="Outlet B"))

            # Ask question again: context is rebuilt automatically with the fresh article
            ans2 = orchestrator.answer_question("How many sources reported this?", "Discovery")
            self.assertTrue(ans2["success"])
            self.assertEqual(len(ans2["supporting_article_ids"]), 2)
            publishers = [s["publisher"] for s in ans2["sources"]]
            self.assertIn("Outlet A", publishers)
            self.assertIn("Outlet B", publishers)

            # Test through HTTP endpoint /api/question
            http_res = client.post(
                "/api/question",
                json={"question": "How many sources reported this?", "query": "Discovery"},
            )
            self.assertEqual(http_res.status_code, 200)
            data = http_res.get_json()
            self.assertTrue(data["success"])
            self.assertEqual(len(data["supporting_article_ids"]), 2)
            self.assertEqual(len(data["sources"]), 2)

        temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
