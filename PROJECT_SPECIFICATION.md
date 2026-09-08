# News History

**Working title:** News History  
**Specification status:** Initial master specification  
**Scope:** Incremental development project; this document defines the product direction and first implementation boundaries.

## 1. Project Name

**News History** is a web application for discovering news about a topic and understanding how that topic developed over time.

The name is provisional and may be changed before public release.

## 2. Problem Statement

News about an important topic is usually distributed across many articles, publishers, dates, and perspectives. A user may be able to find individual articles through a search engine, but it is difficult to determine:

- Which articles are about the same underlying topic or event.
- How the topic changed over time.
- Which facts, events, and turning points came first.
- How different sources reported the same development.
- What information is available from the original source of a report.

News History will organize retrieved articles into a chronological, source-aware view that helps users move from isolated news stories to a basic historical understanding.

## 3. Project Objective

Build an incremental system that can retrieve, store, organize, and present news articles about a user-selected topic as a chronological history.

The initial objective is not to replace professional journalism or produce definitive historical conclusions. It is to provide a transparent research aid that:

- Shows relevant source articles and their publication dates.
- Groups articles that appear to concern the same topic or development.
- Produces a basic chronological timeline from available article metadata and content.
- Keeps article sources visible so users can inspect the underlying reporting.
- Establishes a foundation for progressively more capable NLP and knowledge features.

## 4. Target Users

### Primary users

- Students and researchers investigating a current or historical topic.
- Journalists and editors building background context.
- Analysts and policy professionals tracking an issue, organization, person, or event.
- Curious readers who want a concise history of a news topic.

### Secondary users

- Educators preparing classroom material about current events.
- Developers and researchers evaluating news retrieval, NLP, and timeline generation.

The first version should prioritize a clear research workflow over social features, personalization, or high-volume publishing workflows.

## 5. Core MVP Features

The MVP should deliver the following end-to-end capabilities:

1. **Search for a news topic**
   - Accept a topic, person, organization, event, or issue as a search query.
   - Validate and normalize the query sufficiently for retrieval.
   - Provide a simple search interface with loading, empty, and error states.

2. **Retrieve relevant news articles**
   - Use a replaceable news retrieval integration or provider adapter.
   - Retrieve article links and available metadata for the query.
   - Handle provider failures, rate limits, duplicate results, and incomplete responses.
   - Keep external-provider concerns out of the presentation layer.

3. **Store article metadata**
   - Persist normalized article records in SQLite initially.
   - Avoid storing duplicate articles when the same canonical URL is encountered.
   - Record retrieval time and provider information for traceability.

4. **Display articles chronologically**
   - Sort articles by publication date, with a clear fallback when the date is unknown.
   - Show publication date, title, publisher, source link, and available description or snippet.
   - Distinguish publication dates from the date on which News History retrieved an article.

5. **Identify and group related articles**
   - Implement a simple, explainable first grouping strategy, such as normalized query matching, shared keywords, or configurable text similarity.
   - Represent grouping as an explicit relationship rather than silently merging article records.
   - Make grouping behavior replaceable so semantic similarity can be added later.

6. **Construct a historical timeline**
   - Generate timeline entries from dated articles and related article groups.
   - Preserve links from each timeline entry to its supporting articles.
   - Clearly label the first version as an automatically assembled interpretation rather than verified historical fact.

7. **Display article sources**
   - Make the original publisher and article URL visible for every result.
   - Link users to the original article where permitted.
   - Do not imply that News History is the original publisher or authoritative source.

8. **Provide basic summaries**
   - Use available provider descriptions, article excerpts, or a deterministic short summary strategy for the MVP.
   - Clearly distinguish an excerpt from a generated summary.
   - Avoid presenting unsupported claims as facts.

### MVP quality requirements

- The application should remain usable when some articles lack descriptions, images, dates, or publisher names.
- Retrieval, persistence, grouping, and timeline generation should be independently testable.
- The UI should expose source provenance and uncertainty rather than hide it.
- The initial implementation should use only the stated stack and avoid premature NLP infrastructure.

## 6. Future and Advanced Features

These features are intentionally outside the first implementation slice:

- Semantic similarity using embeddings.
- Event detection and event clustering.
- Entity extraction for people, organizations, places, and concepts.
- A knowledge graph connecting entities, events, claims, and sources.
- AI-generated summaries with citations and source grounding.
- Retrieval-augmented generation (RAG) question answering over collected sources.
- Source reliability analysis and source diversity indicators.
- An interactive, zoomable timeline with event expansion and filtering.
- Related topics, people, organizations, and events.
- Multiple languages, including multilingual retrieval and summarization.
- User accounts, saved investigations, annotations, and sharing.
- Scheduled refreshes and change tracking for long-running topics.
- Human review workflows for correcting groups, dates, and timeline entries.

