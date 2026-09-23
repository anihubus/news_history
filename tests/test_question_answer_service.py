import unittest

from app.providers.ai_provider import AIProviderError, MockAIProvider
from app.services.question_answer_service import QuestionAnswerService


class RecordingAIProvider(MockAIProvider):
    def __init__(self):
        self.received_context = None

    def answer(self, instruction, context, question):
        self.received_context = context
        return super().answer(instruction, context, question)


class FailingAIProvider(MockAIProvider):
    def answer(self, instruction, context, question):
        raise AIProviderError("unavailable")


class QuestionAnswerServiceTestCase(unittest.TestCase):
    def test_receives_context_and_returns_supporting_ids(self):
        provider = RecordingAIProvider()
        context = {"query": "technology", "articles": [{"article_id": 7, "title": "Technology"}], "groups": [], "timeline": []}

        result = QuestionAnswerService(provider).answer("What is covered?", context)

        self.assertTrue(result["success"])
        self.assertEqual(provider.received_context, context)
        self.assertEqual(result["supporting_article_ids"], [7])

    def test_empty_question_is_rejected(self):
        result = QuestionAnswerService(MockAIProvider()).answer("  ", {})

        self.assertFalse(result["success"])
        self.assertEqual(result["supporting_article_ids"], [])

    def test_provider_failure_is_controlled(self):
        result = QuestionAnswerService(FailingAIProvider()).answer("What happened?", {})

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Answer temporarily unavailable.")

    def test_unsupported_context_returns_safe_answer(self):
        result = QuestionAnswerService(MockAIProvider()).answer("Unsupported?", {"articles": []})

        self.assertTrue(result["success"])
        self.assertIn("do not provide enough information", result["answer"])


if __name__ == "__main__":
    unittest.main()
