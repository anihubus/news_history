(() => {
    // Utility to format raw provider timestamps (e.g. 20260918090000 or 20260918 or ISO)
    const formatTimestamp = (raw) => {
        if (!raw) return "Publication date unavailable";
        const str = String(raw).trim();
        if (/^\d{14}$/.test(str)) {
            const year = str.slice(0, 4);
            const month = str.slice(4, 6);
            const day = str.slice(6, 8);
            const hour = str.slice(8, 10);
            const min = str.slice(10, 12);
            return `${year}-${month}-${day} ${hour}:${min} UTC`;
        }
        if (/^\d{8}$/.test(str)) {
            const year = str.slice(0, 4);
            const month = str.slice(4, 6);
            const day = str.slice(6, 8);
            return `${year}-${month}-${day}`;
        }
        if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(str)) {
            const datePart = str.slice(0, 10);
            const timePart = str.slice(11, 16);
            return `${datePart} ${timePart} UTC`;
        }
        return str;
    };

    // Live UTC Clock
    const initLiveClock = () => {
        const clockEl = document.querySelector("#live-clock");
        if (!clockEl) return;
        const update = () => {
            const now = new Date();
            const utc = now.toUTCString().split(" ")[4];
            clockEl.textContent = utc ? `${utc} UTC` : now.toISOString().slice(11, 19) + " UTC";
        };
        update();
        setInterval(update, 1000);
    };

    const initializeSearch = () => {
        const searchForm = document.querySelector("#search-form");
        const searchInput = document.querySelector("#topic-search");
        const searchButton = searchForm?.querySelector("button[type='submit']");
        const searchStatus = document.querySelector("#search-status");
        const searchStatusDot = document.querySelector("#search-status-dot");
        const progressBar = document.querySelector("#system-progress");
        const clearBtn = document.querySelector("#clear-search-btn");
        const resultsCountAll = document.querySelectorAll(".results-count");
        const emptyState = document.querySelector(".results-empty");
        const resultsList = document.querySelector("#results-list");
        const groupsList = document.querySelector("#groups-list");
        const timelineList = document.querySelector("#timeline-list");
        const timelineEmpty = document.querySelector("#timeline-empty");
        const timelineEmptyCard = document.querySelector("#timeline-empty-card");
        const summaryContent = document.querySelector("#summary-content");
        const questionForm = document.querySelector("#question-form");
        const questionInput = document.querySelector("#question-input");
        const questionStatus = document.querySelector("#question-status");
        const btnSpinner = searchButton?.querySelector(".btn-spinner");

        let activeQuery = "";
        let requestInProgress = false;
        const rateLimitMessage = "The news provider is temporarily rate-limited. Please wait a few seconds and try again.";
        const providerErrorMessage = "The news provider is temporarily unavailable.";

        if (!searchForm || !searchInput || !searchStatus || !resultsList) {
            return;
        }

        initLiveClock();

        // View Tabs switching
        const viewTabs = document.querySelectorAll(".view-tabs .tab-btn");
        const timelineContainer = document.querySelector("#timeline-view-container");
        const sourcesContainer = document.querySelector("#sources-view-container");

        viewTabs.forEach((tab) => {
            tab.addEventListener("click", () => {
                viewTabs.forEach((t) => {
                    t.classList.remove("is-active");
                    t.setAttribute("aria-selected", "false");
                });
                tab.classList.add("is-active");
                tab.setAttribute("aria-selected", "true");

                const view = tab.dataset.view;
                if (view === "all") {
                    timelineContainer?.classList.remove("is-hidden");
                    sourcesContainer?.classList.remove("is-hidden");
                } else if (view === "timeline") {
                    timelineContainer?.classList.remove("is-hidden");
                    sourcesContainer?.classList.add("is-hidden");
                } else if (view === "sources") {
                    timelineContainer?.classList.add("is-hidden");
                    sourcesContainer?.classList.remove("is-hidden");
                }
            });
        });

        // Clear button handling
        const updateClearBtn = () => {
            if (clearBtn) {
                clearBtn.classList.toggle("is-hidden", !searchInput.value);
            }
        };
        searchInput.addEventListener("input", updateClearBtn);
        clearBtn?.addEventListener("click", () => {
            searchInput.value = "";
            updateClearBtn();
            searchInput.focus();
        });

        // Quick topic preset buttons
        document.querySelectorAll(".preset-chip").forEach((chip) => {
            chip.addEventListener("click", () => {
                const query = chip.dataset.query;
                if (!query) return;
                searchInput.value = query;
                updateClearBtn();
                if (typeof searchForm.requestSubmit === "function") {
                    searchForm.requestSubmit();
                } else {
                    searchButton?.click();
                }
            });
        });

        // Keyboard Shortcut: Cmd+K or / to focus search
        window.addEventListener("keydown", (e) => {
            if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
                e.preventDefault();
                searchInput.focus();
                searchInput.select();
            } else if (e.key === "/" && document.activeElement !== searchInput && document.activeElement !== questionInput) {
                e.preventDefault();
                searchInput.focus();
                searchInput.select();
            }
        });

        const updateResultsCount = (text) => {
            resultsCountAll.forEach((el) => {
                el.textContent = text;
            });
        };

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
            updateResultsCount(count);
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
            if (timelineEmptyCard) {
                timelineEmptyCard.classList.remove("is-hidden");
            }
            emptyState?.classList.add("is-hidden");
        };

        const renderGroups = (groups) => {
            if (!groupsList) {
                return;
            }
            groupsList.replaceChildren();

            const multiArticleGroups = groups.filter((group) => group.article_count > 1);
            if (multiArticleGroups.length === 0) {
                const emptyWrap = document.createElement("div");
                emptyWrap.className = "groups-empty-placeholder";
                const emptyText = document.createElement("p");
                emptyText.className = "subtle-text";
                emptyText.textContent = "No multi-article clusters detected for this topic.";
                emptyWrap.append(emptyText);
                groupsList.append(emptyWrap);
                return;
            }

            multiArticleGroups.forEach((group, index) => {
                const section = document.createElement("section");
                section.className = "article-group";

                const heading = document.createElement("h3");
                heading.textContent = `Cluster ${index + 1}: ${group.representative_title}`;

                const note = document.createElement("p");
                note.className = "group-note";
                note.textContent = `THEMATIC CLUSTER: ${group.article_count} articles grouped on content similarity`;

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
            const hasEntries = timeline.length > 0;
            timelineEmpty.classList.toggle("is-hidden", hasEntries);
            if (timelineEmptyCard) {
                timelineEmptyCard.classList.toggle("is-hidden", hasEntries);
            }

            if (!hasEntries) {
                timelineEmpty.textContent = "No timeline entries could be assembled from these results.";
                return;
            }

            timeline.forEach((entry) => {
                const item = document.createElement("article");
                item.className = "timeline-entry";

                const date = document.createElement("time");
                date.className = "timeline-date font-mono";
                date.textContent = formatTimestamp(entry.date);

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
                    link.textContent = article.publisher || `Source ${index + 1}`;
                    sources.append(link);
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
                    ? (source.publisher || source.title || `Source ${index + 1}`)
                    : "Original source unavailable";
                if (source.url) {
                    link.href = source.url;
                    link.target = "_blank";
                    link.rel = "noopener noreferrer";
                }
                sources.append(link);
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
            date.textContent = formatTimestamp(article.publication_date);

            const originalSource = document.createElement("a");
            originalSource.className = "original-source";
            originalSource.textContent = article.url ? "Original source ↗" : "Original source unavailable";
            if (article.url) {
                originalSource.href = article.url;
                originalSource.target = "_blank";
                originalSource.rel = "noopener noreferrer";
            }

            const retrieved = document.createElement("p");
            retrieved.className = "article-retrieved";
            retrieved.textContent = article.retrieved_at
                ? `Retrieved by News History: ${formatTimestamp(article.retrieved_at)}`
                : "Retrieval time unavailable";

            card.append(source, title, date, originalSource, retrieved);
            return card;
        };

        const renderResults = (articles) => {
            clearResults();
            articles.forEach((article) => resultsList.append(createArticleCard(article)));
            updateResultsCount(`${articles.length} article${articles.length === 1 ? "" : "s"} indexed`);
        };

        const setLoadingState = (isLoading) => {
            if (isLoading) {
                searchButton?.setAttribute("disabled", "disabled");
                btnSpinner?.classList.remove("is-hidden");
                progressBar?.classList.add("is-active");
                if (searchStatusDot) {
                    searchStatusDot.className = "status-indicator-dot dot-searching";
                }
            } else {
                searchButton?.removeAttribute("disabled");
                btnSpinner?.classList.add("is-hidden");
                progressBar?.classList.remove("is-active");
                if (searchStatusDot) {
                    searchStatusDot.className = "status-indicator-dot dot-idle";
                }
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
            searchStatus.textContent = "Searching index and reconstructing chronology...";
            setLoadingState(true);

            try {
                const currentUrl = new URL(window.location);
                currentUrl.searchParams.set("topic", query);
                window.history.replaceState({}, "", currentUrl);

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
                    if (searchStatusDot) searchStatusDot.className = "status-indicator-dot dot-idle";
                } else {
                    renderResults(data.results);
                    renderGroups(data.groups || []);
                    renderTimeline(data.timeline || []);
                    renderSummary(data.summary);
                    searchStatus.textContent = data.provider_status === "rate_limited"
                        ? `${data.results.length} stored articles found. The provider is temporarily rate-limited.`
                        : data.provider_status === "provider_unavailable"
                            ? `${data.results.length} stored articles found. The provider is temporarily unavailable.`
                            : `${data.results.length} articles indexed and aligned to chronological timeline.`;
                    if (searchStatusDot) searchStatusDot.className = "status-indicator-dot dot-online";
                }
            } catch (error) {
                showEmptyState("Search unavailable", "Try again when the news provider is available.");
                resultsList.replaceChildren();
                groupsList?.replaceChildren();
                renderSummary(null);
                searchStatus.textContent = error.message === rateLimitMessage
                    ? rateLimitMessage
                    : providerErrorMessage;
                if (searchStatusDot) searchStatusDot.className = "status-indicator-dot dot-error";
            } finally {
                requestInProgress = false;
                setLoadingState(false);
            }
        });

        questionForm?.addEventListener("submit", async (event) => {
            event.preventDefault();
            const question = questionInput?.value.trim();
            if (!question || !activeQuery) {
                questionStatus.textContent = "Search for a topic before asking a question.";
                return;
            }
            questionStatus.textContent = "Synthesizing answer from verified sources...";
            const questionBtn = questionForm.querySelector("button[type='submit']");
            questionBtn?.setAttribute("disabled", "disabled");

            try {
                const response = await fetch("/api/question", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ question, query: activeQuery }),
                });
                const data = await response.json();
                questionStatus.textContent = data.success
                    ? `${data.answer} [Supporting sources: ${(data.sources || []).map((source) => source.title).join(", ") || "none"}]`
                    : (data.error || "Query could not be answered.");
            } catch (error) {
                questionStatus.textContent = "Answer temporarily unavailable.";
            } finally {
                questionBtn?.removeAttribute("disabled");
            }
        });

        // Hydrate from URL query param if present
        const urlParams = new URLSearchParams(window.location.search);
        const initialQuery = urlParams.get("topic");
        if (initialQuery && !searchInput.value) {
            searchInput.value = initialQuery;
            updateClearBtn();
            if (typeof searchForm.requestSubmit === "function") {
                searchForm.requestSubmit();
            } else {
                searchButton?.click();
            }
        }
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initializeSearch);
    } else {
        initializeSearch();
    }
})();
