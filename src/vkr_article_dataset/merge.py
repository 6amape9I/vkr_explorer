from __future__ import annotations

from typing import Any, Iterable

from .models import ArticleSeed, ProviderResult, ResolutionResult
from .schema import FULLTEXT_STATUS_NOT_ATTEMPTED, SCHEMA_VERSION, canonical_id
from .tagger import infer_tags
from .utils import extract_arxiv_id, extract_doi, normalize_whitespace, stable_record_id, utc_now_iso


class RecordMerger:
    def build_record(
        self,
        seed: ArticleSeed,
        resolution: ResolutionResult,
        *,
        source_payload_refs: dict[str, str] | None = None,
    ) -> dict[str, Any]:
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

        title = self._choose_value(ordered_candidates, "title") or seed.title
        abstract = self._choose_value(ordered_candidates, "abstract")
        doi = self._choose_value(ordered_candidates, "doi") or seed.doi or extract_doi(seed.url)
        arxiv_id = (
            self._choose_value(ordered_candidates, "arxiv_id")
            or seed.arxiv_id
            or extract_arxiv_id(seed.url)
        )
        openalex_id = self._choose_value(ordered_candidates, "openalex_id")
        record_id = stable_record_id(doi, arxiv_id, openalex_id, title, seed.url)
        topic_tags, method_tags = infer_tags(title=title, abstract=abstract)

        return {
            "schema_version": SCHEMA_VERSION,
            "record_id": record_id,
            "resolution_status": "resolved" if title else "partial",
            "retrieved_at": utc_now_iso(),
            "identifiers": {
                "doi": doi,
                "arxiv_id": arxiv_id,
                "openalex_id": openalex_id,
                "canonical_id": canonical_id(doi, arxiv_id, openalex_id, title),
                # Backward-compatible alias for older consumers.
                "source": primary.provider_name,
            },
            "sources": {
                "primary_source": primary.provider_name,
                "available_sources": _available_sources(ordered_candidates),
                "source_candidates_count": len(resolution.candidates),
            },
            "source_candidates": [_candidate_summary(candidate) for candidate in ordered_candidates],
            "bibliography": {
                "title": title,
                "authors": self._choose_value(ordered_candidates, "authors", default=[]),
                "publication_year": self._choose_value(ordered_candidates, "publication_year"),
                "publication_date": self._choose_value(ordered_candidates, "publication_date"),
                "venue": self._choose_value(ordered_candidates, "venue"),
                "document_type": self._choose_value(ordered_candidates, "document_type"),
            },
            "content": {
                "abstract": abstract,
                "combined_text": _combined_text(title, abstract),
                "language": self._choose_value(ordered_candidates, "language") or "en",
                "fulltext_ref": None,
                "fulltext_status": FULLTEXT_STATUS_NOT_ATTEMPTED,
                "fulltext_quality": None,
            },
            "labels": {
                "gold_label": seed.gold_label,
                "is_hard_negative": seed.is_hard_negative,
                "auto_topic_tags": topic_tags,
                "auto_method_tags": method_tags,
                "manual_topic_tags": [],
                "manual_method_tags": [],
                "notes": seed.notes,
            },
            "quality": {
                "has_abstract": bool(abstract),
                "has_pdf_url": bool(self._choose_value(ordered_candidates, "pdf_url")),
                "is_open_access": self._choose_value(ordered_candidates, "is_open_access"),
                "citation_count": self._choose_value(ordered_candidates, "citation_count"),
            },
            "links": {
                "landing_page_url": self._choose_value(ordered_candidates, "landing_page_url"),
                "pdf_url": self._choose_value(ordered_candidates, "pdf_url"),
            },
            "provenance": {
                "seed_query": seed.seed_query,
                "input_position": seed.input_position,
                "resolver_summary": {
                    "attempted": resolution.attempted,
                    "successful": resolution.successful,
                    "errors": resolution.errors,
                },
            },
            "raw": {
                "seed_extra": seed.extra,
                "source_payload_refs": source_payload_refs,
            },
        }

    def _build_fallback_record(
        self,
        *,
        seed: ArticleSeed,
        resolution: ResolutionResult,
        source_payload_refs: dict[str, str],
    ) -> dict[str, Any]:
        title = seed.title
        doi = seed.doi or extract_doi(seed.url)
        arxiv_id = seed.arxiv_id or extract_arxiv_id(seed.url)
        record_id = stable_record_id(doi, arxiv_id, title, seed.url)
        topic_tags, method_tags = infer_tags(title=title, abstract=None)
        return {
            "schema_version": SCHEMA_VERSION,
            "record_id": record_id,
            "resolution_status": "failed",
            "retrieved_at": utc_now_iso(),
            "identifiers": {
                "doi": doi,
                "arxiv_id": arxiv_id,
                "openalex_id": None,
                "canonical_id": canonical_id(doi, arxiv_id, None, title),
                "source": "manual",
            },
            "sources": {
                "primary_source": "manual",
                "available_sources": [],
                "source_candidates_count": 0,
            },
            "source_candidates": [],
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
                "auto_topic_tags": topic_tags,
                "auto_method_tags": method_tags,
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
                },
            },
            "raw": {
                "seed_extra": seed.extra,
                "source_payload_refs": source_payload_refs,
            },
        }

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
            int(candidate.provider_name == "openalex" and bool(payload.get("doi"))),
            int(bool(payload.get("doi"))),
            metadata_count,
            int(candidate.provider_name == "openalex"),
            int(candidate.provider_name == "arxiv" and bool(payload.get("pdf_url"))),
            candidate.confidence,
        )

    def _choose_value(
        self,
        candidates: Iterable[ProviderResult],
        field_name: str,
        *,
        default: Any = None,
    ) -> Any:
        for candidate in candidates:
            value = candidate.payload.get(field_name)
            if _present(value):
                return value
        return default


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


def _combined_text(title: str | None, abstract: str | None) -> str:
    title = normalize_whitespace(title)
    abstract = normalize_whitespace(abstract)
    if title and abstract:
        return f"{title}\n\n{abstract}"
    return title or abstract or ""


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    return True
