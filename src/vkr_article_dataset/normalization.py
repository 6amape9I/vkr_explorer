from __future__ import annotations

from typing import Iterable

from .merge import RecordMerger
from .models import ArticleSeed, BuildArtifacts, ProviderResult, ResolutionResult
from .utils import slugify_title


class DatasetBuilder:
    def __init__(self, resolvers: Iterable, merger: RecordMerger | None = None) -> None:
        self.resolvers = list(resolvers)
        self.merger = merger or RecordMerger()

    def build_record(self, seed: ArticleSeed) -> dict:
        return self.build_record_with_artifacts(seed).record

    def build_record_with_artifacts(
        self,
        seed: ArticleSeed,
        *,
        source_payload_refs: dict[str, str] | None = None,
    ) -> BuildArtifacts:
        resolution = self._resolve_all(seed)
        record, merge_decision = self.merger.merge(
            seed,
            resolution,
            source_payload_refs=source_payload_refs,
        )
        return BuildArtifacts(
            record=record,
            candidates=resolution.candidates,
            merge_decisions={
                field_name: {
                    "winner": field_decision.winner,
                    "candidates": field_decision.candidates,
                    "reason": field_decision.reason,
                }
                for field_name, field_decision in merge_decision.fields.items()
            },
        )

    def build_records(self, seeds: list[ArticleSeed]) -> list[dict]:
        records = [self.build_record(seed) for seed in seeds]
        return self._deduplicate(records)

    def _resolve_all(self, seed: ArticleSeed) -> ResolutionResult:
        resolution = ResolutionResult()
        for resolver in self.resolvers:
            resolver_name = _resolver_name(resolver)
            resolution.attempted.append(resolver_name)
            try:
                result = resolver.resolve(seed)
            except Exception as exc:  # noqa: BLE001
                resolution.errors[resolver_name] = f"{type(exc).__name__}: {exc}"
                continue
            if result is not None:
                resolution.successful.append(result.provider_name)
                resolution.candidates.append(result)
                continue
            rejection_reason = getattr(resolver, "last_resolution_note", None)
            if rejection_reason:
                resolution.rejections[resolver_name] = rejection_reason
        return resolution

    def _deduplicate(self, records: list[dict]) -> list[dict]:
        if not records:
            return []

        groups: list[list[dict]] = []
        consumed: set[int] = set()

        exact_indices = self._build_exact_duplicate_index(records)
        for index, record in enumerate(records):
            if index in consumed:
                continue
            pending = [index]
            group_indices = set()
            while pending:
                current_index = pending.pop()
                if current_index in group_indices:
                    continue
                group_indices.add(current_index)
                for key in _exact_keys(records[current_index]):
                    for related_index in exact_indices.get(key, set()):
                        if related_index not in group_indices:
                            pending.append(related_index)
            for group_index in group_indices:
                consumed.add(group_index)
            groups.append([records[group_index] for group_index in sorted(group_indices)])

        remaining = [group[0] for group in groups if len(group) == 1]
        fuzzy_groups = self._build_fuzzy_groups(remaining)
        merged_groups: list[list[dict]] = [group for group in groups if len(group) > 1]
        merged_groups.extend(fuzzy_groups)

        fuzzy_consumed = {
            record.get("record_id")
            for group in fuzzy_groups
            for record in group
        }
        for record in remaining:
            if record.get("record_id") in fuzzy_consumed:
                continue
            merged_groups.append([record])

        return [self.merger.merge_records(group) for group in merged_groups]

    def _build_exact_duplicate_index(self, records: list[dict]) -> dict[tuple[str, str], set[int]]:
        index: dict[tuple[str, str], set[int]] = {}
        for record_index, record in enumerate(records):
            for key in _exact_keys(record):
                index.setdefault(key, set()).add(record_index)
        return index

    def _build_fuzzy_groups(self, records: list[dict]) -> list[list[dict]]:
        buckets: dict[tuple[str, int, str], list[dict]] = {}
        for record in records:
            key = _fuzzy_key(record)
            if key is None:
                continue
            if _has_strong_exact_identifier(record):
                continue
            buckets.setdefault(key, []).append(record)
        return [bucket for bucket in buckets.values() if len(bucket) > 1]


def _resolver_name(resolver: object) -> str:
    explicit_name = getattr(resolver, "provider_name", None)
    if isinstance(explicit_name, str) and explicit_name:
        return explicit_name
    class_name = resolver.__class__.__name__
    return class_name.removesuffix("Provider").lower()


def _exact_keys(record: dict) -> list[tuple[str, str]]:
    identifiers = record.get("identifiers", {}) or {}
    keys: list[tuple[str, str]] = []
    for field_name in ("doi", "arxiv_id", "canonical_id"):
        value = identifiers.get(field_name)
        if isinstance(value, str) and value.strip():
            keys.append((field_name, value.strip().lower()))
    return keys


def _fuzzy_key(record: dict) -> tuple[str, int, str] | None:
    bibliography = record.get("bibliography", {}) or {}
    authors = bibliography.get("authors") or []
    title = slugify_title(bibliography.get("title"))
    year = bibliography.get("publication_year")
    if not title or not isinstance(year, int) or not authors:
        return None
    first_author = authors[0]
    if not isinstance(first_author, str) or not first_author.strip():
        return None
    return title, year, first_author.split()[-1].lower()


def _has_strong_exact_identifier(record: dict) -> bool:
    identifiers = record.get("identifiers", {}) or {}
    if identifiers.get("doi") or identifiers.get("arxiv_id"):
        return True
    canonical = identifiers.get("canonical_id")
    return isinstance(canonical, str) and not canonical.startswith("hash:")
