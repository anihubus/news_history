class AIProviderError(Exception):
    """Raised when an AI provider cannot produce a safe response."""


class AIProvider:
    """Replaceable interface for grounded model interactions."""

    name = "unknown"

    def summarize(self, instruction, context):
        raise NotImplementedError

    def answer(self, instruction, context, question):
        raise NotImplementedError


class MockAIProvider(AIProvider):
    name = "mock"

    CONFLICT_KEYWORDS = {
        "deny", "denies", "denied", "dispute", "disputes", "disputed",
        "reject", "rejects", "rejected", "contradict", "contradicts",
        "differ", "differing", "fake"
    }

    GENERAL_QUESTION_WORDS = {
        "what", "when", "where", "which", "who", "why", "how", "is", "are", "was",
        "were", "did", "do", "does", "the", "a", "an", "in", "on", "at", "for", "to", "of", "and", "or",
        "this", "that", "these", "those", "about", "there", "story", "event", "article",
        "articles", "report", "reporting", "reports", "news", "give", "tell", "show",
        "covered", "happened", "occurred", "summary", "summarize", "detail", "details",
        "information", "info", "context", "findings", "finding", "find", "all", "latest",
        "recent", "known", "mention", "mentioned", "describe", "described", "take", "place"
    }

    def summarize(self, instruction, context):
        articles = context.get("articles", [])
        if not articles:
            return "The available reporting is insufficient to produce a summary."

        summary_type = context.get("summary_type")
        timeline = context.get("timeline", [])
        if summary_type == "timeline" and timeline:
            titles = [entry.get("title") for entry in timeline if entry.get("title")]
            return f"Timeline covers {len(timeline)} chronological development(s) from {len(articles)} article(s): " + "; ".join(titles[:3]) + "."

        titles = [article.get("title") for article in articles if article.get("title")]
        return f"Available reporting includes {len(articles)} article(s): " + "; ".join(titles[:3]) + "."

    def answer(self, instruction, context, question):
        articles = context.get("articles", [])
        if not articles:
            return {
                "answer": "The available sources do not provide enough information to answer this question.",
                "supporting_article_ids": [],
            }

        q = (question or "").lower().strip()
        q_clean = q.rstrip("?.!")

        all_ids = [a.get("article_id") for a in articles if a.get("article_id") is not None]
        all_text = " ".join([
            ((a.get("title") or "") + " " + (a.get("description") or "") + " " + (context.get("query") or "")).lower()
            for a in articles
        ])
        general_question_words = self.GENERAL_QUESTION_WORDS

        # 1. Source count questions ("How many sources reported this?", "how many sources", "how many publishers", "how many articles", "source count")
        source_count_triggers = [
            "how many sources", "how many publishers", "how many articles",
            "source count", "number of sources", "how many outlets", "how many reported"
        ]
        if any(trigger in q for trigger in source_count_triggers):
            publishers = sorted(list({
                str(a.get("publisher")).strip()
                for a in articles
                if a.get("publisher") and str(a.get("publisher")).strip()
            }))
            pub_count = len(publishers)
            art_count = len(articles)
            if pub_count > 0:
                answer = f"According to the retrieved reporting, {art_count} article(s) from {pub_count} independent source(s) ({', '.join(publishers)}) reported on this topic."
            else:
                answer = f"According to the retrieved reporting, {art_count} article(s) were found, but publisher information is not identified in the source metadata."
            return {
                "answer": answer,
                "supporting_article_ids": all_ids,
            }

        # 2. Conflicting reports questions ("Are there conflicting reports?", "conflicts", "dispute", "contradict")
        conflict_triggers = [
            "conflicting report", "conflicting reports", "conflict", "conflicts",
            "dispute", "disputes", "differing", "contradict", "contradiction"
        ]
        if any(trigger in q for trigger in conflict_triggers):
            conflicting_refs = context.get("conflicting_references")
            if conflicting_refs is None:
                conflicting_refs = []
                for a in articles:
                    text = ((a.get("title") or "") + " " + (a.get("description") or "")).lower()
                    words = set(text.split())
                    if any(kw in words for kw in self.CONFLICT_KEYWORDS):
                        conflicting_refs.append(a)

            if conflicting_refs:
                c_titles = [f'"{r.get("title")}"' for r in conflicting_refs if r.get("title")]
                c_ids = [r.get("article_id") for r in conflicting_refs if r.get("article_id") is not None]
                answer = f"Yes. Some reports contain differing information. Specifically, conflicting reporting was identified in {', '.join(c_titles[:2]) or 'the retrieved sources'}, where accounts or statements dispute key claims."
                return {
                    "answer": answer,
                    "supporting_article_ids": c_ids or all_ids,
                }
            else:
                answer = f"No conflicting reports were found in the available reporting. All {len(articles)} retrieved article(s) provide consistent or corroborating accounts."
                return {
                    "answer": answer,
                    "supporting_article_ids": all_ids,
                }

        # 3. Warning & Flagged evidence questions ("Why is this story flagged for limited evidence?", "why is this flagged", "warning")
        flag_triggers = [
            "flagged for limited evidence", "why is this story flagged", "why is this flagged",
            "why was this flagged", "why is it flagged", "limited evidence", "warning signal", "warning signals"
        ]
        if any(trigger in q for trigger in flag_triggers):
            warnings = context.get("verification_warnings") or context.get("verification_signals") or []
            if warnings:
                explanations = [w.get("explanation") for w in warnings if w.get("explanation")]
                w_ids = list(dict.fromkeys([
                    aid for w in warnings for aid in w.get("supporting_article_ids", []) if aid is not None
                ]))
                answer = f"This story is flagged for limited evidence because: {' '.join(explanations)}"
                return {
                    "answer": answer,
                    "supporting_article_ids": w_ids or all_ids,
                }
            else:
                answer = "This story is not flagged for limited evidence. The retrieved reporting includes corroboration from multiple independent sources with complete metadata."
                return {
                    "answer": answer,
                    "supporting_article_ids": all_ids,
                }

        # 4. Supporting articles questions ("Which articles support this event?", "which articles support", "supporting articles", "sources support")
        support_triggers = [
            "which articles support", "which sources support", "supporting articles",
            "support this event", "support this story", "who supports", "what sources support"
        ]
        if any(trigger in q for trigger in support_triggers):
            supporting_refs = context.get("supporting_references")
            if supporting_refs is None:
                conflicting_ids = set(context.get("conflicting_article_ids", []))
                supporting_refs = [a for a in articles if a.get("article_id") not in conflicting_ids]

            if supporting_refs:
                items = [
                    f'"{a.get("title")}" ({a.get("publisher") or "Unknown publisher"})'
                    for a in supporting_refs
                    if a.get("title")
                ]
                s_ids = [a.get("article_id") for a in supporting_refs if a.get("article_id") is not None]
                answer = f"The reporting is supported by {len(supporting_refs)} article(s): {'; '.join(items[:3])}."
                return {
                    "answer": answer,
                    "supporting_article_ids": s_ids,
                }
            else:
                return {
                    "answer": "The available sources do not provide enough supporting evidence for this event.",
                    "supporting_article_ids": [],
                }

        # 5. Truth / Fake verdict question guardrail (never claim fake/true without explicit establishment)
        verdict_triggers = ["fake", "hoax", "true", "is it true", "is this true", "is this fake", "is the story true", "debunked"]
        if any(trigger in q for trigger in verdict_triggers):
            warnings = context.get("verification_warnings") or context.get("verification_signals") or []
            obs = f" Observable signals: {' '.join([w['explanation'] for w in warnings])}" if warnings else ""
            answer = f"The available sources do not establish whether this reporting is definitely true or definitely fake. News History provides observable provenance and verification signals rather than definitive credibility verdicts.{obs}"
            return {
                "answer": answer,
                "supporting_article_ids": all_ids,
            }

        # 6. Fresh evidence & breaking news queries ("breaking news", "fresh evidence", "latest update", "recent news")
        fresh_triggers = [
            "fresh evidence", "latest evidence", "new evidence",
            "breaking news", "breaking update", "latest breaking",
            "fresh reporting", "latest update", "latest news", "recent news",
            "recent developments", "latest development"
        ]
        if any(trigger in q for trigger in fresh_triggers):
            specific_words = set(q_clean.split()) - general_question_words - {
                "fresh", "evidence", "breaking", "news", "update", "updates", "latest", "recent", "development", "developments"
            }
            if specific_words and not any(w in all_text for w in specific_words):
                return {
                    "answer": "Fresh evidence is currently unavailable in the retrieved reporting.",
                    "supporting_article_ids": [],
                }
            sorted_arts = sorted(
                articles,
                key=lambda a: (a.get("publication_date") or "", a.get("retrieved_at") or "", a.get("article_id") or 0),
                reverse=True,
            )
            latest = sorted_arts[0]
            latest_id = latest.get("article_id")
            latest_title = latest.get("title") or "Latest report"
            latest_pub = latest.get("publisher") or "Independent source"
            latest_desc = latest.get("description") or "Latest reported details from available coverage."
            date_info = f" ({latest.get('publication_date')})" if latest.get("publication_date") else ""
            answer = f"According to the latest reporting from {latest_pub}{date_info} in \"{latest_title}\", {latest_desc}"
            return {
                "answer": answer,
                "supporting_article_ids": [latest_id] if latest_id is not None else all_ids,
            }

        # 7. Check for completely unsupported / insufficient evidence questions
        question_words = set(q_clean.split()) - general_question_words
        if question_words and not any(w in all_text for w in question_words):
            return {
                "answer": "The available sources do not provide enough information to answer this question.",
                "supporting_article_ids": [],
            }

        # 8. General grounded question (preserve existing Q&A behavior)
        titles = [article.get("title") for article in articles if article.get("title")]
        return {
            "answer": f"Based on the available sources, the retrieved reporting includes: {'; '.join(titles[:3])}.",
            "supporting_article_ids": all_ids,
        }
