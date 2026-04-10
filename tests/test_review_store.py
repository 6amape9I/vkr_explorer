import pytest

from vkr_article_dataset.review_store import (
    DatasetFormatError,
    DuplicateRecordError,
    apply_review_labels,
    index_records,
    load_jsonl_records,
    load_review_dataset,
    save_review_dataset,
    set_gold_label,
)


def test_load_jsonl_records_reads_valid_jsonl(tmp_path) -> None:
    path = tmp_path / "articles.jsonl"
    path.write_text(
        '{"record_id":"r1","labels":{"gold_label":"relevant"}}\n'
        '{"record_id":"r2","labels":{"gold_label":"partial"}}\n',
        encoding="utf-8",
    )

    records = load_jsonl_records(path)

    assert [record["record_id"] for record in records] == ["r1", "r2"]


def test_apply_review_labels_overlays_saved_labels() -> None:
    base_records = [
        {"record_id": "r1", "labels": {"gold_label": "relevant"}, "content": {"combined_text": "A"}},
        {"record_id": "r2", "labels": {"gold_label": "partial"}, "content": {"combined_text": "B"}},
    ]
    reviewed_records = [
        {"record_id": "r2", "labels": {"gold_label": "irrelevant"}},
        {"record_id": "missing", "labels": {"gold_label": "relevant"}},
    ]

    merged = apply_review_labels(base_records, reviewed_records)

    assert merged[0]["labels"]["gold_label"] == "relevant"
    assert merged[1]["labels"]["gold_label"] == "irrelevant"
    assert base_records[1]["labels"]["gold_label"] == "partial"


def test_save_review_dataset_preserves_record_payload(tmp_path) -> None:
    record = {
        "record_id": "r1",
        "bibliography": {"title": "Article"},
        "content": {"combined_text": "Title\n\nAbstract"},
        "labels": {"gold_label": "relevant", "notes": "keep me"},
    }
    path = tmp_path / "articles.reviewed.jsonl"

    save_review_dataset(path, [set_gold_label(record, "partial")])
    loaded = load_jsonl_records(path)

    assert loaded == [
        {
            "record_id": "r1",
            "bibliography": {"title": "Article"},
            "content": {"combined_text": "Title\n\nAbstract"},
            "labels": {"gold_label": "partial", "notes": "keep me"},
        }
    ]


def test_load_review_dataset_raises_for_missing_input(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        load_review_dataset(tmp_path / "missing.jsonl", tmp_path / "reviewed.jsonl")


def test_load_jsonl_records_raises_for_malformed_json(tmp_path) -> None:
    path = tmp_path / "broken.jsonl"
    path.write_text('{"record_id": "r1"}\n{"record_id": \n', encoding="utf-8")

    with pytest.raises(DatasetFormatError):
        load_jsonl_records(path)


def test_index_records_raises_for_duplicate_record_id() -> None:
    with pytest.raises(DuplicateRecordError):
        index_records(
            [
                {"record_id": "r1"},
                {"record_id": "r1"},
            ]
        )


def test_load_jsonl_records_returns_empty_list_for_empty_dataset(tmp_path) -> None:
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")

    assert load_jsonl_records(path) == []
