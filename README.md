# News History

News History is a web application for exploring the context and historical development of news topics.

## Current status

Step 8, explainable related-news detection and grouping, is complete. The project provides a Flask application factory, a responsive News History interface, a GDELT-backed search pipeline, SQLite persistence, local retrieval, and deterministic article grouping. Timeline generation and AI features are planned for later steps.

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
