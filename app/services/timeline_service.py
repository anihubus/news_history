from dataclasses import dataclass
from datetime import datetime

from app.repositories.article_repository import canonicalize_url


@dataclass(frozen=True)
class TimelineEntry:
    timeline_id: str
    date: str | None
    title: str
    description: str | None
    article_ids: list[int]
    group_id: str | None
    automatic: bool
    supporting_articles: list[dict]

    def to_dict(self):
        return {
            "timeline_id": self.timeline_id,
            "date": self.date,
            "title": self.title,
            "description": self.description,
            "article_ids": self.article_ids,
            "group_id": self.group_id,
            "automatic": self.automatic,
            "supporting_articles": self.supporting_articles,
        }


def normalize_publication_date(value):
    if not value or not isinstance(value, str):
        return None

    candidates = ("%Y%m%d%H%M%S", "%Y%m%d", "%Y-%m-%d")
    for date_format in candidates:
        try:
            return datetime.strptime(value, date_format).date().isoformat()
        except ValueError:
            continue

    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).date().isoformat()
    except ValueError:
        return None


class TimelineService:
    """Build an automatically assembled timeline from articles and groups."""

    def generate(self, articles, groups):
        articles_by_id = {article.article_id: article for article in articles if article.article_id is not None}
        grouped_ids = set()
        entries = []

        for group in groups:
            article_ids = [article_id for article_id in group.get("article_ids", []) if article_id in articles_by_id]
            if not article_ids:
                continue
            grouped_ids.update(article_ids)
            group_articles = [articles_by_id[article_id] for article_id in article_ids]
            date = self._earliest_date(group_articles)
            representative = self._article_by_id(group_articles, group.get("article_ids", []))
            entries.append(
                TimelineEntry(
                    timeline_id=f"group-{group['group_id']}",
                    date=date,
                    title=group.get("representative_title") or representative.title,
                    description=self._description(group_articles),
                    article_ids=sorted(article_ids),
                    group_id=str(group["group_id"]),
                    automatic=True,
                    supporting_articles=self._supporting_articles(group_articles),
                )
            )

        for article in articles:
            if article.article_id is None or article.article_id in grouped_ids:
                continue
            entries.append(
                TimelineEntry(
                    timeline_id=f"article-{article.article_id}",
                    date=normalize_publication_date(article.publication_date),
                    title=article.title,
                    description=article.description,
                    article_ids=[article.article_id],
                    group_id=None,
                    automatic=True,
                    supporting_articles=self._supporting_articles([article]),
                )
            )

        return [entry.to_dict() for entry in sorted(entries, key=self._sort_key)]

    @staticmethod
    def _earliest_date(articles):
        dates = [normalize_publication_date(article.publication_date) for article in articles]
        valid_dates = [date for date in dates if date]
        return min(valid_dates) if valid_dates else None

    @staticmethod
    def _article_by_id(articles, ordered_ids):
        articles_by_id = {article.article_id: article for article in articles}
        for article_id in ordered_ids:
            if article_id in articles_by_id:
                return articles_by_id[article_id]
        return articles[0]

    @staticmethod
    def _description(articles):
        for article in articles:
            if article.description:
                return article.description
        return None

    @staticmethod
    def _supporting_articles(articles):
        unique = {}
        for article in articles:
            unique[canonicalize_url(article.url)] = {
                "article_id": article.article_id,
                "title": article.title,
                "url": article.url,
            }
        return list(unique.values())

    @staticmethod
    def _sort_key(entry):
        return (entry.date is None, entry.date or "", entry.timeline_id)
