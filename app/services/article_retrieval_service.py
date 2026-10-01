from dataclasses import dataclass, field, replace

from app.models.article import Article
from app.providers.base_provider import ProviderError, RateLimitError
from app.repositories.article_repository import canonicalize_url


@dataclass
class RetrievalResult:
    articles: list[Article]
    provider_status: str
    provider_error: str | None = None
    providers: dict = field(default_factory=dict)


class ArticleRetrievalService:
    """Combine local article matches with newly retrieved provider articles."""

    def __init__(self, article_repository, news_provider, result_limit=20):
        self.article_repository = article_repository
        self.news_provider = news_provider
        self.result_limit = result_limit

    def search(self, query):
        normalized_query = query.strip()
        stored_articles = [
            self._article_from_row(row)
            for row in self.article_repository.search_articles(normalized_query)
        ]

        provider_status = "ok"
        provider_error = None
        provider_articles = []
        try:
            provider_articles = self.news_provider.search(normalized_query)
            saved_rows = self.article_repository.save_articles(provider_articles)
            updated_provider_articles = []
            for article, row in zip(provider_articles, saved_rows):
                updated_provider_articles.append(
                    replace(
                        article,
                        article_id=row["id"],
                        retrieved_at=row["retrieved_at"],
                        description=article.description if article.description is not None else row["description"],
                        publisher=article.publisher if article.publisher is not None else row["publisher"],
                        publication_date=row["publication_date"] if row["publication_date"] is not None else article.publication_date,
                        source_provider=row["source_provider"] if row.get("source_provider") else article.source_provider,
                    )
                )
            provider_articles = updated_provider_articles
        except RateLimitError:
            provider_status = "rate_limited"
            provider_error = "The news provider is temporarily rate-limited. Please wait before trying again."
        except ProviderError:
            provider_status = "provider_unavailable"
            provider_error = "The news provider is temporarily unavailable."

        providers_info = self._get_providers_status(provider_status)
        combined_articles = self._combine_articles(stored_articles, provider_articles)
        return RetrievalResult(
            articles=self._sort_articles(combined_articles)[: self.result_limit],
            provider_status=provider_status,
            provider_error=provider_error,
            providers=providers_info,
        )

    def _get_providers_status(self, provider_status):
        statuses = {
            "gdelt": {"enabled": False, "success": False},
            "thenewsapi": {"enabled": False, "success": False},
        }

        if hasattr(self.news_provider, "get_provider_statuses"):
            recorded = self.news_provider.get_provider_statuses()
            for name, st in recorded.items():
                statuses[name] = st
        elif hasattr(self.news_provider, "provider_statuses"):
            recorded = getattr(self.news_provider, "provider_statuses", {})
            for name, st in recorded.items():
                statuses[name] = st
        else:
            name = getattr(self.news_provider, "name", self.news_provider.__class__.__name__.lower())
            if "gdelt" in name:
                p_name = "gdelt"
            elif "thenewsapi" in name:
                p_name = "thenewsapi"
            elif "newsapi" in name:
                p_name = "newsapi"
            elif "mock" in name:
                p_name = "mock"
            else:
                p_name = name
            statuses[p_name] = {
                "enabled": True,
                "success": provider_status == "ok",
            }

        return statuses

    def _combine_articles(self, stored_articles, provider_articles):
        articles_by_url = {}
        for article in stored_articles:
            articles_by_url[canonicalize_url(article.url)] = article

        for article in provider_articles:
            canon = canonicalize_url(article.url)
            if canon in articles_by_url:
                stored = articles_by_url[canon]
                providers = [p.strip() for p in (stored.source_provider or "").split(",") if p.strip()]
                for p in (article.source_provider or "").split(","):
                    p = p.strip()
                    if p and p not in providers:
                        providers.append(p)
                merged_provider = ", ".join(providers) if providers else (article.source_provider or stored.source_provider)

                merged = replace(
                    article,
                    description=stored.description if stored.description is not None else article.description,
                    publisher=stored.publisher if stored.publisher is not None else article.publisher,
                    publication_date=stored.publication_date if stored.publication_date is not None else article.publication_date,
                    source_provider=merged_provider,
                    article_id=article.article_id or stored.article_id,
                    retrieved_at=article.retrieved_at or stored.retrieved_at,
                )
                articles_by_url[canon] = merged
            else:
                articles_by_url[canon] = article

        return list(articles_by_url.values())

    @staticmethod
    def _sort_articles(articles):
        def sort_key(article):
            publication_date = article.publication_date
            if not publication_date:
                return (True, 0, canonicalize_url(article.url))
            if publication_date.isdigit():
                return (False, -int(publication_date), canonicalize_url(article.url))
            digits = "".join(ch for ch in str(publication_date) if ch.isdigit())
            if digits:
                return (False, -int(digits[:14].ljust(14, "0")), canonicalize_url(article.url))
            return (True, 0, canonicalize_url(article.url))

        return sorted(
            articles,
            key=sort_key,
        )

    @staticmethod
    def _article_from_row(row):
        return Article(
            title=row["title"],
            url=row["url"],
            publisher=row["publisher"],
            publication_date=row["publication_date"],
            description=row["description"],
            source_provider=row["source_provider"],
            article_id=row["id"],
            retrieved_at=row["retrieved_at"],
        )
