from vkr_article_dataset.models import ArticleSeed, ProviderResult
from vkr_article_dataset.normalization import DatasetBuilder


class DummyResolver:
    def resolve(self, seed: ArticleSeed) -> ProviderResult | None:
        if seed.arxiv_id == "2206.11641":
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
                raw={"provider": "dummy"},
            )
        return None


def test_builder_normalizes_record() -> None:
    builder = DatasetBuilder(resolvers=[DummyResolver()])
    seed = ArticleSeed(
        input_position=1,
        arxiv_id="2206.11641",
        gold_label="relevant",
        notes="seed note",
    )
    record = builder.build_record(seed)

    assert record["resolution_status"] == "resolved"
    assert record["identifiers"]["arxiv_id"] == "2206.11641"
    assert record["labels"]["gold_label"] == "relevant"
    assert "off_chain" in record["labels"]["topic_tags"]
    assert record["content"]["combined_text"].startswith(
        "Advancing Blockchain-based Federated Learning"
    )
