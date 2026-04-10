from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from .http import HttpClient
from .schema import (
    FULLTEXT_STATUS_DOWNLOADED,
    FULLTEXT_STATUS_FAILED,
    FULLTEXT_STATUS_PARSED,
)
from .storage import DatasetStorage, sha256_text
from .tagger import extract_fulltext_excerpt, infer_tags


class PdfPipeline:
    def __init__(self, http_client: HttpClient, storage: DatasetStorage) -> None:
        self.http_client = http_client
        self.storage = storage

    def enrich_record(self, record: dict[str, Any]) -> dict[str, Any]:
        updated = deepcopy(record)
        content = dict(updated.get("content") or {})
        links = dict(updated.get("links") or {})
        pdf_url = links.get("pdf_url")
        if not pdf_url:
            updated["content"] = content
            return updated

        record_id = updated.get("record_id")
        if not record_id:
            raise ValueError("Record is missing record_id")

        try:
            stored_pdf = self._download_pdf(record_id, pdf_url)
            content["fulltext_status"] = FULLTEXT_STATUS_DOWNLOADED
        except Exception as exc:  # noqa: BLE001
            content["fulltext_ref"] = None
            content["fulltext_status"] = FULLTEXT_STATUS_FAILED
            content["fulltext_quality"] = None
            content["fulltext_error"] = f"{type(exc).__name__}: {exc}"
            updated["content"] = content
            return updated

        try:
            payload = self._parse_pdf(
                record_id=record_id,
                pdf_path=stored_pdf.path,
                download_url=pdf_url,
                pdf_sha256=stored_pdf.sha256,
            )
            fulltext_ref = self.storage.save_fulltext(record_id, payload)
            content["fulltext_ref"] = fulltext_ref
            content["fulltext_status"] = FULLTEXT_STATUS_PARSED
            content["fulltext_quality"] = payload.get("quality")
            content["fulltext_error"] = None
            self._refresh_auto_tags(updated, payload.get("full_text"))
        except Exception as exc:  # noqa: BLE001
            content["fulltext_ref"] = None
            content["fulltext_status"] = FULLTEXT_STATUS_FAILED
            content["fulltext_quality"] = None
            content["fulltext_error"] = f"{type(exc).__name__}: {exc}"
        updated["content"] = content
        return updated

    def _download_pdf(self, record_id: str, pdf_url: str):
        content = self.http_client.get_bytes(pdf_url)
        return self.storage.save_pdf(record_id, content)

    def _parse_pdf(
        self,
        *,
        record_id: str,
        pdf_path: Path,
        download_url: str,
        pdf_sha256: str,
    ) -> dict[str, Any]:
        parser_name = "pymupdf"
        page_texts: list[str]
        try:
            page_texts = self._extract_page_texts_pymupdf(pdf_path)
        except Exception:  # noqa: BLE001
            parser_name = "pypdf"
            page_texts = self._extract_page_texts_pypdf(pdf_path)

        normalized_pages = [self._normalize_page_text(page_text) for page_text in page_texts]
        full_text = "\n\n".join(page for page in normalized_pages if page).strip()
        quality = _quality_metrics(normalized_pages, full_text)
        return {
            "record_id": record_id,
            "source": "pdf",
            "parser": parser_name,
            "download_url": download_url,
            "pdf_sha256": pdf_sha256,
            "text_sha256": sha256_text(full_text),
            "page_count": len(normalized_pages),
            "extraction_status": FULLTEXT_STATUS_PARSED,
            "quality": quality,
            "page_texts": normalized_pages,
            "full_text": full_text,
        }

    def _extract_page_texts_pymupdf(self, pdf_path: Path) -> list[str]:
        import fitz

        document = fitz.open(pdf_path)
        try:
            return [page.get_text("text") for page in document]
        finally:
            document.close()

    def _extract_page_texts_pypdf(self, pdf_path: Path) -> list[str]:
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        return [page.extract_text() or "" for page in reader.pages]

    def _normalize_page_text(self, page_text: str | None) -> str:
        if not page_text:
            return ""
        return re.sub(r"\s+", " ", page_text).strip()

    def _refresh_auto_tags(self, record: dict[str, Any], full_text: str | None) -> None:
        labels = dict(record.get("labels") or {})
        bibliography = dict(record.get("bibliography") or {})
        content = dict(record.get("content") or {})
        tagging = infer_tags(
            title=bibliography.get("title"),
            abstract=content.get("abstract"),
            fulltext_excerpt=extract_fulltext_excerpt(full_text),
        )
        labels.update(
            {
                "auto_topic_tags": tagging.topic_tags,
                "auto_method_tags": tagging.method_tags,
                "auto_topic_tag_scores": tagging.topic_scores,
                "auto_method_tag_scores": tagging.method_scores,
                "auto_topic_tag_evidence": tagging.topic_evidence,
                "auto_method_tag_evidence": tagging.method_evidence,
            }
        )
        record["labels"] = labels


def _quality_metrics(page_texts: list[str], full_text: str) -> dict[str, Any]:
    char_count = len(full_text)
    words = re.findall(r"\b\w+\b", full_text, flags=re.UNICODE)
    word_count = len(words)
    page_count = len(page_texts)
    empty_pages = sum(1 for page in page_texts if not page)
    single_letter_words = sum(1 for word in words if len(word) == 1)
    weird_chars = re.findall(r"[^A-Za-zА-Яа-я0-9\s.,;:!?()\[\]\"'/%\-]", full_text)
    weird_ratio = len(weird_chars) / max(char_count, 1)
    single_letter_ratio = single_letter_words / max(word_count, 1)
    sparse_pages = word_count / max(page_count, 1)
    suspected_ocr_noise = weird_ratio > 0.1 or single_letter_ratio > 0.35 or sparse_pages < 20
    return {
        "char_count": char_count,
        "word_count": word_count,
        "page_count": page_count,
        "empty_pages": empty_pages,
        "suspected_ocr_noise": suspected_ocr_noise,
    }
