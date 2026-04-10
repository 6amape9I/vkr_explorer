from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone


DOI_URL_RE = re.compile(r"https?://(?:dx\.)?doi\.org/(?P<doi>10\.[^\s]+)", re.IGNORECASE)
ARXIV_URL_RE = re.compile(
    r"https?://arxiv\.org/(?:abs|pdf)/(?P<arxiv_id>[0-9]{4}\.[0-9]{4,5})(?:v\d+)?(?:\.pdf)?",
    re.IGNORECASE,
)
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
ARXIV_ID_RE = re.compile(r"^[0-9]{4}\.[0-9]{4,5}(?:v\d+)?$", re.IGNORECASE)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_whitespace(text: str | None) -> str | None:
    if text is None:
        return None
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def slugify_title(text: str | None) -> str | None:
    text = normalize_whitespace(text)
    if not text:
        return None
    lowered = text.lower()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip() or None


def stable_record_id(*parts: str | None) -> str:
    basis = "|".join(part.strip().lower() for part in parts if part and part.strip())
    if not basis:
        basis = "empty"
    digest = hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]
    return f"art_{digest}"


def extract_doi(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    match = DOI_URL_RE.search(value)
    if match:
        return match.group("doi")
    match = DOI_RE.search(value)
    if match:
        return match.group(0)
    return None


def extract_arxiv_id(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    match = ARXIV_URL_RE.search(value)
    if match:
        return match.group("arxiv_id")
    if ARXIV_ID_RE.match(value):
        return value.split("v")[0]
    return None


def parse_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "да"}
    return default
