from copy import deepcopy

from vkr_article_dataset.config import Settings
from vkr_article_dataset.models import ArticleSeed
from vkr_article_dataset.normalization import DatasetBuilder
from vkr_article_dataset.providers.openalex_provider import OpenAlexProvider


class FakeHttpClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def get_json(self, url: str, params=None) -> dict:
        return deepcopy(self.payload)


def test_matching_accepts_exact_title_year_author_candidate() -> None:
    payload = {
        "results": [
            {
                "id": "https://openalex.org/W123",
                "display_name": "Advancing Blockchain-Based Federated Learning Through Verifiable Off-Chain Computations",
                "publication_year": 2022,
                "publication_date": "2022-06-23",
                "authorships": [
                    {"author": {"display_name": "Jonathan Heiss"}},
                    {"author": {"display_name": "Elias Grunewald"}},
                ],
                "type": "article",
                "doi": "https://doi.org/10.1000/example",
                "primary_location": {
                    "source": {"display_name": "OpenAlex Venue"},
                    "landing_page_url": "https://doi.org/10.1000/example",
                    "pdf_url": None,
                },
                "open_access": {"is_oa": True},
                "cited_by_count": 21,
                "abstract_inverted_index": {"federated": [0], "learning": [1]},
            },
            {
                "id": "https://openalex.org/W999",
                "display_name": "A Similar But Different Paper",
                "publication_year": 2021,
                "authorships": [{"author": {"display_name": "Other Author"}}],
                "type": "article",
            },
        ]
    }
    provider = OpenAlexProvider(http_client=FakeHttpClient(payload), settings=Settings())
    seed = ArticleSeed(
        input_position=1,
        title="Advancing blockchain based federated learning through verifiable off chain computations",
        extra={"publication_year": 2022, "authors": ["Jonathan Heiss"]},
    )

    result = provider.resolve(seed)

    assert result is not None
    assert result.source_id == "https://openalex.org/W123"
    assert result.match_details["matched_by"] == "title_rerank"
    assert result.confidence >= 0.72


def test_matching_rejects_low_confidence_title_only_candidate() -> None:
    payload = {
        "results": [
            {
                "id": "https://openalex.org/W456",
                "display_name": "Distributed Databases for Enterprise Reporting",
                "publication_year": 2018,
                "authorships": [{"author": {"display_name": "Alice Smith"}}],
                "type": "article",
            }
        ]
    }
    provider = OpenAlexProvider(http_client=FakeHttpClient(payload), settings=Settings())
    seed = ArticleSeed(
        input_position=1,
        title="Blockchain based federated learning for medical imaging",
    )

    result = provider.resolve(seed)

    assert result is None
    assert provider.last_resolution_note is not None
    assert "low-confidence" in provider.last_resolution_note


def test_dedup_merges_records_with_same_doi() -> None:
    builder = DatasetBuilder(resolvers=[])
    record_a = _record(
        record_id="art_a",
        doi="10.1000/example",
        canonical_id="doi:10.1000/example",
        title="A Paper",
        authors=["Jonathan Heiss"],
        abstract="Short abstract.",
        primary_source="arxiv",
    )
    record_b = _record(
        record_id="art_b",
        doi="10.1000/example",
        canonical_id="doi:10.1000/example",
        title="A Paper",
        authors=["Jonathan Heiss", "Elias Grunewald"],
        abstract="Longer abstract with more detail and evaluation information.",
        primary_source="openalex",
        citation_count=42,
    )

    merged = builder._deduplicate([record_a, record_b])

    assert len(merged) == 1
    assert merged[0]["dedup"]["duplicate_group_size"] == 2
    assert merged[0]["dedup"]["dedup_strategy"] == "doi"
    assert merged[0]["content"]["abstract"] == record_b["content"]["abstract"]


def test_dedup_merges_fuzzy_duplicates_without_exact_ids() -> None:
    builder = DatasetBuilder(resolvers=[])
    record_a = _record(
        record_id="art_a",
        title="Verifiable Off Chain Federated Learning",
        authors=["Jonathan Heiss"],
        publication_year=2022,
        canonical_id="hash:111111111111",
    )
    record_b = _record(
        record_id="art_b",
        title="Verifiable Off-Chain Federated Learning",
        authors=["Jonathan Heiss", "Elias Grunewald"],
        publication_year=2022,
        abstract="More complete abstract.",
        canonical_id="hash:222222222222",
    )

    merged = builder._deduplicate([record_a, record_b])

    assert len(merged) == 1
    assert merged[0]["dedup"]["duplicate_group_size"] == 2
    assert merged[0]["dedup"]["dedup_strategy"] == "fuzzy_title_year_author"
    assert merged[0]["bibliography"]["authors"] == ["Jonathan Heiss", "Elias Grunewald"]


def _record(
    *,
    record_id: str,
    title: str,
    authors: list[str],
    publication_year: int = 2022,
    abstract: str = "Abstract.",
    doi: str | None = None,
    canonical_id: str = "hash:123456789abc",
    primary_source: str = "openalex",
    citation_count: int | None = None,
) -> dict:
    return {
        "schema_version": "2",
        "record_id": record_id,
        "resolution_status": "resolved",
        "retrieved_at": "2026-04-10T12:00:00Z",
        "identifiers": {
            "doi": doi,
            "arxiv_id": None,
            "openalex_id": None,
            "canonical_id": canonical_id,
            "source": primary_source,
        },
        "sources": {
            "primary_source": primary_source,
            "available_sources": [primary_source],
            "source_candidates_count": 1,
        },
        "source_candidates": [],
        "merge_decisions": {},
        "bibliography": {
            "title": title,
            "authors": authors,
            "publication_year": publication_year,
            "publication_date": f"{publication_year}-01-01",
            "venue": "Venue",
            "document_type": "article",
        },
        "content": {
            "abstract": abstract,
            "combined_text": f"{title}\n\n{abstract}",
            "language": "en",
            "fulltext_ref": None,
            "fulltext_status": "not_attempted",
            "fulltext_quality": None,
        },
        "labels": {
            "gold_label": "unknown",
            "is_hard_negative": False,
            "auto_topic_tags": [],
            "auto_method_tags": [],
            "auto_topic_tag_scores": {},
            "auto_method_tag_scores": {},
            "auto_topic_tag_evidence": {},
            "auto_method_tag_evidence": {},
            "manual_topic_tags": [],
            "manual_method_tags": [],
            "notes": None,
        },
        "quality": {
            "has_abstract": bool(abstract),
            "has_pdf_url": False,
            "is_open_access": True,
            "citation_count": citation_count,
        },
        "links": {
            "landing_page_url": None,
            "pdf_url": None,
        },
        "provenance": {
            "seed_query": None,
            "input_position": 1,
            "resolver_summary": {
                "attempted": [],
                "successful": [],
                "errors": {},
                "rejections": {},
            },
            "merge_summary": {},
        },
        "raw": {
            "seed_extra": {},
            "source_payload_refs": {},
        },
    }
