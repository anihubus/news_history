/**
 * News History — Minimal Editorial Frontend
 * Handles landing, serene loading, chronological timeline tree, article expansion,
 * grounded Q&A, provenance tracking, and cross-source verification signals.
 */
(() => {
    "use strict";

    // Date formatting helper for GDELT / ISO / YYYYMMDD timestamps
    const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

    const formatDisplayDate = (rawDate) => {
        if (!rawDate) return "Date not specified";
        const str = String(rawDate).trim();

        // Format: YYYYMMDDHHMMSS or YYYYMMDD
        if (/^\d{8,14}$/.test(str)) {
            const year = parseInt(str.slice(0, 4), 10);
            const monthIdx = parseInt(str.slice(4, 6), 10) - 1;
            const day = parseInt(str.slice(6, 8), 10);
            if (monthIdx >= 0 && monthIdx < 12 && day >= 1 && day <= 31) {
                return `${MONTHS[monthIdx]} ${day}, ${year}`;
            }
            return `${str.slice(0, 4)}-${str.slice(4, 6)}-${str.slice(6, 8)}`;
        }

        // Format: YYYY-MM-DD or ISO
        const isoMatch = str.match(/^(\d{4})-(\d{2})-(\d{2})/);
        if (isoMatch) {
            const year = parseInt(isoMatch[1], 10);
            const monthIdx = parseInt(isoMatch[2], 10) - 1;
            const day = parseInt(isoMatch[3], 10);
            if (monthIdx >= 0 && monthIdx < 12) {
                return `${MONTHS[monthIdx]} ${day}, ${year}`;
            }
            return isoMatch[0];
        }

        return str;
    };

    const extractYear = (rawDate) => {
        if (!rawDate) return "Undated";
        const str = String(rawDate).trim();
        const match = str.match(/^(\d{4})/);
        return match ? match[1] : "Undated";
    };

    const initializeApp = () => {
        // Elements
        const siteHeader = document.querySelector("#site-header");
        const headerBrand = document.querySelector("#header-brand");
        const headerSearchWrap = document.querySelector("#header-search-wrap");
        const headerSearchForm = document.querySelector("#header-search-form");
        const headerSearchInput = document.querySelector("#header-topic-search");

        const landingView = document.querySelector("#landing-view");
        const landingSearchForm = document.querySelector("#landing-search-form");
        const landingSearchInput = document.querySelector("#topic-search");

        const loadingView = document.querySelector("#loading-view");

        const resultsView = document.querySelector("#results-view");
        const resultsTitleHeading = document.querySelector("#results-title-heading");
        const resultsStatCount = document.querySelector("#results-stat-count");
        const resultsLeadText = document.querySelector("#results-lead-text");

        const resultsStateCard = document.querySelector("#results-state-card");
        const resultsStateTitle = document.querySelector("#results-state-title");
        const resultsStateMsg = document.querySelector("#results-state-msg");
        const resultsStateResetBtn = document.querySelector("#results-state-reset-btn");

        const timelineWrapper = document.querySelector("#timeline-wrapper");
        const timelineTree = document.querySelector("#timeline-tree");
        const groupsList = document.querySelector("#groups-list");

        const qaSection = document.querySelector("#qa-section");
        const questionForm = document.querySelector("#question-form");
        const questionInput = document.querySelector("#question-input");
        const questionSubmitBtn = document.querySelector("#question-submit-btn");
        const qaResponseBox = document.querySelector("#qa-response-box");
        const qaResponseText = document.querySelector("#qa-response-text");
        const qaWarningsWrap = document.querySelector("#qa-warnings-wrap");
        const qaSourcesChips = document.querySelector("#qa-sources-chips");

        const summarySection = document.querySelector("#summary-section");
        const summaryText = document.querySelector("#summary-text");
        const summarySourcesChips = document.querySelector("#summary-sources-chips");

        let currentQuery = "";
        let isSearching = false;

        // View State Switcher: 'landing' | 'loading' | 'results'
        const setViewState = (state) => {
            if (state === "landing") {
                landingView?.classList.remove("is-hidden");
                loadingView?.classList.add("is-hidden");
                resultsView?.classList.add("is-hidden");

                siteHeader?.classList.remove("has-border");
                headerSearchWrap?.classList.add("is-hidden");

                if (landingSearchInput) {
                    landingSearchInput.value = "";
                    setTimeout(() => landingSearchInput.focus(), 50);
                }
            } else if (state === "loading") {
                landingView?.classList.add("is-hidden");
                loadingView?.classList.remove("is-hidden");
                resultsView?.classList.add("is-hidden");

                siteHeader?.classList.remove("has-border");
                headerSearchWrap?.classList.add("is-hidden");
            } else if (state === "results") {
                landingView?.classList.add("is-hidden");
                loadingView?.classList.add("is-hidden");
                resultsView?.classList.remove("is-hidden");

                siteHeader?.classList.add("has-border");
                headerSearchWrap?.classList.remove("is-hidden");

                if (headerSearchInput) {
                    headerSearchInput.value = currentQuery;
                }
            }
        };

        // Render Empty or Error State in Results View
        const showResultErrorState = (title, message) => {
            timelineWrapper?.classList.add("is-hidden");
            qaSection?.classList.add("is-hidden");
            summarySection?.classList.add("is-hidden");

            if (resultsStateCard) {
                resultsStateCard.classList.remove("is-hidden");
                if (resultsStateTitle) resultsStateTitle.textContent = title;
                if (resultsStateMsg) resultsStateMsg.textContent = message;
            }

            if (resultsStatCount) {
                resultsStatCount.textContent = "0 developments";
            }
        };

        // Helper to construct cross-source signals element
        const createCrossSourceSignalsElement = (signals) => {
            if (!signals || signals.length === 0) return null;

            const signalsSection = document.createElement("div");
            signalsSection.className = "cross-source-signals";

            const signalTitle = document.createElement("p");
            signalTitle.className = "cross-source-title";
            signalTitle.textContent = "Cross-source signals";
            signalsSection.append(signalTitle);

            const signalsList = document.createElement("ul");
            signalsList.className = "cross-source-list";

            signals.forEach((sig) => {
                const li = document.createElement("li");
                li.className = "cross-source-item";

                let iconText = "";
                let iconClass = "";
                let labelText = "";

                if (sig.signal === "supporting_reports") {
                    iconText = "✓";
                    iconClass = "cross-source-icon-success";
                    labelText = "Reported by multiple sources";
                } else if (sig.signal === "conflicting_reports") {
                    iconText = "⚠";
                    iconClass = "cross-source-icon-warning";
                    labelText = "Reports contain differing information";
                } else if (sig.signal === "insufficient_cross_source_evidence") {
                    iconText = "⚠";
                    iconClass = "cross-source-icon-warning";
                    labelText = "Limited independent reporting available";
                } else if (sig.signal === "same_story") {
                    iconText = "ℹ";
                    iconClass = "cross-source-icon-info";
                    labelText = "Multiple outlets syndicating same story";
                }

                if (labelText) {
                    const iconSpan = document.createElement("span");
                    iconSpan.className = `cross-source-icon ${iconClass}`;
                    iconSpan.setAttribute("aria-hidden", "true");
                    iconSpan.textContent = iconText;

                    const textSpan = document.createElement("span");
                    textSpan.textContent = labelText;

                    li.append(iconSpan, textSpan);
                    signalsList.append(li);
                }
            });

            if (signalsList.children.length > 0) {
                signalsSection.append(signalsList);
                return signalsSection;
            }
            return null;
        };

        // Helper to construct source quality and provenance signals element (Step 16)
        const createProvenanceSignalsElement = (signals) => {
            if (!signals) return null;

            const container = document.createElement("div");
            container.className = "provenance-signals-block";

            const label = document.createElement("span");
            label.className = "provenance-signals-header";
            label.textContent = "Source Provenance";
            container.appendChild(label);

            const pills = document.createElement("div");
            pills.className = "provenance-pills-row";

            // Independent source count & publisher identification
            const indepCount = signals.independent_source_count || 0;
            const pubPill = document.createElement("span");
            if (indepCount > 1) {
                pubPill.className = "prov-signal-pill prov-pill-success";
                pubPill.innerHTML = `<span class="prov-pill-icon" aria-hidden="true">✓</span> ${indepCount} independent publishers`;
            } else if (indepCount === 1) {
                pubPill.className = "prov-signal-pill prov-pill-neutral";
                pubPill.innerHTML = `<span class="prov-pill-icon" aria-hidden="true">ℹ</span> 1 publisher identified`;
            } else {
                pubPill.className = "prov-signal-pill prov-pill-subtle-warning";
                pubPill.innerHTML = `<span class="prov-pill-icon" aria-hidden="true">⚠</span> Publisher unidentified`;
            }
            pills.appendChild(pubPill);

            // Multi-source signal if multiple articles from same publisher
            if (signals.multiple_sources_found && indepCount <= 1) {
                const multiPill = document.createElement("span");
                multiPill.className = "prov-signal-pill prov-pill-neutral";
                multiPill.innerHTML = `<span class="prov-pill-icon" aria-hidden="true">ℹ</span> Multiple reports (same publisher)`;
                pills.appendChild(multiPill);
            }

            // Original URL availability
            if (signals.original_url_available) {
                const urlPill = document.createElement("span");
                urlPill.className = "prov-signal-pill prov-pill-neutral";
                urlPill.innerHTML = `<span class="prov-pill-icon" aria-hidden="true">↗</span> Original URL available`;
                pills.appendChild(urlPill);
            }

            // Publication date availability
            if (signals.publication_date_available) {
                const datePill = document.createElement("span");
                datePill.className = "prov-signal-pill prov-pill-neutral";
                datePill.innerHTML = `<span class="prov-pill-icon" aria-hidden="true">📅</span> Publication date available`;
                pills.appendChild(datePill);
            }

            // Source Provider identified
            if (signals.source_provider_identified) {
                const provPill = document.createElement("span");
                provPill.className = "prov-signal-pill prov-pill-neutral";
                provPill.innerHTML = `<span class="prov-pill-icon" aria-hidden="true">✓</span> Provider identified`;
                pills.appendChild(provPill);
            }

            // Source information completeness signal
            const infoPill = document.createElement("span");
            if (signals.source_information_missing) {
                infoPill.className = "prov-signal-pill prov-pill-subtle-warning";
                infoPill.innerHTML = `<span class="prov-pill-icon" aria-hidden="true">⚠</span> Source information missing`;
            } else {
                infoPill.className = "prov-signal-pill prov-pill-success";
                infoPill.innerHTML = `<span class="prov-pill-icon" aria-hidden="true">✓</span> Full metadata present`;
            }
            pills.appendChild(infoPill);

            container.appendChild(pills);
            return container;
        };

        // Helper to construct neutral verification and warning signals element (Step 17)
        const createVerificationWarningsElement = (signals) => {
            if (!signals || signals.length === 0) return null;

            const wrap = document.createElement("div");
            wrap.className = "verification-warnings-block";

            const header = document.createElement("div");
            header.className = "verification-warnings-header";
            header.innerHTML = `
                <span class="warning-badge-icon" aria-hidden="true">⚠</span>
                <span class="warning-badge-title">Reporting Observations</span>
            `;
            wrap.appendChild(header);

            const list = document.createElement("ul");
            list.className = "verification-warnings-list";

            signals.forEach((sig) => {
                const li = document.createElement("li");
                li.className = "verification-warning-item";

                const icon = document.createElement("span");
                icon.className = "warning-item-dot";
                icon.setAttribute("aria-hidden", "true");
                icon.textContent = "•";

                const text = document.createElement("span");
                text.className = "warning-item-text";
                text.textContent = sig.explanation;

                li.append(icon, text);
                list.appendChild(li);
            });

            wrap.appendChild(list);
            return wrap;
        };

        // Render Timeline with Chronological Year Markers, Cross-Source Signals, and Expandable Developments
        const renderTimeline = (timelineData, allArticles, groupsData = []) => {
            if (!timelineTree) return;
            timelineTree.replaceChildren();

            if (!timelineData || timelineData.length === 0) {
                showResultErrorState(
                    "No timeline events assembled",
                    "No chronological events could be assembled from the available news sources."
                );
                return;
            }

            timelineWrapper?.classList.remove("is-hidden");
            resultsStateCard?.classList.add("is-hidden");

            // Build article lookup map
            const articlesById = {};
            (allArticles || []).forEach((art) => {
                if (art.article_id !== undefined && art.article_id !== null) {
                    articlesById[art.article_id] = art;
                }
            });

            // Build group lookup map for cross-source signals and group metadata
            const groupsById = {};
            (groupsData || []).forEach((grp) => {
                if (grp.group_id !== undefined && grp.group_id !== null) {
                    groupsById[String(grp.group_id)] = grp;
                }
            });

            // Group timeline entries by Year
            const entriesByYear = new Map();
            timelineData.forEach((entry) => {
                const year = extractYear(entry.date);
                if (!entriesByYear.has(year)) {
                    entriesByYear.set(year, []);
                }
                entriesByYear.get(year).push(entry);
            });

            // Render each year section
            entriesByYear.forEach((entries, year) => {
                const yearSection = document.createElement("div");
                yearSection.className = "timeline-year-section";

                const yearMarker = document.createElement("div");
                yearMarker.className = "timeline-year-marker";
                yearMarker.textContent = year;
                yearSection.appendChild(yearMarker);

                const eventsContainer = document.createElement("div");
                eventsContainer.className = "timeline-events-container";

                entries.forEach((entry) => {
                    const node = document.createElement("div");
                    node.className = "timeline-node";

                    // Spine pin
                    const pin = document.createElement("div");
                    pin.className = "timeline-node-pin";
                    pin.setAttribute("aria-hidden", "true");

                    // Card body
                    const card = document.createElement("div");
                    card.className = "timeline-node-card";

                    // Card top meta
                    const topRow = document.createElement("div");
                    topRow.className = "timeline-node-top";

                    const dateEl = document.createElement("time");
                    dateEl.className = "timeline-node-date";
                    dateEl.textContent = formatDisplayDate(entry.date);

                    // Provenance badge
                    const isGrouped = Boolean(entry.group_id) || (entry.article_ids && entry.article_ids.length > 1);
                    const provTag = document.createElement("span");
                    provTag.className = isGrouped ? "provenance-tag grouped-tag" : "provenance-tag source-tag";
                    provTag.textContent = isGrouped
                        ? `Grouped (${entry.article_ids.length} articles)`
                        : "Direct Source";

                    topRow.append(dateEl, provTag);

                    // Event Title
                    const titleEl = document.createElement("h3");
                    titleEl.className = "timeline-node-title";
                    titleEl.textContent = entry.title;

                    // Event Description
                    const descEl = document.createElement("p");
                    descEl.className = "timeline-node-desc";
                    descEl.textContent = entry.description || "Reported event assembled from news coverage.";

                    // Cross-source signals (from main branch functionality)
                    const associatedGroup = entry.group_id ? groupsById[String(entry.group_id)] : null;
                    const signals = associatedGroup?.cross_source_signals || entry.cross_source_signals || [];
                    const signalsElement = createCrossSourceSignalsElement(signals);

                    // Card Footer / Disclosure Controls
                    const footerRow = document.createElement("div");
                    footerRow.className = "timeline-node-footer";

                    // Resolve supporting articles metadata
                    const supportingSources = entry.supporting_sources || [];
                    const supportingArticles = entry.supporting_articles || [];
                    const articleCount = entry.article_ids?.length || Math.max(supportingSources.length, supportingArticles.length, 1);

                    const expandBtn = document.createElement("button");
                    expandBtn.type = "button";
                    expandBtn.className = "timeline-expand-btn";
                    expandBtn.setAttribute("aria-expanded", "false");
                    expandBtn.innerHTML = `
                        <span class="expand-text">View ${articleCount} source article${articleCount === 1 ? "" : "s"}</span>
                        <span class="expand-chevron" aria-hidden="true">▼</span>
                    `;

                    // Unique publisher names for quick summary
                    const publishersSet = new Set();
                    supportingSources.forEach((s) => { if (s.publisher) publishersSet.add(s.publisher); });
                    (entry.article_ids || []).forEach((id) => {
                        if (articlesById[id]?.publisher) publishersSet.add(articlesById[id].publisher);
                    });
                    const publisherText = publishersSet.size > 0
                        ? Array.from(publishersSet).slice(0, 3).join(", ") + (publishersSet.size > 3 ? " & more" : "")
                        : "External sources";

                    const pubInfo = document.createElement("span");
                    pubInfo.className = "timeline-source-publishers";
                    pubInfo.textContent = `Via ${publisherText}`;

                    footerRow.append(expandBtn, pubInfo);

                    // Expandable Articles Drawer
                    const drawer = document.createElement("div");
                    drawer.className = "timeline-articles-drawer is-hidden";

                    // Collect all article records for this entry
                    const detailedArticles = [];
                    if (supportingSources.length > 0) {
                        supportingSources.forEach((s) => detailedArticles.push(s));
                    } else if (entry.article_ids && entry.article_ids.length > 0) {
                        entry.article_ids.forEach((id) => {
                            if (articlesById[id]) detailedArticles.push(articlesById[id]);
                        });
                    } else if (supportingArticles.length > 0) {
                        supportingArticles.forEach((s) => detailedArticles.push(s));
                    }

                    if (detailedArticles.length === 0) {
                        const fallbackRow = document.createElement("div");
                        fallbackRow.className = "supporting-article-row";
                        fallbackRow.textContent = "Detailed article citation is preserved in repository.";
                        drawer.appendChild(fallbackRow);
                    } else {
                        detailedArticles.forEach((art) => {
                            const artRow = document.createElement("article");
                            artRow.className = "supporting-article-row";

                            const metaDiv = document.createElement("div");
                            metaDiv.className = "supporting-article-meta";

                            const pubIdentified = art.publisher_identified !== undefined
                                ? art.publisher_identified
                                : Boolean(art.publisher && String(art.publisher).trim());

                            const pubSpan = document.createElement("span");
                            pubSpan.className = "article-publisher" + (pubIdentified ? "" : " is-missing");
                            pubSpan.textContent = art.publisher || "Publisher unidentified";

                            const dateAvailable = art.publication_date_available !== undefined
                                ? art.publication_date_available
                                : Boolean(art.publication_date && String(art.publication_date).trim());

                            const dateSpan = document.createElement("time");
                            dateSpan.className = dateAvailable ? "" : "is-missing";
                            dateSpan.textContent = dateAvailable ? formatDisplayDate(art.publication_date) : "Date unavailable";

                            const srcBadge = document.createElement("span");
                            srcBadge.className = "provenance-tag source-tag";
                            srcBadge.textContent = "Source";

                            metaDiv.append(pubSpan, dateSpan, srcBadge);

                            if (art.source_provider) {
                                const providerSpan = document.createElement("span");
                                providerSpan.className = "provenance-tag provider-tag";
                                providerSpan.textContent = art.source_provider;
                                metaDiv.append(providerSpan);
                            }

                            const infoMissing = art.source_information_missing !== undefined
                                ? art.source_information_missing
                                : !(pubIdentified && dateAvailable && Boolean(art.url) && Boolean(art.source_provider));

                            const qualityTag = document.createElement("span");
                            if (infoMissing) {
                                qualityTag.className = "provenance-tag quality-missing-tag";
                                qualityTag.textContent = "Partial metadata";
                            } else {
                                qualityTag.className = "provenance-tag quality-complete-tag";
                                qualityTag.textContent = "Verified metadata";
                            }
                            metaDiv.append(qualityTag);

                            const headline = document.createElement("h4");
                            headline.className = "supporting-article-headline";

                            const urlAvailable = art.original_url_available !== undefined
                                ? art.original_url_available
                                : Boolean(art.url && String(art.url).trim());

                            if (urlAvailable && art.url) {
                                const link = document.createElement("a");
                                link.href = art.url;
                                link.target = "_blank";
                                link.rel = "noopener noreferrer";
                                link.innerHTML = `${escapeHtml(art.title || "Read article")} <span class="external-icon" aria-hidden="true">↗</span>`;
                                headline.appendChild(link);
                            } else {
                                headline.innerHTML = `${escapeHtml(art.title || "Untitled article")} <span class="url-missing-notice">(Original URL unavailable)</span>`;
                            }

                            artRow.appendChild(metaDiv);
                            artRow.appendChild(headline);

                            if (art.description) {
                                const snippet = document.createElement("p");
                                snippet.className = "supporting-article-snippet";
                                snippet.textContent = art.description;
                                artRow.appendChild(snippet);
                            }

                            const warnList = art.verification_signals || art.warning_signals || [];
                            if (warnList.length > 0) {
                                const warnWrap = document.createElement("div");
                                warnWrap.className = "article-warning-row";
                                warnList.forEach((w) => {
                                    const warnPill = document.createElement("span");
                                    warnPill.className = "article-warning-pill";
                                    warnPill.textContent = `⚠ ${w.explanation}`;
                                    warnWrap.appendChild(warnPill);
                                });
                                artRow.appendChild(warnWrap);
                            }

                            drawer.appendChild(artRow);
                        });
                    }

                    // Toggle drawer interaction
                    expandBtn.addEventListener("click", () => {
                        const isOpen = !drawer.classList.contains("is-hidden");
                        drawer.classList.toggle("is-hidden", isOpen);
                        expandBtn.classList.toggle("is-open", !isOpen);
                        expandBtn.setAttribute("aria-expanded", String(!isOpen));
                        const btnText = expandBtn.querySelector(".expand-text");
                        if (btnText) {
                            btnText.textContent = !isOpen
                                ? `Hide ${articleCount} source article${articleCount === 1 ? "" : "s"}`
                                : `View ${articleCount} source article${articleCount === 1 ? "" : "s"}`;
                        }
                    });

                    card.append(topRow, titleEl, descEl);
                    if (signalsElement) {
                        card.append(signalsElement);
                    }
                    const provSignals = entry.provenance_signals || associatedGroup?.provenance_signals;
                    const provSignalsElement = createProvenanceSignalsElement(provSignals);
                    if (provSignalsElement) {
                        card.append(provSignalsElement);
                    }
                    const warnSignals = entry.verification_signals || entry.warning_signals || associatedGroup?.verification_signals || associatedGroup?.warning_signals;
                    const warnSignalsElement = createVerificationWarningsElement(warnSignals);
                    if (warnSignalsElement) {
                        card.append(warnSignalsElement);
                    }
                    card.append(footerRow, drawer);

                    node.append(pin, card);
                    eventsContainer.appendChild(node);
                });

                yearSection.appendChild(eventsContainer);
                timelineTree.appendChild(yearSection);
            });
        };

        // Render AI Summary Supporting Section (below timeline)
        const renderSummary = (summaryData) => {
            if (!summarySection || !summaryText || !summarySourcesChips) return;

            if (!summaryData || !summaryData.summary) {
                summarySection.classList.add("is-hidden");
                return;
            }

            summarySection.classList.remove("is-hidden");
            summaryText.textContent = summaryData.summary;

            summarySourcesChips.replaceChildren();
            const sources = summaryData.sources || [];
            if (sources.length > 0) {
                sources.forEach((s) => {
                    const chip = document.createElement("a");
                    chip.className = "source-chip";
                    chip.textContent = s.publisher || s.title || "Source";
                    if (s.url) {
                        chip.href = s.url;
                        chip.target = "_blank";
                        chip.rel = "noopener noreferrer";
                    }
                    summarySourcesChips.appendChild(chip);
                });
            } else {
                const noChip = document.createElement("span");
                noChip.className = "source-chip";
                noChip.textContent = "Verified timeline reporting";
                summarySourcesChips.appendChild(noChip);
            }
        };

        // Backward-compatible renderGroups helper (if #groups-list exists)
        const renderLegacyGroups = (groups) => {
            if (!groupsList) return;
            groupsList.replaceChildren();

            const multiArticleGroups = (groups || []).filter((group) => group.article_count > 1);
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

                const signalsSection = createCrossSourceSignalsElement(group.cross_source_signals);

                const sources = document.createElement("p");
                sources.className = "provenance-sources";
                sources.style.marginTop = "10px";
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

                const provSignalsSection = createProvenanceSignalsElement(group.provenance_signals);
                const warnSignalsSection = createVerificationWarningsElement(group.verification_signals || group.warning_signals);

                section.append(heading, note);
                if (signalsSection) section.append(signalsSection);
                if (provSignalsSection) section.append(provSignalsSection);
                if (warnSignalsSection) section.append(warnSignalsSection);
                section.append(sources);
                groupsList.append(section);
            });
        };

        // Escape HTML helper
        const escapeHtml = (text) => {
            const div = document.createElement("div");
            div.textContent = text;
            return div.innerHTML;
        };

        // Primary Search Execution Function
        const performSearch = async (query) => {
            const trimmed = (query || "").trim();
            if (!trimmed || isSearching) return;

            isSearching = true;
            currentQuery = trimmed;

            // Sync inputs
            if (landingSearchInput) landingSearchInput.value = trimmed;
            if (headerSearchInput) headerSearchInput.value = trimmed;

            // Update URL query parameter
            const url = new URL(window.location);
            url.searchParams.set("topic", trimmed);
            window.history.pushState({ topic: trimmed }, "", url);

            // Switch to serene loading view
            setViewState("loading");

            // Reset Q&A input and response
            if (questionInput) questionInput.value = "";
            qaResponseBox?.classList.add("is-hidden");

            try {
                const response = await fetch("/api/search", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ query: trimmed })
                });

                const data = await response.json();

                if (!response.ok || !data.success) {
                    setViewState("results");
                    if (resultsTitleHeading) resultsTitleHeading.textContent = `History of "${trimmed}"`;
                    if (resultsLeadText) resultsLeadText.textContent = "Query could not be completed.";

                    const errorMsg = response.status === 429 || data.status === "rate_limited"
                        ? "The news provider is temporarily rate-limited. Please wait a few seconds and try again."
                        : (data.error || "The news provider is temporarily unavailable.");

                    showResultErrorState("Search unavailable", errorMsg);
                    return;
                }

                // Switch to results view
                setViewState("results");

                // Update headings
                if (resultsTitleHeading) resultsTitleHeading.textContent = `History of "${trimmed}"`;
                const articlesCount = (data.results || []).length;
                const eventsCount = (data.timeline || []).length;

                if (resultsStatCount) {
                    const prov = data.provenance_signals;
                    const provText = prov
                        ? ` · ${prov.independent_source_count} publisher${prov.independent_source_count === 1 ? "" : "s"}${prov.source_information_missing ? " (partial metadata)" : " (complete metadata)"}`
                        : "";
                    resultsStatCount.textContent = `${eventsCount} development${eventsCount === 1 ? "" : "s"} · ${articlesCount} article${articlesCount === 1 ? "" : "s"}${provText}`;
                }

                if (resultsLeadText) {
                    resultsLeadText.textContent = articlesCount > 0
                        ? `Chronological sequence reconstructed from multi-source historical reporting.`
                        : `No historical coverage was found for "${trimmed}".`;
                }

                if (articlesCount === 0 || eventsCount === 0) {
                    showResultErrorState(
                        "No coverage found",
                        `No articles were returned by news providers for "${trimmed}". Try searching another topic, person, or organization.`
                    );
                    renderSummary(null);
                    return;
                }

                // Render Timeline, Cross-Source Signals, Legacy Clusters, and Summary
                renderTimeline(data.timeline || [], data.results || [], data.groups || []);
                renderLegacyGroups(data.groups || []);
                renderSummary(data.summary);
                qaSection?.classList.remove("is-hidden");

            } catch (err) {
                setViewState("results");
                if (resultsTitleHeading) resultsTitleHeading.textContent = `History of "${trimmed}"`;
                showResultErrorState(
                    "Connection issue",
                    "Unable to reach the News History server. Please check your connection and try again."
                );
            } finally {
                isSearching = false;
            }
        };

        // Event Handlers: Landing Search Form
        landingSearchForm?.addEventListener("submit", (e) => {
            e.preventDefault();
            const val = landingSearchInput?.value;
            if (val) performSearch(val);
        });

        // Event Handlers: Header Search Form
        headerSearchForm?.addEventListener("submit", (e) => {
            e.preventDefault();
            const val = headerSearchInput?.value;
            if (val) performSearch(val);
        });

        // Example Query Chips
        document.querySelectorAll(".example-btn").forEach((btn) => {
            btn.addEventListener("click", () => {
                const query = btn.dataset.query || btn.textContent.trim();
                if (query) {
                    if (landingSearchInput) landingSearchInput.value = query;
                    performSearch(query);
                }
            });
        });

        // Reset to Landing on Brand click
        headerBrand?.addEventListener("click", (e) => {
            e.preventDefault();
            const url = new URL(window.location);
            url.searchParams.delete("topic");
            window.history.pushState({}, "", url.pathname);
            setViewState("landing");
        });

        // Reset button on empty/error state card
        resultsStateResetBtn?.addEventListener("click", () => {
            const url = new URL(window.location);
            url.searchParams.delete("topic");
            window.history.pushState({}, "", url.pathname);
            setViewState("landing");
        });

        // Grounded Q&A Quick Prompt Chips
        const promptChips = document.querySelectorAll(".qa-prompt-chip");
        promptChips.forEach((chip) => {
            chip.addEventListener("click", () => {
                const prompt = chip.getAttribute("data-question");
                if (prompt && questionInput) {
                    questionInput.value = prompt;
                    questionForm?.dispatchEvent(new Event("submit"));
                }
            });
        });

        // Grounded Q&A Form Submission
        questionForm?.addEventListener("submit", async (e) => {
            e.preventDefault();
            const question = questionInput?.value.trim();
            if (!question || !currentQuery) return;

            questionSubmitBtn?.setAttribute("disabled", "disabled");
            qaResponseBox?.classList.remove("is-hidden");
            if (qaResponseText) {
                qaResponseText.textContent = "Synthesizing grounded answer from verified sources...";
            }
            if (qaWarningsWrap) {
                qaWarningsWrap.replaceChildren();
                qaWarningsWrap.classList.add("is-hidden");
            }
            if (qaSourcesChips) qaSourcesChips.replaceChildren();

            try {
                const res = await fetch("/api/question", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ question, query: currentQuery })
                });

                const data = await res.json();
                if (data.success && data.answer) {
                    if (qaResponseText) qaResponseText.textContent = data.answer;

                    // Render warning signals if any
                    const warnSignals = data.verification_signals || data.warning_signals;
                    if (qaWarningsWrap && warnSignals && warnSignals.length > 0) {
                        const warnElement = createVerificationWarningsElement(warnSignals);
                        if (warnElement) {
                            qaWarningsWrap.appendChild(warnElement);
                            qaWarningsWrap.classList.remove("is-hidden");
                        }
                    }

                    if (qaSourcesChips && data.sources && data.sources.length > 0) {
                        data.sources.forEach((s) => {
                            const chip = document.createElement("a");
                            chip.className = "source-chip";
                            chip.textContent = s.title || s.publisher || "Source";
                            if (s.url) {
                                chip.href = s.url;
                                chip.target = "_blank";
                                chip.rel = "noopener noreferrer";
                            }
                            qaSourcesChips.appendChild(chip);
                        });
                    }
                } else {
                    if (qaResponseText) {
                        qaResponseText.textContent = data.error || "Unable to answer this question from the available sources.";
                    }
                }
            } catch (err) {
                if (qaResponseText) {
                    qaResponseText.textContent = "Question answering is temporarily unavailable.";
                }
            } finally {
                questionSubmitBtn?.removeAttribute("disabled");
            }
        });

        // Popstate handler for browser back/forward navigation
        window.addEventListener("popstate", (e) => {
            const topic = e.state?.topic || new URLSearchParams(window.location.search).get("topic");
            if (topic) {
                performSearch(topic);
            } else {
                setViewState("landing");
            }
        });

        // Initialize state on page load (support ?topic= in URL)
        const initialParams = new URLSearchParams(window.location.search);
        const initialTopic = initialParams.get("topic");
        if (initialTopic) {
            performSearch(initialTopic);
        } else {
            setViewState("landing");
        }
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initializeApp);
    } else {
        initializeApp();
    }
})();