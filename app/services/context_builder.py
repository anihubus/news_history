from app.services.provenance_service import ProvenanceService
from app.services.cross_source_service import CrossSourceService
from app.services.verification_signal_service import VerificationSignalService


class ContextBuilder:
    """Build the explicit evidence context passed to grounded services."""

    def __init__(self, provenance_service=None, cross_source_service=None, verification_service=None):
        self.provenance_service = provenance_service or ProvenanceService()
        self.cross_source_service = cross_source_service or CrossSourceService()
        self.verification_service = verification_service or VerificationSignalService()

    @staticmethod
    def _extract(item, field):
        if isinstance(item, dict):
            return item.get(field)
        return getattr(item, field, None)

    def _article_context(self, article):
        ref = self.provenance_service.article_reference(article)
        ref["description"] = self._extract(article, "description")
        ref["verification_signals"] = self.verification_service.analyze_article(article)
        return ref

    def build(
        self,
        query,
        articles,
        groups=None,
        timeline=None,
        provenance_signals=None,
        cross_source_signals=None,
        verification_signals=None,
    ):
        articles = list(articles or [])
        groups = list(groups or [])
        timeline = list(timeline or [])

        # 1. Provenance information
        if provenance_signals is not None:
            prov_signals = provenance_signals
        else:
            prov_signals = self.provenance_service.collection_signals(articles)

        # 2. Verification warnings
        if verification_signals is not None:
            verif_signals = verification_signals
        else:
            verif_signals = self.verification_service.analyze_articles(articles)

        # 3. Cross-source signals
        if cross_source_signals is not None:
            cs_signals = cross_source_signals
        else:
            cs_signals = []
            if groups:
                analyzed_groups = self.cross_source_service.analyze_groups(
                    [dict(g) for g in groups], articles
                )
                for g in analyzed_groups:
                    cs_signals.extend(g.get("cross_source_signals", []))

        # 4. Supporting and conflicting article references
        articles_by_id = {
            self._extract(a, "article_id"): a
            for a in articles
            if self._extract(a, "article_id") is not None
        }

        conflicting_ids = set()
        for sig in verif_signals:
            if sig.get("type") == "conflicting_reports":
                conflicting_ids.update(sig.get("supporting_article_ids", []))
        for sig in cs_signals:
            if sig.get("signal") == "conflicting_reports":
                conflicting_ids.update(sig.get("supporting_article_ids", []))

        conflicting_references = [
            self.provenance_service.article_reference(articles_by_id[aid])
            for aid in sorted(conflicting_ids)
            if aid in articles_by_id
        ]

        supporting_ids = [aid for aid in articles_by_id if aid not in conflicting_ids]
        supporting_references = [
            self.provenance_service.article_reference(articles_by_id[aid])
            for aid in sorted(supporting_ids)
        ]

        return {
            "query": query,
            "articles": [self._article_context(article) for article in articles],
            "groups": groups,
            "timeline": timeline,
            "provenance_signals": prov_signals,
            "cross_source_signals": cs_signals,
            "verification_signals": verif_signals,
            "verification_warnings": verif_signals,
            "supporting_references": supporting_references,
            "conflicting_references": conflicting_references,
            "supporting_article_ids": supporting_ids,
            "conflicting_article_ids": sorted(list(conflicting_ids)),
        }
