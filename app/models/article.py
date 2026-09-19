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

    def to_dict(self):
        return asdict(self)
