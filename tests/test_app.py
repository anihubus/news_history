import unittest
from tempfile import TemporaryDirectory

from app import create_app
from app.models.article import Article
from app.providers.gdelt_provider import ProviderError, RateLimitError
from app.providers.ai_provider import AIProviderError, MockAIProvider
from app.services.summary_service import SummaryService
from app.services.search_orchestrator import SearchOrchestrator


class StubProvider:
    def __init__(self, articles=None, error=None):
        self.articles = articles or []
        self.error = error

    def search(self, query):
        if self.error:
            raise self.error
        return self.articles


class AppTestCase(unittest.TestCase):
    def setUp(self):
        self.database_directory = TemporaryDirectory()
        self.app = create_app(
            {
                "TESTING": True,
                "NEWS_PROVIDER": "mock",
                "DATABASE_PATH": f"{self.database_directory.name}/test.db",
            }
        )
        self.client = self.app.test_client()

    def set_provider(self, provider):
        self.app.extensions["search_orchestrator"] = SearchOrchestrator(
            provider,
            self.app.extensions["article_repository"],
            ai_provider=self.app.extensions["ai_provider"],
        )

    def tearDown(self):
        self.database_directory.cleanup()

    def test_homepage_returns_success(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"News History", response.data)

    def test_search_with_valid_query_returns_success(self):
        article = Article(
            title="Climate policy update",
            url="https://example.com/climate-policy",
            publisher="example.com",
            publication_date="20260918000000",
            description=None,
            source_provider="gdelt",
        )
        self.set_provider(StubProvider([article]))

        response = self.client.post(
            "/api/search",
            json={"query": "  climate change  "},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["success"], True)
        self.assertEqual(response.json["query"], "climate change")
        self.assertEqual(response.json["message"], None)
        self.assertEqual(response.json["results"][0]["title"], article.title)
        self.assertEqual(response.json["results"][0]["publisher"], article.publisher)
        self.assertEqual(response.json["results"][0]["publication_date"], article.publication_date)
        self.assertEqual(response.json["results"][0]["source_provider"], article.source_provider)
        self.assertIn("retrieved_at", response.json["results"][0])
        self.assertEqual(response.json["results"][0]["url"], article.url)
        self.assertIn("groups", response.json)
        self.assertEqual(response.json["groups"][0]["article_count"], 1)
        self.assertIn("sources", response.json["groups"][0])
        self.assertIn("timeline", response.json)
        self.assertEqual(len(response.json["timeline"]), 1)
        self.assertIn("supporting_sources", response.json["timeline"][0])
        self.assertIsNotNone(response.json["summary"])
        self.assertIn("sources", response.json["summary"])
        self.assertEqual(self.app.extensions["article_repository"].count_articles(), 1)

    def test_api_keeps_core_results_when_summary_fails(self):
        article = Article(
            title="Technology update",
            url="https://example.com/technology",
            publisher="Example",
            publication_date="20260918000000",
            description=None,
            source_provider="mock",
        )
        self.set_provider(StubProvider([article]))

        class FailingProvider(MockAIProvider):
            def summarize(self, instruction, context):
                raise AIProviderError("unavailable")

        orchestrator = self.app.extensions["search_orchestrator"]
        orchestrator.summary_service = SummaryService(FailingProvider())
        response = self.client.post("/api/search", json={"query": "technology"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json["results"]), 1)
        self.assertIsNone(response.json["summary"])
        self.assertIn("timeline", response.json)

    def test_question_endpoint_returns_grounded_answer(self):
        article = Article(
            title="Technology update",
            url="https://example.com/technology-question",
            publisher="Example",
            publication_date="20260918000000",
            description="A reported technology update.",
            source_provider="mock",
        )
        self.set_provider(StubProvider([article]))
        self.client.post("/api/search", json={"query": "technology"})

        response = self.client.post(
            "/api/question",
            json={"question": "What is covered?", "query": "technology"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["success"])
        self.assertEqual(response.json["supporting_article_ids"], [1])
        self.assertEqual(response.json["sources"][0]["url"], article.url)

    def test_search_with_empty_query_returns_client_error(self):
        self.set_provider(StubProvider())
        response = self.client.post("/api/search", json={"query": "   "})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json["success"], False)
        self.assertEqual(response.json["error"], "Search query cannot be empty.")

    def test_search_without_json_returns_client_error(self):
        response = self.client.post("/api/search", data="query=climate%20change")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json["success"], False)

    def test_search_provider_failure_returns_bad_gateway(self):
        self.set_provider(StubProvider(error=ProviderError()))

        response = self.client.post("/api/search", json={"query": "climate change"})

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json["success"], False)
        self.assertEqual(response.json["error"], "The news provider is temporarily unavailable.")

    def test_search_rate_limit_returns_controlled_response(self):
        self.set_provider(StubProvider(error=RateLimitError()))

        response = self.client.post("/api/search", json={"query": "climate change"})

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json["success"], False)
        self.assertEqual(response.json["status"], "rate_limited")
        self.assertEqual(
            response.json["error"],
            "The news provider is temporarily rate-limited. Please wait before trying again.",
        )

    def test_search_with_no_results_returns_success(self):
        self.set_provider(StubProvider())

        response = self.client.post("/api/search", json={"query": "unknown topic"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["success"], True)
        self.assertEqual(response.json["results"], [])
        self.assertIsNone(response.json["message"])


if __name__ == "__main__":
    unittest.main()
