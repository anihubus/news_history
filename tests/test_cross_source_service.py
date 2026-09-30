import unittest
from app.services.cross_source_service import CrossSourceService
from app.models.article import Article

class CrossSourceServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.service = CrossSourceService()

    def test_insufficient_evidence_single_source(self):
        articles = [
            Article(title="Event happens", url="http://a.com/1", publisher="Publisher A", publication_date=None, description="Test", source_provider="mock", article_id=1)
        ]
        signals = self.service._analyze_group(articles)
        self.assertEqual(len(signals), 2)
        self.assertEqual(signals[0]["signal"], "independent_source_count")
        self.assertEqual(signals[0]["value"], 1)
        self.assertEqual(signals[1]["signal"], "insufficient_cross_source_evidence")

    def test_duplicate_sources_insufficient_evidence(self):
        articles = [
            Article(title="Event happens", url="http://a.com/1", publisher="Publisher A", publication_date=None, description="Test", source_provider="mock", article_id=1),
            Article(title="More on event", url="http://a.com/2", publisher="Publisher A", publication_date=None, description="Test", source_provider="mock", article_id=2)
        ]
        signals = self.service._analyze_group(articles)
        self.assertEqual(len(signals), 2)
        self.assertEqual(signals[0]["signal"], "independent_source_count")
        self.assertEqual(signals[0]["value"], 1)
        self.assertEqual(signals[1]["signal"], "insufficient_cross_source_evidence")

    def test_same_story_exact_title(self):
        articles = [
            Article(title="Event happens", url="http://a.com/1", publisher="Publisher A", publication_date=None, description="Test", source_provider="mock", article_id=1),
            Article(title="Event happens", url="http://b.com/2", publisher="Publisher B", publication_date=None, description="Test", source_provider="mock", article_id=2)
        ]
        signals = self.service._analyze_group(articles)
        self.assertEqual(len(signals), 2)
        self.assertEqual(signals[0]["signal"], "independent_source_count")
        self.assertEqual(signals[0]["value"], 2)
        self.assertEqual(signals[1]["signal"], "same_story")

    def test_multiple_sources_supporting(self):
        articles = [
            Article(title="Event happens", url="http://a.com/1", publisher="Publisher A", publication_date=None, description="It was a great success.", source_provider="mock", article_id=1),
            Article(title="Big event occurred", url="http://b.com/2", publisher="Publisher B", publication_date=None, description="People were happy.", source_provider="mock", article_id=2)
        ]
        signals = self.service._analyze_group(articles)
        self.assertEqual(len(signals), 2)
        self.assertEqual(signals[0]["signal"], "independent_source_count")
        self.assertEqual(signals[0]["value"], 2)
        self.assertEqual(signals[1]["signal"], "supporting_reports")

    def test_conflicting_descriptions(self):
        articles = [
            Article(title="Event happens", url="http://a.com/1", publisher="Publisher A", publication_date=None, description="It was a great success.", source_provider="mock", article_id=1),
            Article(title="Big event occurred", url="http://b.com/2", publisher="Publisher B", publication_date=None, description="Official denies it happened.", source_provider="mock", article_id=2)
        ]
        signals = self.service._analyze_group(articles)
        self.assertEqual(len(signals), 3)
        self.assertEqual(signals[0]["signal"], "independent_source_count")
        self.assertEqual(signals[0]["value"], 2)
        
        signal_names = [s["signal"] for s in signals]
        self.assertIn("conflicting_reports", signal_names)
        self.assertIn("supporting_reports", signal_names)
        
        # Publisher B should be in conflicting, Publisher A in supporting
        conflicting = next(s for s in signals if s["signal"] == "conflicting_reports")
        self.assertEqual(conflicting["supporting_article_ids"], [2])
        
        supporting = next(s for s in signals if s["signal"] == "supporting_reports")
        self.assertEqual(supporting["supporting_article_ids"], [1])

if __name__ == "__main__":
    unittest.main()
