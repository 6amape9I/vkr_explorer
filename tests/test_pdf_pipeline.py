import gzip
import json

from vkr_article_dataset.pdf_pipeline import PdfPipeline
from vkr_article_dataset.storage import DatasetStorage


class FakeHttpClient:
    def __init__(self, content: bytes | None = None, error: Exception | None = None) -> None:
        self.content = content or b"%PDF-1.4 fake pdf bytes"
        self.error = error

    def get_bytes(self, url: str, params=None) -> bytes:
        del url, params
        if self.error is not None:
            raise self.error
        return self.content


def _record() -> dict:
    return {
        "record_id": "art_test123",
        "content": {
            "fulltext_ref": None,
            "fulltext_status": "not_attempted",
            "fulltext_quality": None,
        },
        "links": {
            "pdf_url": "https://example.com/article.pdf",
        },
    }


def test_pdf_download_failure_sets_failed_status(tmp_path) -> None:
    pipeline = PdfPipeline(
        http_client=FakeHttpClient(error=RuntimeError("boom")),
        storage=DatasetStorage(tmp_path),
    )

    updated = pipeline.enrich_record(_record())

    assert updated["content"]["fulltext_status"] == "failed"
    assert updated["content"]["fulltext_ref"] is None


def test_pdf_parsing_success_writes_fulltext_file(tmp_path, monkeypatch) -> None:
    pipeline = PdfPipeline(
        http_client=FakeHttpClient(),
        storage=DatasetStorage(tmp_path),
    )

    def fake_parse_pdf(*, record_id, pdf_path, download_url, pdf_sha256):
        del pdf_path, download_url, pdf_sha256
        return {
            "record_id": record_id,
            "source": "pdf",
            "parser": "pymupdf",
            "download_url": "https://example.com/article.pdf",
            "pdf_sha256": "abc",
            "text_sha256": "def",
            "page_count": 2,
            "extraction_status": "parsed",
            "quality": {
                "char_count": 123,
                "word_count": 20,
                "page_count": 2,
                "empty_pages": 0,
                "suspected_ocr_noise": False,
            },
            "page_texts": ["Page one", "Page two"],
            "full_text": "Page one\n\nPage two",
        }

    monkeypatch.setattr(pipeline, "_parse_pdf", fake_parse_pdf)

    updated = pipeline.enrich_record(_record())

    assert updated["content"]["fulltext_status"] == "parsed"
    assert updated["content"]["fulltext_ref"] == "fulltext/art_test123.json.gz"
    assert (tmp_path / "pdfs" / "art_test123.pdf").exists()
    assert (tmp_path / "fulltext" / "art_test123.json.gz").exists()


def test_main_dataset_does_not_inline_full_text(tmp_path, monkeypatch) -> None:
    pipeline = PdfPipeline(
        http_client=FakeHttpClient(),
        storage=DatasetStorage(tmp_path),
    )

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
                "char_count": 10,
                "word_count": 2,
                "page_count": 1,
                "empty_pages": 0,
                "suspected_ocr_noise": False,
            },
            "page_texts": ["Hello world"],
            "full_text": "Hello world",
        },
    )

    updated = pipeline.enrich_record(_record())

    assert "full_text" not in updated["content"]
    with gzip.open(tmp_path / "fulltext" / "art_test123.json.gz", "rt", encoding="utf-8") as fh:
        payload = json.load(fh)
    assert payload["full_text"] == "Hello world"


def test_fulltext_quality_metrics_present(tmp_path, monkeypatch) -> None:
    pipeline = PdfPipeline(
        http_client=FakeHttpClient(),
        storage=DatasetStorage(tmp_path),
    )

    monkeypatch.setattr(
        pipeline,
        "_parse_pdf",
        lambda **kwargs: {
            "record_id": kwargs["record_id"],
            "source": "pdf",
            "parser": "pypdf",
            "download_url": kwargs["download_url"],
            "pdf_sha256": kwargs["pdf_sha256"],
            "text_sha256": "hash",
            "page_count": 3,
            "extraction_status": "parsed",
            "quality": {
                "char_count": 999,
                "word_count": 111,
                "page_count": 3,
                "empty_pages": 0,
                "suspected_ocr_noise": False,
            },
            "page_texts": ["a", "b", "c"],
            "full_text": "a b c",
        },
    )

    updated = pipeline.enrich_record(_record())

    quality = updated["content"]["fulltext_quality"]
    assert quality["char_count"] == 999
    assert quality["page_count"] == 3
