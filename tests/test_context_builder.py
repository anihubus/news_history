import unittest

from app.models.article import Article
from app.services.context_builder import ContextBuilder


class ContextBuilderTestCase(unittest.TestCase):
    def test_builds_structured_grounded_context(self):
        article = Article("A title", "https://example.com/a", "Example", "20260918", "A description", "mock", 4)

        context = ContextBuilder().build("technology", [article], [{"group_id": "1"}], [{"article_ids": [4]}])

        self.assertEqual(context["query"], "technology")
        self.assertEqual(context["articles"][0]["article_id"], 4)
        self.assertEqual(context["articles"][0]["description"], "A description")
        self.assertEqual(context["groups"], [{"group_id": "1"}])
        self.assertEqual(context["timeline"], [{"article_ids": [4]}])
        self.assertIn("provenance_signals", context)
        self.assertIn("verification_warnings", context)
        self.assertIn("supporting_references", context)
        self.assertIn("conflicting_references", context)

    def test_context_includes_supporting_and_conflicting_references(self):
        art1 = Article("Conference held", "https://a.com/1", "Publisher A", "2026-09-01", "Leaders held summit.", "mock", 1)
        art2 = Article("Summit denied", "https://b.com/2", "Publisher B", "2026-09-02", "Officials dispute the summit took place.", "mock", 2)

        context = ContextBuilder().build("summit", [art1, art2], [], [])

        self.assertEqual(len(context["conflicting_references"]), 1)
        self.assertEqual(context["conflicting_references"][0]["article_id"], 2)
        self.assertEqual(len(context["supporting_references"]), 1)
        self.assertEqual(context["supporting_references"][0]["article_id"], 1)
        self.assertEqual(context["conflicting_article_ids"], [2])
        self.assertEqual(context["supporting_article_ids"], [1])


if __name__ == "__main__":
    unittest.main()
