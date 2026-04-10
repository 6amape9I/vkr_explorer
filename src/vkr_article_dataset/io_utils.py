from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from .models import ArticleSeed
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
    topic_tags = record.get("labels", {}).get("topic_tags") or []
    method_tags = record.get("labels", {}).get("method_tags") or []
    return {
        "record_id": record.get("record_id"),
        "resolution_status": record.get("resolution_status"),
        "source": record.get("identifiers", {}).get("source"),
        "doi": record.get("identifiers", {}).get("doi"),
        "arxiv_id": record.get("identifiers", {}).get("arxiv_id"),
        "openalex_id": record.get("identifiers", {}).get("openalex_id"),
        "title": record.get("bibliography", {}).get("title"),
        "publication_year": record.get("bibliography", {}).get("publication_year"),
        "publication_date": record.get("bibliography", {}).get("publication_date"),
        "venue": record.get("bibliography", {}).get("venue"),
        "document_type": record.get("bibliography", {}).get("document_type"),
        "authors": "; ".join(authors),
        "gold_label": record.get("labels", {}).get("gold_label"),
        "is_hard_negative": record.get("labels", {}).get("is_hard_negative"),
        "topic_tags": "; ".join(topic_tags),
        "method_tags": "; ".join(method_tags),
        "notes": record.get("labels", {}).get("notes"),
        "landing_page_url": record.get("links", {}).get("landing_page_url"),
        "pdf_url": record.get("links", {}).get("pdf_url"),
        "has_abstract": record.get("quality", {}).get("has_abstract"),
        "citation_count": record.get("quality", {}).get("citation_count"),
        "abstract": record.get("content", {}).get("abstract"),
    }


def _none(value: object) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None
