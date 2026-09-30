from app.services.article_retrieval_service import ArticleRetrievalService
from app.services.article_grouping_service import ArticleGroupingService
from app.services.timeline_service import TimelineService
from app.services.context_builder import ContextBuilder
from app.services.summary_service import SummaryService
from app.services.question_answer_service import QuestionAnswerService
from app.services.provenance_service import ProvenanceService
from app.services.cross_source_service import CrossSourceService
from app.services.verification_signal_service import VerificationSignalService


class SearchOrchestrator:
    """Coordinate search validation and provider retrieval."""

    def __init__(self, search_service, article_repository, result_limit=20, relationship_threshold=0.30, ai_provider=None):
        self.search_service = search_service
        self.article_repository = article_repository
        self.retrieval_service = ArticleRetrievalService(
            article_repository,
            search_service,
            result_limit=result_limit,
        )
        self.grouping_service = ArticleGroupingService(
            article_repository,
            threshold=relationship_threshold,
        )
        self.timeline_service = TimelineService()
        self.context_builder = ContextBuilder()
        self.summary_service = SummaryService(ai_provider) if ai_provider else None
        self.question_answer_service = QuestionAnswerService(ai_provider) if ai_provider else None
        self.provenance_service = ProvenanceService()
        self.cross_source_service = CrossSourceService()
        self.verification_service = VerificationSignalService()

    def search(self, query):
        if not isinstance(query, str) or not query.strip():
            return {
                "success": False,
                "error": "Search query cannot be empty.",
            }

        normalized_query = query.strip()
        retrieval = self.retrieval_service.search(normalized_query)
        grouping = self.grouping_service.group_articles(retrieval.articles)
        grouping["groups"] = self.cross_source_service.analyze_groups(
            grouping["groups"], retrieval.articles
        )
        timeline = self.timeline_service.generate(
            retrieval.articles,
            grouping["groups"],
        )
        summaries = self.summary_service.generate(
            normalized_query,
            retrieval.articles,
            grouping["groups"],
            timeline,
        ) if self.summary_service else []
        enriched_groups = self.provenance_service.enrich_groups(
            grouping["groups"], retrieval.articles
        )
        enriched_timeline = self.provenance_service.enrich_timeline(
            timeline, retrieval.articles
        )
        enriched_summaries = self.provenance_service.enrich_summaries(
            summaries, retrieval.articles
        )

        overall_signals = self.provenance_service.collection_signals(retrieval.articles)
        enriched_groups = self.verification_service.enrich_groups(
            enriched_groups, retrieval.articles
        )
        enriched_timeline = self.verification_service.enrich_timeline(
            enriched_timeline, retrieval.articles
        )
        topic_warnings = self.verification_service.analyze_articles(retrieval.articles)

        if retrieval.provider_status != "ok" and not retrieval.articles:
            return {
                "success": False,
                "status": retrieval.provider_status,
                "query": normalized_query,
                "results": [],
                "groups": enriched_groups,
                "relationships": grouping["relationships"],
                "timeline": enriched_timeline,
                "summary": self._topic_summary(enriched_summaries),
                "group_summaries": self._group_summaries(enriched_summaries),
                "provenance_signals": overall_signals,
                "verification_signals": [],
                "warning_signals": [],
                "error": retrieval.provider_error,
            }

        results_payload = []
        for article in retrieval.articles:
            payload = self.provenance_service.article_payload(article)
            signals = self.verification_service.analyze_article(article)
            payload["verification_signals"] = signals
            payload["warning_signals"] = signals
            results_payload.append(payload)

        result = {
            "success": True,
            "query": normalized_query,
            "results": results_payload,
            "message": None,
            "provider_status": retrieval.provider_status,
            "groups": enriched_groups,
            "relationships": grouping["relationships"],
            "timeline": enriched_timeline,
            "summary": self._topic_summary(enriched_summaries),
            "group_summaries": self._group_summaries(enriched_summaries),
            "provenance_signals": overall_signals,
            "verification_signals": topic_warnings,
            "warning_signals": topic_warnings,
        }
        if retrieval.provider_error:
            result["message"] = retrieval.provider_error
        return result

    @staticmethod
    def _topic_summary(summaries):
        return next((summary for summary in summaries if summary["summary_type"] == "topic"), None)

    @staticmethod
    def _group_summaries(summaries):
        return [summary for summary in summaries if summary["summary_type"] == "group"]

    def answer_question(self, question, query):
        normalized_query = (query or "").strip()
        rows = self.article_repository.search_articles(normalized_query) if normalized_query else []
        articles = [self.retrieval_service._article_from_row(row) for row in rows]
        grouping = self.grouping_service.group_articles(articles)
        timeline = self.timeline_service.generate(articles, grouping["groups"])
        context = self.context_builder.build(normalized_query, articles, grouping["groups"], timeline)
        answer = self.question_answer_service.answer(question, context)
        return self.provenance_service.enrich_answer(answer, articles)
