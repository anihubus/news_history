# News History

News History is a web application for exploring the context and historical development of news topics.

## Current status

Step 4, backend search foundation, is complete. The project provides a Flask application factory, a responsive News History interface, and a service-backed search pipeline. Real news retrieval, persistence, grouping, timeline generation, and AI features are planned for later steps.

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

## Search endpoint

The frontend sends searches to `POST /api/search` with a JSON body:

```json
{
	"query": "climate change"
}
```

Valid searches return a normalized response with `success`, the trimmed `query`, an empty `results` array, and a development message. Empty queries and requests without valid JSON return a client error. Real news retrieval is not connected yet.

## Run tests

```text
python -m pytest
```
