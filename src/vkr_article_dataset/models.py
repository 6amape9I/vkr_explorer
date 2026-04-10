from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


ALLOWED_GOLD_LABELS = {"relevant", "partial", "irrelevant", "unknown"}


@dataclass(slots=True)
class ArticleSeed:
    input_position: int
    title: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    url: str | None = None
    seed_query: str | None = None
    gold_label: str = "unknown"
    is_hard_negative: bool = False
    notes: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if self.gold_label not in ALLOWED_GOLD_LABELS:
            raise ValueError(
                f"Unsupported gold_label={self.gold_label!r}. Allowed: {sorted(ALLOWED_GOLD_LABELS)}"
            )
        if not any([self.title, self.doi, self.arxiv_id, self.url]):
            raise ValueError(
                "Each seed must have at least one of: title, doi, arxiv_id, url"
            )


@dataclass(slots=True)
class ProviderResult:
    provider_name: str
    source_id: str | None
    confidence: float
    payload: dict[str, Any]
    raw: dict[str, Any]
    match_details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ResolutionResult:
    candidates: list[ProviderResult] = field(default_factory=list)
    attempted: list[str] = field(default_factory=list)
    successful: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    rejections: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class FieldDecision:
    winner: str | None
    candidates: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass(slots=True)
class MergeDecision:
    primary_source: str | None
    fields: dict[str, FieldDecision] = field(default_factory=dict)


@dataclass(slots=True)
class BuildArtifacts:
    record: dict[str, Any]
    candidates: list[ProviderResult] = field(default_factory=list)
    merge_decisions: dict[str, Any] = field(default_factory=dict)
