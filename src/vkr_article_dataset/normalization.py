from __future__ import annotations

from typing import Iterable

from .merge import RecordMerger
from .models import ArticleSeed, BuildArtifacts, ProviderResult, ResolutionResult


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
        record = self.merger.build_record(
            seed,
            resolution,
            source_payload_refs=source_payload_refs,
        )
        return BuildArtifacts(record=record, candidates=resolution.candidates)

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
        return resolution

    def _deduplicate(self, records: list[dict]) -> list[dict]:
        seen: dict[str, dict] = {}
        for record in records:
            key = record["record_id"]
            current = seen.get(key)
            if current is None:
                seen[key] = record
                continue
            current_status = current.get("resolution_status")
            new_status = record.get("resolution_status")
            if current_status != "resolved" and new_status == "resolved":
                seen[key] = record
        return list(seen.values())


def _resolver_name(resolver: object) -> str:
    explicit_name = getattr(resolver, "provider_name", None)
    if isinstance(explicit_name, str) and explicit_name:
        return explicit_name
    class_name = resolver.__class__.__name__
    return class_name.removesuffix("Provider").lower()
