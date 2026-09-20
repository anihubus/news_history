from app.models.article import Article


class MockNewsProvider:
    """Development-only provider with deterministic sample articles."""

    def search(self, query):
        return [
            Article(
                title=f"{query.title()}: What changed and why it matters",
                url="https://example.com/news-history/overview",
                publisher="Example News Desk",
                publication_date="20260918090000",
                description="A concise overview of the topic and its recent development.",
                source_provider="mock",
            ),
            Article(
                title=f"Experts examine the latest {query.lower()} developments",
                url="https://example.com/news-history/expert-analysis",
                publisher="The Daily Brief",
                publication_date="20260917143000",
                description="Recent analysis from researchers and public-interest observers.",
                source_provider="mock",
            ),
            Article(
                title=f"Timeline: key moments in {query.lower()}",
                url="https://example.com/news-history/timeline",
                publisher="World Report",
                publication_date="20260916110000",
                description="A short chronology of notable events related to the topic.",
                source_provider="mock",
            ),
        ]
