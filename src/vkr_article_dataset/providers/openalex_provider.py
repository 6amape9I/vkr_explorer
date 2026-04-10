from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from ..config import Settings
from ..http import HttpClient
from ..models import ArticleSeed, ProviderResult
from ..utils import extract_doi, normalize_whitespace, slugify_title


OPENALEX_WORKS_URL = "https://api.openalex.org/works"
OPENALEX_TITLE_MATCH_THRESHOLD = 0.72


class OpenAlexProvider:
    provider_name = "openalex"

    def __init__(self, http_client: HttpClient, settings: Settings) -> None:
        self.http_client = http_client
        self.settings = settings
        self.last_resolution_note: str | None = None

    def resolve(self, seed: ArticleSeed) -> ProviderResult | None:
        self.last_resolution_note = None
        doi = seed.doi or extract_doi(seed.url)
        if doi:
            return self._resolve_by_doi(doi)
        if seed.title:
            return self._resolve_by_title(seed)
        self.last_resolution_note = "missing title and doi for OpenAlex lookup"
        return None

    def _resolve_by_doi(self, doi: str) -> ProviderResult | None:
        params = self._base_params()
        params["filter"] = f"doi:{doi.lower()}"
        data = self.http_client.get_json(OPENALEX_WORKS_URL, params=params)
        results = data.get("results") or []
        if not results:
            self.last_resolution_note = f"no OpenAlex work found for DOI {doi.lower()}"
            return None
        work = results[0]
        return self._to_result(
            work=work,
            confidence=0.99,
            match_details={
                "matched_by": "doi",
                "strategy": "exact_doi",
            },
        )

    def _resolve_by_title(self, seed: ArticleSeed) -> ProviderResult | None:
        params = self._base_params()
        params["search"] = seed.title
        params["per-page"] = 10
        data = self.http_client.get_json(OPENALEX_WORKS_URL, params=params)
        results = data.get("results") or []
        if not results:
            self.last_resolution_note = f"no OpenAlex search results for title {seed.title!r}"
            return None

        scored = sorted(
            (self._score_title_candidate(seed, candidate) for candidate in results),
            key=lambda item: item["confidence"],
            reverse=True,
        )
        best = scored[0]
        if best["confidence"] < OPENALEX_TITLE_MATCH_THRESHOLD:
            self.last_resolution_note = (
                "rejected low-confidence OpenAlex title match "
                f"(best_score={best['confidence']:.2f}, best_title={best['title']!r})"
            )
            return None

        return self._to_result(
            work=best["work"],
            confidence=best["confidence"],
            match_details={
                "matched_by": "title_rerank",
                "strategy": "topn_rerank",
                "title_similarity": best["title_similarity"],
                "token_overlap": best["token_overlap"],
                "year_score": best["year_score"],
                "author_score": best["author_score"],
                "completeness_bonus": best["completeness_bonus"],
                "accepted_confidence": best["confidence"],
                "considered_candidates": [
                    {
                        "title": item["title"],
                        "confidence": item["confidence"],
                        "publication_year": item["work"].get("publication_year"),
                        "first_author_surname": item["first_author_surname"],
                    }
                    for item in scored[:3]
                ],
            },
        )

    def _score_title_candidate(self, seed: ArticleSeed, work: dict[str, Any]) -> dict[str, Any]:
        wanted = slugify_title(seed.title) or ""
        candidate_title = normalize_whitespace(work.get("display_name")) or ""
        candidate_slug = slugify_title(candidate_title) or ""
        title_similarity = SequenceMatcher(None, wanted, candidate_slug).ratio() if wanted and candidate_slug else 0.0
        token_overlap = _token_overlap(wanted, candidate_slug)

        score = 0.4 * title_similarity + 0.25 * token_overlap
        if wanted and candidate_slug == wanted:
            score += 0.25

        seed_year = _seed_publication_year(seed)
        work_year = work.get("publication_year")
        year_score = 0.0
        if seed_year is not None and work_year is not None:
            if work_year == seed_year:
                year_score = 0.15
            elif abs(work_year - seed_year) == 1:
                year_score = 0.05
            else:
                year_score = -0.15
            score += year_score

        seed_surname = _seed_first_author_surname(seed)
        candidate_surname = _first_author_surname(work)
        author_score = 0.0
        if seed_surname and candidate_surname:
            if candidate_surname == seed_surname:
                author_score = 0.15
            else:
                author_score = -0.08
            score += author_score

        completeness_bonus = 0.0
        if work.get("doi"):
            completeness_bonus += 0.05
        if _best_pdf_url(work):
            completeness_bonus += 0.02
        if work.get("abstract_inverted_index"):
            completeness_bonus += 0.03
        score += completeness_bonus

        confidence = max(0.0, min(round(score, 4), 0.99))
        return {
            "work": work,
            "title": candidate_title,
            "title_similarity": round(title_similarity, 4),
            "token_overlap": round(token_overlap, 4),
            "year_score": year_score,
            "author_score": author_score,
            "completeness_bonus": completeness_bonus,
            "confidence": confidence,
            "first_author_surname": candidate_surname,
        }

    def _to_result(
        self,
        *,
        work: dict[str, Any],
        confidence: float,
        match_details: dict[str, Any] | None = None,
    ) -> ProviderResult:
        return openalex_work_to_result(
            work=work,
            confidence=confidence,
            match_details=match_details,
        )

    def result_from_work(
        self,
        *,
        work: dict[str, Any],
        confidence: float,
        match_details: dict[str, Any] | None = None,
    ) -> ProviderResult:
        return openalex_work_to_result(
            work=work,
            confidence=confidence,
            match_details=match_details,
        )

    def _base_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if self.settings.contact_email:
            params["mailto"] = self.settings.contact_email
        if self.settings.openalex_api_key:
            params["api_key"] = self.settings.openalex_api_key
        return params


