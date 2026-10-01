import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

from app.database import initialize_database
from app.providers.ai_provider import MockAIProvider
from app.providers.gdelt_provider import GDELTProvider
from app.providers.mock_provider import MockNewsProvider
from app.providers.multi_provider import MultiProvider
from app.providers.newsapi_provider import NewsAPIProvider
from app.providers.newsdata_provider import NewsDataProvider
from app.providers.thenewsapi_provider import TheNewsAPIProvider
from app.repositories.article_repository import ArticleRepository
from app.services.search_orchestrator import SearchOrchestrator


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def create_app(test_config=None):
    # Load the developer's .env only for the normal application.
    #
    # Tests can still provide environment variables explicitly through
    # os.environ without having the developer's local .env affect them.
    if test_config is None:
        load_dotenv(PROJECT_ROOT / ".env")

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
        GDELT_MAX_RESULTS=int(
            os.getenv("GDELT_MAX_RESULTS", "10")
        ),
        GDELT_TIMEOUT=float(
            os.getenv("GDELT_TIMEOUT", "10")
        ),

        NEWSAPI_KEY=os.getenv("NEWSAPI_KEY"),
        NEWSAPI_BASE_URL=os.getenv(
            "NEWSAPI_BASE_URL",
            "https://newsapi.org/v2/everything",
        ),
        NEWSAPI_MAX_RESULTS=int(
            os.getenv("NEWSAPI_MAX_RESULTS", "10")
        ),
        NEWSAPI_TIMEOUT=float(
            os.getenv("NEWSAPI_TIMEOUT", "10")
        ),

        THENEWSAPI_ENABLED=os.getenv(
            "THENEWSAPI_ENABLED",
            "false",
        ).lower() in {
            "1",
            "true",
            "yes",
            "on",
        },
        THENEWSAPI_API_KEY=os.getenv(
            "THENEWSAPI_API_KEY"
        ),
        THENEWSAPI_BASE_URL=os.getenv(
            "THENEWSAPI_BASE_URL",
            "https://api.thenewsapi.com/v1",
        ),
        THENEWSAPI_MAX_RESULTS=int(
            os.getenv("THENEWSAPI_MAX_RESULTS", "10")
        ),
        THENEWSAPI_TIMEOUT=float(
            os.getenv("THENEWSAPI_TIMEOUT", "10")
        ),

        NEWSDATA_ENABLED=os.getenv(
            "NEWSDATA_ENABLED",
            "false",
        ).lower() in {
            "1",
            "true",
            "yes",
            "on",
        },
        NEWSDATA_API_KEY=os.getenv(
            "NEWSDATA_API_KEY"
        ),
        NEWSDATA_BASE_URL=os.getenv(
            "NEWSDATA_BASE_URL",
            "https://newsdata.io/api/1",
        ),
        NEWSDATA_MAX_RESULTS=int(
            os.getenv("NEWSDATA_MAX_RESULTS", "10")
        ),
        NEWSDATA_TIMEOUT=float(
            os.getenv("NEWSDATA_TIMEOUT", "10")
        ),

        DATABASE_PATH=os.getenv(
            "DATABASE_PATH",
            "instance/news_history.db",
        ),
        SEARCH_RESULT_LIMIT=int(
            os.getenv("SEARCH_RESULT_LIMIT", "20")
        ),
        RELATED_ARTICLE_THRESHOLD=float(
            os.getenv("RELATED_ARTICLE_THRESHOLD", "0.30")
        ),
        AI_PROVIDER=os.getenv(
            "AI_PROVIDER",
            "mock",
        ).lower(),
        DEBUG=os.getenv(
            "FLASK_DEBUG",
            "0",
        ).lower() in {
            "1",
            "true",
            "yes",
            "on",
        },
    )

    if test_config:
        app.config.update(test_config)

    initialize_database(app.config["DATABASE_PATH"])

    # ---------------------------------------------------------
    # Determine configured providers
    # ---------------------------------------------------------

    provider_names_str = (
        app.config.get("NEWS_PROVIDERS")
        or app.config.get("NEWS_PROVIDER")
    )

    if provider_names_str and "," in str(provider_names_str):
        provider_names = [
            p.strip()
            for p in str(provider_names_str).split(",")
            if p.strip()
        ]
    elif provider_names_str:
        provider_names = [
            str(provider_names_str).strip()
        ]
    else:
        provider_names = ["gdelt"]

    # ---------------------------------------------------------
    # TheNewsAPI
    # ---------------------------------------------------------

    thenewsapi_cfg = app.config.get(
        "THENEWSAPI_ENABLED"
    )

    if isinstance(thenewsapi_cfg, str):
        thenewsapi_enabled = (
            thenewsapi_cfg.lower()
            in {"1", "true", "yes", "on"}
        )
    else:
        thenewsapi_enabled = bool(
            thenewsapi_cfg
        )

    provider_names_lower = [
        p.lower() for p in provider_names
    ]

    if (
        thenewsapi_enabled
        and "thenewsapi" not in provider_names_lower
    ):
        # Do not automatically add another live provider to a
        # test/mock-only configuration.
        if not (
            "mock" in provider_names_lower
            and len(provider_names) == 1
        ):
            provider_names.append("thenewsapi")

    elif (
        thenewsapi_cfg is not None
        and not thenewsapi_enabled
        and "thenewsapi" in provider_names_lower
    ):
        provider_names = [
            p
            for p in provider_names
            if p.lower() != "thenewsapi"
        ]

        if not provider_names:
            provider_names = ["gdelt"]

    # ---------------------------------------------------------
    # NewsData
    # ---------------------------------------------------------

    newsdata_cfg = app.config.get(
        "NEWSDATA_ENABLED"
    )

    if isinstance(newsdata_cfg, str):
        newsdata_enabled = (
            newsdata_cfg.lower()
            in {"1", "true", "yes", "on"}
        )
    else:
        newsdata_enabled = bool(
            newsdata_cfg
        )

    provider_names_lower = [
        p.lower() for p in provider_names
    ]

    if (
        newsdata_enabled
        and "newsdata" not in provider_names_lower
    ):
        # Explicit NEWSDATA_ENABLED=true should add NewsData
        # alongside configured live providers.
        #
        # The exception is a mock-only configuration, where adding
        # a live provider would make tests unexpectedly hit the
        # internet.
        if not (
            "mock" in provider_names_lower
            and len(provider_names) == 1
        ):
            provider_names.append("newsdata")

    elif (
        newsdata_cfg is not None
        and not newsdata_enabled
        and "newsdata" in provider_names_lower
    ):
        provider_names = [
            p
            for p in provider_names
            if p.lower() != "newsdata"
        ]

        if not provider_names:
            provider_names = ["gdelt"]

    # ---------------------------------------------------------
    # Create provider instances
    # ---------------------------------------------------------

    providers_list = []

    for name in provider_names:
        name = name.lower()

        if name == "mock":
            providers_list.append(
                MockNewsProvider()
            )

        elif name == "gdelt":
            providers_list.append(
                GDELTProvider(
                    base_url=app.config[
                        "GDELT_BASE_URL"
                    ],
                    max_results=app.config[
                        "GDELT_MAX_RESULTS"
                    ],
                    timeout=app.config[
                        "GDELT_TIMEOUT"
                    ],
                )
            )

        elif name == "newsapi":
            providers_list.append(
                NewsAPIProvider(
                    api_key=app.config.get(
                        "NEWSAPI_KEY"
                    ),
                    base_url=app.config[
                        "NEWSAPI_BASE_URL"
                    ],
                    max_results=app.config.get(
                        "NEWSAPI_MAX_RESULTS",
                        10,
                    ),
                    timeout=app.config.get(
                        "NEWSAPI_TIMEOUT",
                        10.0,
                    ),
                )
            )

        elif name == "thenewsapi":
            providers_list.append(
                TheNewsAPIProvider(
                    api_key=app.config.get(
                        "THENEWSAPI_API_KEY"
                    ),
                    base_url=app.config.get(
                        "THENEWSAPI_BASE_URL",
                        "https://api.thenewsapi.com/v1",
                    ),
                    max_results=app.config.get(
                        "THENEWSAPI_MAX_RESULTS",
                        10,
                    ),
                    timeout=app.config.get(
                        "THENEWSAPI_TIMEOUT",
                        10.0,
                    ),
                )
            )

        elif name == "newsdata":
            providers_list.append(
                NewsDataProvider(
                    api_key=app.config.get(
                        "NEWSDATA_API_KEY"
                    ),
                    base_url=app.config.get(
                        "NEWSDATA_BASE_URL",
                        "https://newsdata.io/api/1",
                    ),
                    max_results=app.config.get(
                        "NEWSDATA_MAX_RESULTS",
                        10,
                    ),
                    timeout=app.config.get(
                        "NEWSDATA_TIMEOUT",
                        10.0,
                    ),
                )
            )

        else:
            raise ValueError(
                f"Unknown news provider: {name}"
            )

    # ---------------------------------------------------------
    # Application services
    # ---------------------------------------------------------

    provider = MultiProvider(
        providers_list
    )

    repository = ArticleRepository(
        app.config["DATABASE_PATH"]
    )

    ai_provider = MockAIProvider()

    app.extensions["ai_provider"] = ai_provider
    app.extensions["article_repository"] = repository

    app.extensions[
        "search_orchestrator"
    ] = SearchOrchestrator(
        provider,
        repository,
        result_limit=app.config[
            "SEARCH_RESULT_LIMIT"
        ],
        relationship_threshold=app.config[
            "RELATED_ARTICLE_THRESHOLD"
        ],
        ai_provider=ai_provider,
    )

    from app.routes.main import main_bp

    app.register_blueprint(main_bp)

    return app