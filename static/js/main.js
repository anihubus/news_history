(() => {
    const initializeSearch = () => {
        const searchForm = document.querySelector("#search-form");
        const searchInput = document.querySelector("#topic-search");
        const searchButton = searchForm?.querySelector("button[type='submit']");
        const searchStatus = document.querySelector("#search-status");
        const resultsCount = document.querySelector(".results-count");
        const emptyState = document.querySelector(".results-empty");
        const resultsList = document.querySelector("#results-list");
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
            emptyState?.classList.add("is-hidden");
        };

        const createArticleCard = (article) => {
            const card = document.createElement("article");
            card.className = "article-card";

            const source = document.createElement("p");
            source.className = "article-source";
            source.textContent = `${article.publisher || "Unknown source"} · External source`;

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

            card.append(source, title, date);
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
                    searchStatus.textContent = "No articles were returned by the provider.";
                } else {
                    renderResults(data.results);
                    searchStatus.textContent = `${data.results.length} articles found.`;
                }
            } catch (error) {
                showEmptyState("Search unavailable", "Try again when the news provider is available.");
                resultsList.replaceChildren();
                searchStatus.textContent = error.message === rateLimitMessage
                    ? rateLimitMessage
                    : providerErrorMessage;
            } finally {
                requestInProgress = false;
                searchButton?.removeAttribute("disabled");
            }
        });
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initializeSearch);
    } else {
        initializeSearch();
    }
})();
