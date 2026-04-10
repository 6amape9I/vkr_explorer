from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import Settings
from .http import HttpClient
from .io_utils import load_seeds, write_csv, write_jsonl
from .normalization import DatasetBuilder
from .providers import ArxivProvider, OpenAlexProvider


def build_command(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    http_client = HttpClient(settings=settings)

    resolvers = [
        ArxivProvider(http_client=http_client),
        OpenAlexProvider(http_client=http_client, settings=settings),
    ]
    builder = DatasetBuilder(resolvers=resolvers)

    seeds = load_seeds(args.input)
    records = builder.build_records(seeds)
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Normalize article seeds into a local dataset")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Build normalized dataset from article seeds")
    build.add_argument("--input", required=True, type=Path, help="Input .jsonl or .csv file")
    build.add_argument("--output", required=True, type=Path, help="Output JSONL path")
    build.add_argument("--csv", type=Path, default=None, help="Optional flat CSV export path")
    build.set_defaults(func=build_command)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
