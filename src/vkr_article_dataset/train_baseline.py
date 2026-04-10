from __future__ import annotations

import json
from pathlib import Path

import joblib
from sklearn.linear_model import LogisticRegression
from sklearn.svm import LinearSVC

from .evaluation import build_predictions_table, compute_metrics, save_evaluation_artifacts
from .features import DEFAULT_TEXT_MODE, DEFAULT_TFIDF_CONFIG, fit_vectorizer, transform_rows
from .splitting import create_grouped_splits, save_splits
from .training_dataset import prepare_baseline_dataset, save_baseline_dataset


MODEL_CONFIGS = {
    "logreg": {
        "builder": lambda random_state: LogisticRegression(
            max_iter=2000,
            random_state=random_state,
            class_weight="balanced",
        ),
        "score_column": "pred_proba",
        "config": {
            "model_class": "LogisticRegression",
            "max_iter": 2000,
            "class_weight": "balanced",
        },
    },
    "linear_svm": {
        "builder": lambda _random_state: LinearSVC(
            class_weight="balanced",
        ),
        "score_column": "decision_score",
        "config": {
            "model_class": "LinearSVC",
            "class_weight": "balanced",
        },
    },
}


def run_baseline_pipeline(
    *,
    input_path: str | Path,
    workdir: str | Path,
    text_mode: str = DEFAULT_TEXT_MODE,
    random_state: int = 42,
) -> dict:
    workdir = Path(workdir)
    dataset_dir = workdir / "dataset"
    split_dir = workdir / "splits"
    dataset_rows = prepare_baseline_dataset(input_path)
    if len(dataset_rows) < 3:
        raise ValueError("Baseline dataset is too small for train/val/test split")

    dataset_artifacts = save_baseline_dataset(dataset_rows, dataset_dir)
    splits, split_manifest = create_grouped_splits(dataset_rows, random_state=random_state)
    split_artifacts = save_splits(splits, split_manifest, split_dir)

    models_summary: dict[str, dict] = {}
    for model_name in ("logreg", "linear_svm"):
        models_summary[model_name] = _train_one_model(
            model_name=model_name,
            splits=splits,
            workdir=workdir / model_name,
            text_mode=text_mode,
            random_state=random_state,
        )

    summary = {
        "input": str(input_path),
        "workdir": str(workdir),
        "text_mode": text_mode,
        "random_state": random_state,
        "dataset_records": len(dataset_rows),
        "dataset_artifacts": dataset_artifacts,
        "split_artifacts": split_artifacts,
        "models": models_summary,
    }
    (workdir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


def _train_one_model(
    *,
    model_name: str,
    splits: dict[str, list[dict]],
    workdir: Path,
    text_mode: str,
    random_state: int,
) -> dict:
    workdir.mkdir(parents=True, exist_ok=True)
    train_rows = splits["train"]
    vectorizer, x_train = fit_vectorizer(train_rows, text_mode=text_mode)
    y_train = [int(row["label"]) for row in train_rows]

    model_definition = MODEL_CONFIGS[model_name]
    model = model_definition["builder"](random_state)
    model.fit(x_train, y_train)

    vectorizer_path = workdir / "vectorizer.joblib"
    model_path = workdir / "model.joblib"
    config_path = workdir / "config.json"

    joblib.dump(vectorizer, vectorizer_path)
    joblib.dump(model, model_path)
    config_path.write_text(
        json.dumps(
            {
                "text_mode": text_mode,
                "random_state": random_state,
                "tfidf": DEFAULT_TFIDF_CONFIG,
                "model": model_definition["config"],
                "split_sizes": {split_name: len(rows) for split_name, rows in splits.items()},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    split_metrics: dict[str, dict] = {}
    for split_name, rows in splits.items():
        matrix = transform_rows(vectorizer, rows, text_mode=text_mode)
        y_true = [int(row["label"]) for row in rows]
        y_pred = [int(value) for value in model.predict(matrix)]
        score_values = _score_values(model_name=model_name, model=model, matrix=matrix)
        metrics, confusion = compute_metrics(y_true, y_pred)
        metrics["records"] = len(rows)
        predictions = build_predictions_table(
            rows,
            y_pred=y_pred,
            text_mode=text_mode,
            score_column_name=model_definition["score_column"],
            score_values=score_values,
        )
        save_evaluation_artifacts(
            workdir,
            split_name=split_name,
            metrics=metrics,
            confusion=confusion,
            predictions=predictions,
        )
        split_metrics[split_name] = metrics

    return {
        "artifact_dir": str(workdir),
        "vectorizer": str(vectorizer_path),
        "model": str(model_path),
        "config": str(config_path),
        "metrics": split_metrics,
    }


def _score_values(*, model_name: str, model, matrix) -> list[float]:
    if model_name == "logreg":
        return [float(value) for value in model.predict_proba(matrix)[:, 1]]
    return [float(value) for value in model.decision_function(matrix)]
