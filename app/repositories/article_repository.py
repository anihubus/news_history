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
                    retrieved_at = excluded.retrieved_at
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

    def count_articles(self):
        with self._connection() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM articles").fetchone()
        return row["count"]

    @staticmethod
    def _timestamp():
        return datetime.now(timezone.utc).isoformat()
