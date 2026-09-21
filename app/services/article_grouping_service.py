from collections import Counter, defaultdict
from dataclasses import dataclass

from app.repositories.article_repository import canonicalize_url
from app.services.text_normalizer import normalize_text


@dataclass(frozen=True)
class Relationship:
    article_id: int
    related_article_id: int
    similarity: float
    relationship: str
    reason: str

    def to_dict(self):
        return {
            "article_id": self.article_id,
            "related_article_id": self.related_article_id,
            "similarity": self.similarity,
            "relationship": self.relationship,
            "reason": self.reason,
        }


class ArticleGroupingService:
    """Create explainable related-article groups with weighted token overlap."""

    def __init__(self, article_repository, threshold=0.30):
        self.article_repository = article_repository
        self.threshold = threshold

    def group_articles(self, articles):
        relationships = []
        adjacency = defaultdict(set)
        keyword_sets = {article.article_id: self._keywords(article) for article in articles}

        for index, article in enumerate(articles):
            for related_article in articles[index + 1 :]:
                if article.article_id is None or related_article.article_id is None:
                    continue
                similarity = self._similarity(
                    keyword_sets[article.article_id],
                    keyword_sets[related_article.article_id],
                )
                if similarity >= self.threshold:
                    relationship = Relationship(
                        article_id=article.article_id,
                        related_article_id=related_article.article_id,
                        similarity=similarity,
                        relationship="related",
                        reason="Shared weighted keywords",
                    )
                    relationships.append(relationship)
                    adjacency[article.article_id].add(related_article.article_id)
                    adjacency[related_article.article_id].add(article.article_id)
                    self.article_repository.save_relationship(
                        article.article_id,
                        related_article.article_id,
                        similarity,
                        relationship.reason,
                    )

        groups = self._build_groups(articles, adjacency, relationships)
        return {"groups": groups, "relationships": [item.to_dict() for item in relationships]}

    def _keywords(self, article):
        title_tokens = normalize_text(article.title)
        description_tokens = normalize_text(article.description)
        return Counter({token: 2 for token in title_tokens}) + Counter(description_tokens)

    @staticmethod
    def _similarity(left, right):
        shared = set(left) & set(right)
        union = set(left) | set(right)
        if not union:
            return 0.0
        weighted_shared = sum(min(left[token], right[token]) for token in shared)
        weighted_total = sum(max(left[token], right[token]) for token in union)
        return round(weighted_shared / weighted_total, 4)

    def _build_groups(self, articles, adjacency, relationships):
        articles_by_id = {article.article_id: article for article in articles}
        relationship_map = defaultdict(list)
        for relationship in relationships:
            relationship_map[relationship.article_id].append(relationship.to_dict())
            relationship_map[relationship.related_article_id].append(relationship.to_dict())

        groups = []
        visited = set()
        for article in articles:
            if article.article_id in visited:
                continue
            component = self._component(article.article_id, adjacency, visited)
            component_articles = [articles_by_id[item] for item in component]
            representative = min(
                component_articles,
                key=lambda item: (item.publication_date is None, item.publication_date or "", canonicalize_url(item.url)),
            )
            group_id = self.article_repository.save_group(
                sorted(component),
                representative.article_id,
                representative.title,
            )
            groups.append(
                {
                    "group_id": str(group_id),
                    "article_ids": sorted(component),
                    "article_count": len(component),
                    "representative_title": representative.title,
                    "relationships": [
                        relationship
                        for relationship in relationships
                        if relationship.article_id in component and relationship.related_article_id in component
                        for relationship in [relationship.to_dict()]
                    ],
                    "automatic": True,
                }
            )
        return groups

    @staticmethod
    def _component(start, adjacency, visited):
        stack = [start]
        component = []
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            component.append(current)
            stack.extend(adjacency[current] - visited)
        return component
