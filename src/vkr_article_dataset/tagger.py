from __future__ import annotations

import re
from dataclasses import dataclass, field

from .tag_rules import METHOD_RULES, TOPIC_RULES, TagRule
from .utils import normalize_whitespace


FIELD_WEIGHTS = {
    "title": 3,
    "abstract": 2,
    "fulltext": 1,
}

FULLTEXT_EXCERPT_LIMIT = 4000
REFERENCES_RE = re.compile(r"\b(references|bibliography)\b", flags=re.IGNORECASE)


@dataclass(slots=True)
class TaggingResult:
    topic_tags: list[str] = field(default_factory=list)
    method_tags: list[str] = field(default_factory=list)
    topic_scores: dict[str, int] = field(default_factory=dict)
    method_scores: dict[str, int] = field(default_factory=dict)
    topic_evidence: dict[str, list[dict[str, object]]] = field(default_factory=dict)
    method_evidence: dict[str, list[dict[str, object]]] = field(default_factory=dict)


def infer_tags(
    title: str | None,
    abstract: str | None,
    *,
    fulltext_excerpt: str | None = None,
) -> TaggingResult:
    fields = {
        "title": normalize_whitespace(title) or "",
        "abstract": normalize_whitespace(abstract) or "",
        "fulltext": normalize_whitespace(fulltext_excerpt) or "",
    }

    topic_scores, topic_evidence = _score_rules(TOPIC_RULES, fields)
    method_scores, method_evidence = _score_rules(METHOD_RULES, fields)

    _apply_positive_context(topic_scores, topic_evidence)
    _apply_negative_rules(topic_scores, topic_evidence)
    _apply_negative_rules(method_scores, method_evidence)

    topic_tags = sorted(
        tag for tag, rule in TOPIC_RULES.items() if topic_scores.get(tag, 0) >= rule.threshold
    )
    method_tags = sorted(
        tag for tag, rule in METHOD_RULES.items() if method_scores.get(tag, 0) >= rule.threshold
    )

    return TaggingResult(
        topic_tags=topic_tags,
        method_tags=method_tags,
        topic_scores=topic_scores,
        method_scores=method_scores,
        topic_evidence=topic_evidence,
        method_evidence=method_evidence,
    )


def extract_fulltext_excerpt(full_text: str | None, *, limit: int = FULLTEXT_EXCERPT_LIMIT) -> str | None:
    text = normalize_whitespace(full_text)
    if not text:
        return None
    match = REFERENCES_RE.search(text)
    if match and match.start() > 500:
        text = text[:match.start()]
    return text[:limit].strip() or None


def _score_rules(
    rules: dict[str, TagRule],
    fields: dict[str, str],
) -> tuple[dict[str, int], dict[str, list[dict[str, object]]]]:
    scores: dict[str, int] = {}
    evidence: dict[str, list[dict[str, object]]] = {}
    for tag, rule in rules.items():
        tag_score = 0
        tag_hits: list[dict[str, object]] = []
        for field_name, text in fields.items():
            lowered = text.lower()
            for pattern in rule.patterns:
                count = _count_occurrences(lowered, pattern)
                if not count:
                    continue
                weight = FIELD_WEIGHTS[field_name]
                delta = weight * count
                tag_score += delta
                tag_hits.append(
                    {
                        "field": field_name,
                        "match": pattern,
                        "count": count,
                        "weight": weight,
                        "score": delta,
                    }
                )
        scores[tag] = tag_score
        if tag_hits:
            evidence[tag] = tag_hits
    return scores, evidence


def _apply_negative_rules(
    scores: dict[str, int],
    evidence: dict[str, list[dict[str, object]]],
) -> None:
    if _single_background_parameter_server(evidence):
        scores["parameter_server"] = 0
        evidence.pop("parameter_server", None)

    fl_score = max(scores.get("federated_learning", 0), scores.get("decentralized_learning", 0))
    distributed_hits = evidence.get("distributed_training") or []
    has_distributed_title = any(hit["field"] == "title" for hit in distributed_hits)
    if distributed_hits and not has_distributed_title and fl_score >= 3 and scores.get("distributed_training", 0) <= 3:
        scores["distributed_training"] = 0
        evidence.pop("distributed_training", None)


def _apply_positive_context(
    scores: dict[str, int],
    evidence: dict[str, list[dict[str, object]]],
) -> None:
    blockchain_hits = evidence.get("blockchain") or []
    has_blockchain_fulltext = any(hit["field"] == "fulltext" for hit in blockchain_hits)
    fl_score = max(scores.get("federated_learning", 0), scores.get("decentralized_learning", 0))
    if has_blockchain_fulltext and fl_score >= 3:
        scores["blockchain"] = scores.get("blockchain", 0) + 2
        evidence.setdefault("blockchain", []).append(
            {
                "field": "context",
                "match": "bc_fl_context",
                "count": 1,
                "weight": 2,
                "score": 2,
            }
        )


def _single_background_parameter_server(evidence: dict[str, list[dict[str, object]]]) -> bool:
    hits = evidence.get("parameter_server") or []
    if not hits:
        return False
    if any(hit["field"] == "title" for hit in hits):
        return False
    total_mentions = sum(int(hit["count"]) for hit in hits)
    return total_mentions <= 1


def _count_occurrences(text: str, pattern: str) -> int:
    return len(re.findall(re.escape(pattern.lower()), text))
