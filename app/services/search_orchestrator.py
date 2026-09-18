class SearchOrchestrator:
    """Coordinate search validation and the temporary retrieval boundary."""

    def __init__(self, search_service):
        self.search_service = search_service

    def search(self, query):
        if not isinstance(query, str) or not query.strip():
            raise ValueError("Search query cannot be empty.")

        normalized_query = query.strip()
        search_result = self.search_service.search(normalized_query)

        return {
            "success": True,
            "query": normalized_query,
            "results": search_result["results"],
            "message": search_result["message"],
        }
