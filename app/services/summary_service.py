from app.providers.ai_provider import AIProviderError


GROUNDING_INSTRUCTION = (
    "Use only the supplied News History article metadata and descriptions. "
    "Do not invent dates, people, organizations, events, statistics, quotes, or causes. "
    "If evidence is insufficient, say so. Preserve uncertainty and do not claim completeness."
)


class SummaryService:
    def __init__(self, ai_provider):
        self.ai_provider = ai_provider

    def generate(self, query, articles, groups, timeline):
        context = {
            "query": query,
            "articles": [article.to_dict() | {"article_id": article.article_id} for article in articles],
            "groups": groups,
            "timeline": timeline,
        }
        summaries = []
        summaries.append(self._generate_one("topic", context, [article.article_id for article in articles]))
        for group in groups:
            if group.get("article_count", 0) > 1:
                summaries.append(self._generate_one("group", context, group.get("article_ids", []), group))
        if timeline:
            summaries.append(self._generate_one("timeline", context, [article_id for entry in timeline for article_id in entry.get("article_ids", [])]))
        return [summary for summary in summaries if summary is not None]

    def _generate_one(self, summary_type, context, article_ids, group=None):
        try:
            text = self.ai_provider.summarize(GROUNDING_INSTRUCTION, context)
        except (AIProviderError, TimeoutError, OSError):
            return None
        if not isinstance(text, str) or not text.strip():
            return None
        return {
            "summary": text.strip(),
            "summary_type": summary_type,
            "supporting_article_ids": sorted(set(article_ids)),
            "automatic": True,
            "source_basis": "Retrieved article metadata and descriptions",
            "provider": self.ai_provider.name,
            "group_id": group.get("group_id") if group else None,
        }
