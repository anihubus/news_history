import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.models.article import Article
from app.providers.base_provider import NewsProvider, ProviderError, RateLimitError


class GDELTProvider(NewsProvider):
    def __init__(self, base_url, max_results=10, timeout=10):
        self.base_url = base_url
        self.max_results = max_results
        self.timeout = timeout

    def search(self, query):
        request_url = self._build_request_url(query)
        request = Request(
            request_url,
            headers={"Accept": "application/json", "User-Agent": "NewsHistory/1.0"},
        )

        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            if error.code == 429:
                raise RateLimitError from error
            raise ProviderError("The news provider returned an HTTP error.") from error
        except (URLError, TimeoutError, OSError):
            raise ProviderError("The news provider could not be reached.")
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ProviderError("The news provider returned an invalid response.")

        return self._parse_response(payload)

    def _build_request_url(self, query):
        parameters = urlencode(
            {
                "query": query,
                "mode": "artlist",
                "format": "json",
                "maxrecords": self.max_results,
            }
        )
        separator = "&" if "?" in self.base_url else "?"
        return f"{self.base_url}{separator}{parameters}"

    def _parse_response(self, payload):
        if not isinstance(payload, dict) or not isinstance(payload.get("articles"), list):
            raise ProviderError("The news provider returned an unexpected response.")

        articles = []
        for item in payload["articles"]:
            if not isinstance(item, dict):
                continue

            url = item.get("url")
            title = item.get("title")
            if not isinstance(url, str) or not isinstance(title, str):
                continue

            articles.append(
                Article(
                    title=title,
                    url=url,
                    publisher=self._optional_string(item.get("domain")),
                    publication_date=self._optional_string(item.get("seendate")),
                    description=None,
                    source_provider="gdelt",
                )
            )

        return articles

    @staticmethod
    def _optional_string(value):
        return value if isinstance(value, str) else None
