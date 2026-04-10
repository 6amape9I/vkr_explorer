from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Iterable


class ReviewStoreError(Exception):
    """Base error for review dataset operations."""


class DatasetFormatError(ReviewStoreError):
    """Raised when a JSONL file contains invalid records."""


class DuplicateRecordError(ReviewStoreError):
    """Raised when multiple records share the same record_id."""


def load_jsonl_records(path: str | Path) -> list[dict]:
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
                raise DatasetFormatError(
                    f"Invalid JSON in {path} at line {line_number}: {exc.msg}"
                ) from exc
            if not isinstance(payload, dict):
                raise DatasetFormatError(
                    f"Invalid record in {path} at line {line_number}: expected JSON object"
                )
            records.append(payload)
    return records


def index_records(records: Iterable[dict]) -> dict[str, dict]:
    indexed: dict[str, dict] = {}
    for position, record in enumerate(records, start=1):
        record_id = _record_id(record, position=position)
        if record_id in indexed:
            raise DuplicateRecordError(f"Duplicate record_id={record_id!r} at position {position}")
        indexed[record_id] = record
    return indexed


def load_review_dataset(
    input_path: str | Path,
    reviewed_path: str | Path | None = None,
) -> list[dict]:
    input_records = load_jsonl_records(input_path)
    index_records(input_records)

    if reviewed_path is None:
        return deepcopy(input_records)

    reviewed_path = Path(reviewed_path)
    if not reviewed_path.exists():
        return deepcopy(input_records)

    reviewed_records = load_jsonl_records(reviewed_path)
    index_records(reviewed_records)
    return apply_review_labels(input_records, reviewed_records)


def apply_review_labels(base_records: Iterable[dict], reviewed_records: Iterable[dict]) -> list[dict]:
    merged_records = deepcopy(list(base_records))
    merged_index = index_records(merged_records)

    for reviewed_record in reviewed_records:
        record_id = _record_id(reviewed_record)
        target = merged_index.get(record_id)
        if target is None:
            continue
        reviewed_label = get_gold_label(reviewed_record)
        if reviewed_label is None:
            continue
        labels = dict(target.get("labels") or {})
        labels["gold_label"] = reviewed_label
        target["labels"] = labels
    return merged_records


def save_review_dataset(path: str | Path, records: Iterable[dict]) -> None:
    path = Path(path)
    rows = list(records)
    index_records(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in rows:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def get_gold_label(record: dict) -> str | None:
    return (record.get("labels") or {}).get("gold_label")


def set_gold_label(record: dict, label: str) -> dict:
    updated = deepcopy(record)
    labels = dict(updated.get("labels") or {})
    labels["gold_label"] = label
    updated["labels"] = labels
    return updated


def _record_id(record: dict, position: int | None = None) -> str:
    record_id = record.get("record_id")
    if isinstance(record_id, str) and record_id.strip():
        return record_id
    prefix = f" at position {position}" if position is not None else ""
    raise DatasetFormatError(f"Missing non-empty record_id{prefix}")
