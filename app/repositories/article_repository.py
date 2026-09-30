import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.models.article import Article


_TRACKING_PARAMETERS = {"fbclid", "gclid", "dclid", "mc_cid", "mc_eid"}


def canonicalize_url(url):
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    hostname = (parts.hostname or "").lower()

    if not scheme or not hostname:
        return url.strip()

    try:
        port = parts.port
    except ValueError:
        port = None

    netloc = hostname
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{hostname}:{port}"

    query_items = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_PARAMETERS
    ]
    normalized_query = urlencode(sorted(query_items))
    path = parts.path or "/"

    return urlunsplit((scheme, netloc, path, normalized_query, ""))


class ArticleRepository:
    def __init__(self, database_path):
        self.database_path = database_path

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    def save_article(self, article, retrieved_at=None):
        retrieved_at = retrieved_at or self._timestamp()
        created_at = self._timestamp()
        canonical_url = canonicalize_url(article.url)

        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO articles (
                    title, url, canonical_url, publisher, publication_date,
                    description, source_provider, retrieved_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(canonical_url) DO UPDATE SET
                    retrieved_at = excluded.retrieved_at,
                    description = COALESCE(description, excluded.description),
                    publisher = COALESCE(publisher, excluded.publisher),
                    publication_date = COALESCE(publication_date, excluded.publication_date)
                """,
                (
                    article.title,
                    article.url,
                    canonical_url,
                    article.publisher,
                    article.publication_date,
                    article.description,
                    article.source_provider,
                    retrieved_at,
                    created_at,
                ),
            )
            row = connection.execute(
                "SELECT * FROM articles WHERE canonical_url = ?",
                (canonical_url,),
            ).fetchone()
            connection.commit()

        return dict(row)

    def save_articles(self, articles, retrieved_at=None):
        return [self.save_article(article, retrieved_at=retrieved_at) for article in articles]

    def get_articles_by_canonical_urls(self, urls):
        canonical_urls = [canonicalize_url(url) for url in urls]
        if not canonical_urls:
            return []

        placeholders = ", ".join("?" for _ in canonical_urls)
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM articles WHERE canonical_url IN ({placeholders})",
                canonical_urls,
            ).fetchall()
        return [dict(row) for row in rows]

    def save_relationship(self, article_id, related_article_id, similarity_score, reason):
        created_at = self._timestamp()
        first_id, second_id = sorted((article_id, related_article_id))
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO article_relationships (
                    article_id, related_article_id, similarity_score,
                    relationship_type, reason, created_at
                ) VALUES (?, ?, ?, 'related', ?, ?)
                ON CONFLICT(article_id, related_article_id) DO UPDATE SET
                    similarity_score = excluded.similarity_score,
                    reason = excluded.reason
                """,
                (first_id, second_id, similarity_score, reason, created_at),
            )
            connection.commit()

    def save_group(self, article_ids, representative_article_id, representative_title):
        created_at = self._timestamp()
        with self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO article_groups (
                    representative_article_id, representative_title, created_at
                ) VALUES (?, ?, ?)
                """,
                (representative_article_id, representative_title, created_at),
            )
            group_id = cursor.lastrowid
            connection.executemany(
                "INSERT INTO article_group_members (group_id, article_id) VALUES (?, ?)",
                [(group_id, article_id) for article_id in article_ids],
            )
            connection.commit()
        return group_id

    def get_groups(self):
        with self._connection() as connection:
            groups = connection.execute("SELECT * FROM article_groups ORDER BY id").fetchall()
            result = []
            for group in groups:
                members = connection.execute(
                    "SELECT article_id FROM article_group_members WHERE group_id = ? ORDER BY article_id",
                    (group["id"],),
                ).fetchall()
                result.append(
                    {
                        **dict(group),
                        "article_ids": [member["article_id"] for member in members],
                    }
                )
        return result

    def get_relationships(self):
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM article_relationships ORDER BY id"
            ).fetchall()
        return [dict(row) for row in rows]

    def find_by_canonical_url(self, url):
        canonical_url = canonicalize_url(url)
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM articles WHERE canonical_url = ?",
                (canonical_url,),
            ).fetchone()
        return dict(row) if row else None

    def get_articles(self, limit=None):
        query = "SELECT * FROM articles ORDER BY id"
        parameters = ()
        if limit is not None:
            query += " LIMIT ?"
            parameters = (limit,)

        with self._connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]

    def search_articles(self, query, limit=None):
        normalized_query = query.strip().lower()
        if not normalized_query:
            return []

        pattern = f"%{normalized_query}%"
        sql = """
            SELECT * FROM articles
            WHERE LOWER(title) LIKE ?
               OR LOWER(COALESCE(description, '')) LIKE ?
               OR LOWER(COALESCE(publisher, '')) LIKE ?
            ORDER BY id
        """
        parameters = (pattern, pattern, pattern)
        if limit is not None:
            sql += " LIMIT ?"
            parameters += (limit,)

        with self._connection() as connection:
            rows = connection.execute(sql, parameters).fetchall()
        return [dict(row) for row in rows]

    def count_articles(self):
        with self._connection() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM articles").fetchone()
        return row["count"]

    @staticmethod
    def _timestamp():
        return datetime.now(timezone.utc).isoformat()
