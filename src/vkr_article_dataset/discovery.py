from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from .config import Settings
from .discovery_inference import DiscoveryInference
from .discovery_storage import DiscoveryRunStorage
from .merge import RecordMerger
from .models import ArticleSeed, ProviderResult, ResolutionResult
from .normalization import group_duplicate_record_indices
from .search_sources import (
    OPENALEX_SOURCE,
    DiscoveryQuery,
    OpenAlexSearchSource,
    SearchCandidate,
    SearchSource,
    load_discovery_queries,
    serialize_queries,
)
from .utils import utc_now_iso


def build_search_sources(*, settings: Settings, http_client) -> dict[str, SearchSource]:
    return {
        OPENALEX_SOURCE: OpenAlexSearchSource(http_client=http_client, settings=settings),
    }


def discover_candidates(
    *,
    queries_path: str | Path,
    output_dir: str | Path,
    settings: Settings,
    http_client,
    default_source: str = OPENALEX_SOURCE,
    max_results_per_query: int = 200,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    queries = load_discovery_queries(
        queries_path,
        default_source=default_source,
        default_max_results=max_results_per_query,
    )
    storage = DiscoveryRunStorage(output_dir)
    storage.prepare()
    storage.write_queries(serialize_queries(queries))

    sources = build_search_sources(settings=settings, http_client=http_client)
    merger = RecordMerger()

    raw_candidates: list[dict[str, Any]] = []
    api_errors = 0
    parse_failures = 0
    raw_count = 0

    for query in queries:
        source = sources.get(query.source)
        if source is None:
            raise ValueError(f"Unsupported discovery source: {query.source}")
        try:
            search_candidates, pages = source.search(query)
        except Exception as exc:  # noqa: BLE001
            api_errors += 1
            storage.log(
                f'error | query="{query.query}" | source={query.source} | type={type(exc).__name__} | message="{exc}"'
            )
            continue

        for page in pages:
            storage.write_raw_search_page(
                source=query.source,
                query_index=query.query_index,
                page_number=page.page_number,
                payload=page.payload,
            )

        raw_count += len(search_candidates)
        for search_candidate in search_candidates:
            try:
                raw_candidates.append(
                    _candidate_wrapper_from_search_hit(
                        run_id=storage.run_id,
                        query=query,
                        search_candidate=search_candidate,
                        merger=merger,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                parse_failures += 1
                storage.log(
                    f'parse_error | query="{query.query}" | source={query.source} | rank={search_candidate.search_rank} '
                    f'| type={type(exc).__name__} | message="{exc}"'
                )

        storage.log(
            f'query_summary | query="{query.query}" | source={query.source} | fetched={len(search_candidates)} '
            f'| raw_pages={len(pages)} | parse_failures={parse_failures}'
        )

    deduplicated_candidates = deduplicate_discovery_candidates(raw_candidates)
    storage.write_candidates(deduplicated_candidates)

    summary = {
        "run_id": storage.run_id,
        "storage": storage,
        "queries": queries,
        "raw_candidates": raw_count,
        "deduplicated_candidates": len(deduplicated_candidates),
        "duplicates_removed": max(0, raw_count - len(deduplicated_candidates)),
        "api_errors": api_errors,
        "parse_failures": parse_failures,
    }
    return deduplicated_candidates, summary


def run_discovery_and_label(
    *,
    queries_path: str | Path,
    output_dir: str | Path,
    settings: Settings,
    http_client,
    model_path: str | Path,
    vectorizer_path: str | Path,
    default_source: str = OPENALEX_SOURCE,
    max_results_per_query: int = 200,
    relevant_threshold: float = 0.65,
) -> dict[str, Any]:
    started_at = utc_now_iso()
    candidates, search_summary = discover_candidates(
        queries_path=queries_path,
        output_dir=output_dir,
        settings=settings,
        http_client=http_client,
        default_source=default_source,
        max_results_per_query=max_results_per_query,
    )
    storage: DiscoveryRunStorage = search_summary["storage"]
    inference = DiscoveryInference(
        model_path=model_path,
        vectorizer_path=vectorizer_path,
        threshold=relevant_threshold,
    )
    predictions = inference.score_candidates(candidates)
    storage.write_predictions(predictions, threshold=relevant_threshold)
    _log_predictions(storage, predictions, relevant_threshold)
    _log_query_prediction_summaries(storage, predictions)

    manifest = _build_manifest(
        run_id=storage.run_id,
        mode="discover_and_label",
        started_at=started_at,
        finished_at=utc_now_iso(),
        queries_count=len(search_summary["queries"]),
        source=default_source,
        max_results_per_query=max_results_per_query,
        raw_candidates=search_summary["raw_candidates"],
        deduplicated_candidates=len(candidates),
        duplicates_removed=search_summary["duplicates_removed"],
        predictions=predictions,
        threshold=relevant_threshold,
        model_path=model_path,
        vectorizer_path=vectorizer_path,
        model_name=inference.model_name,
        model_version=inference.model_version,
        api_errors=search_summary["api_errors"],
        parse_failures=search_summary["parse_failures"],
        input_queries_path=queries_path,
    )
    storage.write_manifest(manifest)
    storage.log(
        f'run_summary | run_id={storage.run_id} | queries={manifest["queries_count"]} '
        f'| raw_candidates={manifest["raw_candidates"]} | deduplicated_candidates={manifest["deduplicated_candidates"]} '
        f'| predicted_relevant={manifest["predicted_relevant"]} | predicted_irrelevant={manifest["predicted_irrelevant"]} '
        f'| missing_abstracts={manifest["missing_abstracts"]} | api_errors={manifest["api_errors"]} '
        f'| parse_failures={manifest["parse_failures"]}'
    )
    return manifest


def run_label_candidates(
    *,
    input_path: str | Path,
    output_dir: str | Path,
    model_path: str | Path,
    vectorizer_path: str | Path,
    relevant_threshold: float = 0.65,
) -> dict[str, Any]:
    started_at = utc_now_iso()
    storage = DiscoveryRunStorage(output_dir)
    storage.prepare()
    candidates = load_candidates(input_path)
    storage.write_candidates(candidates)
    storage.write_queries(_queries_from_candidates(candidates))

    inference = DiscoveryInference(
        model_path=model_path,
        vectorizer_path=vectorizer_path,
        threshold=relevant_threshold,
    )
    predictions = inference.score_candidates(candidates)
    storage.write_predictions(predictions, threshold=relevant_threshold)
    _log_predictions(storage, predictions, relevant_threshold)
    _log_query_prediction_summaries(storage, predictions)

    manifest = _build_manifest(
        run_id=storage.run_id,
        mode="label_candidates",
        started_at=started_at,
        finished_at=utc_now_iso(),
        queries_count=len(_queries_from_candidates(candidates)),
        source=_source_from_candidates(candidates),
        max_results_per_query=None,
        raw_candidates=len(candidates),
        deduplicated_candidates=len(candidates),
        duplicates_removed=0,
        predictions=predictions,
        threshold=relevant_threshold,
        model_path=model_path,
        vectorizer_path=vectorizer_path,
        model_name=inference.model_name,
        model_version=inference.model_version,
        api_errors=0,
        parse_failures=0,
        input_candidates_path=input_path,
    )
    storage.write_manifest(manifest)
    storage.log(
        f'run_summary | run_id={storage.run_id} | input_candidates={len(candidates)} '
        f'| predicted_relevant={manifest["predicted_relevant"]} | predicted_irrelevant={manifest["predicted_irrelevant"]} '
        f'| missing_abstracts={manifest["missing_abstracts"]}'
    )
    return manifest


def deduplicate_discovery_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not candidates:
        return []

    merger = RecordMerger()
    record_groups = group_duplicate_record_indices([candidate["record"] for candidate in candidates])
    deduplicated: list[dict[str, Any]] = []
    for group_indices in record_groups:
        group_candidates = [candidates[index] for index in group_indices]
        merged_record = merger.merge_records([candidate["record"] for candidate in group_candidates])
        best_candidate = min(
            group_candidates,
            key=lambda candidate: (
                int(candidate.get("search_rank") or 10**9),
                candidate.get("query") or "",
            ),
        )
        matched_queries = _unique_preserve_order(
            query
            for candidate in group_candidates
            for query in candidate.get("matched_queries") or []
        )
        search_matches = [
            match
            for candidate in sorted(group_candidates, key=lambda item: item.get("search_rank") or 10**9)
            for match in candidate.get("search_matches") or []
        ]
        deduplicated.append(
            {
                "run_id": best_candidate["run_id"],
                "query": best_candidate["query"],
                "matched_queries": matched_queries,
                "search_source": best_candidate["search_source"],
                "search_rank": best_candidate["search_rank"],
                "retrieved_at": best_candidate["retrieved_at"],
                "search_matches": search_matches,
                "record": sanitize_discovery_record(merged_record),
            }
        )
    return deduplicated


def load_candidates(path: str | Path) -> list[dict[str, Any]]:
    from .io_utils import load_records

    return load_records(path)


def sanitize_discovery_record(record: dict[str, Any]) -> dict[str, Any]:
    sanitized = deepcopy(record)
    for key in ("labels", "raw", "provenance", "resolution_status", "retrieved_at"):
        sanitized.pop(key, None)
    return sanitized


def _candidate_wrapper_from_search_hit(
    *,
    run_id: str,
    query: DiscoveryQuery,
    search_candidate: SearchCandidate,
    merger: RecordMerger,
) -> dict[str, Any]:
    record = _build_discovery_record(
        merger=merger,
        provider_result=search_candidate.provider_result,
        query=query,
    )
    return {
        "run_id": run_id,
        "query": search_candidate.query,
        "matched_queries": [search_candidate.query],
        "search_source": search_candidate.search_source,
        "search_rank": search_candidate.search_rank,
        "retrieved_at": search_candidate.retrieved_at,
        "search_matches": [
            {
                "query": search_candidate.query,
                "search_source": search_candidate.search_source,
                "search_rank": search_candidate.search_rank,
                "retrieved_at": search_candidate.retrieved_at,
                "mode": search_candidate.mode,
                "source_info": search_candidate.source_info,
            }
        ],
        "record": sanitize_discovery_record(record),
    }


def _build_discovery_record(
    *,
    merger: RecordMerger,
    provider_result: ProviderResult,
    query: DiscoveryQuery,
) -> dict[str, Any]:
    title = provider_result.payload.get("title")
    seed = ArticleSeed(
        input_position=query.query_index,
        title=title,
        doi=provider_result.payload.get("doi"),
        arxiv_id=provider_result.payload.get("arxiv_id"),
        url=provider_result.payload.get("landing_page_url"),
        seed_query=query.query,
        gold_label="unknown",
        extra={},
    )
    resolution = ResolutionResult(
        candidates=[provider_result],
        attempted=[provider_result.provider_name],
        successful=[provider_result.provider_name],
        errors={},
        rejections={},
    )
    record, _decision = merger.merge(seed, resolution, source_payload_refs={})
    return record


def _unique_preserve_order(values) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _build_manifest(
    *,
    run_id: str,
    mode: str,
    started_at: str,
    finished_at: str,
    queries_count: int,
    source: str | None,
    max_results_per_query: int | None,
    raw_candidates: int,
    deduplicated_candidates: int,
    duplicates_removed: int,
    predictions: list[dict[str, Any]],
    threshold: float,
    model_path: str | Path,
    vectorizer_path: str | Path,
    model_name: str,
    model_version: str,
    api_errors: int,
    parse_failures: int,
    input_queries_path: str | Path | None = None,
    input_candidates_path: str | Path | None = None,
) -> dict[str, Any]:
    missing_abstracts = sum(1 for prediction in predictions if not (prediction.get("abstract") or "").strip())
    predicted_relevant = sum(1 for prediction in predictions if prediction.get("predicted_binary") == 1)
    predicted_irrelevant = sum(1 for prediction in predictions if prediction.get("predicted_binary") == 0)
    manifest = {
        "run_id": run_id,
        "mode": mode,
        "started_at": started_at,
        "finished_at": finished_at,
        "queries_count": queries_count,
        "source": source,
        "max_results_per_query": max_results_per_query,
        "raw_candidates": raw_candidates,
        "deduplicated_candidates": deduplicated_candidates,
        "duplicates_removed": duplicates_removed,
        "predicted_relevant": predicted_relevant,
        "predicted_irrelevant": predicted_irrelevant,
        "missing_abstracts": missing_abstracts,
        "api_errors": api_errors,
        "parse_failures": parse_failures,
        "threshold": threshold,
        "model_name": model_name,
        "model_version": model_version,
        "model_path": str(model_path),
        "vectorizer_path": str(vectorizer_path),
    }
    if input_queries_path is not None:
        manifest["input_queries_path"] = str(input_queries_path)
    if input_candidates_path is not None:
        manifest["input_candidates_path"] = str(input_candidates_path)
    return manifest


def _log_predictions(storage: DiscoveryRunStorage, predictions: list[dict[str, Any]], threshold: float) -> None:
    for prediction in predictions:
        identifier = prediction.get("canonical_id") or prediction.get("record_id")
        storage.log(
            f'{utc_now_iso()} | query="{prediction.get("query")}" | source={prediction.get("search_source")} '
            f'| rank={prediction.get("search_rank")} | title="{prediction.get("title") or ""}" '
            f'| id={identifier} | pred={prediction.get("predicted_label")} '
            f'| score={prediction.get("score"):.4f} | threshold={threshold}'
        )


def _log_query_prediction_summaries(storage: DiscoveryRunStorage, predictions: list[dict[str, Any]]) -> None:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for prediction in predictions:
        grouped.setdefault(str(prediction.get("query") or ""), []).append(prediction)
    for query, items in grouped.items():
        predicted_relevant = sum(1 for item in items if item.get("predicted_binary") == 1)
        predicted_irrelevant = sum(1 for item in items if item.get("predicted_binary") == 0)
        missing_abstracts = sum(1 for item in items if not (item.get("abstract") or "").strip())
        storage.log(
            f'prediction_query_summary | query="{query}" | deduplicated_candidates={len(items)} '
            f'| predicted_relevant={predicted_relevant} | predicted_irrelevant={predicted_irrelevant} '
            f'| missing_abstracts={missing_abstracts}'
        )


def _queries_from_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    queries: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for candidate in candidates:
        source = candidate.get("search_source") or OPENALEX_SOURCE
        for match in candidate.get("search_matches") or []:
            key = (
                str(match.get("query") or candidate.get("query") or ""),
                str(source),
                str(match.get("mode") or "search"),
            )
            if key in seen or not key[0]:
                continue
            seen.add(key)
            queries.append(
                {
                    "query": key[0],
                    "source": key[1],
                    "mode": key[2],
                    "max_results": None,
                }
            )
    return queries


def _source_from_candidates(candidates: list[dict[str, Any]]) -> str | None:
    sources = _unique_preserve_order(
        candidate.get("search_source")
        for candidate in candidates
        if candidate.get("search_source")
    )
    if not sources:
        return None
    if len(sources) == 1:
        return sources[0]
    return ",".join(sources)
