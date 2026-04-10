from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

import pandas as pd

from .io_utils import load_records, write_jsonl


BASELINE_LABELS = {
    "relevant": 1,
    "irrelevant": 0,
}


def prepare_baseline_dataset(input_path: str | Path) -> list[dict]:
    records = load_records(input_path)
    baseline_rows: list[dict] = []
    for record in records:
        label_name = ((record.get("labels") or {}).get("gold_label") or "").strip()
        if label_name not in BASELINE_LABELS:
            continue

        title = ((record.get("bibliography") or {}).get("title") or "").strip()
        abstract = ((record.get("content") or {}).get("abstract") or "").strip()
        if not title and not abstract:
            continue

        baseline_rows.append(
            {
                "record_id": record.get("record_id"),
                "canonical_id": ((record.get("identifiers") or {}).get("canonical_id") or "").strip() or None,
                "title": title,
                "abstract": abstract,
                "title_text": title,
                "abstract_text": abstract,
                "title_abstract_text": _compose_title_abstract_text(title=title, abstract=abstract),
                "label": BASELINE_LABELS[label_name],
                "label_name": label_name,
            }
        )
    return baseline_rows


def save_baseline_dataset(rows: Iterable[dict], output_dir: str | Path) -> dict[str, str]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    jsonl_path = output_dir / "baseline_dataset.jsonl"
    csv_path = output_dir / "baseline_dataset.csv"

    rows = list(rows)
    write_jsonl(jsonl_path, rows)
    _write_csv(csv_path, rows)

    return {
        "jsonl": str(jsonl_path),
        "csv": str(csv_path),
    }


def _compose_title_abstract_text(*, title: str, abstract: str) -> str:
    if title and abstract:
        return f"{title}\n\n{abstract}"
    return title or abstract


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(
                [
                    "record_id",
                    "canonical_id",
                    "title",
                    "abstract",
                    "title_text",
                    "abstract_text",
                    "title_abstract_text",
                    "label",
                    "label_name",
                ]
            )
        return

    dataframe = pd.DataFrame(rows)
    dataframe.to_csv(path, index=False)
