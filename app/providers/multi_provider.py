from dataclasses import replace

from app.providers.base_provider import NewsProvider, ProviderError, RateLimitError
from app.repositories.article_repository import canonicalize_url


class MultiProvider(NewsProvider):
    def __init__(self, providers):
        self.providers = providers

    def search(self, query):
        articles = []
        errors = []
        for provider in self.providers:
            try:
                articles.extend(provider.search(query))
            except Exception as e:
                errors.append(e)

        # If all providers failed, surface the most relevant error
        if not articles and len(errors) == len(self.providers) and self.providers:
            for e in errors:
                if isinstance(e, RateLimitError):
                    raise e
            raise errors[0]

        # Deduplicate across multiple providers using canonical URL
        unique_articles = {}
        for article in articles:
            url = canonicalize_url(article.url)
            if url not in unique_articles:
                unique_articles[url] = article
            else:
                existing = unique_articles[url]
                providers = [p.strip() for p in (existing.source_provider or "").split(",") if p.strip()]
                if article.source_provider and article.source_provider not in providers:
                    providers.append(article.source_provider)
                merged_provider = ", ".join(providers) if providers else existing.source_provider

                unique_articles[url] = replace(
                    existing,
                    description=existing.description if existing.description is not None else article.description,
                    publisher=existing.publisher if existing.publisher is not None else article.publisher,
                    publication_date=existing.publication_date if existing.publication_date is not None else article.publication_date,
                    source_provider=merged_provider,
                )

        return list(unique_articles.values())