def openalex_work_to_result(
    *,
    work: dict[str, Any],
    confidence: float,
    match_details: dict[str, Any] | None = None,
) -> ProviderResult:
        title = normalize_whitespace(work.get("display_name"))
        abstract = _openalex_abstract_to_text(work.get("abstract_inverted_index"))
        source = (work.get("primary_location") or {}).get("source") or {}
        payload = {
            "title": title,
            "abstract": abstract,
            "authors": [
                author.get("author", {}).get("display_name")
                for author in (work.get("authorships") or [])
                if author.get("author", {}).get("display_name")
            ],
            "publication_date": work.get("publication_date"),
            "publication_year": work.get("publication_year"),
            "venue": source.get("display_name") or work.get("host_venue", {}).get("display_name"),
            "document_type": work.get("type"),
            "doi": _strip_doi_prefix(work.get("doi")),
            "arxiv_id": _extract_arxiv_id_from_locations(work),
            "landing_page_url": _best_landing_page(work),
            "pdf_url": _best_pdf_url(work),
            "language": work.get("language"),
            "is_open_access": (work.get("open_access") or {}).get("is_oa"),
            "citation_count": work.get("cited_by_count"),
            "openalex_id": work.get("id"),
        }
        return ProviderResult(
            provider_name="openalex",
            source_id=work.get("id"),
            confidence=confidence,
            payload=payload,
            raw=work,
            match_details=match_details or {},
        )


def _seed_publication_year(seed: ArticleSeed) -> int | None:
    value = seed.extra.get("publication_year")
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _seed_first_author_surname(seed: ArticleSeed) -> str | None:
    surname = seed.extra.get("first_author_surname")
    if isinstance(surname, str) and surname.strip():
        return surname.strip().lower()
    authors = seed.extra.get("authors")
    if isinstance(authors, str):
        authors = [part.strip() for part in authors.split(";") if part.strip()]
    if isinstance(authors, list) and authors:
        return authors[0].split()[-1].lower()
    return None


def _first_author_surname(work: dict[str, Any]) -> str | None:
    authorships = work.get("authorships") or []
    if not authorships:
        return None
    display_name = (authorships[0].get("author") or {}).get("display_name")
    if not display_name:
        return None
    return display_name.split()[-1].lower()


def _token_overlap(left: str, right: str) -> float:
    left_tokens = {token for token in left.split() if token}
    right_tokens = {token for token in right.split() if token}
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _openalex_abstract_to_text(index: dict[str, list[int]] | None) -> str | None:
    if not index:
        return None
    tokens: list[tuple[int, str]] = []
    for word, positions in index.items():
        for pos in positions:
            tokens.append((pos, word))
    if not tokens:
        return None
    tokens.sort(key=lambda item: item[0])
    return normalize_whitespace(" ".join(word for _, word in tokens))


def _strip_doi_prefix(value: str | None) -> str | None:
    if not value:
        return None
    return value.removeprefix("https://doi.org/").strip() or None


def _best_landing_page(work: dict[str, Any]) -> str | None:
    primary_location = work.get("primary_location") or {}
    return primary_location.get("landing_page_url") or primary_location.get("pdf_url")


def _best_pdf_url(work: dict[str, Any]) -> str | None:
    primary_location = work.get("primary_location") or {}
    return primary_location.get("pdf_url")


def _extract_arxiv_id_from_locations(work: dict[str, Any]) -> str | None:
    locations = work.get("locations") or []
    for location in locations:
        landing = location.get("landing_page_url") or ""
        if "arxiv.org/abs/" in landing:
            return landing.rsplit("/", 1)[-1].split("v")[0]
    return None
