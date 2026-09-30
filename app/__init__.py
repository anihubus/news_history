import os

from flask import Flask

from app.database import initialize_database
from app.providers.gdelt_provider import GDELTProvider
from app.providers.mock_provider import MockNewsProvider
from app.providers.multi_provider import MultiProvider
from app.providers.newsapi_provider import NewsAPIProvider
from app.providers.ai_provider import MockAIProvider
from app.repositories.article_repository import ArticleRepository
from app.services.search_orchestrator import SearchOrchestrator


def create_app(test_config=None):
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )

    app.config.from_mapping(
        NEWS_PROVIDERS=os.getenv("NEWS_PROVIDERS"),
        NEWS_PROVIDER=os.getenv("NEWS_PROVIDER", "gdelt").lower(),
        GDELT_BASE_URL=os.getenv(
            "GDELT_BASE_URL",
            "https://api.gdeltproject.org/api/v2/doc/doc",
        ),
        GDELT_MAX_RESULTS=int(os.getenv("GDELT_MAX_RESULTS", "10")),
        GDELT_TIMEOUT=float(os.getenv("GDELT_TIMEOUT", "10")),
        NEWSAPI_KEY=os.getenv("NEWSAPI_KEY"),
        NEWSAPI_BASE_URL=os.getenv(
            "NEWSAPI_BASE_URL",
            "https://newsapi.org/v2/everything",
        ),
        NEWSAPI_MAX_RESULTS=int(os.getenv("NEWSAPI_MAX_RESULTS", "10")),
        NEWSAPI_TIMEOUT=float(os.getenv("NEWSAPI_TIMEOUT", "10")),
        DATABASE_PATH=os.getenv("DATABASE_PATH", "instance/news_history.db"),
        SEARCH_RESULT_LIMIT=int(os.getenv("SEARCH_RESULT_LIMIT", "20")),
        RELATED_ARTICLE_THRESHOLD=float(os.getenv("RELATED_ARTICLE_THRESHOLD", "0.30")),
        AI_PROVIDER=os.getenv("AI_PROVIDER", "mock").lower(),
        DEBUG=os.getenv("FLASK_DEBUG", "0").lower() in {"1", "true", "yes", "on"},
    )
    if test_config:
        app.config.update(test_config)

    initialize_database(app.config["DATABASE_PATH"])

    provider_names_str = app.config.get("NEWS_PROVIDERS") or app.config.get("NEWS_PROVIDER")
    if provider_names_str and "," in str(provider_names_str):
        provider_names = [p.strip() for p in str(provider_names_str).split(",") if p.strip()]
    elif provider_names_str:
        provider_names = [str(provider_names_str).strip()]
    else:
        provider_names = ["gdelt"]

    providers_list = []
    for name in provider_names:
        name = name.lower()
        if name == "mock":
            providers_list.append(MockNewsProvider())
        elif name == "gdelt":
            providers_list.append(
                GDELTProvider(
                    base_url=app.config["GDELT_BASE_URL"],
                    max_results=app.config["GDELT_MAX_RESULTS"],
                    timeout=app.config["GDELT_TIMEOUT"],
                )
            )
        elif name == "newsapi":
            providers_list.append(
                NewsAPIProvider(
                    api_key=app.config.get("NEWSAPI_KEY"),
                    base_url=app.config["NEWSAPI_BASE_URL"],
                    max_results=app.config.get("NEWSAPI_MAX_RESULTS", 10),
                    timeout=app.config.get("NEWSAPI_TIMEOUT", 10.0),
                )
            )
        else:
            raise ValueError(f"Unknown news provider: {name}")

    provider = MultiProvider(providers_list)

    repository = ArticleRepository(app.config["DATABASE_PATH"])
    ai_provider = MockAIProvider()
    app.extensions["ai_provider"] = ai_provider
    app.extensions["article_repository"] = repository
    app.extensions["search_orchestrator"] = SearchOrchestrator(
        provider,
        repository,
        result_limit=app.config["SEARCH_RESULT_LIMIT"],
        relationship_threshold=app.config["RELATED_ARTICLE_THRESHOLD"],
        ai_provider=ai_provider,
    )

    from app.routes.main import main_bp

    app.register_blueprint(main_bp)

    return app
