import os
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app import create_app
from app.providers.gdelt_provider import GDELTProvider
from app.providers.mock_provider import MockNewsProvider


class MockNewsProviderTestCase(unittest.TestCase):
    def test_mock_provider_returns_normalized_articles(self):
        articles = MockNewsProvider().search("climate change")

        self.assertEqual(len(articles), 3)
        self.assertTrue(
            all(article.source_provider == "mock" for article in articles)
        )
        self.assertTrue(
            all(article.to_dict()["title"] for article in articles)
        )
        self.assertTrue(
            all(
                article.to_dict()["url"].startswith("https://")
                for article in articles
            )
        )

    def test_mock_provider_does_not_require_network_request(self):
        with TemporaryDirectory() as temp_dir:
            database_path = os.path.join(temp_dir, "test.db")

            with patch.dict(
                os.environ,
                {
                    "NEWS_PROVIDERS": "mock",
                    "NEWS_PROVIDER": "mock",
                    "NEWSDATA_ENABLED": "false",
                },
            ), patch(
                "app.providers.gdelt_provider.urlopen",
                side_effect=AssertionError("network request made"),
            ):
                client = create_app(
                    {"DATABASE_PATH": database_path}
                ).test_client()

                response = client.post(
                    "/api/search",
                    json={"query": "technology"},
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json["results"][0]["source_provider"],
            "mock",
        )

    def test_mock_provider_selection_works(self):
        with patch.dict(
            os.environ,
            {
                "NEWS_PROVIDERS": "mock",
                "NEWS_PROVIDER": "mock",
                "NEWSDATA_ENABLED": "false",
            },
        ):
            app = create_app()

        provider = app.extensions["search_orchestrator"].search_service
        self.assertIsInstance(provider.providers[0], MockNewsProvider)

    def test_gdelt_is_the_default_provider(self):
        with patch.dict(os.environ, {}, clear=True):
            app = create_app()

        provider = app.extensions["search_orchestrator"].search_service
        self.assertIsInstance(provider.providers[0], GDELTProvider)


if __name__ == "__main__":
    unittest.main()