Advanced features should be added only after the MVP has stable source attribution, data quality checks, and clear evaluation criteria.

## 7. Initial Technology Stack

### Backend

- **Python**
- **Flask** for HTTP routing and application structure

### Frontend

- **HTML** for document structure
- **CSS** for layout and presentation
- **JavaScript** for search interactions, loading states, filtering, and timeline rendering

### Database

- **SQLite** initially, accessed through a small repository or data-access layer

### Expected supporting choices

The implementation may use Python standard-library capabilities and carefully selected dependencies when needed, but package installation is not part of this specification task. The first implementation should keep provider clients, database access, domain logic, and Flask routes separated.

### Potential future technologies

- PostgreSQL for production-scale persistence and concurrent workloads.
- spaCy for entity extraction and NLP pipelines.
- Sentence Transformers for semantic embeddings and similarity.
- FAISS or pgvector for vector search.
- Neo4j for a knowledge graph.
- An LLM API for grounded summaries and question answering.

Technology changes should be justified by a concrete product or scale requirement rather than introduced in advance.

## 8. High-Level System Architecture

The initial request flow is:

```text
User
   |
Frontend
   |
Flask API / Backend
   |
Search Orchestrator
   |-- News Provider Adapter
   |-- Article Normalizer
   `-- Database / Repository
   |
Relationship & Grouping Service
   |
Timeline Generation Service
   |
Response
   |
Frontend
```

The Search Orchestrator coordinates the major application services. Flask routes should validate and forward requests, then return results; they should not contain the business logic for retrieval, persistence, grouping, or timeline construction.

The MVP remains a single Flask application with clearly separated internal modules. It does not introduce microservices, Docker, Kubernetes, message queues, Redis, Neo4j, FAISS, PostgreSQL, or LLM APIs at this stage. Those technologies remain possible future options where they are already identified in this specification.

### Architectural responsibilities

- **Frontend:** Collect the search query, submit requests, display loading and error states, and render results, source details, summaries, groups, and timeline entries.
- **Flask API / backend:** Handle HTTP concerns, validate requests, invoke the Search Orchestrator, and return a stable response shape. Routes remain thin and do not directly contain application or domain logic.
- **Search Orchestrator:** Receive a validated search request; coordinate news retrieval; pass provider results through article normalization; persist normalized articles; retrieve relevant stored articles when appropriate; invoke relationship/grouping and timeline generation services; and return a normalized result to the Flask route layer.
- **News Provider Adapter:** Query an external news source and isolate provider-specific authentication, pagination, rate limits, errors, and response formats.
- **Article Normalizer:** Convert provider results into the internal article model, normalize URLs and dates, and apply basic data-quality and duplicate-detection rules.
- **Database / repository:** Persist and retrieve normalized article metadata, searches, relationships, and generated timeline data without exposing persistence details to services.
- **Relationship & grouping service:** Start with deterministic rules and simple similarity signals; later support embeddings, semantic similarity, entity extraction, and event detection behind replaceable service components.
- **Timeline generation service:** Convert dated article and relationship data into ordered timeline entries while retaining supporting article references. A future summary capability should similarly evolve from metadata/excerpts to grounded AI/RAG behind a replaceable service boundary.

The system should treat external article providers as untrusted and variable inputs. Provider-specific fields should be normalized at the boundary, and missing or conflicting values should be preserved or flagged rather than silently invented.

### Data flow

The normalized data flow is:

```text
External Provider
   -> Provider Adapter
   -> Normalized Article
   -> Repository / Database
   -> Processing Services
   -> Timeline / Result Model
   -> API Response
   -> Frontend
```

Provider-specific response formats must never leak into the frontend or core business logic. The adapter and normalizer form the boundary between external infrastructure and the application’s internal models.

### Architectural principle

**Separate infrastructure concerns from domain logic.**

- Flask handles HTTP.
- Provider adapters handle external news services.
- Repositories handle persistence.
- Services handle application and domain logic.
- The frontend handles presentation.
- Future AI/NLP components should be replaceable.

This separation allows the MVP to remain simple while making later processing strategies replaceable. The relationship flow is therefore:

```text
Search Orchestrator
   -> Relationship Service
   -> Current implementation: deterministic grouping
   -> Future implementation: embeddings / semantic similarity / event detection
```

Similarly, the timeline and summary flow is:

```text
Timeline / Summary Service
   -> Current implementation: metadata / excerpts
   -> Future implementation: grounded AI / RAG
