import sqlite3
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    canonical_url TEXT NOT NULL UNIQUE,
    publisher TEXT,
    publication_date TEXT,
    description TEXT,
    source_provider TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS article_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    representative_article_id INTEGER NOT NULL,
    representative_title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (representative_article_id) REFERENCES articles(id)
);

CREATE TABLE IF NOT EXISTS article_group_members (
    group_id INTEGER NOT NULL,
    article_id INTEGER NOT NULL,
    PRIMARY KEY (group_id, article_id),
    FOREIGN KEY (group_id) REFERENCES article_groups(id),
    FOREIGN KEY (article_id) REFERENCES articles(id)
);

CREATE TABLE IF NOT EXISTS article_relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER NOT NULL,
    related_article_id INTEGER NOT NULL,
    similarity_score REAL NOT NULL,
    relationship_type TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (article_id, related_article_id),
    FOREIGN KEY (article_id) REFERENCES articles(id),
    FOREIGN KEY (related_article_id) REFERENCES articles(id)
)
"""


def initialize_database(database_path):
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(path)
    try:
        connection.executescript(SCHEMA)
        connection.commit()
    finally:
        connection.close()
