import io
import json
import os
import socket
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from app import create_app
from app.database import initialize_database
from app.models.article import Article
from app.providers.base_provider import NewsProvider, ProviderError, RateLimitError
from app.providers.gdelt_provider import GDELTProvider
from app.providers.multi_provider import MultiProvider
from app.providers.thenewsapi_provider import TheNewsAPIProvider
from app.repositories.article_repository import ArticleRepository


class MockHTTPResponse:
    def __init__(self, data, status: int = 200):
        self.data = data
        self.status = status

    def read(self):
        if isinstance(self.data, (dict, list)):
            return json.dumps(self.data).encode("utf-8")
        if isinstance(self.data, bytes):
            return self.data
        return str(self.data).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class TheNewsAPIProviderTestCase(unittest.TestCase):
    def setUp(self):
        self.provider = TheNewsAPIProvider(
            api_key="test_api_token",
            base_url="https://api.thenewsapi.com/v1",
            timeout=5,
            max_results=10,
        )

        self.sample_payload = {
            "meta": {
                "found": 1,
                "returned": 1,
                "limit": 10,
                "page": 1,
            },
            "data": [
                {
                    "uuid": "article-uuid-001",
                    "title": "Breakthrough in Fusion Energy",
                    "description": "Scientists achieve net energy gain in a landmark experiment.",
                    "snippet": "Scientists achieve net energy gain...",
                    "url": "https://sciencedaily.com/fusion-breakthrough",
                    "image_url": "https://sciencedaily.com/images/fusion.jpg",
                    "language": "en",
                    "published_at": "2026-09-30T14:30:00Z",
                    "source": "sciencedaily.com",
                    "categories": ["science", "tech"],
                }
            ],
        }

    # Requirement 2: Follow base NewsProvider interface
    def test_provider_implements_news_provider_interface(self):
        self.assertIsInstance(self.provider, NewsProvider)

    # Requirement 3 & 4: Read API key from env or constructor, never hardcoded
    def test_missing_api_key_raises_provider_error(self):
        with patch.dict(os.environ, {}, clear=True):
            provider = TheNewsAPIProvider(api_key=None)
            with self.assertRaises(ProviderError) as ctx:
                provider.search("fusion")
            self.assertIn("missing", str(ctx.exception).lower())

    def test_api_key_read_from_environment(self):
        with patch.dict(os.environ, {"THENEWSAPI_API_KEY": "env_token_456"}):
            provider = TheNewsAPIProvider()
            self.assertEqual(provider.api_key, "env_token_456")

    # Requirement 6: Build request URL with proper endpoint and parameters
    def test_build_request_url(self):
        url = self.provider._build_request_url("fusion energy")
        self.assertIn("https://api.thenewsapi.com/v1/news/all", url)
        self.assertIn("search=fusion+energy", url)
        self.assertIn("api_token=test_api_token", url)
        self.assertIn("limit=10", url)

    def test_build_request_url_with_full_endpoint_base_url(self):
        provider = TheNewsAPIProvider(
            api_key="token123",
            base_url="https://api.thenewsapi.com/v1/news/all",
        )
        url = provider._build_request_url("quantum")
        self.assertEqual(url.count("/news/all"), 1)

    # Requirement 7, 8, 9, 10, 15: Successful response & normalization
    @patch("app.providers.thenewsapi_provider.urlopen")
    def test_successful_response_and_normalization(self, mock_urlopen):
        mock_urlopen.return_value = MockHTTPResponse(self.sample_payload)

        articles = self.provider.search("fusion energy")

        self.assertEqual(len(articles), 1)
        article = articles[0]
        self.assertIsInstance(article, Article)
        self.assertEqual(article.title, "Breakthrough in Fusion Energy")
        self.assertEqual(article.url, "https://sciencedaily.com/fusion-breakthrough")
        self.assertEqual(article.publisher, "sciencedaily.com")
        self.assertEqual(article.publication_date, "2026-09-30T14:30:00Z")
        self.assertEqual(article.description, "Scientists achieve net energy gain in a landmark experiment.")
        self.assertEqual(article.source_provider, "thenewsapi")
        self.assertIsNone(article.retrieved_at)
        self.assertIsNone(article.article_id)

    # Requirement 15: Normalization with snippet fallback and dict source
    def test_normalization_with_dict_source_and_snippet_fallback(self):
        payload = {
            "meta": {"found": 1, "returned": 1, "limit": 10, "page": 1},
            "data": [
                {
                    "uuid": "article-uuid-002",
                    "title": "Global Climate Accord Signed",
                    "description": None,
                    "snippet": "Delegates from 190 nations have signed a landmark treaty.",
                    "url": "https://bbc.com/news/climate-accord",
                    "published_at": "2026-09-30T10:00:00Z",
                    "source": {"id": "bbc", "name": "BBC News"},
                }
            ],
        }
        articles = self.provider._parse_response(payload)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].publisher, "BBC News")
        self.assertEqual(articles[0].description, "Delegates from 190 nations have signed a landmark treaty.")
        self.assertEqual(articles[0].source_provider, "thenewsapi")

    # Requirement 15: Missing optional fields
    def test_missing_optional_fields_normalized_to_none(self):
        payload = {
            "meta": {"found": 1, "returned": 1, "limit": 10, "page": 1},
            "data": [
                {
                    "uuid": "article-uuid-003",
                    "title": "Minimal Article Record",
                    "description": "",
                    "snippet": None,
                    "url": "https://example.com/minimal",
                    "published_at": "",
                    "source": None,
                }
            ],
        }
        articles = self.provider._parse_response(payload)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].title, "Minimal Article Record")
        self.assertEqual(articles[0].url, "https://example.com/minimal")
        self.assertIsNone(articles[0].publisher)
        self.assertIsNone(articles[0].publication_date)
        self.assertIsNone(articles[0].description)
        self.assertEqual(articles[0].source_provider, "thenewsapi")

    def test_invalid_article_items_skipped(self):
        payload = {
            "meta": {"found": 3, "returned": 3, "limit": 10, "page": 1},
            "data": [
                {"title": None, "url": "https://example.com/no-title"},
                {"title": "No URL Article", "url": None},
                {"title": "   ", "url": "https://example.com/empty-title"},
                "not a dict item",
                {"title": "Valid Article", "url": "https://example.com/valid"},
            ],
        }
        articles = self.provider._parse_response(payload)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].title, "Valid Article")

    # Requirement 11 & 15: Empty response
    @patch("app.providers.thenewsapi_provider.urlopen")
    def test_empty_response_returns_empty_list(self, mock_urlopen):
        mock_urlopen.return_value = MockHTTPResponse({"meta": {"found": 0, "returned": 0, "limit": 10, "page": 1}, "data": []})
        articles = self.provider.search("rare obscure topic")
        self.assertEqual(articles, [])

    # Requirement 11 & 15: Invalid API key (HTTP 401 & payload error)
    @patch("app.providers.thenewsapi_provider.urlopen")
    def test_invalid_api_key_http_401(self, mock_urlopen):
        mock_urlopen.side_effect = HTTPError(
            url="https://api.thenewsapi.com/v1/news/all",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=None,
        )
        with self.assertRaises(ProviderError) as ctx:
            self.provider.search("technology")
        self.assertIn("authentication failed", str(ctx.exception).lower())

    @patch("app.providers.thenewsapi_provider.urlopen")
    def test_invalid_api_key_payload_error(self, mock_urlopen):
        error_payload = {
            "error": {
                "code": "invalid_api_token",
                "message": "The API token provided is invalid.",
            }
        }
        mock_urlopen.return_value = MockHTTPResponse(error_payload)
        with self.assertRaises(ProviderError) as ctx:
            self.provider.search("technology")
        self.assertIn("authentication failed", str(ctx.exception).lower())

    # Requirement 11 & 15: Rate limit (HTTP 429 & payload error)
    @patch("app.providers.thenewsapi_provider.urlopen")
    def test_rate_limit_http_429(self, mock_urlopen):
        mock_urlopen.side_effect = HTTPError(
            url="https://api.thenewsapi.com/v1/news/all",
            code=429,
            msg="Too Many Requests",
            hdrs=None,
            fp=None,
        )
        with self.assertRaises(RateLimitError):
            self.provider.search("technology")

    @patch("app.providers.thenewsapi_provider.urlopen")
    def test_rate_limit_payload_error(self, mock_urlopen):
        error_payload = {
            "error": {
                "code": "rate_limit_reached",
                "message": "You have reached your request limit.",
            }
        }
        mock_urlopen.return_value = MockHTTPResponse(error_payload)
        with self.assertRaises(RateLimitError):
            self.provider.search("technology")

    # Requirement 11 & 15: Timeout handling
    @patch("app.providers.thenewsapi_provider.urlopen")
    def test_timeout_error_handling(self, mock_urlopen):
        mock_urlopen.side_effect = TimeoutError("Connection timed out")
        with self.assertRaises(ProviderError) as ctx:
            self.provider.search("technology")
        self.assertIn("timed out", str(ctx.exception).lower())

    @patch("app.providers.thenewsapi_provider.urlopen")
    def test_socket_timeout_error_handling(self, mock_urlopen):
        mock_urlopen.side_effect = socket.timeout("Socket timed out")
        with self.assertRaises(ProviderError) as ctx:
            self.provider.search("technology")
        self.assertIn("timed out", str(ctx.exception).lower())

    # Requirement 11 & 15: Connection failure handling
    @patch("app.providers.thenewsapi_provider.urlopen")
    def test_connection_failure_handling(self, mock_urlopen):
        mock_urlopen.side_effect = URLError(reason="Name or service not known")
        with self.assertRaises(ProviderError) as ctx:
            self.provider.search("technology")
        self.assertIn("could not be reached", str(ctx.exception).lower())

    # Requirement 11 & 15: Provider API error (HTTP 500)
    @patch("app.providers.thenewsapi_provider.urlopen")
    def test_provider_http_500_error(self, mock_urlopen):
        mock_urlopen.side_effect = HTTPError(
            url="https://api.thenewsapi.com/v1/news/all",
            code=500,
            msg="Internal Server Error",
            hdrs=None,
            fp=None,
        )
        with self.assertRaises(ProviderError) as ctx:
            self.provider.search("technology")
        self.assertIn("http error", str(ctx.exception).lower())

    # Requirement 11 & 15: Malformed responses
    @patch("app.providers.thenewsapi_provider.urlopen")
    def test_malformed_json_response(self, mock_urlopen):
        mock_urlopen.return_value = MockHTTPResponse(b"<!DOCTYPE html><html>Bad Gateway</html>")
        with self.assertRaises(ProviderError) as ctx:
            self.provider.search("technology")
        self.assertIn("invalid response", str(ctx.exception).lower())

    def test_malformed_payload_missing_data(self):
        with self.assertRaises(ProviderError) as ctx:
            self.provider._parse_response({"meta": {"found": 1}})
        self.assertIn("unexpected response", str(ctx.exception).lower())

    def test_malformed_payload_non_dict(self):
        with self.assertRaises(ProviderError) as ctx:
            self.provider._parse_response(["not", "a", "dict"])
        self.assertIn("unexpected response", str(ctx.exception).lower())

    # Requirement 14: Never expose THENEWSAPI_API_KEY in errors, logs, responses
    def test_api_key_not_exposed_in_exception_messages(self):
        secret_token = "ultra_secret_key_9876543210"
        provider = TheNewsAPIProvider(api_key=secret_token)

        with patch("app.providers.thenewsapi_provider.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = HTTPError(
                url=f"https://api.thenewsapi.com/v1/news/all?api_token={secret_token}",
                code=401,
                msg="Unauthorized",
                hdrs=None,
                fp=None,
            )
            try:
                provider.search("query")
            except ProviderError as e:
                self.assertNotIn(secret_token, str(e))

    # Requirement 12 & 13: GDELT continues working when The News API fails
    def test_gdelt_continues_working_when_thenewsapi_fails(self):
        gdelt_mock = MagicMock(spec=GDELTProvider)
        gdelt_mock.search.return_value = [
            Article(
                title="GDELT Reported Event",
                url="https://gdelt.org/event1",
                publisher="gdelt.org",
                publication_date="2026-09-30T10:00:00Z",
                description="Reported via GDELT.",
                source_provider="gdelt",
            )
        ]

        thenewsapi_mock = MagicMock(spec=TheNewsAPIProvider)
        thenewsapi_mock.search.side_effect = ProviderError("The News API authentication failed.")

        multi = MultiProvider([gdelt_mock, thenewsapi_mock])
        articles = multi.search("quantum")

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].title, "GDELT Reported Event")
        self.assertEqual(articles[0].source_provider, "gdelt")

    def test_gdelt_continues_working_when_thenewsapi_rate_limited(self):
        gdelt_mock = MagicMock(spec=GDELTProvider)
        gdelt_mock.search.return_value = [
            Article(
                title="GDELT Story",
                url="https://gdelt.org/story2",
                publisher="gdelt.org",
                publication_date="2026-09-30T11:00:00Z",
                description="GDELT coverage.",
                source_provider="gdelt",
            )
        ]

        thenewsapi_mock = MagicMock(spec=TheNewsAPIProvider)
        thenewsapi_mock.search.side_effect = RateLimitError("Rate limited.")

        multi = MultiProvider([gdelt_mock, thenewsapi_mock])
        articles = multi.search("climate")

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].title, "GDELT Story")

    # Cross-provider deduplication between GDELT and TheNewsAPI
    def test_deduplication_and_provider_merging_between_gdelt_and_thenewsapi(self):
        shared_url = "https://reuters.com/world/treaty-signed?utm_source=gdelt"
        gdelt_art = Article(
            title="Treaty Signed by Leaders",
            url=shared_url,
            publisher=None,
            publication_date="20260930120000",
            description=None,
            source_provider="gdelt",
        )
        thenewsapi_art = Article(
            title="Treaty Signed by Leaders",
            url="https://reuters.com/world/treaty-signed",
            publisher="Reuters",
            publication_date="2026-09-30T12:00:00Z",
            description="Leaders gather to ratify historic treaty.",
            source_provider="thenewsapi",
        )

        multi = MultiProvider([MagicMock(search=MagicMock(return_value=[gdelt_art])),
                                MagicMock(search=MagicMock(return_value=[thenewsapi_art]))])
        articles = multi.search("treaty")

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].publisher, "Reuters")
        self.assertEqual(articles[0].description, "Leaders gather to ratify historic treaty.")
        self.assertIn("gdelt", articles[0].source_provider)
        self.assertIn("thenewsapi", articles[0].source_provider)

    # Integration test with Flask application and configuration
    def test_app_configuration_enables_thenewsapi(self):
        with TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "test.db")
            app = create_app(
                {
                    "DATABASE_PATH": db_path,
                    "NEWS_PROVIDERS": "gdelt,thenewsapi",
                    "THENEWSAPI_API_KEY": "backend_only_token_xyz",
                    "THENEWSAPI_ENABLED": True,
                    "THENEWSAPI_BASE_URL": "https://api.thenewsapi.com/v1",
                    "THENEWSAPI_TIMEOUT": 10.0,
                }
            )

            orchestrator = app.extensions["search_orchestrator"]
            multi_provider = orchestrator.retrieval_service.news_provider
            self.assertIsInstance(multi_provider, MultiProvider)

            provider_types = [type(p) for p in multi_provider.providers]
            self.assertIn(GDELTProvider, provider_types)
            self.assertIn(TheNewsAPIProvider, provider_types)

            # Requirement 14: Ensure the secret token is not leaked to API response
            with patch("app.providers.thenewsapi_provider.urlopen") as mock_thenews, \
                 patch("app.providers.gdelt_provider.urlopen") as mock_gdelt:
                mock_thenews.return_value = MockHTTPResponse(self.sample_payload)
                mock_gdelt.return_value = MockHTTPResponse({"articles": []})

                client = app.test_client()
                response = client.post("/api/search", json={"query": "fusion"})
                self.assertEqual(response.status_code, 200)

                response_text = response.get_data(as_text=True)
                self.assertNotIn("backend_only_token_xyz", response_text)
                self.assertIn("thenewsapi", response_text)

    def test_app_configuration_disables_thenewsapi(self):
        with TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "test.db")
            app = create_app(
                {
                    "DATABASE_PATH": db_path,
                    "NEWS_PROVIDERS": "gdelt,thenewsapi",
                    "THENEWSAPI_ENABLED": False,
                }
            )

            orchestrator = app.extensions["search_orchestrator"]
            multi_provider = orchestrator.retrieval_service.news_provider
            provider_types = [type(p) for p in multi_provider.providers]
            self.assertIn(GDELTProvider, provider_types)
            self.assertNotIn(TheNewsAPIProvider, provider_types)


if __name__ == "__main__":
    unittest.main()
