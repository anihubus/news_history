class VerificationSignalService:
    """Generate structured, neutral verification and warning signals based only on observable data."""

    CONFLICT_KEYWORDS = {
        "deny", "denies", "denied", "dispute", "disputes", "disputed",
        "reject", "rejects", "rejected", "contradict", "contradicts",
        "differ", "differing", "fake"
    }

    @staticmethod
    def _extract(item, field):
        if isinstance(item, dict):
            return item.get(field)
        return getattr(item, field, None)

    def analyze_article(self, article):
        """Analyze a single article record for observable metadata gaps."""
        signals = []
        article_id = self._extract(article, "article_id")
        ids = [article_id] if article_id is not None else []

        publisher = self._extract(article, "publisher")
        pub_date = self._extract(article, "publication_date")
        url = self._extract(article, "url")
        provider = self._extract(article, "source_provider")

        has_publisher = bool(publisher and str(publisher).strip())
        has_date = bool(pub_date and str(pub_date).strip())
        has_url = bool(url and str(url).strip())
        has_provider = bool(provider and str(provider).strip())

        missing_fields = []
        if not has_publisher:
            missing_fields.append("publisher")
            signals.append({
                "type": "missing_publisher",
                "severity": "warning",
                "explanation": "Publisher information is missing from the source record.",
                "supporting_article_ids": ids,
            })

        if not has_date:
            missing_fields.append("publication_date")
            signals.append({
                "type": "missing_publication_date",
                "severity": "warning",
                "explanation": "Publication date is unavailable in the source metadata.",
                "supporting_article_ids": ids,
            })

        if not has_url:
            missing_fields.append("url")
            signals.append({
                "type": "missing_original_url",
                "severity": "warning",
                "explanation": "Original source URL is unavailable.",
                "supporting_article_ids": ids,
            })

        if len(missing_fields) >= 2:
            signals.append({
                "type": "unusually_incomplete_metadata",
                "severity": "warning",
                "explanation": "Source metadata is unusually incomplete.",
                "supporting_article_ids": ids,
            })

        if len(missing_fields) >= 1 or not (has_publisher and has_date and has_url and has_provider):
            signals.append({
                "type": "incomplete_metadata",
                "severity": "warning",
                "explanation": "Source metadata is incomplete.",
                "supporting_article_ids": ids,
            })

        return signals

    def analyze_articles(self, articles):
        """Analyze a set of articles (e.g. for a timeline event, cluster, or query) for warning signals."""
        articles = list(articles or [])
        signals = []
        if not articles:
            return signals

        all_ids = [self._extract(a, "article_id") for a in articles if self._extract(a, "article_id") is not None]

        # 1. Single source only
        if len(articles) == 1:
            signals.append({
                "type": "single_source_only",
                "severity": "warning",
                "explanation": "Limited independent reporting is currently available.",
                "supporting_article_ids": all_ids,
            })

        # 2. No independent supporting reports
        publishers = {
            str(self._extract(a, "publisher")).strip()
            for a in articles
            if self._extract(a, "publisher") and str(self._extract(a, "publisher")).strip()
        }
        if len(publishers) <= 1 and len(articles) > 1:
            signals.append({
                "type": "no_independent_supporting_reports",
                "severity": "warning",
                "explanation": "Limited independent reporting is currently available.",
                "supporting_article_ids": all_ids,
            })

        # 3. Conflicting reports
        conflicting_ids = []
        for a in articles:
            text = ((self._extract(a, "title") or "") + " " + (self._extract(a, "description") or "")).lower()
            words = set(text.split())
            if any(kw in words for kw in self.CONFLICT_KEYWORDS):
                aid = self._extract(a, "article_id")
                if aid is not None:
                    conflicting_ids.append(aid)

        if conflicting_ids:
            signals.append({
                "type": "conflicting_reports",
                "severity": "warning",
                "explanation": "Some reports contain differing information.",
                "supporting_article_ids": conflicting_ids,
            })

        # 4. Metadata gaps across articles
        missing_pub_ids = [
            self._extract(a, "article_id")
            for a in articles
            if not self._extract(a, "publisher") or not str(self._extract(a, "publisher")).strip()
        ]
        if missing_pub_ids:
            signals.append({
                "type": "missing_publisher",
                "severity": "warning",
                "explanation": "Publisher information is missing from the source record.",
                "supporting_article_ids": [i for i in missing_pub_ids if i is not None],
            })

        missing_date_ids = [
            self._extract(a, "article_id")
            for a in articles
            if not self._extract(a, "publication_date") or not str(self._extract(a, "publication_date")).strip()
        ]
        if missing_date_ids:
            signals.append({
                "type": "missing_publication_date",
                "severity": "warning",
                "explanation": "Publication date is unavailable in the source metadata.",
                "supporting_article_ids": [i for i in missing_date_ids if i is not None],
            })

        missing_url_ids = [
            self._extract(a, "article_id")
            for a in articles
            if not self._extract(a, "url") or not str(self._extract(a, "url")).strip()
        ]
        if missing_url_ids:
            signals.append({
                "type": "missing_original_url",
                "severity": "warning",
                "explanation": "Original source URL is unavailable.",
                "supporting_article_ids": [i for i in missing_url_ids if i is not None],
            })

        incomplete_ids = []
        unusual_incomplete_ids = []
        for a in articles:
            missing_count = sum([
                1 if not self._extract(a, "publisher") or not str(self._extract(a, "publisher")).strip() else 0,
                1 if not self._extract(a, "publication_date") or not str(self._extract(a, "publication_date")).strip() else 0,
                1 if not self._extract(a, "url") or not str(self._extract(a, "url")).strip() else 0,
                1 if not self._extract(a, "source_provider") or not str(self._extract(a, "source_provider")).strip() else 0,
            ])
            aid = self._extract(a, "article_id")
            if missing_count >= 1 and aid is not None:
                incomplete_ids.append(aid)
            if missing_count >= 2 and aid is not None:
                unusual_incomplete_ids.append(aid)

        if unusual_incomplete_ids:
            signals.append({
                "type": "unusually_incomplete_metadata",
                "severity": "warning",
                "explanation": "Source metadata is unusually incomplete.",
                "supporting_article_ids": unusual_incomplete_ids,
            })

        if incomplete_ids:
            signals.append({
                "type": "incomplete_metadata",
                "severity": "warning",
                "explanation": "Source metadata is incomplete.",
                "supporting_article_ids": incomplete_ids,
            })

        return signals

    def enrich_groups(self, groups, articles):
        """Enrich groups with verification and warning signals."""
        from app.services.cross_source_service import CrossSourceService

        articles_by_id = {self._extract(a, "article_id"): a for a in articles}
        cross_source = CrossSourceService()
        enriched = []
        for group in groups:
            item = dict(group)
            group_articles = [articles_by_id[aid] for aid in group.get("article_ids", []) if aid in articles_by_id]
            signals = self.analyze_articles(group_articles)
            verification = cross_source.verify_related_articles(group_articles)
            item["verification_signals"] = signals
            item["warning_signals"] = signals
            item["cross_source_verification"] = verification
            item["independent_source_count"] = verification["independent_source_count"]
            item["supporting_reports"] = verification["supporting_reports"]
            item["conflicting_reports"] = verification["conflicting_reports"]
            item["source_metadata_completeness"] = verification["source_metadata_completeness"]
            item["time_of_first_report"] = verification["time_of_first_report"]
            item["time_of_latest_report"] = verification["time_of_latest_report"]
            item["cross_source_signals"] = verification["signals"]
            enriched.append(item)
        return enriched

    def enrich_timeline(self, timeline, articles):
        """Enrich timeline entries with verification and warning signals."""
        from app.services.cross_source_service import CrossSourceService

        articles_by_id = {self._extract(a, "article_id"): a for a in articles}
        cross_source = CrossSourceService()
        enriched = []
        for entry in timeline:
            item = dict(entry)
            entry_articles = [articles_by_id[aid] for aid in entry.get("article_ids", []) if aid in articles_by_id]
            signals = self.analyze_articles(entry_articles)
            verification = cross_source.verify_related_articles(entry_articles)
            item["verification_signals"] = signals
            item["warning_signals"] = signals
            item["cross_source_verification"] = verification
            item["independent_source_count"] = verification["independent_source_count"]
            item["supporting_reports"] = verification["supporting_reports"]
            item["conflicting_reports"] = verification["conflicting_reports"]
            item["source_metadata_completeness"] = verification["source_metadata_completeness"]
            item["time_of_first_report"] = verification["time_of_first_report"]
            item["time_of_latest_report"] = verification["time_of_latest_report"]
            item["cross_source_signals"] = verification["signals"]
            enriched.append(item)
        return enriched

    def build_dashboard(self, articles, groups=None, timeline=None):
        """Construct a structured verification dashboard combining source data, cross-source evidence, and warning signals."""
        from app.services.cross_source_service import CrossSourceService

        articles = list(articles or [])
        groups = list(groups or [])
        timeline = list(timeline or [])

        cross_source = CrossSourceService()
        cross_verification = cross_source.verify_related_articles(articles)

        warnings = self.analyze_articles(articles)
        publishers = sorted(list({
            str(self._extract(a, "publisher")).strip()
            for a in articles
            if self._extract(a, "publisher") and str(self._extract(a, "publisher")).strip()
        }))
        independent_source_count = len(publishers)
        total_sources = len(articles)

        # Conflicting article IDs
        conflicting_ids = set()
        for sig in warnings:
            if sig.get("type") == "conflicting_reports":
                conflicting_ids.update(sig.get("supporting_article_ids", []))

        # Check keyword conflicts directly as well
        for a in articles:
            text = ((self._extract(a, "title") or "") + " " + (self._extract(a, "description") or "")).lower()
            words = set(text.split())
            if any(kw in words for kw in self.CONFLICT_KEYWORDS):
                aid = self._extract(a, "article_id")
                if aid is not None:
                    conflicting_ids.add(aid)

        supporting_ids = [
            self._extract(a, "article_id")
            for a in articles
            if self._extract(a, "article_id") not in conflicting_ids and self._extract(a, "article_id") is not None
        ]

        # Neutral summary statement
        if total_sources == 0:
            summary_statement = "No reporting available to evaluate."
        elif len(conflicting_ids) > 0:
            summary_statement = "Reports contain differing information."
        elif independent_source_count > 1:
            summary_statement = "Reported by multiple sources."
        elif independent_source_count == 1 and total_sources > 1:
            summary_statement = "Limited independent reporting available (single publisher)."
        else:
            summary_statement = "Limited independent reporting available."

        # Source items formatted for dashboard
        source_items = []
        for a in articles:
            aid = self._extract(a, "article_id")
            art_warnings = self.analyze_article(a)
            is_conflicting = aid in conflicting_ids
            is_supporting = aid in supporting_ids

            reporting_status = "Conflicting report" if is_conflicting else ("Supporting report" if is_supporting and independent_source_count > 1 else "Single source report")

            source_items.append({
                "article_id": aid,
                "title": self._extract(a, "title"),
                "original_url": self._extract(a, "url"),
                "publisher": self._extract(a, "publisher") or "Publisher not identified",
                "publication_date": self._extract(a, "publication_date") or "Date unavailable",
                "source_provider": self._extract(a, "source_provider") or "Unknown provider",
                "independent_source_count": independent_source_count,
                "is_supporting": is_supporting,
                "is_conflicting": is_conflicting,
                "reporting_status": reporting_status,
                "verification_warnings": art_warnings,
                "has_warnings": len(art_warnings) > 0,
            })

        return {
            "summary_statement": summary_statement,
            "independent_source_count": independent_source_count,
            "independent_publishers_count": independent_source_count,
            "number_of_independent_publishers": independent_source_count,
            "total_sources": total_sources,
            "publishers": publishers,
            "multiple_sources_found": independent_source_count > 1,
            "has_conflicting_reports": len(conflicting_ids) > 0,
            "conflicting_reports_count": len(conflicting_ids),
            "possible_conflicting_reports": sorted(list(conflicting_ids)),
            "supporting_reports_count": len(supporting_ids),
            "number_of_supporting_reports": len(supporting_ids),
            "supporting_reports": supporting_ids,
            "conflicting_reports": sorted(list(conflicting_ids)),
            "is_single_source": independent_source_count <= 1,
            "single_source_story": independent_source_count <= 1,
            "single_source_stories": [self._extract(a, "article_id") for a in articles if self._extract(a, "article_id") is not None] if independent_source_count <= 1 else [],
            "source_metadata_completeness": cross_verification["source_metadata_completeness"],
            "missing_source_metadata": cross_verification["source_metadata_completeness"],
            "time_of_first_report": cross_verification["time_of_first_report"],
            "earliest_available_publication_time": cross_verification["time_of_first_report"],
            "earliest_publication_time": cross_verification["time_of_first_report"],
            "time_of_latest_report": cross_verification["time_of_latest_report"],
            "latest_available_publication_time": cross_verification["time_of_latest_report"],
            "latest_publication_time": cross_verification["time_of_latest_report"],
            "neutral_signals": cross_verification["signals"],
            "cross_source_verification": cross_verification,
            "warnings": warnings,
            "has_warnings": len(warnings) > 0,
            "sources": source_items,
            "disclaimer": "These indicators represent observable verification signals based on retrieved metadata and reporting patterns, not definitive fact-checking verdicts or credibility scores.",
        }
