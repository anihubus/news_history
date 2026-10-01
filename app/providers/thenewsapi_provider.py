import json
import os
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.models.article import Article
from app.providers.base_provider import NewsProvider, ProviderError, RateLimitError


class TheNewsAPIProvider(NewsProvider):
    name = "thenewsapi"

    def __init__(
        self,
        api_key=None,
        base_url="https://api.thenewsapi.com/v1",
        timeout=10,
        max_results=10,
        language="en",
    ):
        self.api_key = api_key if api_key is not None else os.getenv("THENEWSAPI_API_KEY")
        self.base_url = base_url or "https://api.thenewsapi.com/v1"
        self.timeout = float(timeout) if timeout is not None else 10.0
        self.max_results = int(max_results) if max_results is not None else 10
        self.language = language

    def search(self, query):
        if not self.api_key or not str(self.api_key).strip():
            raise ProviderError("The News API key is missing.")

        request_url = self._build_request_url(query)
        request = Request(
            request_url,
            headers={
                "Accept": "application/json",
                "User-Agent": "NewsHistory/1.0",
            },
        )

        try:
            with urlopen(request, timeout=self.timeout) as response:
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

    def _build_request_url(self, query):
        endpoint = self.base_url.rstrip("/")
        if not endpoint.endswith("/news/all"):
            endpoint = f"{endpoint}/news/all"

        parameters = {
            "api_token": self.api_key,
            "search": query,
            "limit": self.max_results,
        }
        if self.language:
            parameters["language"] = self.language

        encoded_params = urlencode(parameters)
        separator = "&" if "?" in endpoint else "?"
        return f"{endpoint}{separator}{encoded_params}"

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
