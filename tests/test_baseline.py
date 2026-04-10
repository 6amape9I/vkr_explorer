import json
import sys

import pandas as pd

from vkr_article_dataset.cli import main
from vkr_article_dataset.features import fit_vectorizer, select_texts
from vkr_article_dataset.splitting import create_grouped_splits
from vkr_article_dataset.train_baseline import run_baseline_pipeline
from vkr_article_dataset.training_dataset import prepare_baseline_dataset


def _normalized_record(
    *,
    record_id: str,
    canonical_id: str | None,
    label: str,
    title: str,
    abstract: str,
) -> dict:
    return {
        "record_id": record_id,
        "identifiers": {
            "canonical_id": canonical_id,
        },
        "bibliography": {
            "title": title,
        },
        "content": {
            "abstract": abstract,
        },
        "labels": {
            "gold_label": label,
        },
    }


def _write_jsonl(path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _baseline_input_records() -> list[dict]:
    rows: list[dict] = []
    for index in range(12):
        rows.append(
            _normalized_record(
                record_id=f"relevant-{index}",
                canonical_id=f"canon-rel-{index // 2}",
                label="relevant",
                title=f"Federated blockchain paper {index}",
                abstract="Federated learning blockchain secure aggregation relevant signal",
            )
        )
    for index in range(12):
        rows.append(
            _normalized_record(
                record_id=f"irrelevant-{index}",
                canonical_id=f"canon-irrel-{index // 2}",
                label="irrelevant",
                title=f"Computer vision benchmark {index}",
                abstract="Image classification convolution dataset irrelevant signal",
            )
        )
    rows.append(
        _normalized_record(
            record_id="partial-1",
            canonical_id="canon-partial-1",
            label="partial",
            title="Partial candidate",
            abstract="Should not appear",
        )
    )
    rows.append(
        _normalized_record(
            record_id="unknown-1",
            canonical_id="canon-unknown-1",
            label="unknown",
            title="Unknown candidate",
            abstract="Should not appear",
        )
    )
    rows.append(
        _normalized_record(
            record_id="empty-1",
            canonical_id="canon-empty-1",
            label="relevant",
            title="",
            abstract="",
        )
    )
    return rows


def test_prepare_baseline_dataset_filters_and_maps_labels(tmp_path) -> None:
    input_path = tmp_path / "articles.jsonl"
    _write_jsonl(input_path, _baseline_input_records())

    baseline_rows = prepare_baseline_dataset(input_path)

    assert len(baseline_rows) == 24
    assert {row["label_name"] for row in baseline_rows} == {"relevant", "irrelevant"}
    assert {row["label"] for row in baseline_rows} == {0, 1}
    assert all(row["title"] or row["abstract"] for row in baseline_rows)
    assert baseline_rows[0]["title_abstract_text"]


def test_create_grouped_splits_is_reproducible_and_without_overlap(tmp_path) -> None:
    input_path = tmp_path / "articles.jsonl"
    _write_jsonl(input_path, _baseline_input_records())
    baseline_rows = prepare_baseline_dataset(input_path)

    splits_first, manifest_first = create_grouped_splits(baseline_rows, random_state=42)
    splits_second, manifest_second = create_grouped_splits(baseline_rows, random_state=42)

    assert [row["record_id"] for row in splits_first["train"]] == [
        row["record_id"] for row in splits_second["train"]
    ]
    assert manifest_first == manifest_second
    assert manifest_first["overlap_checks"]["record_id_overlap"]["train_val"] == 0
    assert manifest_first["overlap_checks"]["record_id_overlap"]["train_test"] == 0
    assert manifest_first["overlap_checks"]["record_id_overlap"]["val_test"] == 0
    assert manifest_first["overlap_checks"]["canonical_id_overlap"]["train_val"] == 0
    assert manifest_first["overlap_checks"]["canonical_id_overlap"]["train_test"] == 0
    assert manifest_first["overlap_checks"]["canonical_id_overlap"]["val_test"] == 0
    assert sum(manifest_first["counts"].values()) == len(baseline_rows)


def test_features_support_all_text_modes(tmp_path) -> None:
    input_path = tmp_path / "articles.jsonl"
    _write_jsonl(input_path, _baseline_input_records())
    baseline_rows = prepare_baseline_dataset(input_path)
    train_rows = baseline_rows[:12]

    assert len(select_texts(train_rows, "title")) == len(train_rows)
    assert len(select_texts(train_rows, "abstract")) == len(train_rows)
    assert len(select_texts(train_rows, "title_abstract")) == len(train_rows)

    vectorizer, matrix = fit_vectorizer(train_rows, text_mode="title_abstract")

    assert matrix.shape[0] == len(train_rows)
    assert len(vectorizer.get_feature_names_out()) > 0


def test_run_baseline_pipeline_saves_models_metrics_and_predictions(tmp_path) -> None:
    input_path = tmp_path / "articles.jsonl"
    workdir = tmp_path / "baseline_artifacts"
    _write_jsonl(input_path, _baseline_input_records())

    summary = run_baseline_pipeline(input_path=input_path, workdir=workdir, text_mode="title_abstract")

    assert summary["dataset_records"] == 24
    assert (workdir / "dataset" / "baseline_dataset.jsonl").exists()
    assert (workdir / "splits" / "manifest.json").exists()
    assert (workdir / "logreg" / "model.joblib").exists()
    assert (workdir / "linear_svm" / "model.joblib").exists()

    logreg_predictions = pd.read_csv(workdir / "logreg" / "predictions_test.csv")
    svm_predictions = pd.read_csv(workdir / "linear_svm" / "predictions_test.csv")
    assert "pred_proba" in logreg_predictions.columns
    assert "decision_score" in svm_predictions.columns

    manifest = json.loads((workdir / "splits" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["random_state"] == 42


def test_train_baseline_cli_smoke(tmp_path, monkeypatch, capsys) -> None:
    input_path = tmp_path / "articles.jsonl"
    workdir = tmp_path / "baseline_cli"
    _write_jsonl(input_path, _baseline_input_records())

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "vkr-dataset",
            "train-baseline",
            "--input",
            str(input_path),
            "--workdir",
            str(workdir),
            "--text-mode",
            "title_abstract",
            "--random-state",
            "42",
        ],
    )

    exit_code = main()

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["models"]["logreg"]["metrics"]["test"]["records"] >= 1
    assert (workdir / "summary.json").exists()
