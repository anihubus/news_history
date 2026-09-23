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


if __name__ == "__main__":
    unittest.main()
