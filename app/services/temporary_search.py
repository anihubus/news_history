class TemporarySearchService:
    """Temporary retrieval boundary used until a real provider is connected."""

    def search(self, query):
        return {
            "results": [],
            "message": "Search pipeline is ready. News retrieval will be connected in a later step.",
        }
