from dataclasses import asdict, dataclass
from typing import Optional


@dataclass(frozen=True)
class Article:
    title: str
    url: str
    publisher: Optional[str]
    publication_date: Optional[str]
    description: Optional[str]
    source_provider: str
    article_id: Optional[int] = None
    retrieved_at: Optional[str] = None

    def to_dict(self):
        data = asdict(self)
        data.pop("article_id", None)
        return data
