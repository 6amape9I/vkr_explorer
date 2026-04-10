from __future__ import annotations

from typing import Any

from ..config import Settings
from ..http import HttpClient
from ..models import ArticleSeed, ProviderResult
from ..utils import extract_doi, normalize_whitespace, slugify_title


OPENALEX_WORKS_URL = "https://api.openalex.org/works"


class OpenAlexProvider:
    def __init__(self, http_client: HttpClient, settings: Settings) -> None:
        self.http_client = http_client
        self.settings = settings

    def resolve(self, seed: ArticleSeed) -> ProviderResult | None:
        doi = seed.doi or extract_doi(seed.url)
        if doi:
            return self._resolve_by_doi(doi)
        if seed.title:
            return self._resolve_by_title(seed.title)
        return None

    def _resolve_by_doi(self, doi: str) -> ProviderResult | None:
        params = self._base_params()
        params["filter"] = f"doi:{doi.lower()}"
        data = self.http_client.get_json(OPENALEX_WORKS_URL, params=params)
        results = data.get("results") or []
        if not results:
            return None
        work = results[0]
        return self._to_result(work=work, confidence=0.99)

    def _resolve_by_title(self, title: str) -> ProviderResult | None:
        params = self._base_params()
        params["search"] = title
        params["per-page"] = 5
        data = self.http_client.get_json(OPENALEX_WORKS_URL, params=params)
        results = data.get("results") or []
        if not results:
            return None

        wanted = slugify_title(title)
        best = results[0]
        confidence = 0.75
        for candidate in results:
            candidate_title = slugify_title(candidate.get("display_name"))
            if candidate_title and wanted and candidate_title == wanted:
                best = candidate
                confidence = 0.95
                break
        return self._to_result(work=best, confidence=confidence)

    def _to_result(self, work: dict[str, Any], confidence: float) -> ProviderResult:
        title = normalize_whitespace(work.get("display_name"))
        abstract = _openalex_abstract_to_text(work.get("abstract_inverted_index"))
        source = (work.get("primary_location") or {}).get("source") or {}
        payload = {
            "title": title,
            "abstract": abstract,
            "authors": [
                author.get("author", {}).get("display_name")
                for author in (work.get("authorships") or [])
                if author.get("author", {}).get("display_name")
            ],
            "publication_date": work.get("publication_date"),
            "publication_year": work.get("publication_year"),
            "venue": source.get("display_name") or work.get("host_venue", {}).get("display_name"),
            "document_type": work.get("type"),
            "doi": _strip_doi_prefix(work.get("doi")),
            "arxiv_id": _extract_arxiv_id_from_locations(work),
            "landing_page_url": _best_landing_page(work),
            "pdf_url": _best_pdf_url(work),
            "language": work.get("language"),
            "is_open_access": (work.get("open_access") or {}).get("is_oa"),
            "citation_count": work.get("cited_by_count"),
            "openalex_id": work.get("id"),
        }
        return ProviderResult(
            provider_name="openalex",
            source_id=work.get("id"),
            confidence=confidence,
            payload=payload,
            raw=work,
        )

    def _base_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if self.settings.contact_email:
            params["mailto"] = self.settings.contact_email
        if self.settings.openalex_api_key:
            params["api_key"] = self.settings.openalex_api_key
        return params


def _openalex_abstract_to_text(index: dict[str, list[int]] | None) -> str | None:
    if not index:
        return None
    tokens: list[tuple[int, str]] = []
    for word, positions in index.items():
        for pos in positions:
            tokens.append((pos, word))
    if not tokens:
        return None
    tokens.sort(key=lambda item: item[0])
    return normalize_whitespace(" ".join(word for _, word in tokens))


def _strip_doi_prefix(value: str | None) -> str | None:
    if not value:
        return None
    return value.removeprefix("https://doi.org/").strip() or None


def _best_landing_page(work: dict[str, Any]) -> str | None:
    primary_location = work.get("primary_location") or {}
    return primary_location.get("landing_page_url") or primary_location.get("pdf_url")


def _best_pdf_url(work: dict[str, Any]) -> str | None:
    primary_location = work.get("primary_location") or {}
    return primary_location.get("pdf_url")


def _extract_arxiv_id_from_locations(work: dict[str, Any]) -> str | None:
    locations = work.get("locations") or []
    for location in locations:
        landing = location.get("landing_page_url") or ""
        if "arxiv.org/abs/" in landing:
            return landing.rsplit("/", 1)[-1].split("v")[0]
    return None
