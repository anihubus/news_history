from abc import ABC, abstractmethod

class ProviderError(Exception):
    """Raised when a news provider cannot return a usable response."""


class RateLimitError(ProviderError):
    """Raised when the provider asks the application to wait before retrying."""


class NewsProvider(ABC):
    @abstractmethod
    def search(self, query):
        """Search the news provider for the given query."""
        pass
