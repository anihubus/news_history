import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from app.providers.gdelt_provider import GDELTProvider
from app.providers.base_provider import ProviderError, RateLimitError


class GDELTProviderTestCase(unittest.TestCase):
    def setUp(self):
        self.provider = GDELTProvider(
            base_url="https://api.gdeltproject.org/api/v2/doc/doc",
            max_results=10,
            timeout=5,
        )

    def test_parse_response_returns_normalized_articles(self):
        payload = {
            "articles": [
                {
                    "title": "Climate policy update",
                    "url": "https://example.com/article",
                    "domain": "example.com",
                    "seendate": "20260918000000",
                    "socialimage": "https://example.com/image.jpg",
                }
            ]
        }

        articles = self.provider._parse_response(payload)

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].title, "Climate policy update")
        self.assertEqual(articles[0].publisher, "example.com")
        self.assertIsNone(articles[0].description)
        self.assertEqual(articles[0].source_provider, "gdelt")

    def test_parse_response_rejects_unexpected_payload(self):
        with self.assertRaises(ProviderError):
            self.provider._parse_response({"data": []})

    def test_request_url_contains_basic_gdelt_parameters(self):
        request_url = self.provider._build_request_url("climate change")

        self.assertIn("query=climate+change", request_url)
        self.assertIn("mode=artlist", request_url)
        self.assertIn("format=json", request_url)
        self.assertIn("maxrecords=10", request_url)

    @patch("app.providers.gdelt_provider.urlopen")
    def test_http_429_raises_rate_limit_error(self, mocked_urlopen):
        mocked_urlopen.side_effect = HTTPError(
            url="https://api.gdeltproject.org/api/v2/doc/doc",
            code=429,
            msg="Too Many Requests",
            hdrs=None,
            fp=None,
        )

        with self.assertRaises(RateLimitError):
            self.provider.search("climate change")


if __name__ == "__main__":
    unittest.main()