```

## 9. Expected User Flow

1. The user opens News History and sees a search field and a short explanation of the result view.
2. The user enters a topic, person, organization, event, or issue.
3. The frontend sends the query to the Flask API / backend.
4. The Flask route validates the request and passes it to the Search Orchestrator.
5. The Search Orchestrator retrieves relevant articles, normalizes their metadata, and stores new or updated records in SQLite.
6. The Search Orchestrator retrieves relevant stored articles when appropriate and invokes the relationship/grouping service.
7. The Search Orchestrator invokes timeline generation and returns a normalized result through the Flask route.
8. The frontend displays:
   - The searched topic.
   - The chronological timeline.
   - Article groups or related developments.
   - Basic summaries or excerpts.
   - Publication dates and publishers.
   - Links to the original sources.
9. The user opens source links to inspect the reporting and compares articles covering the same development.
10. When data is incomplete, the UI communicates the limitation and continues displaying the usable results.

A later version may allow users to refine date ranges, select sources, correct relationships, save searches, and ask questions about the collected history.

## 10. Major Backend Components

1. **Flask application and route layer**
   - Define the initial web routes and JSON or server-rendered response boundaries.
   - Validate inputs and map application errors to useful user-facing responses.

2. **Search orchestration service**
   - Receive a validated search request from the Flask route layer.
   - Coordinate news retrieval, article normalization, persistence, and retrieval of relevant stored articles when appropriate.
   - Invoke the relationship/grouping service and timeline generation service.
   - Return a normalized result to the Flask route layer.
   - Keep request handling thin and application logic testable without an HTTP server. The Flask route must not contain this business logic.

3. **News provider adapter**
   - Encapsulate external provider requests, authentication configuration, pagination, rate limits, and provider errors.
   - Expose a normalized internal article format.

4. **Article normalization service**
   - Normalize URLs, dates, publisher names, titles, descriptions, and provider identifiers.
   - Apply basic duplicate detection and data-quality rules.

5. **Article repository and database layer**
   - Encapsulate SQLite queries and transactions.
   - Support storing and retrieving articles, searches, relationships, and timeline data without coupling domain code to SQL details.

6. **Relationship and grouping service**
   - Apply the MVP grouping strategy.
   - Record relationship type, confidence or rationale where available, and the articles involved.

7. **Timeline generation service**
   - Order relevant material by publication date.
   - Produce timeline entries with supporting article references and clear handling for uncertain dates.

8. **Summary service**
   - Provide excerpts or basic deterministic summaries for the MVP.
   - Define an interface that can later support grounded LLM summaries.

9. **Configuration and observability**
   - Load provider credentials and environment-specific settings without hard-coding secrets.
   - Log retrieval failures and processing outcomes without logging sensitive credentials.

## 11. Major Frontend Components

1. **Search view**
   - Query input, submit action, validation, and accessible status messaging.

2. **Search state management**
   - Loading, success, empty results, partial results, provider errors, and retry states.

3. **Timeline view**
   - Chronological entries with dates, titles, summaries or excerpts, and supporting source links.

4. **Article list or group view**
   - Display individual articles and related article groups.
   - Support scanning and comparison without hiding source identity.

5. **Article card or article detail component**
   - Show title, publisher, publication date, description, source URL, and any available metadata.

6. **Source attribution component**
   - Consistently identify the original publisher and make the external source link clear.

7. **Filtering and sorting controls**
   - Provide basic chronological ordering and, when useful, date or source filtering without overloading the MVP.

8. **Error and empty-state components**
   - Explain what happened and provide a practical next action, such as refining the query or retrying.

9. **Responsive layout and accessibility foundation**
   - Support desktop and mobile reading.
   - Use semantic HTML, keyboard-accessible controls, visible focus states, and readable date/source presentation.

## 12. Data That Will Need to Be Stored

The exact schema will be designed in a later implementation task. The system will likely need the following logical records.

### Search

- Search identifier.
- Original query text.
- Normalized query text.
- Search creation time.
- Retrieval status and error information, where applicable.
- Provider or provider set used.

### Article

- Internal article identifier.
- Canonical URL and, when available, provider-specific identifier.
- Title.
- Publisher or source name.
- Author, if available.
- Publication date and date precision or unknown-date indicator.
- Description, excerpt, or snippet.
- Retrieved content fields, only where legally and technically appropriate.
- Image URL, if available and needed by the UI.
- First-seen and last-retrieved timestamps.
- Raw provider reference or normalized provider metadata needed for debugging.

### Search-to-article relationship

- Search identifier.
- Article identifier.
- Retrieval rank or relevance score, if supplied.
- Match or retrieval reason.

### Article relationship or group

- Group identifier or relationship identifier.
- Article identifiers.
- Relationship type, such as related topic or possible same event.
- Confidence score and/or explainable matching signals.
- Creation and update timestamps.

### Timeline entry

- Timeline entry identifier.
- Topic or search context.
- Display date and date precision.
- Title or event label.
- Basic summary or excerpt.
- Supporting article identifiers.
- Generation method and generation timestamp.
- Any uncertainty or review status.

Data retention, copyright constraints, provider terms, privacy, and deletion behavior must be considered before storing full article text. The MVP should prefer metadata and permitted excerpts unless a clear use case and legal basis support more.

## 13. Major Technical Challenges

1. **News retrieval quality**
   - Search providers differ in coverage, ranking, quotas, metadata quality, and licensing terms.

2. **Duplicate and canonical article detection**
   - The same article may appear under tracking URLs, syndicated URLs, updated URLs, or multiple provider records.

3. **Publication date accuracy**
   - Dates can be missing, timezone-dependent, updated after publication, or confused with crawl dates.

4. **Relevance and grouping**
   - Shared keywords do not necessarily mean that articles describe the same event. The MVP must be useful without overstating confidence.

5. **Timeline interpretation**
   - A chronological list of articles is not automatically a verified history. The product must separate source reporting from generated interpretation.

6. **Source attribution and legal constraints**
   - The application must respect provider terms, publisher rights, copyright, robots policies where applicable, and link or excerpt restrictions.

7. **Conflicting or incomplete reporting**
   - Sources may disagree or describe different aspects of an event. The system should preserve source distinctions instead of collapsing them into a single claim.

8. **Summary reliability**
   - Summaries can omit context or introduce unsupported statements. Early summaries should be conservative, traceable, and visibly tied to source material.

9. **External service resilience**
   - Timeouts, quotas, malformed responses, outages, and provider changes must not make the entire application unusable.

10. **Evaluation**
   - Relevance, grouping accuracy, timeline quality, source diversity, and summary usefulness need representative test queries and human review.

11. **Scaling and migration**
   - SQLite is appropriate for initial development but may need to be replaced by PostgreSQL as concurrency, history volume, and background processing grow.

## 14. Development Roadmap

### Phase 0: Specification and decisions

- Confirm the product vocabulary, MVP boundaries, source policy, and initial news provider strategy.
- Define success criteria and a small evaluation set of representative topics.
- Decide whether the first UI uses server-rendered HTML, browser-side fetches, or a small hybrid approach.

### Phase 1: Project foundation

- Create a single Flask application with clearly separated internal modules for routes, orchestration, adapters, repositories, and services.
- Establish HTML, CSS, and JavaScript entry points.
- Add an initial SQLite connection and migration or schema-management strategy.
- Define internal article and search data contracts.
- Add basic automated test structure.

### Phase 2: Search and retrieval

- Build the search page and request flow.
- Implement a provider adapter using configuration rather than hard-coded credentials.
- Normalize provider responses into the internal article format.
- Route the workflow through the Search Orchestrator rather than placing business logic in Flask routes.
- Add timeout, error, empty-result, and duplicate-handling behavior.

### Phase 3: Persistence and chronological results

- Persist searches and article metadata.
- Retrieve stored article records for a search.
- Display articles chronologically with publisher names, dates, summaries or excerpts, and original source links.
- Add tests for missing fields, duplicate URLs, invalid dates, and provider failures.

### Phase 4: MVP grouping and timeline

- Implement the first explainable related-article grouping strategy behind the relationship service boundary.
- Add confidence or rationale fields where feasible.
- Generate timeline entries from grouped and dated articles through the timeline generation service.
- Render the timeline and supporting articles together.
- Evaluate results against the representative query set and document known limitations.

### Phase 5: MVP hardening

- Improve accessibility, responsive behavior, validation, logging, and security configuration.
- Add caching or controlled reuse of recent retrievals where provider terms allow it.
- Review source attribution, content storage, retention, and error messaging.
- Add monitoring for retrieval failures and data-quality regressions.

### Phase 6: Advanced research features

- Add embeddings and semantic similarity behind a replaceable similarity interface.
- Introduce entity extraction and event detection.
- Add richer event and entity relationships, potentially backed by a knowledge graph.
- Add grounded AI summaries and RAG question answering with citations and evaluation safeguards.
- Add source reliability and diversity analysis.
- Support interactive timelines, related topics, multilingual workflows, and user accounts as validated needs emerge.

Each phase should produce a usable increment, include focused tests, and preserve the ability to inspect original sources. No advanced feature should be considered complete without an evaluation method and a clear explanation of its uncertainty.
