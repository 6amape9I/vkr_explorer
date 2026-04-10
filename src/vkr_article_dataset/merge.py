from __future__ import annotations

from copy import deepcopy
from statistics import mean
from typing import Any, Iterable

from .models import ArticleSeed, FieldDecision, MergeDecision, ProviderResult, ResolutionResult
from .schema import FULLTEXT_STATUS_NOT_ATTEMPTED, SCHEMA_VERSION, canonical_id
from .tagger import infer_tags
from .utils import extract_arxiv_id, extract_doi, normalize_whitespace, slugify_title, stable_record_id, utc_now_iso


class RecordMerger:
    def merge(
        self,
        seed: ArticleSeed,
        resolution: ResolutionResult,
        *,
        source_payload_refs: dict[str, str] | None = None,
    ) -> tuple[dict[str, Any], MergeDecision]:
        source_payload_refs = source_payload_refs or {}
        if not resolution.candidates:
            return self._build_fallback_record(
                seed=seed,
                resolution=resolution,
                source_payload_refs=source_payload_refs,
            )

        ordered_candidates = sorted(
            resolution.candidates,
            key=self._candidate_score,
            reverse=True,
        )
        primary = ordered_candidates[0]
        decisions: dict[str, FieldDecision] = {}

        doi, decisions["identifiers.doi"] = self._select_identifier(
            ordered_candidates,
            "doi",
            reason="exact DOI from scholarly metadata",
        )
        arxiv_id, decisions["identifiers.arxiv_id"] = self._select_identifier(
            ordered_candidates,
            "arxiv_id",
            reason="exact arXiv identifier",
        )
        openalex_id, decisions["identifiers.openalex_id"] = self._select_identifier(
            ordered_candidates,
            "openalex_id",
            reason="exact OpenAlex identifier",
        )

        title, decisions["bibliography.title"] = self._select_title(ordered_candidates, seed)
        authors, decisions["bibliography.authors"] = self._select_authors(ordered_candidates)
        publication_year, decisions["bibliography.publication_year"] = self._select_generic(
            ordered_candidates,
            "publication_year",
            reason="structured source metadata",
        )
        publication_date, decisions["bibliography.publication_date"] = self._select_generic(
            ordered_candidates,
            "publication_date",
            reason="structured source metadata",
        )
        venue, decisions["bibliography.venue"] = self._select_venue(ordered_candidates)
        document_type, decisions["bibliography.document_type"] = self._select_generic(
            ordered_candidates,
            "document_type",
            reason="structured source metadata",
        )
        abstract, decisions["content.abstract"] = self._select_abstract(ordered_candidates)
        language, decisions["content.language"] = self._select_generic(
            ordered_candidates,
            "language",
            reason="structured source metadata",
            default="en",
        )
        landing_page_url, decisions["links.landing_page_url"] = self._select_landing_page(ordered_candidates)
        pdf_url, decisions["links.pdf_url"] = self._select_pdf_url(ordered_candidates)
        is_open_access, decisions["quality.is_open_access"] = self._select_open_access(ordered_candidates)
        citation_count, decisions["quality.citation_count"] = self._select_citation_count(ordered_candidates)

        doi = doi or seed.doi or extract_doi(seed.url)
        arxiv_id = arxiv_id or seed.arxiv_id or extract_arxiv_id(seed.url)
        canonical, canonical_winner, canonical_reason = canonical_id(
            doi=doi,
            arxiv_id=arxiv_id,
            openalex_id=openalex_id,
            title=title,
            authors=authors,
            publication_year=publication_year,
        )
        decisions["identifiers.canonical_id"] = FieldDecision(
            winner=canonical_winner,
            candidates=_decision_candidates(
                decisions["identifiers.doi"],
                decisions["identifiers.arxiv_id"],
                decisions["identifiers.openalex_id"],
            ),
            reason=canonical_reason,
        )

        record_id = stable_record_id(doi, arxiv_id, openalex_id, canonical, title, authors[0] if authors else None, seed.url)
        tagging = infer_tags(title=title, abstract=abstract)
        merge_decision = MergeDecision(primary_source=primary.provider_name, fields=decisions)

        record = {
            "schema_version": SCHEMA_VERSION,
            "record_id": record_id,
            "resolution_status": "resolved" if title else "partial",
            "retrieved_at": utc_now_iso(),
            "identifiers": {
                "doi": doi,
                "arxiv_id": arxiv_id,
                "openalex_id": openalex_id,
                "canonical_id": canonical,
                "source": primary.provider_name,
            },
            "sources": {
                "primary_source": primary.provider_name,
                "available_sources": _available_sources(ordered_candidates),
                "source_candidates_count": len(resolution.candidates),
            },
            "source_candidates": [_candidate_summary(candidate) for candidate in ordered_candidates],
            "merge_decisions": _serialize_merge_decisions(merge_decision),
            "bibliography": {
                "title": title,
                "authors": authors,
                "publication_year": publication_year,
                "publication_date": publication_date,
                "venue": venue,
                "document_type": document_type,
            },
            "content": {
                "abstract": abstract,
                "combined_text": _combined_text(title, abstract),
                "language": language or "en",
                "fulltext_ref": None,
                "fulltext_status": FULLTEXT_STATUS_NOT_ATTEMPTED,
                "fulltext_quality": None,
            },
            "labels": {
                "gold_label": seed.gold_label,
                "is_hard_negative": seed.is_hard_negative,
                "auto_topic_tags": tagging.topic_tags,
                "auto_method_tags": tagging.method_tags,
                "auto_topic_tag_scores": tagging.topic_scores,
                "auto_method_tag_scores": tagging.method_scores,
                "auto_topic_tag_evidence": tagging.topic_evidence,
                "auto_method_tag_evidence": tagging.method_evidence,
                "manual_topic_tags": [],
                "manual_method_tags": [],
                "notes": seed.notes,
            },
            "quality": {
                "has_abstract": bool(abstract),
                "has_pdf_url": bool(pdf_url),
                "is_open_access": is_open_access,
                "citation_count": citation_count,
            },
            "links": {
                "landing_page_url": landing_page_url,
                "pdf_url": pdf_url,
            },
            "provenance": {
                "seed_query": seed.seed_query,
                "input_position": seed.input_position,
                "resolver_summary": {
                    "attempted": resolution.attempted,
                    "successful": resolution.successful,
                    "errors": resolution.errors,
                    "rejections": resolution.rejections,
                },
                "merge_summary": _merge_summary(decisions),
            },
            "raw": {
                "seed_extra": seed.extra,
                "source_payload_refs": source_payload_refs,
            },
        }
        return record, merge_decision

    def build_record(
        self,
        seed: ArticleSeed,
        resolution: ResolutionResult,
        *,
        source_payload_refs: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        record, _ = self.merge(
            seed,
            resolution,
            source_payload_refs=source_payload_refs,
        )
        return record

    def merge_records(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        if not records:
            raise ValueError("merge_records requires at least one record")
        if len(records) == 1:
            record = deepcopy(records[0])
            record["dedup"] = {
                "duplicate_group_size": 1,
                "dedup_strategy": "none",
                "merged_record_ids": [record.get("record_id")],
            }
            return record

        ordered_records = sorted(records, key=self._record_merge_score, reverse=True)
        primary = ordered_records[0]
        merged = deepcopy(primary)
        merged["source_candidates"] = _merge_source_candidates(ordered_records)
        merged["sources"] = {
            "primary_source": primary.get("sources", {}).get("primary_source") or primary.get("identifiers", {}).get("source"),
            "available_sources": _available_record_sources(ordered_records),
            "source_candidates_count": len(merged["source_candidates"]),
        }

        field_configs = {
            "identifiers.doi": ("identifiers", "doi"),
            "identifiers.arxiv_id": ("identifiers", "arxiv_id"),
            "identifiers.openalex_id": ("identifiers", "openalex_id"),
            "bibliography.title": ("bibliography", "title"),
            "bibliography.authors": ("bibliography", "authors"),
            "bibliography.publication_year": ("bibliography", "publication_year"),
            "bibliography.publication_date": ("bibliography", "publication_date"),
            "bibliography.venue": ("bibliography", "venue"),
            "bibliography.document_type": ("bibliography", "document_type"),
            "content.abstract": ("content", "abstract"),
            "content.language": ("content", "language"),
            "links.landing_page_url": ("links", "landing_page_url"),
            "links.pdf_url": ("links", "pdf_url"),
            "quality.is_open_access": ("quality", "is_open_access"),
            "quality.citation_count": ("quality", "citation_count"),
        }
        decisions: dict[str, FieldDecision] = {}
        for field_name, path in field_configs.items():
            value, decision = self._select_record_field(ordered_records, field_name, path)
            _set_nested_value(merged, path, value)
            decisions[field_name] = decision

        authors = merged.get("bibliography", {}).get("authors") or []
        canonical, canonical_winner, canonical_reason = canonical_id(
            doi=merged.get("identifiers", {}).get("doi"),
            arxiv_id=merged.get("identifiers", {}).get("arxiv_id"),
            openalex_id=merged.get("identifiers", {}).get("openalex_id"),
            title=merged.get("bibliography", {}).get("title"),
            authors=authors,
            publication_year=merged.get("bibliography", {}).get("publication_year"),
        )
        merged["identifiers"]["canonical_id"] = canonical
        merged["identifiers"]["source"] = merged.get("sources", {}).get("primary_source")
        decisions["identifiers.canonical_id"] = FieldDecision(
            winner=canonical_winner,
            candidates=_decision_candidates(
                decisions["identifiers.doi"],
                decisions["identifiers.arxiv_id"],
                decisions["identifiers.openalex_id"],
            ),
            reason=canonical_reason,
        )

        abstract = merged.get("content", {}).get("abstract")
        title = merged.get("bibliography", {}).get("title")
        merged["content"]["combined_text"] = _combined_text(title, abstract)
        merged["quality"]["has_abstract"] = bool(abstract)
        merged["quality"]["has_pdf_url"] = bool(merged.get("links", {}).get("pdf_url"))

        manual_topic_tags = merged.get("labels", {}).get("manual_topic_tags") or []
        manual_method_tags = merged.get("labels", {}).get("manual_method_tags") or []
        tagging = infer_tags(title=title, abstract=abstract)
        merged["labels"].update(
            {
                "auto_topic_tags": tagging.topic_tags,
                "auto_method_tags": tagging.method_tags,
                "auto_topic_tag_scores": tagging.topic_scores,
                "auto_method_tag_scores": tagging.method_scores,
                "auto_topic_tag_evidence": tagging.topic_evidence,
                "auto_method_tag_evidence": tagging.method_evidence,
                "manual_topic_tags": manual_topic_tags,
                "manual_method_tags": manual_method_tags,
            }
        )

        merged["merge_decisions"] = _serialize_merge_decisions(
            MergeDecision(
                primary_source=merged.get("sources", {}).get("primary_source"),
                fields=decisions,
            )
        )
        merged.setdefault("provenance", {})
        merged["provenance"]["merge_summary"] = _merge_summary(decisions)
        merged["provenance"]["dedup_merge"] = {
            "merged_record_ids": [record.get("record_id") for record in ordered_records],
        }
        merged["dedup"] = {
            "duplicate_group_size": len(ordered_records),
            "dedup_strategy": _dedup_strategy(ordered_records),
            "merged_record_ids": [record.get("record_id") for record in ordered_records],
        }
        merged["raw"] = {
            "seed_extra": primary.get("raw", {}).get("seed_extra") or {},
            "source_payload_refs": _merge_source_payload_refs(ordered_records),
        }
        return merged

    def _build_fallback_record(
        self,
        *,
        seed: ArticleSeed,
        resolution: ResolutionResult,
        source_payload_refs: dict[str, str],
    ) -> tuple[dict[str, Any], MergeDecision]:
        title = seed.title
        doi = seed.doi or extract_doi(seed.url)
        arxiv_id = seed.arxiv_id or extract_arxiv_id(seed.url)
        record_id = stable_record_id(doi, arxiv_id, title, seed.url)
        tagging = infer_tags(title=title, abstract=None)
        decisions = MergeDecision(primary_source="manual", fields={})
        record = {
            "schema_version": SCHEMA_VERSION,
            "record_id": record_id,
            "resolution_status": "failed",
            "retrieved_at": utc_now_iso(),
            "identifiers": {
                "doi": doi,
                "arxiv_id": arxiv_id,
                "openalex_id": None,
                "canonical_id": canonical_id(doi, arxiv_id, None, title=title)[0],
                "source": "manual",
            },
            "sources": {
                "primary_source": "manual",
                "available_sources": [],
                "source_candidates_count": 0,
            },
            "source_candidates": [],
            "merge_decisions": _serialize_merge_decisions(decisions),
            "bibliography": {
                "title": title,
                "authors": [],
                "publication_year": None,
                "publication_date": None,
                "venue": None,
                "document_type": None,
            },
            "content": {
                "abstract": None,
                "combined_text": _combined_text(title, None),
                "language": "en",
                "fulltext_ref": None,
                "fulltext_status": FULLTEXT_STATUS_NOT_ATTEMPTED,
                "fulltext_quality": None,
            },
            "labels": {
                "gold_label": seed.gold_label,
                "is_hard_negative": seed.is_hard_negative,
                "auto_topic_tags": tagging.topic_tags,
                "auto_method_tags": tagging.method_tags,
                "auto_topic_tag_scores": tagging.topic_scores,
                "auto_method_tag_scores": tagging.method_scores,
                "auto_topic_tag_evidence": tagging.topic_evidence,
                "auto_method_tag_evidence": tagging.method_evidence,
                "manual_topic_tags": [],
                "manual_method_tags": [],
                "notes": seed.notes,
            },
            "quality": {
                "has_abstract": False,
                "has_pdf_url": False,
                "is_open_access": None,
                "citation_count": None,
            },
            "links": {
                "landing_page_url": seed.url,
                "pdf_url": None,
            },
            "provenance": {
                "seed_query": seed.seed_query,
                "input_position": seed.input_position,
                "resolver_summary": {
                    "attempted": resolution.attempted,
                    "successful": resolution.successful,
                    "errors": resolution.errors,
                    "rejections": resolution.rejections,
                },
                "merge_summary": {},
            },
            "raw": {
                "seed_extra": seed.extra,
                "source_payload_refs": source_payload_refs,
            },
        }
        return record, decisions

    def _candidate_score(self, candidate: ProviderResult) -> tuple[Any, ...]:
        payload = candidate.payload
        metadata_count = sum(
            bool(payload.get(key))
            for key in (
                "title",
                "abstract",
                "authors",
                "publication_year",
                "publication_date",
                "venue",
                "document_type",
                "doi",
                "pdf_url",
                "openalex_id",
            )
        )
        return (
            int(self._structured_source(candidate)),
            int(candidate.provider_name == "openalex" and bool(payload.get("doi"))),
            int(bool(payload.get("doi"))),
            int(bool(payload.get("openalex_id"))),
            metadata_count,
            int(candidate.provider_name == "arxiv" and bool(payload.get("pdf_url"))),
            candidate.confidence,
        )

    def _record_merge_score(self, record: dict[str, Any]) -> tuple[Any, ...]:
        identifiers = record.get("identifiers", {})
        bibliography = record.get("bibliography", {})
        quality = record.get("quality", {})
        sources = record.get("sources", {})
        return (
            int(bool(identifiers.get("doi"))),
            int(bool(identifiers.get("openalex_id"))),
            int(bool(record.get("links", {}).get("pdf_url"))),
            int(quality.get("citation_count") is not None),
            sources.get("source_candidates_count") or 0,
            len(bibliography.get("authors") or []),
            len(record.get("content", {}).get("abstract") or ""),
        )

    def _select_identifier(
        self,
        candidates: Iterable[ProviderResult],
        field_name: str,
        *,
        reason: str,
    ) -> tuple[str | None, FieldDecision]:
        available = [candidate for candidate in candidates if _present(candidate.payload.get(field_name))]
        if not available:
            return None, FieldDecision(winner=None, candidates=[], reason="no candidate value")
        winner = max(available, key=self._candidate_score)
        return winner.payload.get(field_name), FieldDecision(
            winner=winner.provider_name,
            candidates=[candidate.provider_name for candidate in available],
            reason=reason,
        )

    def _select_title(
        self,
        candidates: Iterable[ProviderResult],
        seed: ArticleSeed,
    ) -> tuple[str | None, FieldDecision]:
        available = [candidate for candidate in candidates if _present(candidate.payload.get("title"))]
        if not available:
            return seed.title, FieldDecision(
                winner="manual" if seed.title else None,
                candidates=[],
                reason="fallback to seed title" if seed.title else "no candidate value",
            )

        seed_slug = slugify_title(seed.title)

        def score(candidate: ProviderResult) -> tuple[Any, ...]:
            title = candidate.payload.get("title")
            return (
                int(bool(seed_slug and slugify_title(title) == seed_slug)),
                int(self._structured_source(candidate)),
                int(candidate.provider_name == "openalex"),
                len(title or ""),
                candidate.confidence,
            )

        ranked = sorted(available, key=score, reverse=True)
        winner = ranked[0]
        reason = "structured metadata + exact title match"
        if not (seed_slug and slugify_title(winner.payload.get("title")) == seed_slug):
            reason = "highest-quality structured title"
        return normalize_whitespace(winner.payload.get("title")), FieldDecision(
            winner=winner.provider_name,
            candidates=[candidate.provider_name for candidate in ranked],
            reason=reason,
        )

    def _select_authors(self, candidates: Iterable[ProviderResult]) -> tuple[list[str], FieldDecision]:
        available = [candidate for candidate in candidates if candidate.payload.get("authors")]
        if not available:
            return [], FieldDecision(winner=None, candidates=[], reason="no candidate value")

        def score(candidate: ProviderResult) -> tuple[Any, ...]:
            cleaned = [
                normalize_whitespace(author)
                for author in (candidate.payload.get("authors") or [])
                if normalize_whitespace(author)
            ]
            return (
                len(cleaned),
                int(self._structured_source(candidate)),
                int(mean(len(author) for author in cleaned) if cleaned else 0),
                candidate.confidence,
            )

        ranked = sorted(available, key=score, reverse=True)
        authors = [
            normalize_whitespace(author)
            for author in (ranked[0].payload.get("authors") or [])
            if normalize_whitespace(author)
        ]
        return authors, FieldDecision(
            winner=ranked[0].provider_name,
            candidates=[candidate.provider_name for candidate in ranked],
            reason="more complete author list",
        )

    def _select_abstract(self, candidates: Iterable[ProviderResult]) -> tuple[str | None, FieldDecision]:
        available = [candidate for candidate in candidates if _present(candidate.payload.get("abstract"))]
        if not available:
            return None, FieldDecision(winner=None, candidates=[], reason="no candidate value")

        def score(candidate: ProviderResult) -> tuple[Any, ...]:
            abstract = normalize_whitespace(candidate.payload.get("abstract")) or ""
            return (
                int(not abstract.endswith("...")),
                len(abstract),
                int(candidate.provider_name == "arxiv"),
                int(self._structured_source(candidate)),
                candidate.confidence,
            )

        ranked = sorted(available, key=score, reverse=True)
        return normalize_whitespace(ranked[0].payload.get("abstract")), FieldDecision(
            winner=ranked[0].provider_name,
            candidates=[candidate.provider_name for candidate in ranked],
            reason="longer abstract",
        )

    def _select_venue(self, candidates: Iterable[ProviderResult]) -> tuple[str | None, FieldDecision]:
        available = [candidate for candidate in candidates if _present(candidate.payload.get("venue"))]
        if not available:
            return None, FieldDecision(winner=None, candidates=[], reason="no candidate value")

        def score(candidate: ProviderResult) -> tuple[Any, ...]:
            return (
                int(candidate.provider_name == "openalex"),
                int(self._structured_source(candidate)),
                len(candidate.payload.get("venue") or ""),
                candidate.confidence,
            )

        ranked = sorted(available, key=score, reverse=True)
        return normalize_whitespace(ranked[0].payload.get("venue")), FieldDecision(
            winner=ranked[0].provider_name,
            candidates=[candidate.provider_name for candidate in ranked],
            reason="structured venue metadata",
        )

    def _select_landing_page(self, candidates: Iterable[ProviderResult]) -> tuple[str | None, FieldDecision]:
        available = [candidate for candidate in candidates if _present(candidate.payload.get("landing_page_url"))]
        if not available:
            return None, FieldDecision(winner=None, candidates=[], reason="no candidate value")

        def score(candidate: ProviderResult) -> tuple[Any, ...]:
            url = candidate.payload.get("landing_page_url") or ""
            return (
                int("doi.org/" in url),
                int(self._structured_source(candidate)),
                int(candidate.provider_name == "openalex"),
                candidate.confidence,
            )

        ranked = sorted(available, key=score, reverse=True)
        return ranked[0].payload.get("landing_page_url"), FieldDecision(
            winner=ranked[0].provider_name,
            candidates=[candidate.provider_name for candidate in ranked],
            reason="best scholarly landing page",
        )

    def _select_pdf_url(self, candidates: Iterable[ProviderResult]) -> tuple[str | None, FieldDecision]:
        available = [candidate for candidate in candidates if _present(candidate.payload.get("pdf_url"))]
        if not available:
            return None, FieldDecision(winner=None, candidates=[], reason="no candidate value")

        def score(candidate: ProviderResult) -> tuple[Any, ...]:
            pdf_url = (candidate.payload.get("pdf_url") or "").lower()
            return (
                int(candidate.provider_name == "arxiv" and "arxiv.org/pdf/" in pdf_url),
                int(self._looks_like_pdf_url(pdf_url)),
                int(self._structured_source(candidate)),
                candidate.confidence,
            )

        ranked = sorted(available, key=score, reverse=True)
        pdf_url = ranked[0].payload.get("pdf_url")
        reason = "direct arXiv PDF" if "arxiv.org/pdf/" in (pdf_url or "") else "valid scholarly PDF URL"
        return pdf_url, FieldDecision(
            winner=ranked[0].provider_name,
            candidates=[candidate.provider_name for candidate in ranked],
            reason=reason,
        )

    def _select_open_access(self, candidates: Iterable[ProviderResult]) -> tuple[bool | None, FieldDecision]:
        available = [candidate for candidate in candidates if candidate.payload.get("is_open_access") is not None]
        if not available:
            return None, FieldDecision(winner=None, candidates=[], reason="no candidate value")

        def score(candidate: ProviderResult) -> tuple[Any, ...]:
            return (
                int(candidate.provider_name == "openalex"),
                int(self._structured_source(candidate)),
                candidate.confidence,
            )

        ranked = sorted(available, key=score, reverse=True)
        return ranked[0].payload.get("is_open_access"), FieldDecision(
            winner=ranked[0].provider_name,
            candidates=[candidate.provider_name for candidate in ranked],
            reason="structured open-access metadata",
        )

    def _select_citation_count(self, candidates: Iterable[ProviderResult]) -> tuple[int | None, FieldDecision]:
        available = [candidate for candidate in candidates if candidate.payload.get("citation_count") is not None]
        if not available:
            return None, FieldDecision(winner=None, candidates=[], reason="no candidate value")

        def score(candidate: ProviderResult) -> tuple[Any, ...]:
            value = candidate.payload.get("citation_count")
            return (
                int(candidate.provider_name == "openalex"),
                int(self._structured_source(candidate)),
                value if isinstance(value, int) else -1,
                candidate.confidence,
            )

        ranked = sorted(available, key=score, reverse=True)
        return ranked[0].payload.get("citation_count"), FieldDecision(
            winner=ranked[0].provider_name,
            candidates=[candidate.provider_name for candidate in ranked],
            reason="structured citation metadata",
        )

    def _select_generic(
        self,
        candidates: Iterable[ProviderResult],
        field_name: str,
        *,
        reason: str,
        default: Any = None,
    ) -> tuple[Any, FieldDecision]:
        available = [candidate for candidate in candidates if _present(candidate.payload.get(field_name))]
        if not available:
            return default, FieldDecision(winner=None, candidates=[], reason="no candidate value")
        winner = max(available, key=self._candidate_score)
        return winner.payload.get(field_name), FieldDecision(
            winner=winner.provider_name,
            candidates=[candidate.provider_name for candidate in available],
            reason=reason,
        )

    def _select_record_field(
        self,
        records: Iterable[dict[str, Any]],
        field_name: str,
        path: tuple[str, str],
    ) -> tuple[Any, FieldDecision]:
        available = [record for record in records if _present(_get_nested_value(record, path))]
        if not available:
            return None, FieldDecision(winner=None, candidates=[], reason="no candidate value")
        winner = max(available, key=self._record_merge_score)
        primary_source = winner.get("sources", {}).get("primary_source") or winner.get("identifiers", {}).get("source")
        if field_name.endswith("title"):
            reason = "best merged title from duplicate group"
        elif field_name.endswith("abstract"):
            reason = "longer abstract from duplicate group"
        elif field_name.endswith("authors"):
            reason = "more complete author list from duplicate group"
        else:
            reason = "best merged duplicate record"
        return _get_nested_value(winner, path), FieldDecision(
            winner=primary_source,
            candidates=[
                record.get("sources", {}).get("primary_source") or record.get("identifiers", {}).get("source")
                for record in available
            ],
            reason=reason,
        )

    def _structured_source(self, candidate: ProviderResult) -> bool:
        payload = candidate.payload
        return bool(
            candidate.provider_name == "openalex"
            or payload.get("doi")
            or payload.get("openalex_id")
            or payload.get("citation_count") is not None
        )

    def _looks_like_pdf_url(self, value: str) -> bool:
        return value.endswith(".pdf") or "/pdf/" in value


def _candidate_summary(candidate: ProviderResult) -> dict[str, Any]:
    payload = candidate.payload
    return {
        "provider_name": candidate.provider_name,
        "source_id": candidate.source_id,
        "confidence": candidate.confidence,
        "match_details": candidate.match_details,
        "identifiers": {
            "doi": payload.get("doi"),
            "arxiv_id": payload.get("arxiv_id"),
            "openalex_id": payload.get("openalex_id"),
        },
        "has_abstract": bool(payload.get("abstract")),
        "has_pdf_url": bool(payload.get("pdf_url")),
    }


def _available_sources(candidates: Iterable[ProviderResult]) -> list[str]:
    seen: set[str] = set()
    ordered_sources: list[str] = []
    for candidate in candidates:
        if candidate.provider_name in seen:
            continue
        seen.add(candidate.provider_name)
        ordered_sources.append(candidate.provider_name)
    return ordered_sources


def _available_record_sources(records: Iterable[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    ordered_sources: list[str] = []
    for record in records:
        sources = record.get("sources", {}).get("available_sources") or []
        primary = record.get("sources", {}).get("primary_source")
        for source in [primary, *sources]:
            if not source or source in seen:
                continue
            seen.add(source)
            ordered_sources.append(source)
    return ordered_sources


def _merge_source_candidates(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str | None, str | None]] = set()
    merged: list[dict[str, Any]] = []
    for record in records:
        for candidate in record.get("source_candidates") or []:
            key = (candidate.get("provider_name"), candidate.get("source_id"))
            if key in seen:
                continue
            seen.add(key)
            merged.append(deepcopy(candidate))
    return merged


def _merge_source_payload_refs(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    duplicates: dict[str, list[str]] = {}
    for record in records:
        refs = record.get("raw", {}).get("source_payload_refs") or {}
        for provider_name, ref in refs.items():
            if provider_name not in merged:
                merged[provider_name] = ref
                continue
            if merged[provider_name] == ref:
                continue
            duplicates.setdefault(provider_name, [merged[provider_name]])
            if ref not in duplicates[provider_name]:
                duplicates[provider_name].append(ref)
    for provider_name, refs in duplicates.items():
        merged[provider_name] = refs
    return merged


def _combined_text(title: str | None, abstract: str | None) -> str:
    title = normalize_whitespace(title)
    abstract = normalize_whitespace(abstract)
    if title and abstract:
        return f"{title}\n\n{abstract}"
    return title or abstract or ""


def _merge_summary(decisions: dict[str, FieldDecision]) -> dict[str, Any]:
    summary_fields = {
        "title_winner": "bibliography.title",
        "abstract_winner": "content.abstract",
        "authors_winner": "bibliography.authors",
        "venue_winner": "bibliography.venue",
        "pdf_url_winner": "links.pdf_url",
        "citation_count_winner": "quality.citation_count",
    }
    return {
        summary_key: decisions[field_key].winner
        for summary_key, field_key in summary_fields.items()
        if field_key in decisions
    }


def _serialize_merge_decisions(decision: MergeDecision) -> dict[str, Any]:
    return {
        field_name: {
            "winner": field_decision.winner,
            "candidates": field_decision.candidates,
            "reason": field_decision.reason,
        }
        for field_name, field_decision in decision.fields.items()
    }


def _decision_candidates(*decisions: FieldDecision) -> list[str]:
    seen: set[str] = set()
    candidates: list[str] = []
    for decision in decisions:
        for candidate in decision.candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            candidates.append(candidate)
    return candidates


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    return True


def _get_nested_value(payload: dict[str, Any], path: tuple[str, str]) -> Any:
    node = payload.get(path[0]) or {}
    if not isinstance(node, dict):
        return None
    return node.get(path[1])


def _set_nested_value(payload: dict[str, Any], path: tuple[str, str], value: Any) -> None:
    payload.setdefault(path[0], {})
    payload[path[0]][path[1]] = value


def _dedup_strategy(records: list[dict[str, Any]]) -> str:
    dois = {record.get("identifiers", {}).get("doi") for record in records if record.get("identifiers", {}).get("doi")}
    if len(dois) == 1 and dois:
        return "doi"
    arxiv_ids = {
        record.get("identifiers", {}).get("arxiv_id")
        for record in records
        if record.get("identifiers", {}).get("arxiv_id")
    }
    if len(arxiv_ids) == 1 and arxiv_ids:
        return "arxiv_id"
    canonical_ids = {
        record.get("identifiers", {}).get("canonical_id")
        for record in records
        if record.get("identifiers", {}).get("canonical_id")
    }
    if len(canonical_ids) == 1 and canonical_ids:
        return "canonical_id"
    return "fuzzy_title_year_author"
