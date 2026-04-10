from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .io_utils import infer_data_root


@dataclass(slots=True)
class StoredPdf:
    path: Path
    ref: str
    sha256: str


class DatasetStorage:
    def __init__(self, data_root: str | Path) -> None:
        self.data_root = Path(data_root)

    @classmethod
    def from_dataset_path(cls, dataset_path: str | Path) -> "DatasetStorage":
        return cls(infer_data_root(dataset_path))

    def save_pdf(self, record_id: str, content: bytes) -> StoredPdf:
        pdf_dir = self.data_root / "pdfs"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = pdf_dir / f"{record_id}.pdf"
        pdf_path.write_bytes(content)
        return StoredPdf(
            path=pdf_path,
            ref=pdf_path.relative_to(self.data_root).as_posix(),
            sha256=_sha256_bytes(content),
        )

    def save_fulltext(self, record_id: str, payload: dict[str, Any]) -> str:
        fulltext_dir = self.data_root / "fulltext"
        fulltext_dir.mkdir(parents=True, exist_ok=True)
        fulltext_path = fulltext_dir / f"{record_id}.json.gz"
        with gzip.open(fulltext_path, "wt", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
        return fulltext_path.relative_to(self.data_root).as_posix()

    def save_raw_payload(self, provider_name: str, record_id: str, payload: dict[str, Any]) -> str:
        provider_dir = self.data_root / "raw" / provider_name
        provider_dir.mkdir(parents=True, exist_ok=True)
        payload_path = provider_dir / f"{record_id}.json"
        with payload_path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        return payload_path.relative_to(self.data_root).as_posix()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
