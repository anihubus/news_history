class ProvenanceService:
    """Build neutral source references from already retrieved application data."""

    def article_reference(self, article):
        return {
            "article_id": article.article_id,
            "title": article.title,
            "publisher": article.publisher,
            "url": article.url,
            "publication_date": article.publication_date,
            "retrieved_at": article.retrieved_at,
            "source_provider": article.source_provider,
        }

    def article_payload(self, article):
        payload = article.to_dict()
        payload.update(self.article_reference(article))
        return payload

    def references_for_ids(self, article_ids, articles_by_id):
        references = []
        seen = set()
        for article_id in article_ids:
            article = articles_by_id.get(article_id)
            if article is None or article_id in seen:
                continue
            references.append(self.article_reference(article))
            seen.add(article_id)
        return references

    def enrich_groups(self, groups, articles):
        articles_by_id = {article.article_id: article for article in articles}
        enriched = []
        for group in groups:
            item = dict(group)
            item["sources"] = self.references_for_ids(group.get("article_ids", []), articles_by_id)
            enriched.append(item)
        return enriched

    def enrich_timeline(self, timeline, articles):
        articles_by_id = {article.article_id: article for article in articles}
        enriched = []
        for entry in timeline:
            item = dict(entry)
            item["supporting_sources"] = self.references_for_ids(
                entry.get("article_ids", []), articles_by_id
            )
            enriched.append(item)
        return enriched

    def enrich_summaries(self, summaries, articles):
        articles_by_id = {article.article_id: article for article in articles}
        enriched = []
        for summary in summaries:
            item = dict(summary)
            item["sources"] = self.references_for_ids(
                summary.get("supporting_article_ids", []), articles_by_id
            )
            enriched.append(item)
        return enriched

    def enrich_answer(self, answer, articles):
        item = dict(answer)
        articles_by_id = {article.article_id: article for article in articles}
        item["sources"] = self.references_for_ids(
            answer.get("supporting_article_ids", []), articles_by_id
        )
        return item
