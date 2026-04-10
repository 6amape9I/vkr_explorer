from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable

from .io_utils import write_jsonl


class DiscoveryRunStorage:
    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)
        self.run_id = self.output_dir.name
        self.raw_search_dir = self.output_dir / "raw_search"
        self.logs_dir = self.output_dir / "logs"

    def prepare(self) -> None:
        if self.output_dir.exists() and any(self.output_dir.iterdir()):
            raise ValueError(f"Discovery output directory must be new or empty: {self.output_dir}")
        self.raw_search_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def write_queries(self, queries: list[dict[str, Any]]) -> Path:
        path = self.output_dir / "queries.jsonl"
        write_jsonl(path, queries)
        return path

    def write_raw_search_page(
        self,
        *,
        source: str,
        query_index: int,
        page_number: int,
        payload: dict[str, Any],
    ) -> Path:
        path = self.raw_search_dir / f"{source}_query_{query_index:03d}_page_{page_number:03d}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def write_candidates(self, candidates: list[dict[str, Any]]) -> dict[str, str]:
        jsonl_path = self.output_dir / "candidates.jsonl"
        csv_path = self.output_dir / "candidates.csv"
        write_jsonl(jsonl_path, candidates)
        self._write_csv(csv_path, [_candidate_csv_row(candidate) for candidate in candidates])
        return {"jsonl": str(jsonl_path), "csv": str(csv_path)}

    def write_predictions(self, predictions: list[dict[str, Any]], *, threshold: float) -> dict[str, str]:
        predictions_path = self.output_dir / "predictions.jsonl"
        predictions_csv = self.output_dir / "predictions.csv"
        relevant = [row for row in predictions if float(row.get("score") or 0.0) >= threshold]
        relevant_path = self.output_dir / "relevant_predictions.jsonl"
        relevant_csv = self.output_dir / "relevant_predictions.csv"

        write_jsonl(predictions_path, predictions)
        write_jsonl(relevant_path, relevant)
        self._write_csv(predictions_csv, [_prediction_csv_row(row) for row in predictions])
        self._write_csv(relevant_csv, [_prediction_csv_row(row) for row in relevant])
        return {
            "predictions_jsonl": str(predictions_path),
            "predictions_csv": str(predictions_csv),
            "relevant_predictions_jsonl": str(relevant_path),
            "relevant_predictions_csv": str(relevant_csv),
        }

    def write_manifest(self, manifest: dict[str, Any]) -> Path:
        path = self.output_dir / "manifest.json"
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def log(self, message: str) -> None:
        path = self.logs_dir / "discovery.log"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(message + "\n")

    def _write_csv(self, path: Path, rows: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        fieldnames = list(rows[0].keys())
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


def _candidate_csv_row(candidate: dict[str, Any]) -> dict[str, Any]:
    record = candidate.get("record") or {}
    bibliography = record.get("bibliography") or {}
    identifiers = record.get("identifiers") or {}
    links = record.get("links") or {}
    return {
        "record_id": record.get("record_id"),
        "canonical_id": identifiers.get("canonical_id"),
        "title": bibliography.get("title"),
        "publication_year": bibliography.get("publication_year"),
        "venue": bibliography.get("venue"),
        "query": candidate.get("query"),
        "matched_queries": "; ".join(candidate.get("matched_queries") or []),
        "search_source": candidate.get("search_source"),
        "search_rank": candidate.get("search_rank"),
        "landing_page_url": links.get("landing_page_url"),
        "pdf_url": links.get("pdf_url"),
    }


def _prediction_csv_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_id": row.get("record_id"),
        "canonical_id": row.get("canonical_id"),
        "title": row.get("title"),
        "publication_year": row.get("publication_year"),
        "venue": row.get("venue"),
        "query": row.get("query"),
        "matched_queries": "; ".join(row.get("matched_queries") or []),
        "predicted_label": row.get("predicted_label"),
        "predicted_binary": row.get("predicted_binary"),
        "score": row.get("score"),
        "search_source": row.get("search_source"),
        "search_rank": row.get("search_rank"),
        "landing_page_url": row.get("landing_page_url"),
        "pdf_url": row.get("pdf_url"),
    }
