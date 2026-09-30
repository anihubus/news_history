# News History

News History is a web application for exploring the context and historical development of news topics.

## Current status

Steps 1–16 are complete (including Phase 2 Step 16: Source Quality and Provenance Signals). The project provides a Flask application factory, a responsive News History interface, replaceable news providers, SQLite persistence, local retrieval, deterministic grouping, cross-source verification, an automatically assembled timeline, mock-first grounded AI services, and explicit source quality and provenance signals.

## Features

- Search GDELT coverage or use the deterministic mock provider.
- Store normalized article metadata in SQLite.
- Deduplicate articles by canonical URL.
- Combine stored and newly retrieved articles.
- Detect related articles with explainable weighted keyword overlap.
- Cross-source agreement and conflict detection.
- Expose source-quality and provenance signals without subjective credibility rankings.
- Assemble a chronological timeline from publication dates.
- Generate grounded mock summaries and question answers from available metadata.
- Display publishers, providers, publication dates, retrieval timestamps, original URLs, and supporting sources.

## Architecture

```text
Frontend
	-> Flask route
	-> Search Orchestrator
	-> Retrieval / Grouping / Timeline / Provenance / Summary services
	-> News provider and ArticleRepository
	-> SQLite
```

Flask routes handle HTTP only. Provider adapters handle external services, repositories handle persistence, services handle application logic, and the frontend handles presentation. AI services receive explicit retrieved context and cannot browse the web or access SQLite directly.

## Setup

Create a virtual environment:

```text
python -m venv .venv
```

Activate it on Windows PowerShell:

```text
.venv\Scripts\Activate.ps1
```

Activate it on macOS or Linux:

```text
source .venv/bin/activate
```

Install dependencies:

```text
python -m pip install -r requirements.txt
```

## Run the application

```text
python run.py
```

Then open `http://127.0.0.1:5000/` in a browser.

For local development, `NEWS_PROVIDER=mock` avoids external network calls. Debug mode is disabled by default. Enable it only locally with `FLASK_DEBUG=1`.

### Choose a news provider

The application uses multiple providers. By default it uses `gdelt`. To use the development-only mock provider
without making external network requests, set `NEWS_PROVIDERS=mock` before starting
the application:

```powershell
$env:NEWS_PROVIDERS = "mock"
python run.py
```

To explicitly use GDELT, set `NEWS_PROVIDERS=gdelt`:

```powershell
$env:NEWS_PROVIDERS = "gdelt"
python run.py
```

To use NewsAPI as an additional provider, set `NEWS_PROVIDERS=gdelt,newsapi` and configure `NEWSAPI_KEY`:

```powershell
$env:NEWS_PROVIDERS = "gdelt,newsapi"
$env:NEWSAPI_KEY = "your_newsapi_key"
python run.py
```

## Search endpoint and provider

The frontend sends searches to `POST /api/search` with a JSON body. The Flask route delegates to the Search Orchestrator, which uses the selected provider adapter. The frontend never calls a provider directly.

```json
{
	"query": "climate change"
}
```

Valid searches first check stored articles by title, description, and publisher, then query the selected provider for new results. Results are persisted, combined, deduplicated by canonical URL, and sorted newest-first by `publication_date`. Articles without a valid publication date appear after dated articles in deterministic URL order. `retrieved_at` remains separate from `publication_date`.

The final result count is controlled by `SEARCH_RESULT_LIMIT`, which defaults to `20`:

```powershell
$env:SEARCH_RESULT_LIMIT = "20"
python run.py
```

If the provider is unavailable or rate-limited, matching stored articles are still returned with a provider status. If no stored matches exist, the API returns a controlled provider error without exposing exceptions. GDELT retrieves available matching coverage and is not the complete historical archive for a topic.

## Related article grouping

Articles are automatically grouped using a deterministic, explainable heuristic. Title and description text is lowercased, punctuation and extra whitespace are normalized, common stop words and very short tokens are removed, and title tokens receive twice the weight of description tokens. Similarity is calculated as:

```text
weighted shared keywords / weighted union of keywords
```

The default `RELATED_ARTICLE_THRESHOLD` is `0.30` and can be configured through the environment. Relationships are stored explicitly in SQLite with their similarity score and reason. Groups use deterministic representative titles and are an automatic interpretation, not proof that articles describe the same event. Future versions may replace this heuristic with more advanced NLP or embedding methods.

## Historical timeline

After retrieval and grouping, the Timeline Service derives a chronological view at search time. Multi-article groups produce one entry using the earliest valid `publication_date` and all supporting article IDs. Unrelated articles produce individual entries. Dates are normalized from supported provider formats; missing or invalid dates remain unknown and are placed after valid dates. `retrieved_at` is never used as a historical date.

Timeline entries are automatically assembled interpretations of available reporting, not definitive historical records. They do not invent events, infer causality, or replace source inspection. No separate timeline table is used in this MVP.

## AI summaries and grounded context

The Search Orchestrator passes normalized articles, groups, and timeline entries to the replaceable Summary Service. The Summary Service calls the configured AI provider with explicit evidence context only. `MockAIProvider` is the default fallback and produces deterministic summaries without network access. Configure the provider selection with `AI_PROVIDER=mock`; no API key is required or exposed to frontend code.

