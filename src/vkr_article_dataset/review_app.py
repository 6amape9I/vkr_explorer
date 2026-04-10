from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
from typing import Any

import streamlit as st

from vkr_article_dataset.models import ALLOWED_GOLD_LABELS
from vkr_article_dataset.review_store import (
    DatasetFormatError,
    DuplicateRecordError,
    get_gold_label,
    load_review_dataset,
    save_review_dataset,
)


DEFAULT_INPUT_PATH = Path("data/normalized/articles.jsonl")
DEFAULT_OUTPUT_PATH = Path("data/normalized/articles.reviewed.jsonl")
LABEL_OPTIONS = sorted(ALLOWED_GOLD_LABELS)


def main() -> None:
    args = parse_args()
    st.set_page_config(page_title="Dataset Review", layout="wide")
    _inject_styles()

    st.title("Dataset Review")
    st.caption(f"Input: `{args.input}`  |  Reviewed output: `{args.output}`")

    try:
        input_mtime = args.input.stat().st_mtime_ns if args.input.exists() else None
        output_mtime = args.output.stat().st_mtime_ns if args.output.exists() else None
        records = _load_records(args.input, args.output, input_mtime, output_mtime)
    except FileNotFoundError:
        st.error(f"Input file not found: {args.input}")
        return
    except (DatasetFormatError, DuplicateRecordError) as exc:
        st.error(str(exc))
        return

    if not records:
        st.warning("Dataset is empty. Add records to the input JSONL and rerun the app.")
        return

    dataset_key = _dataset_key(args.input, args.output)
    if st.session_state.get("dataset_key") != dataset_key:
        st.session_state.dataset_key = dataset_key
        st.session_state.records = deepcopy(records)
        st.session_state.loaded_labels = {record["record_id"]: get_gold_label(record) for record in records}
        st.session_state.selected_record_id = records[0]["record_id"]

    working_records = st.session_state.records
    records_by_id = {record["record_id"]: record for record in working_records}
    filtered_ids = _render_sidebar(working_records)

    if not filtered_ids:
        st.warning("No records match the current filters.")
        return

    selected_record_id = st.session_state.get("selected_record_id")
    if selected_record_id not in filtered_ids:
        selected_record_id = filtered_ids[0]
        st.session_state.selected_record_id = selected_record_id

    selected_record_id = st.sidebar.selectbox(
        "Articles",
        filtered_ids,
        index=filtered_ids.index(selected_record_id),
        format_func=lambda record_id: _record_option_label(records_by_id[record_id]),
    )
    st.session_state.selected_record_id = selected_record_id

    current_index = filtered_ids.index(selected_record_id)
    record = records_by_id[selected_record_id]
    dirty_count = _dirty_count(working_records, st.session_state.loaded_labels)

    _render_record(record, current_index=current_index, total=len(filtered_ids), filtered_ids=filtered_ids)

    st.sidebar.divider()
    st.sidebar.metric("Unsaved label changes", dirty_count)
    if st.sidebar.button("Save review", type="primary", use_container_width=True):
        save_review_dataset(args.output, working_records)
        st.session_state.loaded_labels = {
            item["record_id"]: get_gold_label(item) for item in working_records
        }
        st.cache_data.clear()
        st.sidebar.success(f"Saved to {args.output}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args, _ = parser.parse_known_args(argv)
    return args


@st.cache_data(show_spinner=False)
def _load_records(
    input_path: Path,
    output_path: Path,
    input_mtime_ns: int | None = None,
    output_mtime_ns: int | None = None,
) -> list[dict]:
    del input_mtime_ns, output_mtime_ns
    return load_review_dataset(input_path, output_path)


def _render_sidebar(records: list[dict]) -> list[str]:
    st.sidebar.header("Browse")
    search_query = st.sidebar.text_input("Search by title")
    selected_labels = st.sidebar.multiselect(
        "Gold label",
        options=LABEL_OPTIONS,
        default=LABEL_OPTIONS,
    )
    hard_negative_mode = st.sidebar.selectbox(
        "Hard negative",
        options=["All", "Only hard negatives", "Exclude hard negatives"],
    )

    filtered_ids = [
        record["record_id"]
        for record in records
        if _matches_filters(
            record=record,
            search_query=search_query,
            selected_labels=selected_labels,
            hard_negative_mode=hard_negative_mode,
        )
    ]
    st.sidebar.caption(f"Showing {len(filtered_ids)} of {len(records)} records")
    return filtered_ids


def _render_record(record: dict, *, current_index: int, total: int, filtered_ids: list[str]) -> None:
    title = _title(record)
    gold_label = get_gold_label(record) or "unknown"
    combined_text = _combined_text(record)
    abstract = (record.get("content") or {}).get("abstract")
    notes = (record.get("labels") or {}).get("notes")
    labels = record.get("labels") or {}
    auto_topic_tags = labels.get("auto_topic_tags") or labels.get("topic_tags") or []
    auto_method_tags = labels.get("auto_method_tags") or labels.get("method_tags") or []
    manual_topic_tags = labels.get("manual_topic_tags") or []
    manual_method_tags = labels.get("manual_method_tags") or []

    nav_left, nav_center, nav_right = st.columns([1, 1, 1])
    with nav_left:
        if st.button("Previous", disabled=current_index == 0, use_container_width=True):
            st.session_state.selected_record_id = filtered_ids[current_index - 1]
            st.rerun()
    with nav_center:
        st.markdown(
            f"<div class='review-counter'>{current_index + 1} / {total}</div>",
            unsafe_allow_html=True,
        )
    with nav_right:
        if st.button("Next", disabled=current_index >= total - 1, use_container_width=True):
            st.session_state.selected_record_id = filtered_ids[current_index + 1]
            st.rerun()

    st.markdown(f"<div class='review-title'>{title}</div>", unsafe_allow_html=True)

    current_label = gold_label if gold_label in LABEL_OPTIONS else "unknown"
    selected_label = st.selectbox(
        "Gold label",
        LABEL_OPTIONS,
        index=LABEL_OPTIONS.index(current_label),
        key=f"gold_label_selector_{record['record_id']}",
    )
    if selected_label != current_label:
        labels = dict(record.get("labels") or {})
        labels["gold_label"] = selected_label
        record["labels"] = labels
        gold_label = selected_label

    st.markdown(
        f"<div class='label-chip label-{gold_label}'>{gold_label}</div>",
        unsafe_allow_html=True,
    )

    meta1, meta2, meta3, meta4 = st.columns(4)
    bibliography = record.get("bibliography") or {}
    identifiers = record.get("identifiers") or {}
    sources = record.get("sources") or {}
    links = record.get("links") or {}
    quality = record.get("quality") or {}

    meta1.metric("Year", bibliography.get("publication_year") or "N/A")
    meta2.metric("Source", sources.get("primary_source") or identifiers.get("source") or "N/A")
    meta3.metric("Abstract", "Yes" if quality.get("has_abstract") else "No")
    meta4.metric("PDF", "Yes" if quality.get("has_pdf_url") else "No")

    authors = bibliography.get("authors") or []
    if authors:
        st.caption("Authors: " + ", ".join(authors))
    else:
        st.caption("Authors: N/A")

    link_left, link_right = st.columns(2)
    with link_left:
        landing_page_url = links.get("landing_page_url")
        if landing_page_url:
            st.link_button("Open landing page", landing_page_url, use_container_width=True)
    with link_right:
        pdf_url = links.get("pdf_url")
        if pdf_url:
            st.link_button("Open PDF", pdf_url, use_container_width=True)

    if combined_text:
        st.text_area("Article text", combined_text, height=360, disabled=True)
    else:
        st.warning("This record has no `content.combined_text`.")

    lower_left, lower_right = st.columns(2)
    with lower_left:
        if abstract:
            st.text_area("Abstract", abstract, height=220, disabled=True)
        else:
            st.info("No abstract available for this record.")
    with lower_right:
        st.text_area("Notes", notes or "", height=220, disabled=True)

    tag_left, tag_right = st.columns(2)
    with tag_left:
        st.markdown("**Auto topic tags**")
        st.write(", ".join(auto_topic_tags) if auto_topic_tags else "N/A")
    with tag_right:
        st.markdown("**Auto method tags**")
        st.write(", ".join(auto_method_tags) if auto_method_tags else "N/A")

    manual_left, manual_right = st.columns(2)
    with manual_left:
        st.markdown("**Manual topic tags**")
        st.write(", ".join(manual_topic_tags) if manual_topic_tags else "N/A")
    with manual_right:
        st.markdown("**Manual method tags**")
        st.write(", ".join(manual_method_tags) if manual_method_tags else "N/A")

    with st.expander("Record metadata"):
        provenance = record.get("provenance") or {}
        st.json(
            {
                "record_id": record.get("record_id"),
                "resolution_status": record.get("resolution_status"),
                "publication_date": bibliography.get("publication_date"),
                "venue": bibliography.get("venue"),
                "input_position": provenance.get("input_position"),
                "seed_query": provenance.get("seed_query"),
            }
        )


def _dataset_key(input_path: Path, output_path: Path) -> str:
    input_mtime = input_path.stat().st_mtime_ns if input_path.exists() else "missing"
    output_mtime = output_path.stat().st_mtime_ns if output_path.exists() else "missing"
    return f"{input_path.resolve()}::{input_mtime}::{output_path.resolve()}::{output_mtime}"


def _matches_filters(
    *,
    record: dict[str, Any],
    search_query: str,
    selected_labels: list[str],
    hard_negative_mode: str,
) -> bool:
    if selected_labels:
        gold_label = get_gold_label(record) or "unknown"
        if gold_label not in selected_labels:
            return False

    if search_query:
        title = _title(record).lower()
        if search_query.lower() not in title:
            return False

    is_hard_negative = bool((record.get("labels") or {}).get("is_hard_negative"))
    if hard_negative_mode == "Only hard negatives" and not is_hard_negative:
        return False
    if hard_negative_mode == "Exclude hard negatives" and is_hard_negative:
        return False
    return True


def _record_option_label(record: dict) -> str:
    label = get_gold_label(record) or "unknown"
    year = (record.get("bibliography") or {}).get("publication_year") or "N/A"
    hard_negative = " | hard-negative" if (record.get("labels") or {}).get("is_hard_negative") else ""
    return f"{label} | {year} | {_title(record)}{hard_negative}"


def _title(record: dict) -> str:
    return (record.get("bibliography") or {}).get("title") or "[untitled record]"


def _combined_text(record: dict) -> str:
    return (record.get("content") or {}).get("combined_text") or ""


def _dirty_count(records: list[dict], baseline_labels: dict[str, str | None]) -> int:
    dirty = 0
    for record in records:
        record_id = record["record_id"]
        current_label = get_gold_label(record)
        if baseline_labels.get(record_id) != current_label:
            dirty += 1
    return dirty


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background: linear-gradient(180deg, #f6f3ed 0%, #fcfbf8 45%, #f5f7fa 100%);
        }
        .review-title {
            font-size: 2rem;
            font-weight: 700;
            line-height: 1.2;
            margin: 0.3rem 0 0.8rem 0;
        }
        .review-counter {
            text-align: center;
            font-size: 1rem;
            font-weight: 600;
            padding-top: 0.5rem;
        }
        .label-chip {
            display: inline-block;
            padding: 0.3rem 0.75rem;
            border-radius: 999px;
            font-size: 0.9rem;
            font-weight: 700;
            margin-bottom: 1rem;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }
        .label-relevant {
            background: #d9f2d8;
            color: #0f5b22;
        }
        .label-partial {
            background: #fff1c2;
            color: #855b00;
        }
        .label-irrelevant {
            background: #ffd9d4;
            color: #8c1d18;
        }
        .label-unknown {
            background: #dde5ef;
            color: #29435c;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
