# News History

News History is a web application for exploring the context and historical development of news topics.

## Current status

Step 2, project foundation, is complete. The project currently provides a Flask application factory, a homepage, a basic responsive frontend shell, and a homepage test. Search, news retrieval, persistence, grouping, timeline generation, and AI features are planned for later steps.

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

## Run tests

```text
python -m unittest discover -s tests
```
