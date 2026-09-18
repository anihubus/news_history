(() => {
    const initializeSearch = () => {
        const searchForm = document.querySelector("#search-form");
        const searchInput = document.querySelector("#topic-search");
        const searchButton = searchForm?.querySelector("button[type='submit']");
        const searchStatus = document.querySelector("#search-status");
        const resultsCount = document.querySelector(".results-count");
        const emptyHeading = document.querySelector(".results-empty h3");
        const emptyMessage = document.querySelector(".results-empty p");

        if (!searchForm || !searchInput || !searchStatus) {
            return;
        }

        const showEmptyState = (heading, message, count = "No results yet") => {
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

        searchForm.addEventListener("submit", async (event) => {
            event.preventDefault();

            const query = searchInput.value.trim();
            if (!query) {
                searchStatus.textContent = "Enter a topic before searching.";
                searchInput.focus();
                return;
            }

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
                    throw new Error(data.error || "The search could not be completed.");
                }

                searchStatus.textContent = data.message;
                showEmptyState(
                    "No articles yet",
                    data.message,
                    `${data.results.length} results`
                );
            } catch (error) {
                searchStatus.textContent = error.message || "Unable to connect to the search service.";
                showEmptyState("Search unavailable", "Try again when the search service is available.");
            } finally {
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
