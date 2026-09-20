from app.providers.gdelt_provider import ProviderError, RateLimitError


class SearchOrchestrator:
    """Coordinate search validation and provider retrieval."""

    def __init__(self, search_service):
        self.search_service = search_service

    def search(self, query):
        if not isinstance(query, str) or not query.strip():
            return {
                "success": False,
                "error": "Search query cannot be empty.",
            }

        normalized_query = query.strip()
        try:
            articles = self.search_service.search(normalized_query)
        except RateLimitError:
            return {
                "success": False,
                "status": "rate_limited",
                "query": normalized_query,
                "error": "The news provider is temporarily rate-limited. Please wait before trying again.",
            }
        except ProviderError:
            return {
                "success": False,
                "status": "provider_unavailable",
                "query": normalized_query,
                "error": "The news provider is temporarily unavailable.",
            }

        return {
            "success": True,
            "query": normalized_query,
            "results": [article.to_dict() for article in articles],
            "message": None,
        }