Summaries are automatically generated from the available News History source data and may be incomplete. They must not invent facts, dates, causes, quotes, or information outside the supplied metadata and descriptions. AI failures do not remove articles, groups, relationships, or timeline results.

The context builder creates the foundation for future grounded question answering from retrieved articles, groups, and timeline entries. `POST /api/question` accepts `question` and `query` and returns a mock grounded answer with supporting article IDs. It does not perform web browsing, vector search, or arbitrary internet access.

## Source provenance and quality signals

`ProvenanceService` builds neutral source references and exposes objective source-quality and provenance signals from already retrieved application data without creating subjective credibility rankings.

Each source reference preserves the article ID, title, publisher, original URL, publication date, retrieval timestamp, and metadata provider. `publication_date` is when the source reports publication; `retrieved_at` is when News History obtained the metadata. Missing values remain missing.

### Provenance signals

Signals are computed using only information actually available in the system:

- `publisher_identified`: Boolean indicating whether a publisher name is identified in the source metadata.
- `original_url_available`: Boolean indicating whether the original article URL is available. Original URLs are always preserved unchanged.
- `publication_date_available`: Boolean indicating whether a valid publication date was reported.
- `source_provider_identified`: Boolean indicating whether the provider adapter (e.g. GDELT, NewsAPI, Mock) is identified.
- `multiple_sources_found`: Boolean indicating whether multiple source records corroborate an event, cluster, or query.
- `independent_source_count`: Integer count of distinct, identified publishers covering the story.
- `source_information_missing`: Boolean flag highlighting whether any key provenance metadata (publisher, date, URL, or provider) is incomplete.

### Neutrality and ethical guardrails

News History provides transparency into source provenance and metadata completeness:
- **Original source URLs are kept unchanged.**
- **Publisher information is never invented or fabricated.**
- **No credibility scores or trust rankings are assigned** (never ranks publishers as trustworthy/untrustworthy).
- **No political bias is inferred or scored.**

### API and Frontend exposure

These signals are exposed at all levels of the API (`POST /api/search`):
- Top-level `provenance_signals` summarize coverage across the entire query.
- Each result item in `results` includes its individual provenance signals and metadata completeness.
- Timeline entries in `timeline` and thematic clusters in `groups` provide aggregate signals (`independent_source_count`, `multiple_sources_found`, `source_information_missing`).
- The frontend renders these signals cleanly via subtle badges, indicators in event cards, metadata statuses in the expandable source drawer, and coverage stats in the research workspace.

## SQLite database

The application automatically initializes an SQLite database at `instance/news_history.db` when it starts. The `articles` table stores normalized article metadata, retrieval timestamps, and canonical URLs. Canonical URL uniqueness prevents the same article from being inserted more than once while preserving different URLs.

Set `DATABASE_PATH` to use a different database location:

```powershell
$env:DATABASE_PATH = "path/to/news_history.db"
python run.py
```

The database uses Python's built-in `sqlite3` module; no manual SQL commands or additional database packages are required.

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `NEWS_PROVIDERS` | `gdelt` | Selects multiple providers like `gdelt`, `mock`, or `newsapi` (comma separated). |
| `NEWS_PROVIDER` | `gdelt` | Fallback for `NEWS_PROVIDERS`. |
| `GDELT_BASE_URL` | GDELT DOC endpoint | Provider endpoint. |
| `GDELT_MAX_RESULTS` | `10` | Maximum provider results per request. |
| `GDELT_TIMEOUT` | `10` | Provider request timeout in seconds. |
| `NEWSAPI_KEY` | None | API key for NewsAPI. |
| `NEWSAPI_BASE_URL` | `https://newsapi.org/v2/everything` | NewsAPI endpoint. |
| `DATABASE_PATH` | `instance/news_history.db` | SQLite database location. |
| `SEARCH_RESULT_LIMIT` | `20` | Final search result limit. |
| `RELATED_ARTICLE_THRESHOLD` | `0.30` | Deterministic grouping threshold. |
| `AI_PROVIDER` | `mock` | Current AI provider selection; mock is the supported implementation. |
| `FLASK_DEBUG` | `0` | Enables Flask debug mode only when explicitly set. |

Keep secrets and machine-specific configuration in `.env`. Do not expose them to frontend JavaScript or commit them to source control.

## Run tests

```text
python -m pytest -v
```

## Deployment notes

The included `run.py` uses Flask's development server and is intended for local smoke testing only. For deployment, run the application factory with a production WSGI server supplied by the deployment environment, set `FLASK_DEBUG=0`, provide environment variables securely, and use a writable persistent `DATABASE_PATH`. Review provider quotas, source terms, content retention, backups, and concurrency requirements before production use.

## Known limitations

- GDELT coverage is not a complete historical archive and may be rate-limited.
- SQLite is intended for the initial single-application deployment.
- Grouping and timelines are deterministic automatic interpretations, not verified events or causal histories.
- Mock AI summaries and answers are development implementations; no real AI provider is configured.
- Summaries use metadata and descriptions only and may be incomplete.
- News History provides source traceability but does not independently verify publisher claims.
