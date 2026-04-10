from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .config import Settings
from .http import HttpClient
from .models import ProviderResult
from .providers.openalex_provider import openalex_work_to_result
from .utils import utc_now_iso


OPENALEX_SEARCH_URL = "https://api.openalex.org/works"
OPENALEX_SOURCE = "openalex"
SEARCH_MODES = {"search", "title", "abstract", "title_abstract"}


@dataclass(slots=True)
class DiscoveryQuery:
    query: str
    source: str = OPENALEX_SOURCE
    mode: str = "search"
    max_results: int = 200
    query_index: int = 1


@dataclass(slots=True)
class SearchMatch:
    query: str
    search_source: str
    search_rank: int
    retrieved_at: str
    mode: str
    source_info: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SearchCandidate:
    provider_result: ProviderResult
    query: str
    search_source: str
    search_rank: int
    retrieved_at: str
    mode: str
    source_info: dict[str, Any] = field(default_factory=dict)

    def to_search_match(self) -> SearchMatch:
        return SearchMatch(
            query=self.query,
            search_source=self.search_source,
            search_rank=self.search_rank,
            retrieved_at=self.retrieved_at,
            mode=self.mode,
            source_info=self.source_info,
        )


@dataclass(slots=True)
class SearchPage:
    page_number: int
    payload: dict[str, Any]
    results_count: int


class SearchSource:
    source_name: str

    def search(self, query: DiscoveryQuery) -> tuple[list[SearchCandidate], list[SearchPage]]:
        raise NotImplementedError


class OpenAlexSearchSource(SearchSource):
    source_name = OPENALEX_SOURCE

    def __init__(self, http_client: HttpClient, settings: Settings) -> None:
        self.http_client = http_client
        self.settings = settings

    def search(self, query: DiscoveryQuery) -> tuple[list[SearchCandidate], list[SearchPage]]:
        if query.mode not in SEARCH_MODES:
            raise ValueError(f"Unsupported OpenAlex search mode: {query.mode}")

        per_page = min(200, max(1, query.max_results))
        candidates: list[SearchCandidate] = []
        pages: list[SearchPage] = []
        page_number = 1

        while len(candidates) < query.max_results:
            params = self._build_params(query=query, per_page=per_page, page_number=page_number)
            payload = self.http_client.get_json(OPENALEX_SEARCH_URL, params=params, openalex=True)
            results = payload.get("results") or []
            pages.append(
                SearchPage(
                    page_number=page_number,
                    payload=payload,
                    results_count=len(results),
                )
            )
            if not results:
                break

            for page_offset, work in enumerate(results, start=1):
                overall_rank = len(candidates) + 1
                provider_result = openalex_work_to_result(
                    work=work,
                    confidence=_discovery_confidence(work, overall_rank),
                    match_details={
                        "matched_by": "discovery_search",
                        "strategy": f"openalex_{query.mode}",
                        "page": page_number,
                        "page_rank": page_offset,
                    },
                )
                candidates.append(
                    SearchCandidate(
                        provider_result=provider_result,
                        query=query.query,
                        search_source=self.source_name,
                        search_rank=overall_rank,
                        retrieved_at=utc_now_iso(),
                        mode=query.mode,
                        source_info={
                            "page": page_number,
                            "page_rank": page_offset,
                            "openalex_id": work.get("id"),
                        },
                    )
                )
                if len(candidates) >= query.max_results:
                    break
            if len(results) < per_page:
                break
            page_number += 1

        return candidates, pages

    def _build_params(self, *, query: DiscoveryQuery, per_page: int, page_number: int) -> dict[str, Any]:
        params: dict[str, Any] = {
            "per-page": per_page,
            "page": page_number,
        }
        if self.settings.contact_email:
            params["mailto"] = self.settings.contact_email
        if self.settings.openalex_api_key:
            params["api_key"] = self.settings.openalex_api_key

        if query.mode == "search":
            params["search"] = query.query
        else:
            filter_name = {
                "title": "title.search",
                "abstract": "abstract.search",
                "title_abstract": "title_and_abstract.search",
            }[query.mode]
            params["filter"] = f"{filter_name}:{query.query}"
        return params


def load_discovery_queries(
    path: str | Path,
    *,
    default_source: str = OPENALEX_SOURCE,
    default_mode: str = "search",
    default_max_results: int = 200,
) -> list[DiscoveryQuery]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() == ".jsonl":
        return _load_jsonl_queries(
            path,
            default_source=default_source,
            default_mode=default_mode,
            default_max_results=default_max_results,
        )
    return _load_text_queries(
        path,
        default_source=default_source,
        default_mode=default_mode,
        default_max_results=default_max_results,
    )


def serialize_queries(queries: list[DiscoveryQuery]) -> list[dict[str, Any]]:
    return [asdict(query) for query in queries]


def _load_text_queries(
    path: Path,
    *,
    default_source: str,
    default_mode: str,
    default_max_results: int,
) -> list[DiscoveryQuery]:
    queries: list[DiscoveryQuery] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_index, line in enumerate(fh, start=1):
            text = line.strip()
            if not text or text.startswith("#"):
                continue
            queries.append(
                DiscoveryQuery(
                    query=text,
                    source=default_source,
                    mode=default_mode,
                    max_results=default_max_results,
                    query_index=len(queries) + 1,
                )
            )
    return queries


def _load_jsonl_queries(
    path: Path,
    *,
    default_source: str,
    default_mode: str,
    default_max_results: int,
) -> list[DiscoveryQuery]:
    queries: list[DiscoveryQuery] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_number, line in enumerate(fh, start=1):
            text = line.strip()
            if not text:
                continue
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise ValueError(f"Invalid query entry at line {line_number}: expected JSON object")
            query_text = str(payload.get("query") or "").strip()
            if not query_text:
                raise ValueError(f"Invalid query entry at line {line_number}: missing query")
            source = str(payload.get("source") or default_source).strip() or default_source
            mode = str(payload.get("mode") or default_mode).strip() or default_mode
            max_results = int(payload.get("max_results") or default_max_results)
            queries.append(
                DiscoveryQuery(
                    query=query_text,
                    source=source,
                    mode=mode,
                    max_results=max_results,
                    query_index=len(queries) + 1,
                )
            )
    return queries


def _discovery_confidence(work: dict[str, Any], rank: int) -> float:
    score = 0.45
    if work.get("doi"):
        score += 0.20
    if work.get("abstract_inverted_index"):
        score += 0.10
    if (work.get("primary_location") or {}).get("pdf_url"):
        score += 0.05
    score += max(0.0, 0.15 - (rank * 0.002))
    return max(0.0, min(round(score, 4), 0.99))
