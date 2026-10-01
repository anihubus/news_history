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
from app.providers.newsdata_provider import NewsDataProvider
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


class NewsDataProviderTestCase(unittest.TestCase):
    def setUp(self):
        self.provider = NewsDataProvider(
            api_key="test_newsdata_token",
            base_url="https://newsdata.io/api/1",
            timeout=5,
            max_results=10,
        )

        self.sample_payload = {
            "status": "success",
            "totalResults": 2,
            "results": [
                {
                    "article_id": "nd_001",
                    "title": "Quantum Advantage Demonstrated in Laboratory",
                    "link": "https://techchronicle.com/quantum-advantage",
                    "keywords": ["quantum", "computing"],
                    "creator": ["Jane Doe"],
                    "video_url": None,
                    "description": "Researchers confirm benchmark quantum speedup in production hardware.",
                    "content": "Full article text content...",
                    "pubDate": "2026-10-01 07:36:00",
                    "pubDateTZ": "UTC",
                    "image_url": "https://techchronicle.com/img.jpg",
                    "source_id": "techchronicle",
                    "source_priority": 1,
                    "source_name": "Tech Chronicle",
                    "source_url": "https://techchronicle.com",
                    "source_icon": "https://techchronicle.com/icon.png",
                    "language": "english",
                    "country": ["united states of america"],
                    "category": ["technology"],
                },
                {
                    "article_id": "nd_002",
                    "title": "Global Telecom Standard Finalized",
                    "link": "https://telecomwire.com/standard-finalized",
                    "keywords": ["telecom"],
                    "creator": None,
                    "description": "International committee ratifies next-generation network specs.",
                    "pubDate": "2026-10-01 08:15:00",
                    "source_id": "telecomwire",
                    "source_name": "Telecom Wire",
                    "language": "english",
                    "country": ["united kingdom"],
                    "category": ["business"],
                },
            ],
            "nextPage": "1727768160000",
        }

    # 1. Base NewsProvider interface & name
    def test_provider_implements_news_provider_interface(self):
        self.assertIsInstance(self.provider, NewsProvider)
        self.assertEqual(self.provider.name, "newsdata")

    # 2. Missing API key handling
    def test_missing_api_key_raises_provider_error(self):
        with patch.dict(os.environ, {}, clear=True):
            provider = NewsDataProvider(api_key=None)
            with self.assertRaises(ProviderError) as ctx:
                provider.search("fusion")
            self.assertIn("missing", str(ctx.exception).lower())

    def test_empty_string_api_key_raises_provider_error(self):
        provider = NewsDataProvider(api_key="   ")
        with self.assertRaises(ProviderError) as ctx:
            provider.search("fusion")
        self.assertIn("missing", str(ctx.exception).lower())

    # 3. Read API key from environment
    def test_api_key_read_from_environment(self):
        with patch.dict(os.environ, {"NEWSDATA_API_KEY": "env_newsdata_key_999"}):
            provider = NewsDataProvider()
            self.assertEqual(provider.api_key, "env_newsdata_key_999")

    # 4. Request URL building
    def test_build_request_url_default(self):
        url = self.provider._build_request_url("artificial intelligence")
        self.assertIn("https://newsdata.io/api/1/latest", url)
        self.assertIn("q=artificial+intelligence", url)
        self.assertIn("apikey=test_newsdata_token", url)
        self.assertIn("language=en", url)

    def test_build_request_url_with_full_endpoint(self):
        provider = NewsDataProvider(
            api_key="token123",
            base_url="https://newsdata.io/api/1/latest",
        )
        url = provider._build_request_url("robotics")
        self.assertEqual(url.count("/latest"), 1)
        self.assertIn("q=robotics", url)

    def test_build_request_url_with_news_endpoint(self):
        provider = NewsDataProvider(
            api_key="token123",
            base_url="https://newsdata.io/api/1/news",
        )
        url = provider._build_request_url("space")
        self.assertTrue(url.startswith("https://newsdata.io/api/1/news?"))
        self.assertNotIn("/news/latest", url)
        self.assertIn("q=space", url)

    # 5. Successful response and article normalization
    @patch("app.providers.newsdata_provider.urlopen")
    def test_successful_response_and_normalization(self, mock_urlopen):
        mock_urlopen.return_value = MockHTTPResponse(self.sample_payload)

        articles = self.provider.search("quantum")

        self.assertEqual(len(articles), 2)
        art1 = articles[0]
        self.assertIsInstance(art1, Article)
        self.assertEqual(art1.title, "Quantum Advantage Demonstrated in Laboratory")
        self.assertEqual(art1.url, "https://techchronicle.com/quantum-advantage")
        self.assertEqual(art1.publisher, "Tech Chronicle")
        self.assertEqual(art1.publication_date, "2026-10-01 07:36:00")
        self.assertEqual(art1.description, "Researchers confirm benchmark quantum speedup in production hardware.")
        self.assertEqual(art1.source_provider, "newsdata")
        self.assertIsNone(art1.retrieved_at)

        art2 = articles[1]
        self.assertEqual(art2.title, "Global Telecom Standard Finalized")
        self.assertEqual(art2.url, "https://telecomwire.com/standard-finalized")
        self.assertEqual(art2.publisher, "Telecom Wire")
        self.assertEqual(art2.source_provider, "newsdata")

    # 6. Fallback fields in article normalization
    @patch("app.providers.newsdata_provider.urlopen")
    def test_normalization_with_fallback_fields(self, mock_urlopen):
        payload = {
            "status": "success",
            "totalResults": 1,
            "results": [
                {
                    "title": "Renewable Breakthrough",
                    "url": "https://fallback.example.com/item",  # 'url' instead of 'link'
                    "source_id": "fallback_source",             # source_id fallback when source_name missing
                    "snippet": "Fallback snippet text",          # snippet fallback when description missing
                    "published_at": "2026-10-01T12:00:00Z",
                }
            ],
        }
        mock_urlopen.return_value = MockHTTPResponse(payload)

        articles = self.provider.search("renewable")
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].url, "https://fallback.example.com/item")
        self.assertEqual(articles[0].publisher, "fallback_source")
        self.assertEqual(articles[0].description, "Fallback snippet text")
        self.assertEqual(articles[0].publication_date, "2026-10-01T12:00:00Z")

    @patch("app.providers.newsdata_provider.urlopen")
    def test_missing_optional_fields_normalized_to_none(self, mock_urlopen):
        payload = {
            "status": "success",
            "results": [
                {
                    "title": "Minimal Article",
                    "link": "https://minimal.example.com/1",
                    "source_name": "",
                    "description": "",
                    "pubDate": None,
                }
            ],
        }
        mock_urlopen.return_value = MockHTTPResponse(payload)

        articles = self.provider.search("minimal")
        self.assertEqual(len(articles), 1)
        self.assertIsNone(articles[0].publisher)
        self.assertIsNone(articles[0].description)
        self.assertIsNone(articles[0].publication_date)

    @patch("app.providers.newsdata_provider.urlopen")
    def test_invalid_items_skipped(self, mock_urlopen):
        payload = {
            "status": "success",
            "results": [
                "not a dict",
                {"title": "", "link": "https://example.com/empty-title"},
                {"title": "Missing link"},
                {"title": "Valid Article", "link": "https://example.com/valid"},
            ],
        }
        mock_urlopen.return_value = MockHTTPResponse(payload)

        articles = self.provider.search("test")
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].title, "Valid Article")

    @patch("app.providers.newsdata_provider.urlopen")
    def test_empty_results_returns_empty_list(self, mock_urlopen):
        payload = {
            "status": "success",
            "totalResults": 0,
            "results": [],
        }
        mock_urlopen.return_value = MockHTTPResponse(payload)

        articles = self.provider.search("nonexistent query")
        self.assertEqual(articles, [])

    # 7. Authentication failure handling
    @patch("app.providers.newsdata_provider.urlopen")
    def test_authentication_failure_http_401(self, mock_urlopen):
        mock_urlopen.side_effect = HTTPError(
            "https://newsdata.io/api/1/latest", 401, "Unauthorized", {}, io.BytesIO(b'{"status":"error"}')
        )
        with self.assertRaises(ProviderError) as ctx:
            self.provider.search("auth")
        self.assertIn("authentication failed", str(ctx.exception).lower())

    @patch("app.providers.newsdata_provider.urlopen")
    def test_authentication_failure_http_403(self, mock_urlopen):
        mock_urlopen.side_effect = HTTPError(
            "https://newsdata.io/api/1/latest", 403, "Forbidden", {}, io.BytesIO(b'{"status":"error"}')
        )
        with self.assertRaises(ProviderError) as ctx:
            self.provider.search("auth")
        self.assertIn("authentication failed", str(ctx.exception).lower())

    @patch("app.providers.newsdata_provider.urlopen")
    def test_in_payload_authentication_error(self, mock_urlopen):
        payload = {
            "status": "error",
            "results": {
                "message": "Invalid API key provided",
                "code": "unauthorized",
            },
        }
        mock_urlopen.return_value = MockHTTPResponse(payload)
        with self.assertRaises(ProviderError) as ctx:
            self.provider.search("query")
        self.assertIn("authentication failed", str(ctx.exception).lower())

    # 8. Rate limit error handling
    @patch("app.providers.newsdata_provider.urlopen")
    def test_rate_limit_http_429(self, mock_urlopen):
        mock_urlopen.side_effect = HTTPError(
            "https://newsdata.io/api/1/latest", 429, "Too Many Requests", {}, io.BytesIO(b'{"status":"error"}')
        )
        with self.assertRaises(RateLimitError) as ctx:
            self.provider.search("ratelimit")
        self.assertIn("rate-limited", str(ctx.exception).lower())

    @patch("app.providers.newsdata_provider.urlopen")
    def test_in_payload_rate_limit_error(self, mock_urlopen):
        payload = {
            "status": "error",
            "results": {
                "message": "You have exceeded your rate limit",
                "code": "rateLimitExceeded",
            },
        }
        mock_urlopen.return_value = MockHTTPResponse(payload)
        with self.assertRaises(RateLimitError) as ctx:
            self.provider.search("query")
        self.assertIn("rate-limited", str(ctx.exception).lower())

    # 9. Provider failure isolation (HTTP 500, timeout, connection errors)
    @patch("app.providers.newsdata_provider.urlopen")
    def test_provider_http_500_error(self, mock_urlopen):
        mock_urlopen.side_effect = HTTPError(
            "https://newsdata.io/api/1/latest", 500, "Internal Server Error", {}, io.BytesIO(b'{"status":"error"}')
        )
        with self.assertRaises(ProviderError) as ctx:
            self.provider.search("server_error")
        self.assertIn("http error", str(ctx.exception).lower())

    @patch("app.providers.newsdata_provider.urlopen")
    def test_timeout_error_handling(self, mock_urlopen):
        mock_urlopen.side_effect = TimeoutError("Request timed out")
        with self.assertRaises(ProviderError) as ctx:
            self.provider.search("timeout")
        self.assertIn("timed out", str(ctx.exception).lower())

    @patch("app.providers.newsdata_provider.urlopen")
    def test_socket_timeout_handling(self, mock_urlopen):
        mock_urlopen.side_effect = socket.timeout("timed out")
        with self.assertRaises(ProviderError) as ctx:
            self.provider.search("socket_timeout")
        self.assertIn("timed out", str(ctx.exception).lower())

    @patch("app.providers.newsdata_provider.urlopen")
    def test_connection_error_handling(self, mock_urlopen):
        mock_urlopen.side_effect = URLError("Network unreachable")
        with self.assertRaises(ProviderError) as ctx:
            self.provider.search("network_error")
        self.assertIn("could not be reached", str(ctx.exception).lower())

    # 10. Malformed response handling
    @patch("app.providers.newsdata_provider.urlopen")
    def test_malformed_json_response(self, mock_urlopen):
        mock_urlopen.return_value = MockHTTPResponse(b"invalid json {<", status=200)
        with self.assertRaises(ProviderError) as ctx:
            self.provider.search("bad_json")
        self.assertIn("invalid response", str(ctx.exception).lower())

    @patch("app.providers.newsdata_provider.urlopen")
    def test_malformed_payload_non_dict(self, mock_urlopen):
        mock_urlopen.return_value = MockHTTPResponse(["not", "a", "dict"])
        with self.assertRaises(ProviderError) as ctx:
            self.provider.search("bad_payload")
        self.assertIn("unexpected response", str(ctx.exception).lower())

    @patch("app.providers.newsdata_provider.urlopen")
    def test_malformed_payload_missing_results(self, mock_urlopen):
        mock_urlopen.return_value = MockHTTPResponse({"status": "success", "results": "not_a_list"})
        with self.assertRaises(ProviderError) as ctx:
            self.provider.search("missing_results")
        self.assertIn("unexpected response", str(ctx.exception).lower())

    # 11. Security requirement: Never expose API key in exceptions
    def test_api_key_not_exposed_in_exception_messages(self):
        secret_token = "super_secret_newsdata_token_12345"
        provider = NewsDataProvider(api_key=secret_token)

        with patch("app.providers.newsdata_provider.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = HTTPError(
                f"https://newsdata.io/api/1/latest?apikey={secret_token}",
                401,
                "Unauthorized",
                {},
                io.BytesIO(b'{"status":"error"}'),
            )
            with self.assertRaises(ProviderError) as ctx:
                provider.search("secret test")
            self.assertNotIn(secret_token, str(ctx.exception))

    # 12. Flask configuration: enable / disable NewsData.io
    def test_app_configuration_enables_newsdata(self):
        temp_dir = TemporaryDirectory()
        db_path = os.path.join(temp_dir.name, "test_newsdata_cfg.db")
        try:
            with patch.dict(
                os.environ,
                {
                    "NEWS_PROVIDERS": "gdelt",
                    "NEWSDATA_ENABLED": "true",
                    "NEWSDATA_API_KEY": "test_cfg_key",
                },
            ):
                app = create_app({"DATABASE_PATH": db_path})
                orchestrator = app.extensions["search_orchestrator"]
                provider = orchestrator.retrieval_service.news_provider

                self.assertIsInstance(provider, MultiProvider)
                provider_names = [p.name for p in provider.providers]
                self.assertIn("gdelt", provider_names)
                self.assertIn("newsdata", provider_names)
        finally:
            temp_dir.cleanup()

    def test_app_configuration_disables_newsdata_by_default(self):
        temp_dir = TemporaryDirectory()
        db_path = os.path.join(temp_dir.name, "test_newsdata_cfg_disabled.db")
        try:
            with patch.dict(
                os.environ,
                {
                    "NEWS_PROVIDERS": "gdelt",
                    "NEWSDATA_ENABLED": "false",
                },
            ):
                app = create_app({"DATABASE_PATH": db_path})
                orchestrator = app.extensions["search_orchestrator"]
                provider = orchestrator.retrieval_service.news_provider

                self.assertIsInstance(provider, MultiProvider)
                provider_names = [p.name for p in provider.providers]
                self.assertIn("gdelt", provider_names)
                self.assertNotIn("newsdata", provider_names)
        finally:
            temp_dir.cleanup()

    # 13. Multi-provider search with GDELT + NewsData.io
    def test_multi_provider_search_gdelt_and_newsdata(self):
        art_gdelt = Article(
            title="Satellite Constellation Launched",
            url="https://gdelt.example.com/satellite-launch",
            publisher="Aero Science",
            publication_date="2026-10-01T06:00:00Z",
            description="60 next-gen broadband satellites deploy into orbit.",
            source_provider="gdelt",
        )
        art_newsdata = Article(
            title="Ground Stations Link to New Constellation",
            url="https://newsdata.example.com/ground-stations",
            publisher="Space Tech Review",
            publication_date="2026-10-01T07:00:00Z",
            description="Telemetry confirmed across equatorial ground stations.",
            source_provider="newsdata",
        )

        p_gdelt = MagicMock()
        p_gdelt.name = "gdelt"
        p_gdelt.search.return_value = [art_gdelt]

        p_newsdata = MagicMock()
        p_newsdata.name = "newsdata"
        p_newsdata.search.return_value = [art_newsdata]

        multi = MultiProvider([p_gdelt, p_newsdata])
        results = multi.search("satellite")

        self.assertEqual(len(results), 2)
        urls = {a.url for a in results}
        self.assertIn("https://gdelt.example.com/satellite-launch", urls)
        self.assertIn("https://newsdata.example.com/ground-stations", urls)

        statuses = multi.get_provider_statuses()
        self.assertTrue(statuses["gdelt"]["success"])
        self.assertTrue(statuses["newsdata"]["success"])

    # 14. Multi-provider failure isolation
    def test_multi_provider_gdelt_succeeds_newsdata_fails(self):
        art_gdelt = Article(
            title="Deep Submersible Explores Mariana Trench",
            url="https://gdelt.example.com/submersible",
            publisher="Ocean Research",
            publication_date="2026-10-01T05:00:00Z",
            description="Autonomous vehicle reaches 10,900 meters.",
            source_provider="gdelt",
        )

        p_gdelt = MagicMock()
        p_gdelt.name = "gdelt"
        p_gdelt.search.return_value = [art_gdelt]

        p_newsdata = MagicMock()
        p_newsdata.name = "newsdata"
        p_newsdata.search.side_effect = ProviderError("NewsData outage")

        multi = MultiProvider([p_gdelt, p_newsdata])
        results = multi.search("submersible")

        # Surviving GDELT results returned
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "Deep Submersible Explores Mariana Trench")

        statuses = multi.get_provider_statuses()
        self.assertTrue(statuses["gdelt"]["success"])
        self.assertFalse(statuses["newsdata"]["success"])

    def test_multi_provider_newsdata_succeeds_gdelt_fails(self):
        art_newsdata = Article(
            title="Solar Cell Efficiency Record",
            url="https://newsdata.example.com/solar-cell",
            publisher="Clean Energy Daily",
            publication_date="2026-10-01T09:00:00Z",
            description="Perovskite tandem cell surpasses 34% efficiency.",
            source_provider="newsdata",
        )

        p_gdelt = MagicMock()
        p_gdelt.name = "gdelt"
        p_gdelt.search.side_effect = ProviderError("GDELT connection timeout")

        p_newsdata = MagicMock()
        p_newsdata.name = "newsdata"
        p_newsdata.search.return_value = [art_newsdata]

        multi = MultiProvider([p_gdelt, p_newsdata])
        results = multi.search("solar cell")

        # Surviving NewsData results returned
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "Solar Cell Efficiency Record")

        statuses = multi.get_provider_statuses()
        self.assertFalse(statuses["gdelt"]["success"])
        self.assertTrue(statuses["newsdata"]["success"])

    # 15. Cross-provider deduplication between GDELT and NewsData.io
    def test_deduplication_between_gdelt_and_newsdata(self):
        art_gdelt = Article(
            title="Arctic Climate Station Data Released",
            url="https://example.com/arctic-data?utm_source=gdelt",
            publisher="Arctic Institute",
            publication_date="2026-10-01T04:00:00Z",
            description="Winter telemetry dataset published.",
            source_provider="gdelt",
        )
        art_newsdata = Article(
            title="Arctic Climate Station Data Released",
            url="https://example.com/arctic-data?utm_medium=newsdata",
            publisher="Arctic Institute",
            publication_date="2026-10-01T04:00:00Z",
            description="Winter telemetry dataset published.",
            source_provider="newsdata",
        )

        p_gdelt = MagicMock()
        p_gdelt.name = "gdelt"
        p_gdelt.search.return_value = [art_gdelt]

        p_newsdata = MagicMock()
        p_newsdata.name = "newsdata"
        p_newsdata.search.return_value = [art_newsdata]

        multi = MultiProvider([p_gdelt, p_newsdata])
        results = multi.search("arctic data")

        self.assertEqual(len(results), 1)
        self.assertIn("gdelt", results[0].source_provider)
        self.assertIn("newsdata", results[0].source_provider)


if __name__ == "__main__":
    unittest.main()
