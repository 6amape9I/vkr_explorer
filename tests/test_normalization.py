import argparse

from vkr_article_dataset import cli
from vkr_article_dataset.models import ArticleSeed, ProviderResult
from vkr_article_dataset.normalization import DatasetBuilder


class DummyArxivResolver:
    provider_name = "arxiv"

    def resolve(self, seed: ArticleSeed) -> ProviderResult | None:
        if seed.arxiv_id != "2206.11641":
            return None
        return ProviderResult(
            provider_name="arxiv",
            source_id="2206.11641",
            confidence=0.99,
            payload={
                "title": "Advancing Blockchain-based Federated Learning through Verifiable Off-chain Computations",
                "abstract": "We explore verifiable off-chain computations.",
                "authors": ["Jonathan Heiss"],
                "publication_year": 2022,
                "publication_date": "2022-06-23",
                "venue": "arXiv",
                "document_type": "preprint",
                "doi": None,
                "arxiv_id": "2206.11641",
                "landing_page_url": "https://arxiv.org/abs/2206.11641",
                "pdf_url": "https://arxiv.org/pdf/2206.11641.pdf",
                "language": "en",
                "is_open_access": True,
                "citation_count": None,
                "openalex_id": None,
            },
            raw={"provider": "dummy-arxiv"},
            match_details={"matched_by": "arxiv_id"},
        )


class DummyOpenAlexResolver:
    provider_name = "openalex"

    def resolve(self, seed: ArticleSeed) -> ProviderResult | None:
        if seed.arxiv_id != "2206.11641":
            return None
        return ProviderResult(
            provider_name="openalex",
            source_id="https://openalex.org/W123",
            confidence=0.95,
            payload={
                "title": "Advancing Blockchain-based Federated Learning through Verifiable Off-chain Computations",
                "abstract": "We explore verifiable off-chain computations with richer metadata.",
                "authors": ["Jonathan Heiss", "Elias Grunewald"],
                "publication_year": 2022,
                "publication_date": "2022-06-23",
                "venue": "OpenAlex Venue",
                "document_type": "article",
                "doi": "10.1000/example",
                "arxiv_id": "2206.11641",
                "landing_page_url": "https://doi.org/10.1000/example",
                "pdf_url": None,
                "language": "en",
                "is_open_access": True,
                "citation_count": 42,
                "openalex_id": "https://openalex.org/W123",
            },
            raw={"provider": "dummy-openalex"},
            match_details={"matched_by": "doi"},
        )


def _seed() -> ArticleSeed:
    return ArticleSeed(
        input_position=1,
        arxiv_id="2206.11641",
        gold_label="relevant",
        notes="seed note",
    )


def test_collects_multiple_candidates() -> None:
    builder = DatasetBuilder(resolvers=[DummyArxivResolver(), DummyOpenAlexResolver()])

    artifacts = builder.build_record_with_artifacts(_seed())

    assert len(artifacts.candidates) == 2
    assert {candidate.provider_name for candidate in artifacts.candidates} == {"arxiv", "openalex"}


def test_build_record_v2_contains_sources_block() -> None:
    builder = DatasetBuilder(resolvers=[DummyArxivResolver(), DummyOpenAlexResolver()])

    record = builder.build_record(_seed())

    assert record["schema_version"] == "2"
    assert record["sources"]["primary_source"] == "openalex"
    assert set(record["sources"]["available_sources"]) == {"arxiv", "openalex"}
    assert record["sources"]["source_candidates_count"] == 2
    assert record["content"]["fulltext_status"] == "not_attempted"
    assert record["identifiers"]["canonical_id"] == "doi:10.1000/example"


def test_labels_split_auto_manual_fields() -> None:
    builder = DatasetBuilder(resolvers=[DummyArxivResolver()])

    record = builder.build_record(_seed())

    labels = record["labels"]
    assert "auto_topic_tags" in labels
    assert "auto_method_tags" in labels
    assert labels["manual_topic_tags"] == []
    assert labels["manual_method_tags"] == []
    assert "off_chain" in labels["auto_topic_tags"]


def test_build_command_remains_backward_compatible(tmp_path, monkeypatch) -> None:
    input_path = tmp_path / "input.jsonl"
    output_path = tmp_path / "normalized" / "articles.jsonl"
    csv_path = tmp_path / "normalized" / "articles.csv"
    input_path.write_text('{"arxiv_id": "2206.11641", "gold_label": "relevant"}\n', encoding="utf-8")

    monkeypatch.setattr(cli, "ArxivProvider", lambda http_client: DummyArxivResolver())
    monkeypatch.setattr(cli, "OpenAlexProvider", lambda http_client, settings: DummyOpenAlexResolver())

    exit_code = cli.build_command(
        argparse.Namespace(input=input_path, output=output_path, csv=csv_path)
    )

    assert exit_code == 0
    assert output_path.exists()
    assert csv_path.exists()
    assert (tmp_path / "raw" / "arxiv").exists()
    assert (tmp_path / "raw" / "openalex").exists()
