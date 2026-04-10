from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from .models import ArticleSeed, ProviderResult
from .utils import parse_bool


EXPECTED_COLUMNS = {
    "title",
    "doi",
    "arxiv_id",
    "url",
    "seed_query",
    "gold_label",
    "is_hard_negative",
    "notes",
}


def load_seeds(path: str | Path) -> list[ArticleSeed]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    if path.suffix.lower() == ".jsonl":
        return _load_jsonl(path)
    if path.suffix.lower() == ".csv":
        return _load_csv(path)
    raise ValueError("Unsupported input format. Use .jsonl or .csv")


def _load_jsonl(path: Path) -> list[ArticleSeed]:
    seeds: list[ArticleSeed] = []
    with path.open("r", encoding="utf-8") as fh:
        for index, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            seed = _seed_from_row(row=row, input_position=index)
            seed.validate()
            seeds.append(seed)
    return seeds


def _load_csv(path: Path) -> list[ArticleSeed]:
    seeds: list[ArticleSeed] = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for index, row in enumerate(reader, start=1):
            seed = _seed_from_row(row=row, input_position=index)
            seed.validate()
            seeds.append(seed)
    return seeds


def _seed_from_row(row: dict, input_position: int) -> ArticleSeed:
    extra = {k: v for k, v in row.items() if k not in EXPECTED_COLUMNS}
    return ArticleSeed(
        input_position=input_position,
        title=_none(row.get("title")),
        doi=_none(row.get("doi")),
        arxiv_id=_none(row.get("arxiv_id")),
        url=_none(row.get("url")),
        seed_query=_none(row.get("seed_query")),
        gold_label=_none(row.get("gold_label")) or "unknown",
        is_hard_negative=parse_bool(row.get("is_hard_negative"), default=False),
        notes=_none(row.get("notes")),
        extra=extra,
    )


def write_jsonl(path: str | Path, records: Iterable[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_records(path: str | Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    records: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_number, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in {path} at line {line_number}: {exc.msg}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"Invalid record in {path} at line {line_number}: expected JSON object")
            records.append(payload)
    return records


def write_source_payload_refs(
    output_dataset_path: str | Path,
    record_id: str,
    candidates: Iterable[ProviderResult],
) -> dict[str, str]:
    output_dataset_path = Path(output_dataset_path)
    data_root = infer_data_root(output_dataset_path)
    refs: dict[str, str] = {}
    for candidate in candidates:
        provider_dir = data_root / "raw" / candidate.provider_name
        provider_dir.mkdir(parents=True, exist_ok=True)
        payload_path = provider_dir / f"{record_id}.json"
        payload = {
            "provider_name": candidate.provider_name,
            "source_id": candidate.source_id,
            "confidence": candidate.confidence,
            "match_details": candidate.match_details,
            "payload": candidate.raw,
        }
        with payload_path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        refs[candidate.provider_name] = payload_path.relative_to(data_root).as_posix()
    return refs


def infer_data_root(dataset_path: str | Path) -> Path:
    dataset_path = Path(dataset_path)
    if dataset_path.parent.name == "normalized" and dataset_path.parent.parent.name:
        return dataset_path.parent.parent
    return dataset_path.parent


def write_csv(path: str | Path, records: Iterable[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [_flatten_record(record) for record in records]
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _flatten_record(record: dict) -> dict:
    authors = record.get("bibliography", {}).get("authors") or []
    labels = record.get("labels", {}) or {}
    auto_topic_tags = labels.get("auto_topic_tags") or []
    auto_method_tags = labels.get("auto_method_tags") or []
    manual_topic_tags = labels.get("manual_topic_tags") or []
    manual_method_tags = labels.get("manual_method_tags") or []
    primary_source = record.get("sources", {}).get("primary_source") or record.get("identifiers", {}).get("source")
    return {
        "schema_version": record.get("schema_version"),
        "record_id": record.get("record_id"),
        "resolution_status": record.get("resolution_status"),
        "source": primary_source,
        "primary_source": primary_source,
        "available_sources": "; ".join(record.get("sources", {}).get("available_sources") or []),
        "source_candidates_count": record.get("sources", {}).get("source_candidates_count"),
        "doi": record.get("identifiers", {}).get("doi"),
        "arxiv_id": record.get("identifiers", {}).get("arxiv_id"),
        "openalex_id": record.get("identifiers", {}).get("openalex_id"),
        "canonical_id": record.get("identifiers", {}).get("canonical_id"),
        "title": record.get("bibliography", {}).get("title"),
        "publication_year": record.get("bibliography", {}).get("publication_year"),
        "publication_date": record.get("bibliography", {}).get("publication_date"),
        "venue": record.get("bibliography", {}).get("venue"),
        "document_type": record.get("bibliography", {}).get("document_type"),
        "authors": "; ".join(authors),
        "gold_label": labels.get("gold_label"),
        "is_hard_negative": labels.get("is_hard_negative"),
        "auto_topic_tags": "; ".join(auto_topic_tags),
        "auto_method_tags": "; ".join(auto_method_tags),
        "manual_topic_tags": "; ".join(manual_topic_tags),
        "manual_method_tags": "; ".join(manual_method_tags),
        "notes": labels.get("notes"),
        "landing_page_url": record.get("links", {}).get("landing_page_url"),
        "pdf_url": record.get("links", {}).get("pdf_url"),
        "has_abstract": record.get("quality", {}).get("has_abstract"),
        "citation_count": record.get("quality", {}).get("citation_count"),
        "fulltext_status": record.get("content", {}).get("fulltext_status"),
        "fulltext_ref": record.get("content", {}).get("fulltext_ref"),
        "abstract": record.get("content", {}).get("abstract"),
    }


def _none(value: object) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None
