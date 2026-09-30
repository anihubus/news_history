from dataclasses import dataclass
from datetime import datetime

from app.repositories.article_repository import canonicalize_url
from app.services.provenance_service import ProvenanceService
from app.services.verification_signal_service import VerificationSignalService


@dataclass(frozen=True)
class TimelineEntry:
    timeline_id: str
    date: str | None
    title: str
    description: str | None
    article_ids: list[int]
    group_id: str | None
    automatic: bool
    supporting_articles: list[dict]
    updated: bool = False
    is_new: bool = False

    def to_dict(self):
        return {
            "timeline_id": self.timeline_id,
            "date": self.date,
            "title": self.title,
            "description": self.description,
            "article_ids": self.article_ids,
            "group_id": self.group_id,
            "automatic": self.automatic,
            "supporting_articles": self.supporting_articles,
            "updated": self.updated,
            "is_new": self.is_new,
        }


def normalize_publication_date(value):
    if not value or not isinstance(value, str):
        return None

    candidates = ("%Y%m%d%H%M%S", "%Y%m%d", "%Y-%m-%d")
    for date_format in candidates:
        try:
            return datetime.strptime(value, date_format).date().isoformat()
        except ValueError:
            continue

    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).date().isoformat()
    except ValueError:
        return None


class TimelineService:
    """Build and incrementally update an automatically assembled timeline from articles and groups."""

    def __init__(self, provenance_service=None, verification_service=None):
        self.provenance_service = provenance_service or ProvenanceService()
        self.verification_service = verification_service or VerificationSignalService()

    @staticmethod
    def _extract_field(item, field_name):
        if isinstance(item, dict):
            return item.get(field_name)
        return getattr(item, field_name, None)

    def generate(self, articles, groups):
        articles_by_id = {article.article_id: article for article in articles if article.article_id is not None}
        grouped_ids = set()
        entries = []

        for group in groups:
            article_ids = [article_id for article_id in group.get("article_ids", []) if article_id in articles_by_id]
            if not article_ids:
                continue
            grouped_ids.update(article_ids)
            group_articles = [articles_by_id[article_id] for article_id in article_ids]
            date = self._earliest_date(group_articles)
            representative = self._article_by_id(group_articles, group.get("article_ids", []))
            entries.append(
                TimelineEntry(
                    timeline_id=f"group-{group['group_id']}",
                    date=date,
                    title=group.get("representative_title") or representative.title,
                    description=self._description(group_articles),
                    article_ids=sorted(article_ids),
                    group_id=str(group["group_id"]),
                    automatic=True,
                    supporting_articles=self._supporting_articles(group_articles),
                    updated=False,
                    is_new=False,
                )
            )

        for article in articles:
            if article.article_id is None or article.article_id in grouped_ids:
                continue
            entries.append(
                TimelineEntry(
                    timeline_id=f"article-{article.article_id}",
                    date=normalize_publication_date(article.publication_date),
                    title=article.title,
                    description=article.description,
                    article_ids=[article.article_id],
                    group_id=None,
                    automatic=True,
                    supporting_articles=self._supporting_articles([article]),
                    updated=False,
                    is_new=False,
                )
            )

        return [entry.to_dict() for entry in sorted(entries, key=self._sort_key)]

    def update_timeline(self, existing_timeline, new_articles, groups=None, all_articles=None):
        """Incorporate newly retrieved articles into an existing timeline incrementally without unnecessary recreation."""
        if not new_articles:
            return [dict(e) if isinstance(e, dict) else e.to_dict() for e in (existing_timeline or [])]

        # Step A: Collect known article IDs and canonical URLs to prevent duplicates
        known_article_ids = set()
        known_canonical_urls = set()

        for entry in existing_timeline or []:
            entry_dict = entry if isinstance(entry, dict) else entry.to_dict()
            for aid in entry_dict.get("article_ids", []):
                if aid is not None:
                    known_article_ids.add(aid)
            for sup in entry_dict.get("supporting_articles", []):
                if sup.get("article_id") is not None:
                    known_article_ids.add(sup["article_id"])
                if sup.get("url"):
                    known_canonical_urls.add(canonicalize_url(sup["url"]))
            for src in entry_dict.get("supporting_sources", []):
                if src.get("article_id") is not None:
                    known_article_ids.add(src["article_id"])
                if src.get("url"):
                    known_canonical_urls.add(canonicalize_url(src["url"]))

        if all_articles:
            for art in all_articles:
                aid = self._extract_field(art, "article_id")
                a_url = self._extract_field(art, "url")
                if aid in known_article_ids and a_url:
                    known_canonical_urls.add(canonicalize_url(a_url))

        # Step B: Filter new articles for duplicates
        unique_new_articles = []
        for art in new_articles:
            aid = self._extract_field(art, "article_id")
            url = self._extract_field(art, "url")
            canon = canonicalize_url(url) if url else ""

            if aid is not None and aid in known_article_ids:
                continue
            if canon and canon in known_canonical_urls:
                continue

            unique_new_articles.append(art)
            if aid is not None:
                known_article_ids.add(aid)
            if canon:
                known_canonical_urls.add(canon)

        # If all incoming articles are duplicates, return existing timeline unchanged
        if not unique_new_articles:
            return [dict(e) if isinstance(e, dict) else e.to_dict() for e in (existing_timeline or [])]

        # Step C: Index all articles for metadata & provenance lookup
        articles_by_id = {}
        if all_articles:
            for a in all_articles:
                aid = self._extract_field(a, "article_id")
                if aid is not None:
                    articles_by_id[aid] = a
        for a in unique_new_articles:
            aid = self._extract_field(a, "article_id")
            if aid is not None:
                articles_by_id[aid] = a

        # Step D: Prepare mutable copies of existing timeline entries (preserve unchanged entries in-place)
        updated_timeline = []
        for entry in existing_timeline or []:
            entry_dict = dict(entry) if isinstance(entry, dict) else entry.to_dict()
            entry_dict["article_ids"] = list(entry_dict.get("article_ids", []))
            entry_dict["supporting_articles"] = list(entry_dict.get("supporting_articles", []))
            if "supporting_sources" in entry_dict:
                entry_dict["supporting_sources"] = list(entry_dict.get("supporting_sources", []))
            entry_dict["updated"] = False
            entry_dict["is_new"] = False
            updated_timeline.append(entry_dict)

        # Step E: Group mapping
        article_to_group = {}
        for grp in groups or []:
            for aid in grp.get("article_ids", []):
                article_to_group[aid] = grp

        for art in unique_new_articles:
            aid = self._extract_field(art, "article_id")
            gid = self._extract_field(art, "group_id")
            if gid is not None and aid not in article_to_group:
                article_to_group[aid] = {
                    "group_id": str(gid),
                    "article_ids": [aid],
                    "representative_title": self._extract_field(art, "title"),
                }

        # Step F: Incorporate new articles into existing groups or create new entries
        for art in unique_new_articles:
            aid = self._extract_field(art, "article_id")
            art_url = self._extract_field(art, "url")
            art_title = self._extract_field(art, "title") or ""
            canon_url = canonicalize_url(art_url) if art_url else ""
            grp = article_to_group.get(aid)

            if grp:
                gid = str(grp.get("group_id"))
                target_entry = None
                for entry in updated_timeline:
                    if str(entry.get("group_id")) == gid or entry.get("timeline_id") == f"group-{gid}":
                        target_entry = entry
                        break

                if not target_entry and grp.get("article_ids"):
                    other_ids = set(grp["article_ids"]) - ({aid} if aid is not None else set())
                    for entry in updated_timeline:
                        if any(o_id in entry.get("article_ids", []) for o_id in other_ids):
                            target_entry = entry
                            target_entry["timeline_id"] = f"group-{gid}"
                            target_entry["group_id"] = gid
                            if grp.get("representative_title"):
                                target_entry["title"] = grp["representative_title"]
                            break

                if target_entry:
                    # Update group's article_ids
                    if aid is not None and aid not in target_entry["article_ids"]:
                        target_entry["article_ids"].append(aid)
                        target_entry["article_ids"].sort()

                    # Update supporting_articles
                    existing_sup_urls = {canonicalize_url(s.get("url")) for s in target_entry["supporting_articles"] if s.get("url")}
                    if canon_url and canon_url not in existing_sup_urls:
                        target_entry["supporting_articles"].append({
                            "article_id": aid,
                            "title": art_title,
                            "url": art_url,
                        })

                    # Update supporting_sources (provenance references)
                    if "supporting_sources" in target_entry or hasattr(self, "provenance_service"):
                        target_entry.setdefault("supporting_sources", [])
                        existing_src_urls = {canonicalize_url(s.get("url")) for s in target_entry["supporting_sources"] if s.get("url")}
                        if canon_url and canon_url not in existing_src_urls:
                            ref = self.provenance_service.article_reference(art)
                            target_entry["supporting_sources"].append(ref)

                    # Update provenance collection signals
                    member_articles = [articles_by_id[m_id] for m_id in target_entry["article_ids"] if m_id in articles_by_id]
                    if member_articles:
                        prov_sig = self.provenance_service.collection_signals(member_articles)
                        target_entry["provenance_signals"] = prov_sig
                        for k in [
                            "publisher_identified", "original_url_available", "publication_date_available",
                            "source_provider_identified", "multiple_sources_found", "independent_source_count",
                            "source_information_missing"
                        ]:
                            if k in prov_sig:
                                target_entry[k] = prov_sig[k]

                    # Recalculate event date: Task 1 & 5: normalized publication date only, NEVER retrieved_at!
                    member_dates = [
                        normalize_publication_date(self._extract_field(m, "publication_date"))
                        for m in member_articles
                    ]
                    valid_dates = [d for d in member_dates if d]
                    prev_date = normalize_publication_date(target_entry.get("date"))
                    if prev_date:
                        valid_dates.append(prev_date)
                    target_entry["date"] = min(valid_dates) if valid_dates else None

                    target_entry["updated"] = True
                else:
                    # New group entry
                    group_article_ids = sorted(list(set([aid] + [m_id for m_id in grp.get("article_ids", []) if m_id in articles_by_id]))) if aid is not None else []
                    all_grp_arts = [articles_by_id[m_id] for m_id in group_article_ids if m_id in articles_by_id] or [art]
                    new_group_entry = {
                        "timeline_id": f"group-{gid}",
                        "date": self._earliest_date(all_grp_arts),
                        "title": grp.get("representative_title") or self._extract_field(art, "title") or "",
                        "description": self._description(all_grp_arts),
                        "article_ids": group_article_ids,
                        "group_id": gid,
                        "automatic": True,
                        "supporting_articles": self._supporting_articles(all_grp_arts),
                        "supporting_sources": [self.provenance_service.article_reference(a) for a in all_grp_arts],
                        "updated": True,
                        "is_new": True,
                    }
                    prov_sig = self.provenance_service.collection_signals(all_grp_arts)
                    new_group_entry["provenance_signals"] = prov_sig
                    for k in [
                        "publisher_identified", "original_url_available", "publication_date_available",
                        "source_provider_identified", "multiple_sources_found", "independent_source_count",
                        "source_information_missing"
                    ]:
                        new_group_entry[k] = prov_sig.get(k)

                    updated_timeline.append(new_group_entry)
            else:
                # Standalone article entry
                # Task 1 & 5: normalize publication date only; NEVER use retrieved_at as the historical event date!
                pub_date = normalize_publication_date(self._extract_field(art, "publication_date"))
                new_entry = {
                    "timeline_id": f"article-{aid}" if aid is not None else f"article-{len(updated_timeline)+1}",
                    "date": pub_date,
                    "title": art_title,
                    "description": self._extract_field(art, "description"),
                    "article_ids": [aid] if aid is not None else [],
                    "group_id": None,
                    "automatic": True,
                    "supporting_articles": self._supporting_articles([art]),
                    "supporting_sources": [self.provenance_service.article_reference(art)],
                    "updated": True,
                    "is_new": True,
                }
                sig = self.provenance_service.source_signals(art)
                new_entry["provenance_signals"] = sig
                for k in [
                    "publisher_identified", "original_url_available", "publication_date_available",
                    "source_provider_identified", "multiple_sources_found", "independent_source_count",
                    "source_information_missing"
                ]:
                    new_entry[k] = sig.get(k)

                updated_timeline.append(new_entry)

        # Step G: Enrich verification signals on updated/new entries
        has_verification = any("verification_signals" in e for e in existing_timeline or [])
        for entry in updated_timeline:
            if entry.get("updated") or entry.get("is_new"):
                entry_arts = [articles_by_id[m_id] for m_id in entry.get("article_ids", []) if m_id in articles_by_id]
                if entry_arts:
                    v_signals = self.verification_service.analyze_articles(entry_arts)
                    entry["verification_signals"] = v_signals
                    entry["warning_signals"] = v_signals
                elif has_verification:
                    entry.setdefault("verification_signals", [])
                    entry.setdefault("warning_signals", [])

        # Step H: Chronological ordering & preserving missing dates separately at the end
        updated_timeline.sort(key=self._sort_key)
        return updated_timeline

    def _earliest_date(self, articles):
        dates = [normalize_publication_date(self._extract_field(article, "publication_date")) for article in articles]
        valid_dates = [date for date in dates if date]
        return min(valid_dates) if valid_dates else None

    def _article_by_id(self, articles, ordered_ids):
        articles_by_id = {self._extract_field(article, "article_id"): article for article in articles}
        for article_id in ordered_ids:
            if article_id in articles_by_id:
                return articles_by_id[article_id]
        return articles[0]

    def _description(self, articles):
        for article in articles:
            desc = self._extract_field(article, "description")
            if desc:
                return desc
        return None

    def _supporting_articles(self, articles):
        unique = {}
        for article in articles:
            url = self._extract_field(article, "url")
            if not url:
                continue
            unique[canonicalize_url(url)] = {
                "article_id": self._extract_field(article, "article_id"),
                "title": self._extract_field(article, "title"),
                "url": url,
            }
        return list(unique.values())

    @staticmethod
    def _sort_key(entry):
        if isinstance(entry, dict):
            date = entry.get("date")
            tid = entry.get("timeline_id", "")
        else:
            date = entry.date
            tid = entry.timeline_id
        return (date is None, date or "", str(tid or ""))

