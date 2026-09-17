(() => {
    const initializeSearch = () => {
        const searchForm = document.querySelector("#search-form");
        const searchStatus = document.querySelector("#search-status");

        if (!searchForm || !searchStatus) {
            return;
        }

        searchForm.addEventListener("submit", (event) => {
            event.preventDefault();
            searchStatus.textContent = "Search functionality will be connected in the next step.";
        });
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initializeSearch);
    } else {
        initializeSearch();
    }
})();
document.addEventListener("DOMContentLoaded", () => {
    document.body.classList.add("js-loaded");
});
