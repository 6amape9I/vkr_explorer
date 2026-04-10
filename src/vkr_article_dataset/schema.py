from __future__ import annotations

from .utils import slugify_title


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
) -> str | None:
    if doi:
        return f"doi:{doi}"
    if arxiv_id:
        return f"arxiv:{arxiv_id}"
    if openalex_id:
        return f"openalex:{openalex_id.rsplit('/', 1)[-1]}"
    title_slug = slugify_title(title)
    if title_slug:
        return f"title:{title_slug}"
    return None
