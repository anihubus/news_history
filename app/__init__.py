import os

from flask import Flask

from app.database import initialize_database
from app.providers.gdelt_provider import GDELTProvider
from app.providers.mock_provider import MockNewsProvider
from app.repositories.article_repository import ArticleRepository
from app.services.search_orchestrator import SearchOrchestrator


def create_app(test_config=None):
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )

    app.config.from_mapping(
        NEWS_PROVIDER=os.getenv("NEWS_PROVIDER", "gdelt").lower(),
        GDELT_BASE_URL=os.getenv(
            "GDELT_BASE_URL",
            "https://api.gdeltproject.org/api/v2/doc/doc",
        ),
        GDELT_MAX_RESULTS=int(os.getenv("GDELT_MAX_RESULTS", "10")),
        GDELT_TIMEOUT=float(os.getenv("GDELT_TIMEOUT", "10")),
        DATABASE_PATH=os.getenv("DATABASE_PATH", "instance/news_history.db"),
    )
    if test_config:
        app.config.update(test_config)

    initialize_database(app.config["DATABASE_PATH"])

    if app.config["NEWS_PROVIDER"] == "mock":
        provider = MockNewsProvider()
    elif app.config["NEWS_PROVIDER"] == "gdelt":
        provider = GDELTProvider(
            base_url=app.config["GDELT_BASE_URL"],
            max_results=app.config["GDELT_MAX_RESULTS"],
            timeout=app.config["GDELT_TIMEOUT"],
        )
    else:
        raise ValueError("NEWS_PROVIDER must be either 'gdelt' or 'mock'.")

    repository = ArticleRepository(app.config["DATABASE_PATH"])
    app.extensions["article_repository"] = repository
    app.extensions["search_orchestrator"] = SearchOrchestrator(provider, repository)

    from app.routes.main import main_bp

    app.register_blueprint(main_bp)

    return app
