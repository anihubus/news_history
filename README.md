# News History

News History is a web application for exploring the context and historical development of news topics.

## Current status

Steps 1-11 are complete. Step 12 final testing and deployment readiness is in progress. The project provides a Flask application factory, a responsive News History interface, a replaceable news provider, SQLite persistence, local retrieval, deterministic grouping, an automatically assembled timeline, mock-first grounded AI services, and explicit source traceability.

## Features

- Search GDELT coverage or use the deterministic mock provider.
- Store normalized article metadata in SQLite.
- Deduplicate articles by canonical URL.
- Combine stored and newly retrieved articles.
- Detect related articles with explainable weighted keyword overlap.
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

The application uses GDELT by default. To use the development-only mock provider
without making external network requests, set `NEWS_PROVIDER=mock` before starting
the application:

```powershell
$env:NEWS_PROVIDER = "mock"
python run.py
```

To explicitly use GDELT, set `NEWS_PROVIDER=gdelt`:

```powershell
$env:NEWS_PROVIDER = "gdelt"
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

## Source provenance

`ProvenanceService` builds neutral source references from existing article records. Each reference preserves the article ID, publisher, original URL, publication date, retrieval timestamp, and metadata provider. `publication_date` is when the source reports publication; `retrieved_at` is when News History obtained the metadata. Missing values remain missing.

Groups and timelines expose supporting source references, while summaries and grounded answers expose the sources behind their generated content. The UI distinguishes `SOURCE DATA`, `AUTOMATIC GROUPING`, `AUTOMATIC TIMELINE`, and `AI-GENERATED CONTENT`. Automatic groups and timelines are interpretations, not independently verified events. Conflicting reports remain separate rather than being resolved automatically.

News History provides source traceability and provenance. It does not independently verify every claim made by external publishers. It does not assign reliability, credibility, bias, or fact-checking scores.

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
| `NEWS_PROVIDER` | `gdelt` | Selects `gdelt` or `mock`. |
| `GDELT_BASE_URL` | GDELT DOC endpoint | Provider endpoint. |
| `GDELT_MAX_RESULTS` | `10` | Maximum provider results per request. |
| `GDELT_TIMEOUT` | `10` | Provider request timeout in seconds. |
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
