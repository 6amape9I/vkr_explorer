from __future__ import annotations

from typing import Iterable

from .models import ArticleSeed, ProviderResult
from .tagger import infer_tags
from .utils import extract_arxiv_id, extract_doi, normalize_whitespace, stable_record_id, utc_now_iso


class DatasetBuilder:
    def __init__(self, resolvers: Iterable) -> None:
        self.resolvers = list(resolvers)

    def build_record(self, seed: ArticleSeed) -> dict:
        provider_result = self._resolve(seed)
        if provider_result is None:
            return self._build_fallback_record(seed)
        return self._normalize(seed, provider_result)

    def build_records(self, seeds: list[ArticleSeed]) -> list[dict]:
        records = [self.build_record(seed) for seed in seeds]
        return self._deduplicate(records)

    def _resolve(self, seed: ArticleSeed) -> ProviderResult | None:
        for resolver in self.resolvers:
            try:
                result = resolver.resolve(seed)
            except Exception as exc:  # noqa: BLE001
                result = None
                last_error = f"{type(exc).__name__}: {exc}"
            else:
                last_error = None
            if result is not None:
                if last_error:
                    result.raw.setdefault("resolution_warnings", []).append(last_error)
                return result
        return None

    def _normalize(self, seed: ArticleSeed, provider: ProviderResult) -> dict:
        payload = provider.payload
        title = payload.get("title") or seed.title
        abstract = payload.get("abstract")
        topic_tags, method_tags = infer_tags(title=title, abstract=abstract)

        doi = payload.get("doi") or seed.doi or extract_doi(seed.url)
        arxiv_id = payload.get("arxiv_id") or seed.arxiv_id or extract_arxiv_id(seed.url)
        record_id = stable_record_id(doi, arxiv_id, title)

        combined_text = _combined_text(title, abstract)
        has_abstract = bool(abstract)
        has_pdf_url = bool(payload.get("pdf_url"))

        return {
            "record_id": record_id,
            "resolution_status": "resolved" if title else "partial",
            "retrieved_at": utc_now_iso(),
            "identifiers": {
                "doi": doi,
                "arxiv_id": arxiv_id,
                "openalex_id": payload.get("openalex_id"),
                "source": provider.provider_name,
            },
            "bibliography": {
                "title": title,
                "authors": payload.get("authors") or [],
                "publication_year": payload.get("publication_year"),
                "publication_date": payload.get("publication_date"),
                "venue": payload.get("venue"),
                "document_type": payload.get("document_type"),
            },
            "content": {
                "abstract": abstract,
                "combined_text": combined_text,
                "language": payload.get("language") or "en",
            },
            "labels": {
                "gold_label": seed.gold_label,
                "is_hard_negative": seed.is_hard_negative,
                "topic_tags": topic_tags,
                "method_tags": method_tags,
                "notes": seed.notes,
            },
            "quality": {
                "has_abstract": has_abstract,
                "has_pdf_url": has_pdf_url,
                "is_open_access": payload.get("is_open_access"),
                "citation_count": payload.get("citation_count"),
            },
            "links": {
                "landing_page_url": payload.get("landing_page_url"),
                "pdf_url": payload.get("pdf_url"),
            },
            "provenance": {
                "seed_query": seed.seed_query,
                "input_position": seed.input_position,
                "resolver": provider.provider_name,
                "resolver_confidence": provider.confidence,
            },
            "raw": {
                "provider": provider.provider_name,
                "seed_extra": seed.extra,
                "provider_payload": provider.raw,
            },
        }

    def _build_fallback_record(self, seed: ArticleSeed) -> dict:
        title = seed.title
        topic_tags, method_tags = infer_tags(title=title, abstract=None)
        doi = seed.doi or extract_doi(seed.url)
        arxiv_id = seed.arxiv_id or extract_arxiv_id(seed.url)
        record_id = stable_record_id(doi, arxiv_id, title, seed.url)
        return {
            "record_id": record_id,
            "resolution_status": "failed",
            "retrieved_at": utc_now_iso(),
            "identifiers": {
                "doi": doi,
                "arxiv_id": arxiv_id,
                "openalex_id": None,
                "source": "manual",
            },
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
            },
            "labels": {
                "gold_label": seed.gold_label,
                "is_hard_negative": seed.is_hard_negative,
                "topic_tags": topic_tags,
                "method_tags": method_tags,
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
                "resolver": "manual",
                "resolver_confidence": 0.0,
            },
            "raw": {
                "provider": "manual",
                "seed_extra": seed.extra,
            },
        }

    def _deduplicate(self, records: list[dict]) -> list[dict]:
        seen: dict[str, dict] = {}
        for record in records:
            key = record["record_id"]
            current = seen.get(key)
            if current is None:
                seen[key] = record
                continue
            current_status = current.get("resolution_status")
            new_status = record.get("resolution_status")
            if current_status != "resolved" and new_status == "resolved":
                seen[key] = record
        return list(seen.values())


def _combined_text(title: str | None, abstract: str | None) -> str:
    title = normalize_whitespace(title)
    abstract = normalize_whitespace(abstract)
    if title and abstract:
        return f"{title}\n\n{abstract}"
    return title or abstract or ""
