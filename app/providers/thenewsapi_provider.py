from datetime import date, datetime, timedelta, timezone
import json
import os
import socket
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import certifi

from app.models.article import Article
from app.providers.base_provider import NewsProvider, ProviderError, RateLimitError
from app.repositories.article_repository import canonicalize_url


class TheNewsAPIProvider(NewsProvider):
    name = "thenewsapi"

    def __init__(
        self,
        api_key=None,
        base_url="https://api.thenewsapi.com/v1",
        timeout=10,
        max_results=10,
        language="en",
        historical_date_ranges=None,
    ):
        self.api_key = api_key if api_key is not None else os.getenv("THENEWSAPI_API_KEY")
        self.base_url = base_url or "https://api.thenewsapi.com/v1"
        self.timeout = float(timeout) if timeout is not None else 10.0
        self.max_results = int(max_results) if max_results is not None else 10
        self.language = language
        self.historical_date_ranges = historical_date_ranges

    def search(self, query):
        if not self.api_key or not str(self.api_key).strip():
            raise ProviderError("The News API key is missing.")

        request_url = self._build_request_url(query)
        return self._execute_request(request_url)

    def _execute_request(self, request_url):
        request = Request(
            request_url,
            headers={
                "Accept": "application/json",
                "User-Agent": "NewsHistory/1.0",
            },
        )

        try:
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            with urlopen(request, timeout=self.timeout, context=ssl_context) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            if error.code == 429:
                raise RateLimitError("The news provider is temporarily rate-limited.") from None
            if error.code in (401, 403):
                raise ProviderError("The News API authentication failed.") from None
            raise ProviderError("The news provider returned an HTTP error.") from None
        except (TimeoutError, socket.timeout):
            raise ProviderError("The news provider timed out.") from None
        except URLError as error:
            if isinstance(error.reason, (TimeoutError, socket.timeout)) or "timed out" in str(error.reason).lower():
                raise ProviderError("The news provider timed out.") from None
            raise ProviderError("The news provider could not be reached.") from None
        except OSError:
            raise ProviderError("The news provider could not be reached.") from None
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ProviderError("The news provider returned an invalid response.") from None

        return self._parse_response(payload)

    def _build_request_url(
        self,
        query,
        published_after=None,
        published_before=None,
        published_on=None,
        sort=None,
        limit=None,
    ):
        endpoint = self.base_url.rstrip("/")
        if not endpoint.endswith("/news/all"):
            endpoint = f"{endpoint}/news/all"

        parameters = {
            "api_token": self.api_key,
            "search": query,
            "limit": limit if limit is not None else self.max_results,
        }
        if self.language:
            parameters["language"] = self.language
        if published_after:
            parameters["published_after"] = published_after
        if published_before:
            parameters["published_before"] = published_before
        if published_on:
            parameters["published_on"] = published_on
        if sort:
            parameters["sort"] = sort

        encoded_params = urlencode(parameters)
        separator = "&" if "?" in endpoint else "?"
        return f"{endpoint}{separator}{encoded_params}"

    @staticmethod
    def get_default_historical_ranges(reference_date=None, max_ranges=3):
        if reference_date is None:
            ref = datetime.now(timezone.utc).date()
        elif isinstance(reference_date, datetime):
            ref = reference_date.date()
        elif isinstance(reference_date, date):
            ref = reference_date
        elif isinstance(reference_date, str):
            ref = date.fromisoformat(reference_date)
        else:
            ref = datetime.now(timezone.utc).date()

        windows = [
            (
                (ref - timedelta(days=30)).isoformat(),
                (ref - timedelta(days=7)).isoformat(),
            ),
            (
                (ref - timedelta(days=90)).isoformat(),
                (ref - timedelta(days=30)).isoformat(),
            ),
            (
                (ref - timedelta(days=180)).isoformat(),
                (ref - timedelta(days=90)).isoformat(),
            ),
        ]
        return windows[:max(1, int(max_ranges))]

    @staticmethod
    def _extract_date_bounds(range_spec):
        if isinstance(range_spec, (list, tuple)):
            after = range_spec[0] if len(range_spec) > 0 else None
            before = range_spec[1] if len(range_spec) > 1 else None
            return after, before
        if isinstance(range_spec, dict):
            after = range_spec.get("published_after") or range_spec.get("after")
            before = range_spec.get("published_before") or range_spec.get("before")
            return after, before
        return None, None

    def search_historical(self, query, date_ranges=None, max_ranges=3):
        if not self.api_key or not str(self.api_key).strip():
            raise ProviderError("The News API key is missing.")

        if not isinstance(query, str) or not query.strip():
            return []

        normalized_query = query.strip()
        max_r = max(1, int(max_ranges)) if max_ranges is not None else 3

        if date_ranges is None:
            if self.historical_date_ranges is not None:
                ranges = list(self.historical_date_ranges)[:max_r]
            else:
                ranges = self.get_default_historical_ranges(max_ranges=max_r)
        else:
            ranges = list(date_ranges)[:max_r]

        articles = []
        errors = []

        for range_spec in ranges:
            after, before = self._extract_date_bounds(range_spec)
            try:
                request_url = self._build_request_url(
                    normalized_query,
                    published_after=after,
                    published_before=before,
                    sort="published_on",
                )
                range_articles = self._execute_request(request_url)
                articles.extend(range_articles)
            except (RateLimitError, ProviderError) as error:
                errors.append(error)
            except Exception as error:
                errors.append(ProviderError(f"Historical request failed: {error}"))

        # Deduplicate articles across windows by canonical URL
        unique_articles = {}
        for article in articles:
            canon = canonicalize_url(article.url)
            if canon not in unique_articles:
                unique_articles[canon] = article

        # If all requested ranges failed and produced no articles, surface the error
        if not unique_articles and ranges and len(errors) == len(ranges):
            for err in errors:
                if isinstance(err, RateLimitError):
                    raise err
            raise errors[0]

        return list(unique_articles.values())

    def _parse_response(self, payload):
        if not isinstance(payload, dict):
            raise ProviderError("The news provider returned an unexpected response.")

        if isinstance(payload.get("error"), dict):
            error_info = payload["error"]
            error_code = str(error_info.get("code", "")).lower()
            if error_code in ("rate_limit_reached", "429"):
                raise RateLimitError("The news provider is temporarily rate-limited.")
            if error_code in ("invalid_api_token", "unauthorized", "401", "403"):
                raise ProviderError("The News API authentication failed.")
            raise ProviderError("The news provider returned an error.")

        data = payload.get("data")
        if not isinstance(data, list):
            raise ProviderError("The news provider returned an unexpected response.")

        articles = []
        for item in data:
            if not isinstance(item, dict):
                continue

            url = item.get("url")
            title = item.get("title")
            if not isinstance(url, str) or not isinstance(title, str) or not url.strip() or not title.strip():
                continue

            publisher = None
            source = item.get("source")
            if isinstance(source, str):
                publisher = source.strip()
            elif isinstance(source, dict):
                publisher = source.get("name") or source.get("domain")

            description = item.get("description")
            if not description and item.get("snippet"):
                description = item.get("snippet")

            articles.append(
                Article(
                    title=title.strip(),
                    url=url.strip(),
                    publisher=self._optional_string(publisher),
                    publication_date=self._optional_string(item.get("published_at")),
                    description=self._optional_string(description),
                    source_provider="thenewsapi",
                    retrieved_at=None,
                )
            )

        return articles

    @staticmethod
    def _optional_string(value):
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None
