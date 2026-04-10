from vkr_article_dataset.merge import RecordMerger
from vkr_article_dataset.models import ArticleSeed, ProviderResult, ResolutionResult


def _seed() -> ArticleSeed:
    return ArticleSeed(
        input_position=1,
        title="Advancing blockchain based federated learning through verifiable off chain computations",
        arxiv_id="2206.11641",
    )


def _resolution(*candidates: ProviderResult) -> ResolutionResult:
    return ResolutionResult(
        candidates=list(candidates),
        attempted=["arxiv", "openalex"],
        successful=[candidate.provider_name for candidate in candidates],
    )


def test_merge_prefers_structured_title_when_candidates_exist() -> None:
    merger = RecordMerger()
    arxiv = ProviderResult(
        provider_name="arxiv",
        source_id="2206.11641",
        confidence=0.99,
        payload={
            "title": "advancing blockchain based federated learning through verifiable off chain computations",
            "authors": ["Jonathan Heiss"],
            "arxiv_id": "2206.11641",
        },
        raw={},
    )
    openalex = ProviderResult(
        provider_name="openalex",
        source_id="https://openalex.org/W123",
        confidence=0.91,
        payload={
            "title": "Advancing Blockchain-Based Federated Learning Through Verifiable Off-Chain Computations",
            "authors": ["Jonathan Heiss", "Elias Grunewald"],
            "doi": "10.1000/example",
            "openalex_id": "https://openalex.org/W123",
        },
        raw={},
    )

    record, _ = merger.merge(_seed(), _resolution(arxiv, openalex))

    assert record["bibliography"]["title"] == openalex.payload["title"]
    assert record["merge_decisions"]["bibliography.title"]["winner"] == "openalex"


def test_merge_prefers_longer_nonempty_abstract() -> None:
    merger = RecordMerger()
    arxiv = ProviderResult(
        provider_name="arxiv",
        source_id="2206.11641",
        confidence=0.99,
        payload={
            "title": "Paper",
            "abstract": "This is a longer abstract with actual detail about the method and evaluation setup.",
            "arxiv_id": "2206.11641",
        },
        raw={},
    )
    openalex = ProviderResult(
        provider_name="openalex",
        source_id="https://openalex.org/W123",
        confidence=0.95,
        payload={
            "title": "Paper",
            "abstract": "Short abstract.",
            "doi": "10.1000/example",
            "openalex_id": "https://openalex.org/W123",
        },
        raw={},
    )

    record, _ = merger.merge(_seed(), _resolution(arxiv, openalex))

    assert record["content"]["abstract"] == arxiv.payload["abstract"]
    assert record["merge_decisions"]["content.abstract"]["winner"] == "arxiv"


def test_merge_builds_primary_source_and_decision_trace() -> None:
    merger = RecordMerger()
    arxiv = ProviderResult(
        provider_name="arxiv",
        source_id="2206.11641",
        confidence=0.99,
        payload={
            "title": "Paper",
            "abstract": "Long abstract from arxiv.",
            "authors": ["Jonathan Heiss"],
            "pdf_url": "https://arxiv.org/pdf/2206.11641.pdf",
            "arxiv_id": "2206.11641",
        },
        raw={},
        match_details={"matched_by": "arxiv_id"},
    )
    openalex = ProviderResult(
        provider_name="openalex",
        source_id="https://openalex.org/W123",
        confidence=0.95,
        payload={
            "title": "Paper",
            "abstract": "Short abstract.",
            "authors": ["Jonathan Heiss", "Elias Grunewald"],
            "venue": "OpenAlex Venue",
            "doi": "10.1000/example",
            "citation_count": 42,
            "openalex_id": "https://openalex.org/W123",
        },
        raw={},
        match_details={"matched_by": "doi"},
    )

    record, _ = merger.merge(_seed(), _resolution(arxiv, openalex))

    assert record["sources"]["primary_source"] == "openalex"
    assert set(record["sources"]["available_sources"]) == {"arxiv", "openalex"}
    assert "bibliography.title" in record["merge_decisions"]
    assert record["provenance"]["merge_summary"]["pdf_url_winner"] == "arxiv"
