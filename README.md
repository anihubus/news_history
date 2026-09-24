# News History

News History is a web application for exploring the context and historical development of news topics.

## Current status

Step 11, source verification and provenance, is complete. The project provides a Flask application factory, a responsive News History interface, a GDELT-backed search pipeline, SQLite persistence, local retrieval, deterministic grouping, an automatically assembled timeline, a mock-first grounded AI layer, and explicit source traceability.

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

## Run tests

```text
python -m pytest
```
