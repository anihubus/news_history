from dataclasses import dataclass, replace

from app.models.article import Article
from app.providers.base_provider import ProviderError, RateLimitError
from app.repositories.article_repository import canonicalize_url


@dataclass
class RetrievalResult:
    articles: list[Article]
    provider_status: str
    provider_error: str | None = None


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
                    )
                )
            provider_articles = updated_provider_articles
        except RateLimitError:
            provider_status = "rate_limited"
            provider_error = "The news provider is temporarily rate-limited. Please wait before trying again."
        except ProviderError:
            provider_status = "provider_unavailable"
            provider_error = "The news provider is temporarily unavailable."

        combined_articles = self._combine_articles(stored_articles, provider_articles)
        return RetrievalResult(
            articles=self._sort_articles(combined_articles)[: self.result_limit],
            provider_status=provider_status,
            provider_error=provider_error,
        )

    def _combine_articles(self, stored_articles, provider_articles):
        articles_by_url = {}
        for article in stored_articles:
            articles_by_url[canonicalize_url(article.url)] = article

        for article in provider_articles:
            canon = canonicalize_url(article.url)
            if canon in articles_by_url:
                stored = articles_by_url[canon]
                merged = replace(
                    article,
                    description=article.description if article.description is not None else stored.description,
                    publisher=article.publisher if article.publisher is not None else stored.publisher,
                    publication_date=stored.publication_date if stored.publication_date is not None else article.publication_date,
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
