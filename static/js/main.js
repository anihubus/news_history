(() => {
    const initializeSearch = () => {
        const searchForm = document.querySelector("#search-form");
        const searchInput = document.querySelector("#topic-search");
        const searchButton = searchForm?.querySelector("button[type='submit']");
        const searchStatus = document.querySelector("#search-status");
        const resultsCount = document.querySelector(".results-count");
        const emptyState = document.querySelector(".results-empty");
        const resultsList = document.querySelector("#results-list");
        const groupsList = document.querySelector("#groups-list");
        const timelineList = document.querySelector("#timeline-list");
        const timelineEmpty = document.querySelector("#timeline-empty");
        const summaryContent = document.querySelector("#summary-content");
        const questionForm = document.querySelector("#question-form");
        const questionInput = document.querySelector("#question-input");
        const questionStatus = document.querySelector("#question-status");
        let activeQuery = "";
        let requestInProgress = false;
        const rateLimitMessage = "The news provider is temporarily rate-limited. Please wait a few seconds and try again.";
        const providerErrorMessage = "The news provider is temporarily unavailable.";

        if (!searchForm || !searchInput || !searchStatus || !resultsList) {
            return;
        }

        const showEmptyState = (heading, message, count = "No results yet") => {
            emptyState?.classList.remove("is-hidden");
            const emptyHeading = emptyState?.querySelector("h3");
            const emptyMessage = emptyState?.querySelector("p");

            if (emptyHeading) {
                emptyHeading.textContent = heading;
            }
            if (emptyMessage) {
                emptyMessage.textContent = message;
            }
            if (resultsCount) {
                resultsCount.textContent = count;
            }
        };

        const clearResults = () => {
            resultsList.replaceChildren();
            groupsList?.replaceChildren();
            timelineList?.replaceChildren();
            if (summaryContent) {
                summaryContent.textContent = "A summary will appear after a search.";
            }
            if (timelineEmpty) {
                timelineEmpty.textContent = "Timeline entries will appear after a search.";
                timelineEmpty.classList.remove("is-hidden");
            }
            emptyState?.classList.add("is-hidden");
        };

        const renderGroups = (groups) => {
            if (!groupsList) {
                return;
            }
            groupsList.replaceChildren();
            groups.filter((group) => group.article_count > 1).forEach((group, index) => {
                const section = document.createElement("section");
                section.className = "article-group";

                const heading = document.createElement("h3");
                heading.textContent = `Related group ${index + 1}: ${group.representative_title}`;

                const note = document.createElement("p");
                note.className = "group-note";
                note.textContent = "AUTOMATIC GROUPING: Automatically grouped based on article similarity.";

                const sources = document.createElement("p");
                sources.className = "provenance-sources";
                sources.textContent = "Supporting sources: ";
                (group.sources || []).forEach((source, sourceIndex) => {
                    const link = document.createElement("a");
                    link.textContent = source.url
                        ? (source.title || `Source ${sourceIndex + 1}`)
                        : "Original source unavailable";
                    if (source.url) {
                        link.href = source.url;
                        link.target = "_blank";
                        link.rel = "noopener noreferrer";
                    }
                    sources.append(link);
                    if (sourceIndex < group.sources.length - 1) sources.append(" · ");
                });

                section.append(heading, note, sources);
                groupsList.append(section);
            });
        };

        const renderTimeline = (timeline) => {
            if (!timelineList || !timelineEmpty) {
                return;
            }
            timelineList.replaceChildren();
            timelineEmpty.classList.toggle("is-hidden", timeline.length > 0);
            if (timeline.length === 0) {
                timelineEmpty.textContent = "No timeline entries could be assembled from these results.";
                return;
            }

            timeline.forEach((entry) => {
                const item = document.createElement("article");
                item.className = "timeline-entry";

                const date = document.createElement("time");
                date.className = "timeline-date";
                date.textContent = entry.date || "Date unavailable";

                const content = document.createElement("div");
                const title = document.createElement("h3");
                title.textContent = entry.title;
                const description = document.createElement("p");
                description.textContent = entry.description || "Automatically assembled from available article metadata.";
                const sourceNote = document.createElement("p");
                sourceNote.className = "timeline-source-note";
                sourceNote.textContent = `${entry.article_ids.length} supporting article${entry.article_ids.length === 1 ? "" : "s"}`;
                const sources = document.createElement("p");
                sources.className = "timeline-sources";
                const supportingSources = entry.supporting_sources || entry.supporting_articles || [];
                sources.textContent = "Supporting sources: ";
                supportingSources.forEach((article, index) => {
                    const link = document.createElement("a");
                    link.href = article.url;
                    link.target = "_blank";
                    link.rel = "noopener noreferrer";
                    link.textContent = `Source ${index + 1}`;
                    sources.append(link);
                    if (index < supportingSources.length - 1) {
                        sources.append(" · ");
                    }
                });
                content.append(title, description, sourceNote, sources);
                item.append(date, content);
                timelineList.append(item);
            });
        };

        const renderSummary = (summary) => {
            if (!summaryContent) {
                return;
            }
            summaryContent.replaceChildren();
            if (!summary?.summary) {
                summaryContent.textContent = "Summary temporarily unavailable.";
                return;
            }
            summaryContent.textContent = summary.summary;
            const sources = document.createElement("p");
            sources.className = "provenance-sources";
            sources.textContent = "Supporting sources: ";
            (summary.sources || []).forEach((source, index) => {
                const link = document.createElement("a");
                    link.textContent = source.url
                        ? (source.title || `Source ${index + 1}`)
                        : "Original source unavailable";
                    if (source.url) {
                        link.href = source.url;
                        link.target = "_blank";
                        link.rel = "noopener noreferrer";
                    }
                sources.append(link);
                if (index < summary.sources.length - 1) sources.append(" · ");
            });
            summaryContent.append(sources);
        };

        const createArticleCard = (article) => {
            const card = document.createElement("article");
            card.className = "article-card";

            const source = document.createElement("p");
            source.className = "article-source";
            source.textContent = `${article.publisher || "Publisher unavailable"} · Source provider: ${article.source_provider || "Unavailable"}`;

            const title = document.createElement("h3");
            const link = document.createElement("a");
            link.href = article.url;
            link.target = "_blank";
            link.rel = "noopener noreferrer";
            link.textContent = article.title;
            title.append(link);

            const date = document.createElement("p");
            date.className = "article-date";
            date.textContent = article.publication_date || "Publication date unavailable";

            const originalSource = document.createElement("a");
            originalSource.className = "original-source";
            originalSource.textContent = article.url ? "Original source" : "Original source unavailable";
            if (article.url) {
                originalSource.href = article.url;
                originalSource.target = "_blank";
                originalSource.rel = "noopener noreferrer";
            }

            const retrieved = document.createElement("p");
            retrieved.className = "article-retrieved";
            retrieved.textContent = article.retrieved_at
                ? `Retrieved by News History: ${article.retrieved_at}`
                : "Retrieval time unavailable";

            card.append(source, title, date, originalSource, retrieved);
            return card;
        };

        const renderResults = (articles) => {
            clearResults();
            articles.forEach((article) => resultsList.append(createArticleCard(article)));
            if (resultsCount) {
                resultsCount.textContent = `${articles.length} results`;
            }
        };

        searchForm.addEventListener("submit", async (event) => {
            event.preventDefault();

            if (requestInProgress) {
                return;
            }

            const query = searchInput.value.trim();
            if (!query) {
                searchStatus.textContent = "Enter a topic before searching.";
                searchInput.focus();
                return;
            }

            requestInProgress = true;
            activeQuery = query;
            searchStatus.textContent = "Searching...";
            searchButton?.setAttribute("disabled", "disabled");

            try {
                const response = await fetch("/api/search", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ query }),
                });
                const data = await response.json();

                if (!response.ok || !data.success) {
                    if (response.status === 429 || data.status === "rate_limited") {
                        throw new Error(rateLimitMessage);
                    }
                    throw new Error(providerErrorMessage);
                }

                if (data.results.length === 0) {
                    showEmptyState(
                        "No articles found",
                        "No matching coverage was returned for this search.",
                        "0 results"
                    );
                    resultsList.replaceChildren();
                    groupsList?.replaceChildren();
                    renderTimeline([]);
                    renderSummary(null);
                    searchStatus.textContent = "No articles were returned by the provider.";
                } else {
                    renderResults(data.results);
                    renderGroups(data.groups || []);
                    renderTimeline(data.timeline || []);
                    renderSummary(data.summary);
                    searchStatus.textContent = data.provider_status === "rate_limited"
                        ? `${data.results.length} stored articles found. The provider is temporarily rate-limited.`
                        : data.provider_status === "provider_unavailable"
                            ? `${data.results.length} stored articles found. The provider is temporarily unavailable.`
                            : `${data.results.length} articles found.`;
                }
            } catch (error) {
                showEmptyState("Search unavailable", "Try again when the news provider is available.");
                resultsList.replaceChildren();
                groupsList?.replaceChildren();
                renderSummary(null);
                searchStatus.textContent = error.message === rateLimitMessage
                    ? rateLimitMessage
                    : providerErrorMessage;
            } finally {
                requestInProgress = false;
                searchButton?.removeAttribute("disabled");
            }
        });

        questionForm?.addEventListener("submit", async (event) => {
            event.preventDefault();
            const question = questionInput?.value.trim();
            if (!question || !activeQuery) {
                questionStatus.textContent = "Search for a topic before asking a question.";
                return;
            }
            questionStatus.textContent = "Preparing an answer from the available sources...";
            try {
                const response = await fetch("/api/question", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ question, query: activeQuery }),
                });
                const data = await response.json();
                questionStatus.textContent = data.success
                    ? `${data.answer} Supporting sources: ${(data.sources || []).map((source) => source.title).join(", ") || "none"}.`
                    : data.error;
            } catch (error) {
                questionStatus.textContent = "Answer temporarily unavailable.";
            }
        });
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initializeSearch);
    } else {
        initializeSearch();
    }
})();
