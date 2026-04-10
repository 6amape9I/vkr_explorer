from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Iterable

import pandas as pd
from sklearn.model_selection import train_test_split

from .io_utils import write_jsonl


TRAIN_SIZE = 0.70
VAL_SIZE = 0.15
TEST_SIZE = 0.15


def create_grouped_splits(
    rows: Iterable[dict],
    *,
    random_state: int = 42,
    train_size: float = TRAIN_SIZE,
    val_size: float = VAL_SIZE,
    test_size: float = TEST_SIZE,
) -> tuple[dict[str, list[dict]], dict]:
    rows = list(rows)
    if not rows:
        raise ValueError("Cannot create baseline split from an empty dataset")
    if round(train_size + val_size + test_size, 8) != 1.0:
        raise ValueError("train_size + val_size + test_size must sum to 1.0")

    dataframe = pd.DataFrame(rows)
    dataframe["group_key"] = dataframe.apply(_group_key_from_row, axis=1)

    _validate_group_labels(dataframe)

    group_frame = (
        dataframe.groupby("group_key", sort=True)
        .agg(label=("label", "first"), group_size=("record_id", "count"))
        .reset_index()
    )

    train_groups, temp_groups = _split_group_frame(
        group_frame,
        train_size=train_size,
        random_state=random_state,
    )
    temp_train_fraction = val_size / (val_size + test_size)
    val_groups, test_groups = _split_group_frame(
        temp_groups,
        train_size=temp_train_fraction,
        random_state=random_state + 1,
    )

    group_sets = {
        "train": set(train_groups["group_key"].tolist()),
        "val": set(val_groups["group_key"].tolist()),
        "test": set(test_groups["group_key"].tolist()),
    }
    splits = {
        split_name: dataframe[dataframe["group_key"].isin(group_keys)]
        .drop(columns=["group_key"])
        .sort_values("record_id")
        .to_dict(orient="records")
        for split_name, group_keys in group_sets.items()
    }

    manifest = _build_manifest(
        splits=splits,
        group_sets=group_sets,
        random_state=random_state,
        train_size=train_size,
        val_size=val_size,
        test_size=test_size,
    )
    return splits, manifest


def save_splits(splits: dict[str, list[dict]], manifest: dict, output_dir: str | Path) -> dict[str, str]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_paths = {
        "train": output_dir / "train.jsonl",
        "val": output_dir / "val.jsonl",
        "test": output_dir / "test.jsonl",
        "manifest": output_dir / "manifest.json",
    }
    write_jsonl(output_paths["train"], splits["train"])
    write_jsonl(output_paths["val"], splits["val"])
    write_jsonl(output_paths["test"], splits["test"])
    output_paths["manifest"].write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {name: str(path) for name, path in output_paths.items()}


def _group_key_from_row(row: pd.Series) -> str:
    canonical_id = row.get("canonical_id")
    if isinstance(canonical_id, str) and canonical_id.strip():
        return canonical_id.strip()
    record_id = row.get("record_id")
    if isinstance(record_id, str) and record_id.strip():
        return record_id.strip()
    raise ValueError("Baseline row is missing both canonical_id and record_id")


def _validate_group_labels(dataframe: pd.DataFrame) -> None:
    group_label_counts = dataframe.groupby("group_key")["label"].nunique()
    conflicting = group_label_counts[group_label_counts > 1]
    if not conflicting.empty:
        conflict_keys = ", ".join(conflicting.index.astype(str).tolist())
        raise ValueError(f"Conflicting labels found inside grouped baseline dataset: {conflict_keys}")


def _split_group_frame(
    group_frame: pd.DataFrame,
    *,
    train_size: float,
    random_state: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if len(group_frame) < 2:
        raise ValueError("Not enough grouped records to create train/val/test splits")

    stratify = group_frame["label"] if _can_stratify(group_frame, train_size=train_size) else None
    try:
        train_keys, test_keys = train_test_split(
            group_frame["group_key"].tolist(),
            train_size=train_size,
            random_state=random_state,
            shuffle=True,
            stratify=stratify,
        )
    except ValueError:
        train_keys, test_keys = train_test_split(
            group_frame["group_key"].tolist(),
            train_size=train_size,
            random_state=random_state,
            shuffle=True,
            stratify=None,
        )

    train_frame = group_frame[group_frame["group_key"].isin(train_keys)].copy()
    test_frame = group_frame[group_frame["group_key"].isin(test_keys)].copy()
    return train_frame, test_frame


def _can_stratify(group_frame: pd.DataFrame, *, train_size: float) -> bool:
    labels = group_frame["label"]
    if labels.nunique() < 2:
        return False
    counts = labels.value_counts()
    if (counts < 2).any():
        return False
    test_size = max(1, len(group_frame) - int(round(len(group_frame) * train_size)))
    return test_size >= labels.nunique()


def _build_manifest(
    *,
    splits: dict[str, list[dict]],
    group_sets: dict[str, set[str]],
    random_state: int,
    train_size: float,
    val_size: float,
    test_size: float,
) -> dict:
    overlap_checks = _build_overlap_checks(splits=splits, group_sets=group_sets)
    return {
        "random_state": random_state,
        "train_size": train_size,
        "val_size": val_size,
        "test_size": test_size,
        "counts": {split_name: len(rows) for split_name, rows in splits.items()},
        "label_distribution": {
            split_name: dict(sorted(Counter(str(row["label"]) for row in rows).items()))
            for split_name, rows in splits.items()
        },
        "overlap_checks": overlap_checks,
    }


def _build_overlap_checks(
    *,
    splits: dict[str, list[dict]],
    group_sets: dict[str, set[str]],
) -> dict:
    record_sets = {
        split_name: {row["record_id"] for row in rows}
        for split_name, rows in splits.items()
    }
    canonical_sets = {
        split_name: {row["canonical_id"] for row in rows if row.get("canonical_id")}
        for split_name, rows in splits.items()
    }
    return {
        "record_id_overlap": _pairwise_overlap_sizes(record_sets),
        "canonical_id_overlap": _pairwise_overlap_sizes(canonical_sets),
        "group_overlap": _pairwise_overlap_sizes(group_sets),
    }


def _pairwise_overlap_sizes(values: dict[str, set[str]]) -> dict[str, int]:
    pairs = [("train", "val"), ("train", "test"), ("val", "test")]
    return {
        f"{left}_{right}": len(values[left] & values[right])
        for left, right in pairs
    }
