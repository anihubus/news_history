import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from app.providers.newsapi_provider import NewsAPIProvider
from app.providers.base_provider import ProviderError, RateLimitError


class NewsAPIProviderTestCase(unittest.TestCase):
    def setUp(self):
        self.provider = NewsAPIProvider(
            api_key="test_key",
            base_url="https://newsapi.org/v2/everything",
            max_results=10,
            timeout=5,
        )

    def test_missing_api_key_raises_error(self):
        provider = NewsAPIProvider(api_key=None)
        with self.assertRaises(ProviderError):
            provider.search("technology")

    def test_parse_response_returns_normalized_articles(self):
        payload = {
            "status": "ok",
            "totalResults": 1,
            "articles": [
                {
                    "source": {"id": "wired", "name": "Wired"},
                    "author": "Author Name",
                    "title": "A new tech breakthrough",
                    "description": "Tech is advancing rapidly.",
                    "url": "https://wired.com/article",
                    "urlToImage": "https://wired.com/image.jpg",
                    "publishedAt": "2026-09-18T10:00:00Z",
                    "content": "Full article content..."
                }
            ]
        }

        articles = self.provider._parse_response(payload)

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].title, "A new tech breakthrough")
        self.assertEqual(articles[0].publisher, "Wired")
        self.assertEqual(articles[0].publication_date, "2026-09-18T10:00:00Z")
        self.assertEqual(articles[0].description, "Tech is advancing rapidly.")
        self.assertEqual(articles[0].source_provider, "newsapi")

    def test_parse_response_rejects_error_status(self):
        with self.assertRaises(ProviderError):
            self.provider._parse_response({"status": "error", "message": "Invalid API key"})

    def test_parse_response_rejects_unexpected_payload(self):
        with self.assertRaises(ProviderError):
            self.provider._parse_response({"data": []})

    def test_request_url_contains_basic_newsapi_parameters(self):
        request_url = self.provider._build_request_url("climate change")

        self.assertIn("q=climate+change", request_url)
        self.assertIn("pageSize=10", request_url)
        self.assertIn("language=en", request_url)

    @patch("app.providers.newsapi_provider.urlopen")
    def test_http_429_raises_rate_limit_error(self, mocked_urlopen):
        mocked_urlopen.side_effect = HTTPError(
            url="https://newsapi.org/v2/everything",
            code=429,
            msg="Too Many Requests",
            hdrs=None,
            fp=None,
        )

        with self.assertRaises(RateLimitError):
            self.provider.search("climate change")

    @patch("app.providers.newsapi_provider.urlopen")
    def test_http_401_raises_authentication_error(self, mocked_urlopen):
        mocked_urlopen.side_effect = HTTPError(
            url="https://newsapi.org/v2/everything",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=None,
        )

        with self.assertRaises(ProviderError) as context:
            self.provider.search("climate change")
        
        self.assertIn("authentication failed", str(context.exception))


if __name__ == "__main__":
    unittest.main()
