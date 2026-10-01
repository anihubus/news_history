from datetime import datetime, timezone

from app.services.text_normalizer import normalize_text


def parse_report_datetime(value):
    """Parse publication date string into a comparable datetime object."""
    if not value or not isinstance(value, str):
        return None
    val = value.strip()
    if not val:
        return None

    # Common explicit formats
    for fmt in ("%Y%m%d%H%M%S", "%Y%m%d%H%M", "%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue

    # ISO formats
    try:
        normalized = val.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except ValueError:
        pass

    # Pure digits fallback
    digits = "".join(ch for ch in val if ch.isdigit())
    if len(digits) >= 8:
        try:
            return datetime.strptime(digits[:14].ljust(14, "0"), "%Y%m%d%H%M%S")
        except ValueError:
            pass

    return None


class CrossSourceService:
    """Compare fresh reports from different sources and provide transparent verification signals."""

    CONFLICT_KEYWORDS = {
        "deny", "denies", "denied", "dispute", "disputes", "disputed",
        "reject", "rejects", "rejected", "contradict", "contradicts",
        "differ", "differing", "fake", "oppose", "opposes", "opposed",
        "refute", "refutes", "refuted"
    }

    @staticmethod
    def _extract(item, field):
        if isinstance(item, dict):
            return item.get(field)
        return getattr(item, field, None)

    def verify_related_articles(self, articles):
        """
        For a set of related articles, calculate:
        - number of independent sources
        - supporting reports
        - conflicting reports
        - source metadata completeness
        - time of first report
        - time of latest report

        Display neutral signals such as:
        - 'Reported by multiple sources.'
        - 'Limited independent reporting available.'
        - 'Reports contain differing information.'
        - 'Source metadata is incomplete.'

        Every signal references the supporting article IDs.
        No credibility scores, publisher rankings, or 'fake'/'true' labels are produced.
        """
        articles = list(articles or [])
        if not articles:
            empty_metadata = {
                "is_complete": False,
                "complete_article_count": 0,
                "total_article_count": 0,
                "incomplete_article_ids": [],
                "missing_fields": [],
            }
            return {
                "independent_source_count": 0,
                "independent_publishers_count": 0,
                "number_of_independent_publishers": 0,
                "supporting_reports": [],
                "supporting_reports_count": 0,
                "number_of_supporting_reports": 0,
                "conflicting_reports": [],
                "conflicting_reports_count": 0,
                "possible_conflicting_reports": [],
                "single_source_stories": [],
                "single_source_story": False,
                "is_single_source": False,
                "source_metadata_completeness": empty_metadata,
                "missing_source_metadata": empty_metadata,
                "time_of_first_report": None,
                "earliest_available_publication_time": None,
                "earliest_publication_time": None,
                "time_of_latest_report": None,
                "latest_available_publication_time": None,
                "latest_publication_time": None,
                "signals": [],
            }

        all_ids = [
            self._extract(a, "article_id")
            for a in articles
            if self._extract(a, "article_id") is not None
        ]

        # 1. Number of independent sources
        publishers = {
            str(self._extract(a, "publisher")).strip()
            for a in articles
            if self._extract(a, "publisher") and str(self._extract(a, "publisher")).strip()
        }
        independent_source_count = len(publishers)

        # 2. Conflicting and supporting reports
        conflicting_ids = []
        for a in articles:
            text = ((self._extract(a, "title") or "") + " " + (self._extract(a, "description") or "")).lower()
            words = set(text.split())
            if any(kw in words for kw in self.CONFLICT_KEYWORDS):
                aid = self._extract(a, "article_id")
                if aid is not None and aid not in conflicting_ids:
                    conflicting_ids.append(aid)

        supporting_ids = [aid for aid in all_ids if aid not in conflicting_ids]
        if not conflicting_ids and not supporting_ids:
            supporting_ids = list(all_ids)

        # 3. Source metadata completeness
        incomplete_ids = []
        missing_fields_set = set()
        complete_count = 0

        for a in articles:
            aid = self._extract(a, "article_id")
            has_pub = bool(self._extract(a, "publisher") and str(self._extract(a, "publisher")).strip())
            has_date = bool(self._extract(a, "publication_date") and str(self._extract(a, "publication_date")).strip())
            has_url = bool(self._extract(a, "url") and str(self._extract(a, "url")).strip())
            has_provider = bool(self._extract(a, "source_provider") and str(self._extract(a, "source_provider")).strip())

            article_missing = []
            if not has_pub:
                article_missing.append("publisher")
            if not has_date:
                article_missing.append("publication_date")
            if not has_url:
                article_missing.append("url")
            if not has_provider:
                article_missing.append("source_provider")

            if article_missing:
                if aid is not None and aid not in incomplete_ids:
                    incomplete_ids.append(aid)
                missing_fields_set.update(article_missing)
            else:
                complete_count += 1

        metadata_completeness = {
            "is_complete": len(incomplete_ids) == 0 and len(articles) > 0,
            "complete_article_count": complete_count,
            "total_article_count": len(articles),
            "incomplete_article_ids": incomplete_ids,
            "missing_fields": sorted(list(missing_fields_set)),
        }

        # 4. Time of first report and time of latest report
        articles_with_dates = []
        for a in articles:
            raw_date = self._extract(a, "publication_date")
            dt = parse_report_datetime(raw_date)
            if dt:
                articles_with_dates.append((dt, raw_date))

        if articles_with_dates:
            articles_with_dates.sort(key=lambda item: item[0])
            time_of_first_report = articles_with_dates[0][1]
            time_of_latest_report = articles_with_dates[-1][1]
        else:
            time_of_first_report = None
            time_of_latest_report = None

        is_single_source = bool(independent_source_count <= 1 or len(articles) <= 1)

        # 5. Neutral signals (each references supporting_article_ids and article_ids)
        signals = []

        # Multiple sources vs single source reporting
        if independent_source_count > 1 and supporting_ids:
            signals.append({
                "signal": "supporting_reports",
                "type": "supporting_reports",
                "label": "Multiple sources reporting",
                "statement": "Reported by multiple sources.",
                "explanation": "Multiple sources reporting",
                "supporting_article_ids": supporting_ids,
                "article_ids": supporting_ids,
            })
        else:
            signals.append({
                "signal": "insufficient_cross_source_evidence",
                "type": "single_source_report",
                "label": "Single-source report",
                "statement": "Limited independent reporting available.",
                "explanation": "Single-source report",
                "supporting_article_ids": all_ids,
                "article_ids": all_ids,
            })

        # Conflicting reports signal
        if conflicting_ids:
            signals.append({
                "signal": "conflicting_reports",
                "type": "conflicting_reports",
                "label": "Conflicting reports detected",
                "statement": "Reports contain differing information.",
                "explanation": "Conflicting reports detected",
                "supporting_article_ids": conflicting_ids,
                "article_ids": conflicting_ids,
            })

        # Metadata completeness signal
        if incomplete_ids:
            signals.append({
                "signal": "incomplete_metadata",
                "type": "limited_source_information",
                "label": "Limited source information",
                "statement": "Source metadata is incomplete.",
                "explanation": "Limited source information",
                "supporting_article_ids": incomplete_ids,
                "article_ids": incomplete_ids,
            })

        return {
            "independent_source_count": independent_source_count,
            "independent_publishers_count": independent_source_count,
            "number_of_independent_publishers": independent_source_count,
            "supporting_reports": supporting_ids,
            "supporting_reports_count": len(supporting_ids),
            "number_of_supporting_reports": len(supporting_ids),
            "conflicting_reports": conflicting_ids,
            "conflicting_reports_count": len(conflicting_ids),
            "possible_conflicting_reports": conflicting_ids,
            "single_source_stories": all_ids if is_single_source else [],
            "single_source_story": is_single_source,
            "is_single_source": is_single_source,
            "source_metadata_completeness": metadata_completeness,
            "missing_source_metadata": metadata_completeness,
            "time_of_first_report": time_of_first_report,
            "earliest_available_publication_time": time_of_first_report,
            "earliest_publication_time": time_of_first_report,
            "time_of_latest_report": time_of_latest_report,
            "latest_available_publication_time": time_of_latest_report,
            "latest_publication_time": time_of_latest_report,
            "signals": signals,
        }

    def analyze_groups(self, groups, articles):
        articles_by_id = {
            self._extract(article, "article_id"): article
            for article in articles
            if self._extract(article, "article_id") is not None
        }

        for group in groups:
            group_articles = [
                articles_by_id[aid]
                for aid in group.get("article_ids", [])
                if aid in articles_by_id
            ]
            if not group_articles:
                group["cross_source_signals"] = []
                group["cross_source_verification"] = None
                continue

            verification = self.verify_related_articles(group_articles)
            group["cross_source_verification"] = verification
            group["independent_source_count"] = verification["independent_source_count"]
            group["independent_publishers_count"] = verification["independent_publishers_count"]
            group["number_of_independent_publishers"] = verification["number_of_independent_publishers"]
            group["supporting_reports"] = verification["supporting_reports"]
            group["supporting_reports_count"] = verification["supporting_reports_count"]
            group["number_of_supporting_reports"] = verification["number_of_supporting_reports"]
            group["conflicting_reports"] = verification["conflicting_reports"]
            group["conflicting_reports_count"] = verification["conflicting_reports_count"]
            group["possible_conflicting_reports"] = verification["possible_conflicting_reports"]
            group["single_source_stories"] = verification["single_source_stories"]
            group["single_source_story"] = verification["single_source_story"]
            group["is_single_source"] = verification["is_single_source"]
            group["source_metadata_completeness"] = verification["source_metadata_completeness"]
            group["missing_source_metadata"] = verification["missing_source_metadata"]
            group["time_of_first_report"] = verification["time_of_first_report"]
            group["earliest_available_publication_time"] = verification["earliest_available_publication_time"]
            group["earliest_publication_time"] = verification["earliest_publication_time"]
            group["time_of_latest_report"] = verification["time_of_latest_report"]
            group["latest_available_publication_time"] = verification["latest_available_publication_time"]
            group["latest_publication_time"] = verification["latest_publication_time"]
            group["cross_source_signals"] = verification["signals"]

        return groups

    def _analyze_group(self, articles):
        """Maintained for legacy compatibility with existing Step 11 tests."""
        publishers = {self._extract(a, "publisher") for a in articles if self._extract(a, "publisher")}
        count = len(publishers)
        signals = []

        all_ids = [self._extract(a, "article_id") for a in articles]
        signals.append({"signal": "independent_source_count", "value": count, "supporting_article_ids": all_ids})

        if count <= 1:
            signals.append({
                "signal": "insufficient_cross_source_evidence",
                "statement": "Limited independent reporting available.",
                "supporting_article_ids": all_ids,
            })
            return signals

        titles = {str(self._extract(a, "title")).lower().strip() for a in articles}
        if len(titles) == 1:
            signals.append({
                "signal": "same_story",
                "statement": "Multiple outlets syndicating same story.",
                "supporting_article_ids": all_ids,
            })
            return signals

        conflict_keywords = self.CONFLICT_KEYWORDS
        conflicting_ids = []
        for a in articles:
            text = ((self._extract(a, "title") or "") + " " + (self._extract(a, "description") or "")).lower()
            if any(word in text.split() for word in conflict_keywords):
                conflicting_ids.append(self._extract(a, "article_id"))

        if conflicting_ids:
            signals.append({
                "signal": "conflicting_reports",
                "statement": "Reports contain differing information.",
                "supporting_article_ids": conflicting_ids,
            })

        supporting_ids = [self._extract(a, "article_id") for a in articles if self._extract(a, "article_id") not in conflicting_ids]
        if len(supporting_ids) >= 1:
            signals.append({
                "signal": "supporting_reports",
                "statement": "Reported by multiple sources.",
                "supporting_article_ids": supporting_ids,
            })
        elif not conflicting_ids:
            signals.append({
                "signal": "supporting_reports",
                "statement": "Reported by multiple sources.",
                "supporting_article_ids": all_ids,
            })

        return signals
