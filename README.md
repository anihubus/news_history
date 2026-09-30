# News History

News History is a web application for exploring the context and historical development of news topics.

## Current status

Steps 1–22 are complete (including Step 22: Multiple Real-Time News Sources). The project provides a Flask application factory, a responsive News History interface, multi-provider adapter architecture with live GDELT and NewsAPI integrations, SQLite persistence, real-time news retrieval on every search, cross-provider canonical URL deduplication and provider merging, automatic frontend polling with configurable refresh intervals, local retrieval, deterministic grouping, cross-source verification, an automatically assembled timeline, mock-first grounded AI services, explicit source quality and provenance signals, transparent suspicious-content warning indicators, evidence-based AI verification, and a unified Verification & Sources dashboard.

## Features

- Search live GDELT coverage, NewsAPI, or use the deterministic mock provider via the extensible `NewsProvider` adapter architecture.
- Multi-provider support (`MultiProvider`) combining results across independent providers with isolated failure and rate limit handling.
- Environment-variable-based credential management (`NEWSAPI_KEY`, etc.) without hardcoded secrets.
- Cross-provider deduplication using canonical URLs, merging metadata (richer descriptions, publishers, publication dates) and concatenating provider attributions (e.g. `gdelt, newsapi`).
- Keep provider names visible in provenance signals, article payloads, and the verification dashboard.
- Retrieve fresh real-time news results from providers on every user search without replacing the SQLite database.
- Automatic frontend refresh polling with configurable intervals (default: 60s) without full-page reloads or WebSockets.
- Page Visibility API integration to pause polling when the tab is hidden.
- Real-time article arrival detection via canonical URL / article ID with dynamic "New articles available" notifications and "Last updated: <time>" indicator.
- Manual "Refresh" button with in-flight overlap protection.
- Store normalized article metadata in SQLite with `retrieved_at` timestamps while preserving historical `publication_date`.
- Deduplicate articles by canonical URL and avoid overwriting existing historical articles unnecessarily.
- Gracefully handle provider failures and rate limits, returning stored historical articles and provider status without disrupting active viewing.
- Return provider status to the frontend with live connection indicators and status notices.
- Combine stored historical and newly retrieved articles.
- Detect related articles with explainable weighted keyword overlap.
- Cross-source agreement and conflict detection.
- Expose source-quality and provenance signals without subjective credibility rankings.
- Identify suspicious-content warning signals based on observable metadata and corroboration patterns without truth/fake value judgments.
- Grounded AI verification explaining source evidence, corroboration, conflicts, and verification warnings.
- Verification & Sources dashboard combining source metadata, corroboration metrics, conflict tracking, and warning explanations.
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

## Suspicious-content warning signals

`VerificationSignalService` analyzes articles, clusters, and timeline entries to identify potentially unreliable reporting using transparent warning signals based solely on observable data.

The system adheres to strict neutrality principles:
- **It DOES NOT declare articles "true" or "fake"**, nor does it produce hoax/debunked verdicts.
- **It DOES NOT use hidden, unexplained scoring** or arbitrary credibility numbers.
- **It DOES NOT infer or score political bias.**
- **It uses calm, neutral, observable editorial language.**

### Structured signal schema

Each signal is structured as a dictionary containing:
- `type`: Specific signal identifier (e.g. `single_source_only`, `no_independent_supporting_reports`, `conflicting_reports`, `missing_publisher`, `missing_publication_date`, `missing_original_url`, `incomplete_metadata`, `unusually_incomplete_metadata`).
- `severity`: `"warning"` indicating observational caution.
- `explanation`: Human-readable, neutral explanation of the observable reporting state.
- `supporting_article_ids`: List of article IDs associated with the observation.

### Observable warning signals

1. **`single_source_only`**:
   - Condition: Only one article is retrieved for an event, cluster, or query.
   - Explanation: `"Limited independent reporting is currently available."`
2. **`no_independent_supporting_reports`**:
   - Condition: Multiple articles exist, but all originate from the same publisher.
   - Explanation: `"Limited independent reporting is currently available."`
3. **`conflicting_reports`**:
   - Condition: Reports contain explicit conflict or denial markers (e.g. disputing or contradicting accounts).
   - Explanation: `"Some reports contain differing information."`
4. **`missing_publisher`**:
   - Condition: Publisher is omitted or blank in the source record.
   - Explanation: `"Publisher information is missing from the source record."`
5. **`missing_publication_date`**:
   - Condition: Publication date is missing or invalid.
   - Explanation: `"Publication date is unavailable in the source metadata."`
6. **`missing_original_url`**:
   - Condition: Original source URL is unavailable or empty.
   - Explanation: `"Original source URL is unavailable."`
