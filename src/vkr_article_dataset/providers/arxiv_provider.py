from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from ..http import HttpClient
from ..models import ArticleSeed, ProviderResult
from ..utils import extract_arxiv_id, normalize_whitespace


ARXIV_API_URL = "http://export.arxiv.org/api/query"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


class ArxivProvider:
    def __init__(self, http_client: HttpClient) -> None:
        self.http_client = http_client

    def resolve(self, seed: ArticleSeed) -> ProviderResult | None:
        arxiv_id = seed.arxiv_id or extract_arxiv_id(seed.url)
        if not arxiv_id:
            return None

        xml_text = self.http_client.get_text(
            ARXIV_API_URL,
            params={"id_list": arxiv_id},
            arxiv=True,
        )
        entry = self._parse_first_entry(xml_text)
        if not entry:
            return None

        payload = {
            "title": normalize_whitespace(entry.get("title")),
            "abstract": normalize_whitespace(entry.get("summary")),
            "authors": entry.get("authors") or [],
            "publication_date": entry.get("published"),
            "publication_year": _year_from_date(entry.get("published")),
            "venue": "arXiv",
            "document_type": "preprint",
            "doi": entry.get("doi"),
            "arxiv_id": arxiv_id,
            "landing_page_url": entry.get("id") or f"https://arxiv.org/abs/{arxiv_id}",
            "pdf_url": entry.get("pdf_url") or f"https://arxiv.org/pdf/{arxiv_id}.pdf",
            "language": "en",
            "is_open_access": True,
            "citation_count": None,
            "openalex_id": None,
        }
        return ProviderResult(
            provider_name="arxiv",
            source_id=arxiv_id,
            confidence=0.99,
            payload=payload,
            raw=entry,
        )

    def _parse_first_entry(self, xml_text: str) -> dict[str, Any] | None:
        root = ET.fromstring(xml_text)
        entry = root.find("atom:entry", ATOM_NS)
        if entry is None:
            return None

        authors = [
            normalize_whitespace(author.findtext("atom:name", default="", namespaces=ATOM_NS))
            for author in entry.findall("atom:author", ATOM_NS)
        ]
        authors = [author for author in authors if author]

        pdf_url = None
        for link in entry.findall("atom:link", ATOM_NS):
            if link.attrib.get("title") == "pdf":
                pdf_url = link.attrib.get("href")
                break

        doi = None
        doi_node = entry.find("arxiv:doi", ATOM_NS)
        if doi_node is not None:
            doi = normalize_whitespace(doi_node.text)

        return {
            "id": normalize_whitespace(entry.findtext("atom:id", default="", namespaces=ATOM_NS)),
            "title": normalize_whitespace(entry.findtext("atom:title", default="", namespaces=ATOM_NS)),
            "summary": normalize_whitespace(entry.findtext("atom:summary", default="", namespaces=ATOM_NS)),
            "published": normalize_whitespace(entry.findtext("atom:published", default="", namespaces=ATOM_NS)),
            "updated": normalize_whitespace(entry.findtext("atom:updated", default="", namespaces=ATOM_NS)),
            "authors": authors,
            "doi": doi,
            "categories": [cat.attrib.get("term") for cat in entry.findall("atom:category", ATOM_NS)],
            "pdf_url": pdf_url,
        }


def _year_from_date(value: str | None) -> int | None:
    if not value or len(value) < 4:
        return None
    try:
        return int(value[:4])
    except ValueError:
        return None
