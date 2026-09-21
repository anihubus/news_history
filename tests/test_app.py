import unittest
from tempfile import TemporaryDirectory

from app import create_app
from app.models.article import Article
from app.providers.gdelt_provider import ProviderError, RateLimitError
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
        self.assertEqual(response.json["results"][0], article.to_dict())
        self.assertIn("groups", response.json)
        self.assertEqual(response.json["groups"][0]["article_count"], 1)
        self.assertEqual(self.app.extensions["article_repository"].count_articles(), 1)

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
