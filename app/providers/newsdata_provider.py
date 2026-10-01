import json
import os
import socket
import ssl

import certifi
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.models.article import Article
from app.providers.base_provider import NewsProvider, ProviderError, RateLimitError


class NewsDataProvider(NewsProvider):
    name = "newsdata"

    def __init__(
        self,
        api_key=None,
        base_url="https://newsdata.io/api/1",
        timeout=10,
        max_results=10,
        language="en",
    ):
        self.api_key = (
            api_key if api_key is not None else os.getenv("NEWSDATA_API_KEY")
        )
        self.base_url = base_url or "https://newsdata.io/api/1"
        self.timeout = float(timeout) if timeout is not None else 10.0
        self.max_results = int(max_results) if max_results is not None else 10
        self.language = language

    def search(self, query):
        if not self.api_key or not str(self.api_key).strip():
            raise ProviderError("NewsData.io API key is missing.")

        request_url = self._build_request_url(query)

        request = Request(
            request_url,
            headers={
                "Accept": "application/json",
                "User-Agent": "NewsHistory/1.0",
                "X-ACCESS-KEY": str(self.api_key),
            },
        )

        try:
            # Use certifi's trusted CA bundle.
            # This fixes certificate verification issues on some macOS/Python setups
            # without disabling SSL verification.
            ssl_context = ssl.create_default_context(
                cafile=certifi.where()
            )

            with urlopen(
                request,
                timeout=self.timeout,
                context=ssl_context,
            ) as response:
                payload = json.loads(
                    response.read().decode("utf-8")
                )

        except HTTPError as error:
            if error.code == 429:
                raise RateLimitError(
                    "The news provider is temporarily rate-limited."
                ) from None

            if error.code in (401, 403):
                raise ProviderError(
                    "NewsData.io authentication failed."
                ) from None

            raise ProviderError(
                "The news provider returned an HTTP error."
            ) from None

        except (TimeoutError, socket.timeout):
            raise ProviderError(
                "The news provider timed out."
            ) from None

        except URLError as error:
            if (
                isinstance(error.reason, (TimeoutError, socket.timeout))
                or "timed out" in str(error.reason).lower()
            ):
                raise ProviderError(
                    "The news provider timed out."
                ) from None

            raise ProviderError(
                "The news provider could not be reached."
            ) from None

        except OSError:
            raise ProviderError(
                "The news provider could not be reached."
            ) from None

        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ProviderError(
                "The news provider returned an invalid response."
            ) from None

        return self._parse_response(payload)

    def _build_request_url(self, query):
        endpoint = self.base_url.rstrip("/")

        if not endpoint.endswith("/latest") and not endpoint.endswith("/news"):
            endpoint = f"{endpoint}/latest"

        parameters = {
            "apikey": self.api_key,
            "q": query,
        }

        if self.language:
            parameters["language"] = self.language

        encoded_params = urlencode(parameters)

        separator = "&" if "?" in endpoint else "?"

        return f"{endpoint}{separator}{encoded_params}"

    def _parse_response(self, payload):
        if not isinstance(payload, dict):
            raise ProviderError(
                "The news provider returned an unexpected response."
            )

        # Handle NewsData API error responses.
        if payload.get("status") == "error":
            results_obj = payload.get("results")

            code = ""
            message = ""

            if isinstance(results_obj, dict):
                code = str(
                    results_obj.get("code") or ""
                ).lower()

                message = str(
                    results_obj.get("message") or ""
                ).lower()

            if not code and payload.get("code"):
                code = str(payload.get("code")).lower()

            if not message and payload.get("message"):
                message = str(payload.get("message")).lower()

            if (
                code in (
                    "ratelimitexceeded",
                    "rate_limit_exceeded",
                    "429",
                )
                or "rate limit" in message
            ):
                raise RateLimitError(
                    "The news provider is temporarily rate-limited."
                )

            if (
                code in (
                    "unauthorized",
                    "invalid_api_key",
                    "forbidden",
                    "401",
                    "403",
                )
                or "unauthorized" in message
                or "api key" in message
            ):
                raise ProviderError(
                    "NewsData.io authentication failed."
                )

            raise ProviderError(
                "The news provider returned an error."
            )

        results = payload.get("results")

        if not isinstance(results, list):
            raise ProviderError(
                "The news provider returned an unexpected response."
            )

        articles = []

        for item in results:
            if not isinstance(item, dict):
                continue

            # NewsData.io uses "link" as the primary article URL.
            # "url" is kept as a fallback for compatibility.
            url = item.get("link") or item.get("url")
            title = item.get("title")

            if (
                not isinstance(url, str)
                or not isinstance(title, str)
                or not url.strip()
                or not title.strip()
            ):
                continue

            # Publisher extraction.
            publisher = None

            if (
                isinstance(item.get("source_name"), str)
                and item["source_name"].strip()
            ):
                publisher = item["source_name"].strip()

            elif (
                isinstance(item.get("source_id"), str)
                and item["source_id"].strip()
            ):
                publisher = item["source_id"].strip()

            elif (
                isinstance(item.get("publisher"), str)
                and item["publisher"].strip()
            ):
                publisher = item["publisher"].strip()

            elif (
                isinstance(item.get("source"), str)
                and item["source"].strip()
            ):
                publisher = item["source"].strip()

            elif isinstance(item.get("source"), dict):
                publisher = (
                    item["source"].get("name")
                    or item["source"].get("domain")
                    or item["source"].get("id")
                )

            # Description extraction.
            description = item.get("description")

            if not description and item.get("snippet"):
                description = item.get("snippet")

            elif not description and item.get("content"):
                description = item.get("content")

            # Publication date extraction.
            pub_date = (
                item.get("pubDate")
                or item.get("published_at")
                or item.get("publication_date")
            )

            articles.append(
                Article(
                    title=title.strip(),
                    url=url.strip(),
                    publisher=self._optional_string(publisher),
                    publication_date=self._optional_string(pub_date),
                    description=self._optional_string(description),
                    source_provider="newsdata",
                    retrieved_at=None,
                )
            )

        return articles[: self.max_results]

    @staticmethod
    def _optional_string(value):
        if isinstance(value, str) and value.strip():
            return value.strip()

        return None