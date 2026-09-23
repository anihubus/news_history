import unittest

from app.models.article import Article
from app.providers.ai_provider import AIProviderError, MockAIProvider
from app.services.summary_service import SummaryService


class FailingAIProvider(MockAIProvider):
    def summarize(self, instruction, context):
        raise AIProviderError("unavailable")


class SummaryServiceTestCase(unittest.TestCase):
    def articles(self):
        return [
            Article("Technology update", "https://example.com/1", "Example", "20260918", "A reported update.", "mock", 1),
            Article("Technology analysis", "https://example.com/2", "Example", "20260917", None, "mock", 2),
        ]

    def test_mock_provider_returns_deterministic_topic_summary(self):
        summaries = SummaryService(MockAIProvider()).generate("technology", self.articles(), [], [])

        self.assertEqual(summaries[0]["summary_type"], "topic")
        self.assertEqual(summaries[0]["supporting_article_ids"], [1, 2])
        self.assertTrue(summaries[0]["automatic"])
        self.assertEqual(summaries[0]["provider"], "mock")

    def test_group_summary_uses_group_article_ids(self):
        group = {"group_id": "5", "article_ids": [1, 2], "article_count": 2, "representative_title": "Technology"}

        summaries = SummaryService(MockAIProvider()).generate("technology", self.articles(), [group], [])

        group_summary = next(summary for summary in summaries if summary["summary_type"] == "group")
        self.assertEqual(group_summary["supporting_article_ids"], [1, 2])
        self.assertEqual(group_summary["group_id"], "5")

    def test_timeline_summary_uses_supplied_timeline(self):
        timeline = [{"article_ids": [1, 2], "title": "Technology development"}]

        summaries = SummaryService(MockAIProvider()).generate("technology", self.articles(), [], timeline)

        self.assertTrue(any(summary["summary_type"] == "timeline" for summary in summaries))

    def test_provider_failure_does_not_raise(self):
        summaries = SummaryService(FailingAIProvider()).generate("technology", self.articles(), [], [])

        self.assertEqual(summaries, [])


if __name__ == "__main__":
    unittest.main()
