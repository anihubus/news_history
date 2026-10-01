from datetime import date
import json
import os
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from app import create_app
from app.database import initialize_database
from app.models.article import Article
from app.providers.base_provider import NewsProvider, ProviderError, RateLimitError
from app.providers.multi_provider import MultiProvider
from app.providers.thenewsapi_provider import TheNewsAPIProvider
from app.repositories.article_repository import ArticleRepository
from app.services.article_retrieval_service import ArticleRetrievalService
from app.services.timeline_service import TimelineService


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


class HistoricalRetrievalTestCase(unittest.TestCase):
    def setUp(self):
        self.provider = TheNewsAPIProvider(
            api_key="test_historical_token",
            base_url="https://api.thenewsapi.com/v1",
            timeout=5,
            max_results=5,
        )

    # 1. Historical URL Parameters
    def test_build_request_url_with_historical_date_parameters(self):
        url = self.provider._build_request_url(
            query="artificial intelligence",
            published_after="2026-06-01",
            published_before="2026-08-01",
            published_on=None,
            sort="published_on",
            limit=5,
        )
        self.assertIn("https://api.thenewsapi.com/v1/news/all", url)
        self.assertIn("api_token=test_historical_token", url)
        self.assertIn("search=artificial+intelligence", url)
        self.assertIn("published_after=2026-06-01", url)
        self.assertIn("published_before=2026-08-01", url)
        self.assertIn("sort=published_on", url)
        self.assertIn("limit=5", url)

    def test_build_request_url_without_dates_remains_standard(self):
        url = self.provider._build_request_url("robotics")
        self.assertNotIn("published_after", url)
        self.assertNotIn("published_before", url)
        self.assertNotIn("published_on", url)
        self.assertNotIn("sort=", url)

    # 2. Date-Range Generation
    def test_default_historical_ranges_generation(self):
        ref_date = date(2026, 10, 1)
        ranges = TheNewsAPIProvider.get_default_historical_ranges(reference_date=ref_date, max_ranges=3)
        self.assertEqual(len(ranges), 3)

        # Window 1: 30 days ago to 7 days ago (2026-09-01 to 2026-09-24)
        self.assertEqual(ranges[0], ("2026-09-01", "2026-09-24"))
        # Window 2: 90 days ago to 30 days ago (2026-07-03 to 2026-09-01)
        self.assertEqual(ranges[1], ("2026-07-03", "2026-09-01"))
        # Window 3: 180 days ago to 90 days ago (2026-04-04 to 2026-07-03)
        self.assertEqual(ranges[2], ("2026-04-04", "2026-07-03"))

    def test_default_historical_ranges_respects_max_ranges(self):
        ref_date = "2026-10-01"
        ranges_2 = TheNewsAPIProvider.get_default_historical_ranges(reference_date=ref_date, max_ranges=2)
        self.assertEqual(len(ranges_2), 2)

        ranges_1 = TheNewsAPIProvider.get_default_historical_ranges(reference_date=ref_date, max_ranges=1)
        self.assertEqual(len(ranges_1), 1)

    def test_extract_date_bounds_tuple_and_dict(self):
        after, before = TheNewsAPIProvider._extract_date_bounds(("2026-01-01", "2026-02-01"))
        self.assertEqual(after, "2026-01-01")
        self.assertEqual(before, "2026-02-01")

        after_d, before_d = TheNewsAPIProvider._extract_date_bounds(
            {"published_after": "2026-03-01", "published_before": "2026-04-01"}
        )
        self.assertEqual(after_d, "2026-03-01")
        self.assertEqual(before_d, "2026-04-01")

    # 3. search_historical() and Bounded Request Count
    @patch("app.providers.thenewsapi_provider.urlopen")
    def test_search_historical_strictly_bounds_requests_to_max_ranges(self, mock_urlopen):
        mock_urlopen.return_value = MockHTTPResponse({"data": []})

        # Request 3 ranges
        custom_ranges = [
            ("2026-01-01", "2026-02-01"),
            ("2026-02-01", "2026-03-01"),
            ("2026-03-01", "2026-04-01"),
            ("2026-04-01", "2026-05-01"),  # 4th range should be ignored
        ]
        articles = self.provider.search_historical("fusion", date_ranges=custom_ranges, max_ranges=3)
        self.assertEqual(mock_urlopen.call_count, 3)
        self.assertEqual(articles, [])

    @patch("app.providers.thenewsapi_provider.urlopen")
    def test_search_historical_collects_articles_across_windows(self, mock_urlopen):
        def side_effect(request, *args, **kwargs):
            req_url = request.full_url
            if "2026-01-01" in req_url:
                payload = {
                    "data": [
                        {
                            "title": "Early Milestone",
                            "url": "https://example.com/early",
                            "published_at": "2026-01-15T10:00:00Z",
                            "source": "Tech Journal",
                        }
                    ]
                }
            elif "2026-02-01" in req_url:
                payload = {
                    "data": [
                        {
                            "title": "Middle Milestone",
                            "url": "https://example.com/middle",
                            "published_at": "2026-02-20T10:00:00Z",
                            "source": "Science Daily",
                        }
                    ]
                }
            else:
                payload = {"data": []}
            return MockHTTPResponse(payload)

        mock_urlopen.side_effect = side_effect

        ranges = [("2026-01-01", "2026-01-31"), ("2026-02-01", "2026-02-28")]
        articles = self.provider.search_historical("quantum", date_ranges=ranges, max_ranges=2)

        self.assertEqual(len(articles), 2)
        titles = {a.title for a in articles}
        self.assertIn("Early Milestone", titles)
        self.assertIn("Middle Milestone", titles)

    # 4. Canonical Deduplication Across Windows
    @patch("app.providers.thenewsapi_provider.urlopen")
    def test_search_historical_deduplicates_by_canonical_url(self, mock_urlopen):
        # Both windows return the same underlying article with different query parameters
        mock_urlopen.side_effect = [
            MockHTTPResponse({
                "data": [
                    {
                        "title": "Historic Discovery",
                        "url": "https://example.com/article?utm_source=twitter",
                        "published_at": "2026-05-10T12:00:00Z",
                    }
                ]
            }),
            MockHTTPResponse({
                "data": [
                    {
                        "title": "Historic Discovery",
                        "url": "https://EXAMPLE.com/article#section",
                        "published_at": "2026-05-10T12:00:00Z",
                    }
                ]
            }),
        ]

        ranges = [("2026-04-01", "2026-05-01"), ("2026-05-01", "2026-06-01")]
        articles = self.provider.search_historical("discovery", date_ranges=ranges, max_ranges=2)

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].title, "Historic Discovery")

    # 5. Graceful Partial Failures
    @patch("app.providers.thenewsapi_provider.urlopen")
    def test_search_historical_partial_failures_keep_successful_articles(self, mock_urlopen):
        # Window 1 succeeds, Window 2 hits HTTP 429, Window 3 succeeds
        mock_urlopen.side_effect = [
            MockHTTPResponse({
                "data": [
                    {
                        "title": "Window 1 Story",
                        "url": "https://example.com/w1",
                        "published_at": "2026-07-01T08:00:00Z",
                    }
                ]
            }),
            HTTPError(
                url="https://api.thenewsapi.com/v1/news/all",
                code=429,
                msg="Too Many Requests",
                hdrs=None,
                fp=None,
            ),
            MockHTTPResponse({
                "data": [
                    {
                        "title": "Window 3 Story",
                        "url": "https://example.com/w3",
                        "published_at": "2026-09-01T08:00:00Z",
                    }
                ]
            }),
        ]

        ranges = [("2026-06-01", "2026-07-01"), ("2026-07-01", "2026-08-01"), ("2026-08-01", "2026-09-01")]
        articles = self.provider.search_historical("topic", date_ranges=ranges, max_ranges=3)

        self.assertEqual(len(articles), 2)
        self.assertEqual({a.title for a in articles}, {"Window 1 Story", "Window 3 Story"})

    @patch("app.providers.thenewsapi_provider.urlopen")
    def test_search_historical_all_ranges_failing_surfaces_error(self, mock_urlopen):
        mock_urlopen.side_effect = HTTPError(
            url="https://api.thenewsapi.com/v1/news/all",
            code=429,
            msg="Too Many Requests",
            hdrs=None,
            fp=None,
        )

        ranges = [("2026-06-01", "2026-07-01"), ("2026-07-01", "2026-08-01")]
        with self.assertRaises(RateLimitError):
            self.provider.search_historical("topic", date_ranges=ranges, max_ranges=2)

    # 6. Backward Compatibility for NewsProvider.search(query)
    @patch("app.providers.thenewsapi_provider.urlopen")
    def test_search_query_makes_single_request_without_date_parameters(self, mock_urlopen):
        mock_urlopen.return_value = MockHTTPResponse({"data": [{"title": "Current Story", "url": "https://example.com/c1"}]})

        articles = self.provider.search("ai ethics")
        self.assertEqual(mock_urlopen.call_count, 1)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].title, "Current Story")

    # 7. MultiProvider search_historical
    def test_multiprovider_search_historical_delegates_to_capable_provider(self):
        mock_newsdata = MagicMock(spec=NewsProvider)
        # NewsData has no search_historical method

        mock_thenewsapi = MagicMock(spec=TheNewsAPIProvider)
        mock_thenewsapi.name = "thenewsapi"
        mock_thenewsapi.search_historical.return_value = [
            Article(
                title="Historical Milestone",
                url="https://historical.org/news1",
                publisher="Historical Org",
                publication_date="2026-05-01T10:00:00Z",
                description="Past event",
                source_provider="thenewsapi",
            )
        ]

        multi = MultiProvider([mock_newsdata, mock_thenewsapi])
        results = multi.search_historical("milestone", max_ranges=2)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "Historical Milestone")
        self.assertEqual(results[0].source_provider, "thenewsapi")
        mock_thenewsapi.search_historical.assert_called_once()

    # 8. ArticleRetrievalService combining Current + Historical
    def test_article_retrieval_service_combines_current_and_historical(self):
        with TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "test.db")
            initialize_database(db_path)
            repo = ArticleRepository(db_path)

            provider = MagicMock()
            provider.search.return_value = [
                Article(
                    title="Today's Breaking Topic News",
                    url="https://newsdata.io/breaking",
                    publisher="NewsData",
                    publication_date="2026-10-01T12:00:00Z",
                    description="Happening right now.",
                    source_provider="newsdata",
                )
            ]
            provider.search_historical.return_value = [
                Article(
                    title="Three Months Ago Topic Event",
                    url="https://thenewsapi.com/3mo",
                    publisher="TheNewsAPI",
                    publication_date="2026-07-01T10:00:00Z",
                    description="Historic announcement.",
                    source_provider="thenewsapi",
                )
            ]

            service = ArticleRetrievalService(repo, provider, enable_historical=True)
            result = service.search("topic")

            self.assertEqual(result.provider_status, "ok")
            self.assertEqual(len(result.articles), 2)

            titles = [a.title for a in result.articles]
            # Verify sorting: newest first
            self.assertEqual(titles[0], "Today's Breaking Topic News")
            self.assertEqual(titles[1], "Three Months Ago Topic Event")

            # Verify saved into repository
            stored_rows = repo.search_articles("topic")
            self.assertEqual(len(stored_rows), 2)

    # 9. ArticleRetrievalService gracefully isolates historical failure
    def test_article_retrieval_service_historical_failure_does_not_break_current_results(self):
        with TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "test.db")
            initialize_database(db_path)
            repo = ArticleRepository(db_path)

            provider = MagicMock()
            provider.search.return_value = [
                Article(
                    title="Current News Active",
                    url="https://newsdata.io/active",
                    publisher="NewsData",
                    publication_date="2026-10-01T09:00:00Z",
                    description="Latest dispatch.",
                    source_provider="newsdata",
                )
            ]
            # Historical provider hits 429
            provider.search_historical.side_effect = RateLimitError("Rate limited")

            service = ArticleRetrievalService(repo, provider, enable_historical=True)
            result = service.search("active")

            self.assertEqual(result.provider_status, "ok")
            self.assertEqual(len(result.articles), 1)
            self.assertEqual(result.articles[0].title, "Current News Active")

    # 10. ArticleRetrievalService gracefully preserves historical when current fails
    def test_article_retrieval_service_current_failure_with_historical_success(self):
        with TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "test.db")
            initialize_database(db_path)
            repo = ArticleRepository(db_path)

            provider = MagicMock()
            provider.search.side_effect = RateLimitError("Current provider rate-limited")
            provider.search_historical.return_value = [
                Article(
                    title="Historical Event Preserved",
                    url="https://thenewsapi.com/preserved",
                    publisher="TheNewsAPI",
                    publication_date="2026-06-15T08:00:00Z",
                    description="Preserved historical record.",
                    source_provider="thenewsapi",
                )
            ]

            service = ArticleRetrievalService(repo, provider, enable_historical=True)
            result = service.search("preserved")

            self.assertEqual(result.provider_status, "ok")
            self.assertEqual(len(result.articles), 1)
            self.assertEqual(result.articles[0].title, "Historical Event Preserved")

    # 11. Timeline generation with historical and current articles
    def test_timeline_service_builds_chronological_timeline_across_historical_eras(self):
        articles = [
            Article(
                title="Current Release v2.0",
                url="https://example.com/v2",
                publisher="NewsData",
                publication_date="2026-10-01T12:00:00Z",
                description="v2.0 released today",
                source_provider="newsdata",
                article_id=1,
            ),
            Article(
                title="Beta Testing Phase",
                url="https://example.com/beta",
                publisher="TheNewsAPI",
                publication_date="2026-08-15T10:00:00Z",
                description="Beta testing opened",
                source_provider="thenewsapi",
                article_id=2,
            ),
            Article(
                title="Initial Prototype Unveiled",
                url="https://example.com/alpha",
                publisher="TheNewsAPI",
                publication_date="2026-05-01T09:00:00Z",
                description="Prototype shown to public",
                source_provider="thenewsapi",
                article_id=3,
            ),
        ]

        timeline_svc = TimelineService()
        entries = timeline_svc.generate(articles, groups=[])

        self.assertEqual(len(entries), 3)
        dates = [entry["date"] for entry in entries]
        # Should be ordered chronologically
        self.assertEqual(dates, ["2026-05-01", "2026-08-15", "2026-10-01"])

    # 12. App configuration toggles
    def test_app_configuration_historical_settings(self):
        with TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "test.db")
            app = create_app(
                {
                    "DATABASE_PATH": db_path,
                    "NEWS_PROVIDERS": "newsdata,thenewsapi",
                    "THENEWSAPI_ENABLED": True,
                    "THENEWSAPI_HISTORICAL_ENABLED": False,
                }
            )

            orchestrator = app.extensions["search_orchestrator"]
            self.assertFalse(orchestrator.retrieval_service.enable_historical)

            app_enabled = create_app(
                {
                    "DATABASE_PATH": db_path,
                    "NEWS_PROVIDERS": "newsdata,thenewsapi",
                    "THENEWSAPI_ENABLED": True,
                    "THENEWSAPI_HISTORICAL_ENABLED": True,
                    "MAX_HISTORICAL_RANGES": 2,
                }
            )
            orch_enabled = app_enabled.extensions["search_orchestrator"]
            self.assertTrue(orch_enabled.retrieval_service.enable_historical)
            self.assertEqual(orch_enabled.retrieval_service.max_historical_ranges, 2)


if __name__ == "__main__":
    unittest.main()
