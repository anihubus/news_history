import unittest

from app.providers.ai_provider import AIProvider, AIProviderError, MockAIProvider
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


class HallucinatingAIProvider(AIProvider):
    name = "hallucinating_mock"

    def summarize(self, instruction, context):
        return "Summary"

    def answer(self, instruction, context, question):
        # Returns legitimate ID 1 and hallucinated/fabricated ID 9999
        return {
            "answer": "Fabricated claim about nonexistent source.",
            "supporting_article_ids": [1, 9999],
        }


class QuestionAnswerServiceTestCase(unittest.TestCase):
    def test_receives_context_and_returns_supporting_ids(self):
        provider = RecordingAIProvider()
        context = {
            "query": "technology",
            "articles": [{"article_id": 7, "title": "Technology"}],
            "groups": [],
            "timeline": []
        }

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
        self.assertEqual(result["supporting_article_ids"], [])

    def test_supporting_evidence_question(self):
        context = {
            "articles": [
                {"article_id": 1, "title": "Summit Opens", "publisher": "Global News"},
                {"article_id": 2, "title": "Leaders Convene", "publisher": "Daily Wire"},
            ],
            "supporting_references": [
                {"article_id": 1, "title": "Summit Opens", "publisher": "Global News"},
                {"article_id": 2, "title": "Leaders Convene", "publisher": "Daily Wire"},
            ],
            "conflicting_references": [],
            "conflicting_article_ids": [],
        }

        result = QuestionAnswerService(MockAIProvider()).answer("Which articles support this event?", context)

        self.assertTrue(result["success"])
        self.assertIn("supported by 2 article(s)", result["answer"])
        self.assertIn("Summit Opens", result["answer"])
        self.assertEqual(sorted(result["supporting_article_ids"]), [1, 2])

    def test_conflicting_evidence_question(self):
        context = {
            "articles": [
                {"article_id": 1, "title": "Accord signed", "publisher": "Publisher A", "description": "Parties sign accord."},
                {"article_id": 2, "title": "Accord dispute", "publisher": "Publisher B", "description": "Opponents dispute accord was signed."},
            ],
            "conflicting_references": [
                {"article_id": 2, "title": "Accord dispute", "publisher": "Publisher B"}
            ],
            "conflicting_article_ids": [2],
            "verification_warnings": [
                {"type": "conflicting_reports", "severity": "warning", "explanation": "Some reports contain differing information.", "supporting_article_ids": [2]}
            ],
        }

        result = QuestionAnswerService(MockAIProvider()).answer("Are there conflicting reports?", context)

        self.assertTrue(result["success"])
        self.assertIn("differing information", result["answer"])
        self.assertIn("Accord dispute", result["answer"])
        self.assertIn(2, result["supporting_article_ids"])

    def test_no_conflicting_evidence_question(self):
        context = {
            "articles": [
                {"article_id": 1, "title": "Accord signed", "publisher": "Publisher A", "description": "Official signing."},
                {"article_id": 2, "title": "Accord confirmed", "publisher": "Publisher B", "description": "Confirmed by all."},
            ],
            "conflicting_references": [],
            "conflicting_article_ids": [],
        }

        result = QuestionAnswerService(MockAIProvider()).answer("Are there conflicting reports?", context)

        self.assertTrue(result["success"])
        self.assertIn("No conflicting reports were found", result["answer"])
        self.assertEqual(sorted(result["supporting_article_ids"]), [1, 2])

    def test_source_count_question(self):
        context = {
            "articles": [
                {"article_id": 10, "title": "First Report", "publisher": "Times Hub"},
                {"article_id": 11, "title": "Second Report", "publisher": "Chronicle"},
            ],
        }

        result = QuestionAnswerService(MockAIProvider()).answer("How many sources reported this?", context)

        self.assertTrue(result["success"])
        self.assertIn("2 article(s) from 2 independent source(s)", result["answer"])
        self.assertIn("Chronicle", result["answer"])
        self.assertIn("Times Hub", result["answer"])
        self.assertEqual(sorted(result["supporting_article_ids"]), [10, 11])

    def test_flagged_limited_evidence_question(self):
        context = {
            "articles": [
                {"article_id": 5, "title": "Single source leak", "publisher": "Sole Publisher"}
            ],
            "verification_warnings": [
                {
                    "type": "single_source_only",
                    "severity": "warning",
                    "explanation": "Limited independent reporting is currently available.",
                    "supporting_article_ids": [5],
                }
            ],
        }

        result = QuestionAnswerService(MockAIProvider()).answer("Why is this story flagged for limited evidence?", context)

        self.assertTrue(result["success"])
        self.assertIn("flagged for limited evidence", result["answer"])
        self.assertIn("Limited independent reporting is currently available.", result["answer"])
        self.assertEqual(result["supporting_article_ids"], [5])

    def test_insufficient_evidence_unrelated_query(self):
        context = {
            "articles": [
                {"article_id": 1, "title": "Local municipal budget passed", "description": "City council approves budget.", "publisher": "City News"}
            ],
            "query": "local budget",
        }

        result = QuestionAnswerService(MockAIProvider()).answer("What did astronauts find on Mars?", context)

        self.assertTrue(result["success"])
        self.assertIn("do not provide enough information", result["answer"])
        self.assertEqual(result["supporting_article_ids"], [])

    def test_fabricated_source_prevention(self):
        provider = HallucinatingAIProvider()
        context = {
            "articles": [
                {"article_id": 1, "title": "Real article", "publisher": "Real Outlet"}
            ]
        }

        result = QuestionAnswerService(provider).answer("What sources exist?", context)

        self.assertTrue(result["success"])
        # Only article 1 should be included, article 9999 was fabricated by the provider and MUST be stripped
        self.assertIn(1, result["supporting_article_ids"])
        self.assertNotIn(9999, result["supporting_article_ids"])
        self.assertEqual(result["supporting_article_ids"], [1])

    def test_source_attribution_and_neutrality_guardrail(self):
        context = {
            "articles": [
                {"article_id": 3, "title": "Unverified rumor", "publisher": "Forum Blog"}
            ],
            "verification_warnings": [
                {"type": "single_source_only", "explanation": "Limited independent reporting is currently available."}
            ]
        }

        result = QuestionAnswerService(MockAIProvider()).answer("Is this article fake or true?", context)

        self.assertTrue(result["success"])
        self.assertIn("do not establish whether this reporting is definitely true or definitely fake", result["answer"])
        self.assertEqual(result["supporting_article_ids"], [3])


if __name__ == "__main__":
    unittest.main()
