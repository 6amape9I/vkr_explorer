from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import Settings
from .discovery import run_discovery_and_label, run_label_candidates
from .http import HttpClient
from .io_utils import load_records, load_seeds, write_csv, write_jsonl, write_source_payload_refs
from .normalization import DatasetBuilder
from .pdf_pipeline import PdfPipeline
from .providers import ArxivProvider, OpenAlexProvider
from .storage import DatasetStorage
from .train_baseline import run_baseline_pipeline


def build_command(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    http_client = HttpClient(settings=settings)

    resolvers = [
        ArxivProvider(http_client=http_client),
        OpenAlexProvider(http_client=http_client, settings=settings),
    ]
    builder = DatasetBuilder(resolvers=resolvers)

    seeds = load_seeds(args.input)
    records: list[dict] = []
    for seed in seeds:
        artifacts = builder.build_record_with_artifacts(seed)
        source_payload_refs = write_source_payload_refs(
            args.output,
            artifacts.record["record_id"],
            artifacts.candidates,
        )
        artifacts.record["raw"]["source_payload_refs"] = source_payload_refs
        records.append(artifacts.record)
    records = builder._deduplicate(records)
    write_jsonl(args.output, records)

    if args.csv:
        write_csv(args.csv, records)

    summary = {
        "input": str(args.input),
        "output": str(args.output),
        "records": len(records),
        "csv": str(args.csv) if args.csv else None,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def enrich_fulltext_command(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    http_client = HttpClient(settings=settings)
    storage = DatasetStorage.from_dataset_path(args.output)
    pipeline = PdfPipeline(http_client=http_client, storage=storage)

    records = load_records(args.input)
    enriched_records = [pipeline.enrich_record(record) for record in records]
    write_jsonl(args.output, enriched_records)

    summary = {
        "input": str(args.input),
        "output": str(args.output),
        "records": len(enriched_records),
        "parsed": sum(
            1
            for record in enriched_records
            if (record.get("content") or {}).get("fulltext_status") == "parsed"
        ),
        "failed": sum(
            1
            for record in enriched_records
            if (record.get("content") or {}).get("fulltext_status") == "failed"
        ),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def train_baseline_command(args: argparse.Namespace) -> int:
    summary = run_baseline_pipeline(
        input_path=args.input,
        workdir=args.workdir,
        text_mode=args.text_mode,
        random_state=args.random_state,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def discover_and_label_command(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    http_client = HttpClient(settings=settings)
    summary = run_discovery_and_label(
        queries_path=args.queries,
        output_dir=args.output_dir,
        settings=settings,
        http_client=http_client,
        model_path=args.model,
        vectorizer_path=args.vectorizer,
        default_source=args.source,
        max_results_per_query=args.max_results_per_query,
        relevant_threshold=args.relevant_threshold,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def label_candidates_command(args: argparse.Namespace) -> int:
    summary = run_label_candidates(
        input_path=args.input,
        output_dir=args.output_dir,
        model_path=args.model,
        vectorizer_path=args.vectorizer,
        relevant_threshold=args.relevant_threshold,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Normalize article seeds into a local dataset")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Build normalized dataset from article seeds")
    build.add_argument("--input", required=True, type=Path, help="Input .jsonl or .csv file")
    build.add_argument("--output", required=True, type=Path, help="Output JSONL path")
    build.add_argument("--csv", type=Path, default=None, help="Optional flat CSV export path")
    build.set_defaults(func=build_command)

    enrich = subparsers.add_parser(
        "enrich-fulltext",
        help="Download PDFs and store extracted full text outside the main dataset",
    )
    enrich.add_argument("--input", required=True, type=Path, help="Input normalized JSONL path")
    enrich.add_argument("--output", required=True, type=Path, help="Output JSONL path")
    enrich.set_defaults(func=enrich_fulltext_command)

    baseline = subparsers.add_parser(
        "train-baseline",
        help="Train TF-IDF baseline classifiers on the normalized dataset",
    )
    baseline.add_argument("--input", required=True, type=Path, help="Input normalized JSONL path")
    baseline.add_argument("--workdir", required=True, type=Path, help="Directory for baseline artifacts")
    baseline.add_argument(
        "--text-mode",
        default="title_abstract",
        choices=["title", "abstract", "title_abstract"],
        help="Text field configuration for the baseline",
    )
    baseline.add_argument(
        "--random-state",
        default=42,
        type=int,
        help="Random seed used for the grouped train/val/test split",
    )
    baseline.set_defaults(func=train_baseline_command)

    discover = subparsers.add_parser(
        "discover-and-label",
        help="Search new candidates and score them with the trained baseline model",
    )
    discover.add_argument("--queries", required=True, type=Path, help="Input query file (.txt or .jsonl)")
    discover.add_argument("--model", required=True, type=Path, help="Path to trained LogisticRegression model")
    discover.add_argument("--vectorizer", required=True, type=Path, help="Path to fitted TF-IDF vectorizer")
    discover.add_argument("--output-dir", required=True, type=Path, help="Output discovery run directory")
    discover.add_argument(
        "--source",
        default="openalex",
        choices=["openalex"],
        help="Discovery source for plain text query files",
    )
    discover.add_argument(
        "--max-results-per-query",
        default=200,
        type=int,
        help="Maximum number of raw search hits to collect per query",
    )
    discover.add_argument(
        "--relevant-threshold",
        default=0.65,
        type=float,
        help="Probability threshold for predicted_relevant",
    )
    discover.set_defaults(func=discover_and_label_command)

    label = subparsers.add_parser(
        "label-candidates",
        help="Rescore an existing discovery candidates.jsonl file with the trained baseline model",
    )
    label.add_argument("--input", required=True, type=Path, help="Input candidates.jsonl path")
    label.add_argument("--model", required=True, type=Path, help="Path to trained LogisticRegression model")
    label.add_argument("--vectorizer", required=True, type=Path, help="Path to fitted TF-IDF vectorizer")
    label.add_argument("--output-dir", required=True, type=Path, help="Output discovery run directory")
    label.add_argument(
        "--relevant-threshold",
        default=0.65,
        type=float,
        help="Probability threshold for predicted_relevant",
    )
    label.set_defaults(func=label_candidates_command)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
