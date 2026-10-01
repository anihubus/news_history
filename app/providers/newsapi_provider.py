import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.models.article import Article
from app.providers.base_provider import NewsProvider, ProviderError, RateLimitError


class NewsAPIProvider(NewsProvider):
    name = "newsapi"

    def __init__(self, api_key, base_url="https://newsapi.org/v2/everything", max_results=10, timeout=10):
        self.api_key = api_key
        self.base_url = base_url
        self.max_results = max_results
        self.timeout = timeout

    def search(self, query):
        if not self.api_key:
            raise ProviderError("NewsAPI key is missing.")

        request_url = self._build_request_url(query)
        request = Request(
            request_url,
            headers={
                "Accept": "application/json",
                "User-Agent": "NewsHistory/1.0",
                "X-Api-Key": self.api_key,
            },
        )

        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            if error.code == 429:
                raise RateLimitError("The news provider is temporarily rate-limited.") from error
            if error.code == 401:
                raise ProviderError("NewsAPI authentication failed.") from error
            raise ProviderError("The news provider returned an HTTP error.") from error
        except (URLError, TimeoutError, OSError):
            raise ProviderError("The news provider could not be reached.")
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ProviderError("The news provider returned an invalid response.")

        return self._parse_response(payload)

    def _build_request_url(self, query):
        parameters = urlencode(
            {
                "q": query,
                "pageSize": self.max_results,
                "language": "en",
            }
        )
        separator = "&" if "?" in self.base_url else "?"
        return f"{self.base_url}{separator}{parameters}"

    def _parse_response(self, payload):
        if not isinstance(payload, dict) or not isinstance(payload.get("articles"), list):
            raise ProviderError("The news provider returned an unexpected response.")

        if payload.get("status") != "ok":
            raise ProviderError("NewsAPI returned an error status.")

        articles = []
        for item in payload["articles"]:
            if not isinstance(item, dict):
                continue

            url = item.get("url")
            title = item.get("title")
            if not isinstance(url, str) or not isinstance(title, str) or not url.strip() or not title.strip():
                continue

            publisher = None
            source = item.get("source")
            if isinstance(source, dict):
                publisher = source.get("name")

            articles.append(
                Article(
                    title=title,
                    url=url,
                    publisher=self._optional_string(publisher),
                    publication_date=self._optional_string(item.get("publishedAt")),
                    description=self._optional_string(item.get("description")),
                    source_provider="newsapi",
                )
            )

        return articles

    @staticmethod
    def _optional_string(value):
        return value if isinstance(value, str) else None
