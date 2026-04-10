from vkr_article_dataset.pdf_pipeline import PdfPipeline
from vkr_article_dataset.storage import DatasetStorage
from vkr_article_dataset.tagger import infer_tags


class FakeHttpClient:
    def get_bytes(self, url: str, params=None) -> bytes:
        del url, params
        return b"%PDF-1.4 fake pdf bytes"


def test_tagger_assigns_blockchain_and_fl_for_bcfl_paper() -> None:
    title = "Advancing Blockchain-Based Federated Learning Through Verifiable Off-Chain Computations"
    abstract = (
        "We explore verifiable off-chain computations using zero-knowledge proofs "
        "for blockchain-based federated learning."
    )

    result = infer_tags(title=title, abstract=abstract)

    assert "blockchain" in result.topic_tags
    assert "federated_learning" in result.topic_tags
    assert "verification" in result.method_tags
    assert result.topic_scores["blockchain"] >= 3
    assert result.topic_evidence["blockchain"]


def test_tagger_does_not_assign_parameter_server_on_single_background_mention() -> None:
    title = "Blockchain-Based Federated Learning for Secure Aggregation"
    abstract = (
        "We study blockchain coordination for federated learning. "
        "A parameter server is mentioned once in background discussion."
    )

    result = infer_tags(title=title, abstract=abstract)

    assert "parameter_server" not in result.topic_tags
    assert result.topic_scores["parameter_server"] == 0


def test_tagger_uses_fulltext_excerpt_when_available() -> None:
    title = "Federated Learning for Medical Imaging"
    abstract = "We study federated learning under secure aggregation."
    fulltext_excerpt = (
        "The proposed blockchain coordination layer stores aggregation proofs "
        "and smart contract events for each training round."
    )

    result = infer_tags(title=title, abstract=abstract, fulltext_excerpt=fulltext_excerpt)

    assert "blockchain" in result.topic_tags
    assert any(hit["field"] == "fulltext" for hit in result.topic_evidence["blockchain"])


def test_tagger_keeps_manual_tags_separate_from_auto_tags(tmp_path, monkeypatch) -> None:
    pipeline = PdfPipeline(http_client=FakeHttpClient(), storage=DatasetStorage(tmp_path))
    record = {
        "record_id": "art_manual",
        "bibliography": {
            "title": "Federated Learning Coordination",
        },
        "content": {
            "abstract": "We study federated learning.",
            "fulltext_ref": None,
            "fulltext_status": "not_attempted",
            "fulltext_quality": None,
        },
        "links": {
            "pdf_url": "https://example.com/article.pdf",
        },
        "labels": {
            "gold_label": "relevant",
            "is_hard_negative": False,
            "auto_topic_tags": [],
            "auto_method_tags": [],
            "auto_topic_tag_scores": {},
            "auto_method_tag_scores": {},
            "auto_topic_tag_evidence": {},
            "auto_method_tag_evidence": {},
            "manual_topic_tags": ["manual_bc_tag"],
            "manual_method_tags": ["manual_method"],
            "notes": None,
        },
    }

    monkeypatch.setattr(
        pipeline,
        "_parse_pdf",
        lambda **kwargs: {
            "record_id": kwargs["record_id"],
            "source": "pdf",
            "parser": "pymupdf",
            "download_url": kwargs["download_url"],
            "pdf_sha256": kwargs["pdf_sha256"],
            "text_sha256": "hash",
            "page_count": 1,
            "extraction_status": "parsed",
            "quality": {
                "char_count": 100,
                "word_count": 20,
                "page_count": 1,
                "empty_pages": 0,
                "suspected_ocr_noise": False,
            },
            "page_texts": ["Blockchain coordination for federated learning"],
            "full_text": "Blockchain coordination for federated learning references omitted",
        },
    )

    updated = pipeline.enrich_record(record)

    assert updated["labels"]["manual_topic_tags"] == ["manual_bc_tag"]
    assert updated["labels"]["manual_method_tags"] == ["manual_method"]
    assert "blockchain" in updated["labels"]["auto_topic_tags"]
