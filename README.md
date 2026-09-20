# News History

News History is a web application for exploring the context and historical development of news topics.

## Current status

Step 6, SQLite persistence and canonical URL deduplication, is complete. The project provides a Flask application factory, a responsive News History interface, a GDELT-backed search pipeline, and an SQLite article repository. History reconstruction, grouping, timeline generation, and AI features are planned for later steps.

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

Valid searches return normalized article results in the provider order. Each result includes a title, original URL, publisher, publication date when available, nullable description, and `source_provider`. Empty queries return a client error; provider failures return a controlled server error. GDELT retrieves available matching coverage and is not the complete historical archive for a topic. Persistence and historical reconstruction will be implemented in later steps.

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
