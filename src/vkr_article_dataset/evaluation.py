from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import pandas as pd
from sklearn.metrics import accuracy_score, confusion_matrix, precision_recall_fscore_support


def compute_metrics(y_true: list[int], y_pred: list[int]) -> tuple[dict, dict]:
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true,
        y_pred,
        average="binary",
        zero_division=0,
    )
    matrix = confusion_matrix(y_true, y_pred, labels=[0, 1])
    metrics = {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
    }
    confusion = {
        "labels": [0, 1],
        "matrix": matrix.tolist(),
    }
    return metrics, confusion


def build_predictions_table(
    rows: Iterable[dict],
    *,
    y_pred: list[int],
    text_mode: str,
    score_column_name: str,
    score_values: list[float],
) -> pd.DataFrame:
    rows = list(rows)
    table_rows = []
    for row, pred_label, score_value in zip(rows, y_pred, score_values, strict=True):
        table_row = {
            "record_id": row.get("record_id"),
            "canonical_id": row.get("canonical_id"),
            "label": int(row["label"]),
            "pred_label": int(pred_label),
            "correct": int(row["label"]) == int(pred_label),
            "title": row.get("title") or "",
            "abstract": row.get("abstract") or "",
            "text_mode": text_mode,
            score_column_name: float(score_value),
        }
        table_rows.append(table_row)
    return pd.DataFrame(table_rows)


def save_evaluation_artifacts(
    output_dir: str | Path,
    *,
    split_name: str,
    metrics: dict,
    confusion: dict,
    predictions: pd.DataFrame,
) -> dict[str, str]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    metrics_path = output_dir / f"metrics_{split_name}.json"
    confusion_path = output_dir / f"confusion_matrix_{split_name}.json"
    predictions_path = output_dir / f"predictions_{split_name}.csv"

    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    confusion_path.write_text(json.dumps(confusion, ensure_ascii=False, indent=2), encoding="utf-8")
    predictions.to_csv(predictions_path, index=False)

    return {
        "metrics": str(metrics_path),
        "confusion": str(confusion_path),
        "predictions": str(predictions_path),
    }
