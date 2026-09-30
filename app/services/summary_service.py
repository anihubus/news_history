from app.providers.ai_provider import AIProviderError


GROUNDING_INSTRUCTION = (
    "Use only the supplied News History article metadata and descriptions. "
    "Do not invent dates, people, organizations, events, statistics, quotes, or causes. "
    "If evidence is insufficient, say so. Preserve uncertainty and do not claim completeness."
)


class SummaryService:
    def __init__(self, ai_provider):
        self.ai_provider = ai_provider

    @staticmethod
    def _extract_id(item):
        if isinstance(item, dict):
            return item.get("article_id")
        return getattr(item, "article_id", None)

    @staticmethod
    def _extract_article_dict(art):
        if hasattr(art, "to_dict"):
            d = art.to_dict()
            aid = getattr(art, "article_id", None)
            if aid is not None:
                d["article_id"] = aid
            return d
        elif isinstance(art, dict):
            return dict(art)
        return {
            "article_id": getattr(art, "article_id", None),
            "title": getattr(art, "title", ""),
            "url": getattr(art, "url", ""),
            "publisher": getattr(art, "publisher", None),
            "publication_date": getattr(art, "publication_date", None),
            "description": getattr(art, "description", None),
            "source_provider": getattr(art, "source_provider", None),
            "retrieved_at": getattr(art, "retrieved_at", None),
        }

    def generate(self, query, articles, groups, timeline):
        article_dicts = [self._extract_article_dict(a) for a in (articles or [])]
        context = {
            "query": query,
            "articles": article_dicts,
            "groups": groups or [],
            "timeline": timeline or [],
        }
        all_ids = [self._extract_id(a) for a in (articles or []) if self._extract_id(a) is not None]
        summaries = []
        summaries.append(self._generate_one("topic", context, all_ids))
        for group in (groups or []):
            if group.get("article_count", 0) > 1 or len(group.get("article_ids", [])) > 1:
                summaries.append(self._generate_one("group", context, group.get("article_ids", []), group))
        if timeline:
            timeline_ids = [
                aid
                for entry in timeline
                for aid in (entry.get("article_ids", []) if isinstance(entry, dict) else getattr(entry, "article_ids", []))
            ]
            summaries.append(self._generate_one("timeline", context, timeline_ids))
        return [summary for summary in summaries if summary is not None]

    # Explicit alias for updating summary context after timeline changes
    update_summaries = generate

    def _generate_one(self, summary_type, context, article_ids, group=None):
        scoped_context = dict(context)
        scoped_context["summary_type"] = summary_type
        if group:
            scoped_context["active_group"] = group
        try:
            text = self.ai_provider.summarize(GROUNDING_INSTRUCTION, scoped_context)
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
