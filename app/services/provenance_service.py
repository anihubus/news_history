class ProvenanceService:
    """Build neutral source references from already retrieved application data."""

    @staticmethod
    def _extract_field(item, field_name):
        if isinstance(item, dict):
            return item.get(field_name)
        return getattr(item, field_name, None)

    def source_signals(self, article):
        """Compute objective source-quality and provenance signals for a single source without credibility scores."""
        publisher = self._extract_field(article, "publisher")
        url = self._extract_field(article, "url")
        pub_date = self._extract_field(article, "publication_date")
        provider = self._extract_field(article, "source_provider")

        publisher_identified = bool(publisher and str(publisher).strip())
        original_url_available = bool(url and str(url).strip())
        publication_date_available = bool(pub_date and str(pub_date).strip())
        source_provider_identified = bool(provider and str(provider).strip())

        missing_fields = []
        if not publisher_identified:
            missing_fields.append("publisher")
        if not original_url_available:
            missing_fields.append("url")
        if not publication_date_available:
            missing_fields.append("publication_date")
        if not source_provider_identified:
            missing_fields.append("source_provider")

        source_information_missing = len(missing_fields) > 0

        return {
            "publisher_identified": publisher_identified,
            "original_url_available": original_url_available,
            "publication_date_available": publication_date_available,
            "source_provider_identified": source_provider_identified,
            "multiple_sources_found": False,
            "independent_source_count": 1 if publisher_identified else 0,
            "source_information_missing": source_information_missing,
            "missing_fields": missing_fields,
        }

    # Alias for convenience
    article_signals = source_signals

    def collection_signals(self, articles):
        """Aggregate provenance signals across multiple sources without ranking or credibility scores."""
        articles = list(articles or [])
        count = len(articles)

        publishers = set()
        has_missing = False
        any_url = False
        any_date = False
        any_provider = False

        for a in articles:
            sig = self.source_signals(a)
            if sig["source_information_missing"]:
                has_missing = True
            if sig["original_url_available"]:
                any_url = True
            if sig["publication_date_available"]:
                any_date = True
            if sig["source_provider_identified"]:
                any_provider = True

            pub = self._extract_field(a, "publisher")
            if pub and str(pub).strip():
                publishers.add(str(pub).strip())

        independent_count = len(publishers)
        multiple_found = count > 1

        return {
            "publisher_identified": len(publishers) > 0,
            "original_url_available": any_url if count > 0 else False,
            "publication_date_available": any_date if count > 0 else False,
            "source_provider_identified": any_provider if count > 0 else False,
            "multiple_sources_found": multiple_found,
            "independent_source_count": independent_count,
            "source_information_missing": has_missing or count == 0,
            "source_count": count,
        }

    def article_reference(self, article):
        signals = self.source_signals(article)
        return {
            "article_id": self._extract_field(article, "article_id"),
            "title": self._extract_field(article, "title"),
            "publisher": self._extract_field(article, "publisher"),
            "url": self._extract_field(article, "url"),
            "publication_date": self._extract_field(article, "publication_date"),
            "retrieved_at": self._extract_field(article, "retrieved_at"),
            "source_provider": self._extract_field(article, "source_provider"),
            "provenance_signals": signals,
            "publisher_identified": signals["publisher_identified"],
            "original_url_available": signals["original_url_available"],
            "publication_date_available": signals["publication_date_available"],
            "source_provider_identified": signals["source_provider_identified"],
            "multiple_sources_found": signals["multiple_sources_found"],
            "independent_source_count": signals["independent_source_count"],
            "source_information_missing": signals["source_information_missing"],
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
            group_articles = [articles_by_id[aid] for aid in group.get("article_ids", []) if aid in articles_by_id]
            item["sources"] = self.references_for_ids(group.get("article_ids", []), articles_by_id)
            signals = self.collection_signals(group_articles)
            item["provenance_signals"] = signals
            item["publisher_identified"] = signals["publisher_identified"]
            item["original_url_available"] = signals["original_url_available"]
            item["publication_date_available"] = signals["publication_date_available"]
            item["source_provider_identified"] = signals["source_provider_identified"]
            item["multiple_sources_found"] = signals["multiple_sources_found"]
            item["independent_source_count"] = signals["independent_source_count"]
            item["source_information_missing"] = signals["source_information_missing"]
            enriched.append(item)
        return enriched

    def enrich_timeline(self, timeline, articles):
        articles_by_id = {article.article_id: article for article in articles}
        enriched = []
        for entry in timeline:
            item = dict(entry)
            entry_articles = [articles_by_id[aid] for aid in entry.get("article_ids", []) if aid in articles_by_id]
            item["supporting_sources"] = self.references_for_ids(
                entry.get("article_ids", []), articles_by_id
            )
            signals = self.collection_signals(entry_articles)
            item["provenance_signals"] = signals
            item["publisher_identified"] = signals["publisher_identified"]
            item["original_url_available"] = signals["original_url_available"]
            item["publication_date_available"] = signals["publication_date_available"]
            item["source_provider_identified"] = signals["source_provider_identified"]
            item["multiple_sources_found"] = signals["multiple_sources_found"]
            item["independent_source_count"] = signals["independent_source_count"]
            item["source_information_missing"] = signals["source_information_missing"]
            enriched.append(item)
        return enriched

    def enrich_summaries(self, summaries, articles):
        articles_by_id = {article.article_id: article for article in articles}
        enriched = []
        for summary in summaries:
            item = dict(summary)
            supporting = [articles_by_id[aid] for aid in summary.get("supporting_article_ids", []) if aid in articles_by_id]
            item["sources"] = self.references_for_ids(
                summary.get("supporting_article_ids", []), articles_by_id
            )
            item["provenance_signals"] = self.collection_signals(supporting)
            enriched.append(item)
        return enriched

    def enrich_answer(self, answer, articles):
        item = dict(answer)
        articles_by_id = {article.article_id: article for article in articles}
        supporting = [articles_by_id[aid] for aid in answer.get("supporting_article_ids", []) if aid in articles_by_id]
        item["sources"] = self.references_for_ids(
            answer.get("supporting_article_ids", []), articles_by_id
        )
        item["provenance_signals"] = self.collection_signals(supporting)
        return item
