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

        return list(unique_articles.values())
