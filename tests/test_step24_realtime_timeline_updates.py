import unittest
from tempfile import TemporaryDirectory

from app.models.article import Article
from app.services.provenance_service import ProvenanceService
from app.services.timeline_service import TimelineService, normalize_publication_date
from app import create_app
from app.repositories.article_repository import ArticleRepository
from app.services.search_orchestrator import SearchOrchestrator


class StubProvider:
    def __init__(self, articles=None):
        self.articles = articles or []

    def search(self, query):
        return list(self.articles)


class RealTimeTimelineUpdatesTestCase(unittest.TestCase):
    def setUp(self):
        self.service = TimelineService()
        self.provenance_service = ProvenanceService()

    def make_article(
        self,
        article_id,
        title,
        publication_date=None,
        url=None,
        publisher="Reuters",
        source_provider="gdelt",
        retrieved_at=None,
        description=None,
    ):
        return Article(
            article_id=article_id,
            title=title,
            url=url or f"https://example.com/article/{article_id}",
            publisher=publisher,
            publication_date=publication_date,
            source_provider=source_provider,
            retrieved_at=retrieved_at,
            description=description or f"Description for {title}",
        )

    def test_new_article_insertion(self):
        """New article is inserted into existing timeline, marking it updated/is_new without recreating existing entries."""
        initial_article = self.make_article(1, "Initial Event", "2026-09-10")
        existing_timeline = self.service.generate([initial_article], [])
        self.assertEqual(len(existing_timeline), 1)
        self.assertFalse(existing_timeline[0].get("updated", False))

        new_article = self.make_article(2, "Follow-up Event", "2026-09-12")
        updated = self.service.update_timeline(existing_timeline, [new_article])

        self.assertEqual(len(updated), 2)
        # Find entries
        initial_entry = next(e for e in updated if e["timeline_id"] == "article-1")
        new_entry = next(e for e in updated if e["timeline_id"] == "article-2")

        # Existing entry was not modified or marked updated
        self.assertFalse(initial_entry.get("updated", False))
        self.assertFalse(initial_entry.get("is_new", False))

        # New entry is marked updated and is_new
        self.assertTrue(new_entry.get("updated", False))
        self.assertTrue(new_entry.get("is_new", False))
        self.assertEqual(new_entry["title"], "Follow-up Event")
        self.assertEqual(new_entry["date"], "2026-09-12")
        self.assertEqual(new_entry["article_ids"], [2])

    def test_chronological_ordering(self):
        """Newly arrived articles are inserted into the exact chronological positions."""
        art_mid = self.make_article(1, "Mid Event", "2026-09-10")
        art_late = self.make_article(2, "Late Event", "2026-09-20")
        existing_timeline = self.service.generate([art_mid, art_late], [])

        # Add an article earlier than all existing, and another in between
        art_earliest = self.make_article(3, "Earliest Event", "2026-09-01")
        art_between = self.make_article(4, "Between Event", "2026-09-15")

        updated = self.service.update_timeline(existing_timeline, [art_between, art_earliest])

        self.assertEqual(len(updated), 4)
        dates = [entry["date"] for entry in updated]
        titles = [entry["title"] for entry in updated]

        self.assertEqual(dates, ["2026-09-01", "2026-09-10", "2026-09-15", "2026-09-20"])
        self.assertEqual(titles, ["Earliest Event", "Mid Event", "Between Event", "Late Event"])

    def test_duplicate_prevention(self):
        """Articles matching existing article IDs or canonical URLs are prevented from duplicating."""
        art1 = self.make_article(1, "Original Headline", "2026-09-10", url="https://example.com/news/tech?utm_source=rss")
        existing_timeline = self.service.generate([art1], [])
        self.assertEqual(len(existing_timeline), 1)

        # 1. Attempt duplicate by article_id
        dup_by_id = self.make_article(1, "Duplicate Headline by ID", "2026-09-10", url="https://different.org/url")

        # 2. Attempt duplicate by canonical URL with different tracking parameters
        dup_by_url = self.make_article(99, "Duplicate by URL", "2026-09-10", url="https://example.com/news/tech?utm_medium=twitter&fbclid=123")

        # 3. Two copies of a new article in the same incoming batch
        new_batch_1 = self.make_article(2, "New Unique Event", "2026-09-12", url="https://example.com/unique-2")
        new_batch_2 = self.make_article(2, "New Unique Event Copy", "2026-09-12", url="https://example.com/unique-2?utm_campaign=daily")

        updated = self.service.update_timeline(
            existing_timeline,
            [dup_by_id, dup_by_url, new_batch_1, new_batch_2],
        )

        # Only one new article should have been added
        self.assertEqual(len(updated), 2)
        article_ids_in_timeline = [e["article_ids"] for e in updated]
        self.assertIn([1], article_ids_in_timeline)
        self.assertIn([2], article_ids_in_timeline)

    def test_missing_dates(self):
        """Articles with missing or invalid publication dates are preserved separately, and retrieved_at is NEVER used as the event date."""
        art_dated = self.make_article(1, "Dated Story", "2026-09-10")
        existing_timeline = self.service.generate([art_dated], [])

        # Article with None publication date but with a retrieved_at timestamp
        art_none_date = self.make_article(
            2,
            "Story with Missing Date",
            publication_date=None,
            retrieved_at="2026-09-30T10:00:00Z",
        )

        # Article with unparseable date
        art_invalid_date = self.make_article(
            3,
            "Story with Invalid Date",
            publication_date="not-a-valid-date-format",
            retrieved_at="2026-09-30T10:00:00Z",
        )

        updated = self.service.update_timeline(
            existing_timeline,
            [art_none_date, art_invalid_date],
        )

        self.assertEqual(len(updated), 3)

        # First entry is the dated story
        self.assertEqual(updated[0]["timeline_id"], "article-1")
        self.assertEqual(updated[0]["date"], "2026-09-10")

        # Missing date entries are preserved separately at the end
        missing_entry_1 = next(e for e in updated if e["timeline_id"] == "article-2")
        missing_entry_2 = next(e for e in updated if e["timeline_id"] == "article-3")

        # retrieved_at must NEVER be used as the historical date
        self.assertIsNone(missing_entry_1["date"])
        self.assertIsNone(missing_entry_2["date"])
        self.assertNotEqual(missing_entry_1["date"], "2026-09-30")
        self.assertNotEqual(missing_entry_2["date"], "2026-09-30")

        # Verify they are positioned after all dated entries
        self.assertIsNone(updated[1]["date"])
        self.assertIsNone(updated[2]["date"])

    def test_group_updates(self):
        """When a new article belongs to an existing article group, the group entry is updated in-place."""
        art1 = self.make_article(1, "Initial Cluster Report", "2026-09-20")
        groups_initial = [{
            "group_id": "grp-100",
            "article_ids": [1],
            "representative_title": "Cluster Event",
        }]
        existing_timeline = self.service.generate([art1], groups_initial)
        self.assertEqual(len(existing_timeline), 1)
        self.assertEqual(existing_timeline[0]["date"], "2026-09-20")
        self.assertEqual(existing_timeline[0]["article_ids"], [1])

        # New article arrives belonging to grp-100 with an EARLIER date
        art2 = self.make_article(2, "Breaking Earlier Detail", "2026-09-15")
        groups_updated = [{
            "group_id": "grp-100",
            "article_ids": [1, 2],
            "representative_title": "Cluster Event",
        }]

        updated = self.service.update_timeline(
            existing_timeline,
            [art2],
            groups=groups_updated,
            all_articles=[art1, art2],
        )

        # Still 1 group entry, updated in-place
        self.assertEqual(len(updated), 1)
        group_entry = updated[0]

        self.assertEqual(group_entry["timeline_id"], "group-grp-100")
        self.assertEqual(group_entry["group_id"], "grp-100")
        self.assertEqual(group_entry["article_ids"], [1, 2])
        # Earliest date was updated to 2026-09-15
        self.assertEqual(group_entry["date"], "2026-09-15")
        self.assertTrue(group_entry["updated"])

        # Supporting articles contains both
        supporting_ids = [s["article_id"] for s in group_entry["supporting_articles"]]
        self.assertIn(1, supporting_ids)
        self.assertIn(2, supporting_ids)

    def test_provenance_preservation(self):
        """All existing provenance information is preserved when new articles arrive and update timeline groups."""
        art1 = self.make_article(1, "Primary Report", "2026-09-10", publisher="BBC News", source_provider="gdelt")
        groups = [{
            "group_id": "story-1",
            "article_ids": [1],
            "representative_title": "Primary Report",
        }]
        raw_timeline = self.service.generate([art1], groups)
        enriched_timeline = self.provenance_service.enrich_timeline(raw_timeline, [art1])

        # Verify initial provenance
        self.assertIn("supporting_sources", enriched_timeline[0])
        self.assertIn("provenance_signals", enriched_timeline[0])
        self.assertEqual(len(enriched_timeline[0]["supporting_sources"]), 1)
        self.assertEqual(enriched_timeline[0]["supporting_sources"][0]["publisher"], "BBC News")
        self.assertTrue(enriched_timeline[0]["publisher_identified"])

        # New article arrives from a different publisher
        art2 = self.make_article(2, "Corroborating Report", "2026-09-11", publisher="Reuters", source_provider="newsapi")
        updated_groups = [{
            "group_id": "story-1",
            "article_ids": [1, 2],
            "representative_title": "Primary Report",
        }]

        updated_timeline = self.service.update_timeline(
            enriched_timeline,
            [art2],
            groups=updated_groups,
            all_articles=[art1, art2],
        )

        self.assertEqual(len(updated_timeline), 1)
        entry = updated_timeline[0]

        # Provenance is preserved and enriched for the new source
        self.assertEqual(len(entry["supporting_sources"]), 2)
        publishers = [s["publisher"] for s in entry["supporting_sources"]]
        self.assertIn("BBC News", publishers)
        self.assertIn("Reuters", publishers)

        providers = [s["source_provider"] for s in entry["supporting_sources"]]
        self.assertIn("gdelt", providers)
        self.assertIn("newsapi", providers)

        # Collection signals updated
        self.assertTrue(entry["provenance_signals"]["multiple_sources_found"])
        self.assertEqual(entry["provenance_signals"]["independent_source_count"], 2)
        self.assertTrue(entry["multiple_sources_found"])
        self.assertEqual(entry["independent_source_count"], 2)
        self.assertTrue(entry["updated"])

    def test_search_endpoint_with_existing_timeline_updates_incrementally(self):
        """Integration test: /api/search accepts existing_timeline and returns updated entries."""
        temp_dir = TemporaryDirectory()
        db_path = f"{temp_dir.name}/test_step24.db"
        app = create_app({
            "TESTING": True,
            "NEWS_PROVIDER": "mock",
            "DATABASE_PATH": db_path,
        })
        client = app.test_client()

        with app.app_context():
            app.extensions["search_orchestrator"] = SearchOrchestrator(
                StubProvider([]),
                app.extensions["article_repository"],
                ai_provider=app.extensions.get("ai_provider"),
            )
            repo = app.extensions["article_repository"]
            repo.save_article(Article(
                title="Existing Historical Event",
                url="https://example.com/hist-1",
                publisher="Archive News",
                publication_date="2026-01-01",
                description="Summary 1",
                source_provider="mock",
            ))

            # First search builds initial timeline
            res1 = client.post("/api/search", json={"query": "Historical"})
            self.assertEqual(res1.status_code, 200)
            data1 = res1.get_json()
            initial_timeline = data1["timeline"]
            self.assertEqual(len(initial_timeline), 1)

            # Insert a new article into database (simulating fresh arrival)
            repo.save_article(Article(
                title="New Historical Event",
                url="https://example.com/hist-2",
                publisher="Live News",
                publication_date="2026-02-01",
                description="Summary 2",
                source_provider="mock",
            ))

            # Second search passes existing_timeline to simulate real-time refresh
            res2 = client.post(
                "/api/search",
                json={
                    "query": "Historical",
                    "existing_timeline": initial_timeline,
                },
            )
            self.assertEqual(res2.status_code, 200)
            data2 = res2.get_json()
            updated_timeline = data2["timeline"]

            # The new related article updates the existing cluster entry in-place
            self.assertEqual(len(updated_timeline), 1)
            group_entry = updated_timeline[0]
            self.assertEqual(group_entry["article_ids"], [1, 2])
            self.assertTrue(group_entry["updated"])
            self.assertEqual(len(group_entry["supporting_articles"]), 2)
            self.assertEqual(len(group_entry["supporting_sources"]), 2)

            # Now insert a distinct, unrelated article matching the same query
            repo.save_article(Article(
                title="Historical Artifact Discovered Underwater",
                url="https://example.com/hist-3",
                publisher="Oceanic News",
                publication_date="2026-03-01",
                description="Deep sea discovery",
                source_provider="mock",
            ))

            res3 = client.post(
                "/api/search",
                json={
                    "query": "Historical",
                    "existing_timeline": updated_timeline,
                },
            )
            self.assertEqual(res3.status_code, 200)
            data3 = res3.get_json()
            final_timeline = data3["timeline"]

            self.assertEqual(len(final_timeline), 2)
            distinct_entry = next(e for e in final_timeline if any("hist-3" in s.get("url", "") for s in e.get("supporting_articles", [])))
            self.assertTrue(distinct_entry["updated"])
            self.assertTrue(distinct_entry["is_new"])

        temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
