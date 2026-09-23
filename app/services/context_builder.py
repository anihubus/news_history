class ContextBuilder:
    """Build the explicit evidence context passed to grounded services."""

    def build(self, query, articles, groups, timeline):
        return {
            "query": query,
            "articles": [self._article_context(article) for article in articles],
            "groups": groups,
            "timeline": timeline,
        }

    @staticmethod
    def _article_context(article):
        return {
            "article_id": article.article_id,
            "title": article.title,
            "description": article.description,
            "publication_date": article.publication_date,
            "publisher": article.publisher,
            "url": article.url,
        }
