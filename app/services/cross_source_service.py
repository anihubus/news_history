from app.services.text_normalizer import normalize_text

class CrossSourceService:
    def analyze_groups(self, groups, articles):
        articles_by_id = {article.article_id: article for article in articles}
        
        for group in groups:
            group_articles = [articles_by_id[aid] for aid in group.get("article_ids", []) if aid in articles_by_id]
            if not group_articles:
                group["cross_source_signals"] = []
                continue
                
            signals = self._analyze_group(group_articles)
            group["cross_source_signals"] = signals
            
        return groups

    def _analyze_group(self, articles):
        publishers = {a.publisher for a in articles if a.publisher}
        count = len(publishers)
        signals = []
        
        all_ids = [a.article_id for a in articles]
        signals.append({"signal": "independent_source_count", "value": count, "supporting_article_ids": all_ids})

        if count <= 1:
            signals.append({"signal": "insufficient_cross_source_evidence", "supporting_article_ids": all_ids})
            return signals

        titles = {a.title.lower().strip() for a in articles}
        if len(titles) == 1:
            signals.append({"signal": "same_story", "supporting_article_ids": all_ids})
            return signals

        conflict_keywords = {"deny", "denies", "denied", "dispute", "disputes", "disputed", "reject", "rejects", "rejected", "contradict", "contradicts", "differ", "differing", "fake"}
        conflicting_ids = []
        for a in articles:
            text = (a.title + " " + (a.description or "")).lower()
            if any(word in text.split() for word in conflict_keywords):
                conflicting_ids.append(a.article_id)
        
        if conflicting_ids:
            signals.append({"signal": "conflicting_reports", "supporting_article_ids": conflicting_ids})
            
        supporting_ids = [a.article_id for a in articles if a.article_id not in conflicting_ids]
        if len(supporting_ids) >= 1:
            signals.append({"signal": "supporting_reports", "supporting_article_ids": supporting_ids})
        elif not conflicting_ids:
            signals.append({"signal": "supporting_reports", "supporting_article_ids": all_ids})

        return signals
