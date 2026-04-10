from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import Settings
from .http import HttpClient
from .io_utils import load_records, load_seeds, write_csv, write_jsonl, write_source_payload_refs
from .normalization import DatasetBuilder
from .pdf_pipeline import PdfPipeline
from .providers import ArxivProvider, OpenAlexProvider
from .storage import DatasetStorage


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
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