7. **`incomplete_metadata`**:
   - Condition: One or more key metadata fields (publisher, date, URL, provider) are missing.
   - Explanation: `"Source metadata is incomplete."`
8. **`unusually_incomplete_metadata`**:
   - Condition: Two or more key metadata fields are missing simultaneously.
   - Explanation: `"Source metadata is unusually incomplete."`

### API and Frontend exposure

- **API**: Exposed via `verification_signals` (and `warning_signals`) in `POST /api/search` at the query root, per article in `results`, per cluster in `groups`, and per event in `timeline`.
- **Frontend**: Rendered in the timeline event cards, thematic cluster sections, and expandable article rows with clear, calm warning styling that informs users of reporting gaps without making subjective truth claims.

## Evidence-based AI verification (Q&A)

`QuestionAnswerService` and `ContextBuilder` allow the grounded AI layer to explain source evidence, corroboration, conflicts, and verification signals without declaring articles fake or true.

The AI uses **ONLY**:
- Retrieved article metadata and descriptions
- Article groups and cross-source analysis
- Timeline entries
- Provenance information (publishers, URLs, publication dates, providers)
- Cross-source signals (corroboration, independent source counts, conflicts)
- Verification warnings

### Grounded context extensions

`ContextBuilder` automatically structures:
- `articles`: Full article metadata with provenance and verification signals.
- `supporting_references`: Complete source references for articles corroborating reporting.
- `conflicting_references`: Complete source references for articles containing conflicting or disputed reporting.
- `provenance_signals`: Aggregate collection signals.
- `cross_source_signals`: Cross-publisher agreement and conflict signals.
- `verification_warnings`: Transparent warning signals on metadata completeness and corroboration.

### Verification questions supported

Users can ask direct verification and evidence inquiries:
- *"How many sources reported this?"*: Summarizes article counts and distinct independent publishers.
- *"Are there conflicting reports?"*: Explains whether reports contain consistent information or conflicting claims, citing the specific reporting.
- *"Why is this story flagged for limited evidence?"*: Explains observable warning signals (such as single-source reporting or missing publisher/date metadata).
- *"Which articles support this event?"*: Enumerates the corroborating articles with titles and publishers.
- General historical inquiries (*"What happened?", "What is covered?"*): Summarizes retrieved evidence while preserving existing grounded Q&A behavior.

### Guardrails and principles

- **Every AI answer includes supporting article IDs and source citations**: Answers cite real sources and their provenance references.
- **Fabricated-source prevention**: Hallucinated or non-existent article IDs are strictly rejected and stripped before answers are emitted.
- **Explicit insufficiency reporting**: If available sources do not provide sufficient information, the AI explicitly states that evidence is insufficient.
- **No truth/fake value judgments**: The AI never claims an article is definitely fake or definitely true unless the supplied evidence explicitly establishes that fact.
- **Zero invented data**: The AI never invents publishers, URLs, dates, people, or events.

## Verification dashboard and sources

The research workspace features a dedicated **Verification & Sources** dashboard combining source metadata, corroboration analysis, conflict signals, and warning explanations in a transparent user interface.

### Displayed verification information

For every research query, the dashboard shows:
1. **Original source**: Preserved direct links to original article URLs.
2. **Publisher**: Distinct publisher identification or transparent missing-publisher notice.
3. **Publication date**: Historical publication date or explicit date-unavailable notice.
4. **Source provider**: Identified metadata adapter (GDELT, NewsAPI, Mock, etc.).
5. **Number of independent sources**: Aggregated count of distinct, independent publishers covering the topic.
6. **Supporting reports**: Explicit status indicating corroboration across multiple independent publishers (*"Reported by multiple sources"*).
7. **Conflicting reports**: Transparent indicators when reporting contains disputes or contradictory statements (*"Reports contain differing information"*).
8. **Verification warnings**: Active warning indicators for coverage gaps (e.g. single-source reporting, incomplete metadata).
9. **Explanation of why a warning exists**: Clear, neutral editorial explanations detailing observable gaps (e.g. *"Publisher information is missing from the source record."*, *"Limited independent reporting available."*).

### Strict neutrality and non-judgmental guardrails

- **NO fake/real verdicts**: The system never labels articles as "fake" or "real", nor does it render truth judgments.
- **NO credibility scores**: Never computes or displays arbitrary trust scores or percentages.
- **NO publisher rankings**: Never ranks news outlets as trustworthy or untrustworthy.
- **NO political bias scores**: Does not infer, score, or display political alignment.
- **Clear disclaimer**: The dashboard explicitly reminds users that indicators represent observable verification signals based on retrieved metadata and reporting patterns, not definitive fact-checking verdicts.

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
