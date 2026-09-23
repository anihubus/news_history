class AIProviderError(Exception):
    """Raised when an AI provider cannot produce a safe response."""


class AIProvider:
    """Replaceable interface for grounded model interactions."""

    name = "unknown"

    def summarize(self, instruction, context):
        raise NotImplementedError

    def answer(self, instruction, context, question):
        raise NotImplementedError


class MockAIProvider(AIProvider):
    name = "mock"

    def summarize(self, instruction, context):
        articles = context.get("articles", [])
        if not articles:
            return "The available reporting is insufficient to produce a summary."

        titles = [article.get("title") for article in articles if article.get("title")]
        return f"Available reporting includes {len(articles)} article(s): " + "; ".join(titles[:3]) + "."

    def answer(self, instruction, context, question):
        articles = context.get("articles", [])
        if not articles:
            return {
                "answer": "The available sources do not provide enough information to answer this question.",
                "supporting_article_ids": [],
            }

        titles = [article.get("title") for article in articles if article.get("title")]
        return {
            "answer": f"Based on the available sources, the retrieved reporting includes: {'; '.join(titles[:3])}.",
            "supporting_article_ids": [article.get("article_id") for article in articles if article.get("article_id") is not None],
        }
