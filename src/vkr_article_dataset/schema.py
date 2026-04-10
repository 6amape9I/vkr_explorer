from __future__ import annotations

from .utils import slugify_title
from .utils import stable_record_id


SCHEMA_VERSION = "2"

FULLTEXT_STATUS_NOT_ATTEMPTED = "not_attempted"
FULLTEXT_STATUS_DOWNLOADED = "downloaded"
FULLTEXT_STATUS_PARSED = "parsed"
FULLTEXT_STATUS_FAILED = "failed"

FULLTEXT_STATUSES = {
    FULLTEXT_STATUS_NOT_ATTEMPTED,
    FULLTEXT_STATUS_DOWNLOADED,
    FULLTEXT_STATUS_PARSED,
    FULLTEXT_STATUS_FAILED,
}


def canonical_id(
    doi: str | None,
    arxiv_id: str | None,
    openalex_id: str | None,
    title: str | None = None,
    *,
    authors: list[str] | None = None,
    publication_year: int | None = None,
) -> tuple[str | None, str | None, str]:
    if doi:
        return f"doi:{doi}", "doi", "canonical id derived from DOI"
    if arxiv_id:
        return f"arxiv:{arxiv_id}", "arxiv", "canonical id derived from arXiv id"
    if openalex_id:
        return (
            f"openalex:{openalex_id.rsplit('/', 1)[-1]}",
            "openalex",
            "canonical id derived from OpenAlex id",
        )
    title_slug = slugify_title(title)
    if title_slug:
        first_author = (authors or [None])[0]
        digest = stable_record_id(title_slug, first_author, str(publication_year) if publication_year else None)
        return f"hash:{digest.removeprefix('art_')}", "merged", "canonical id derived from title + author + year hash"
    return None, None, "canonical id unavailable"
