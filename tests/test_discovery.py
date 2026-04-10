import json
import sys

from vkr_article_dataset import cli
from vkr_article_dataset.discovery import deduplicate_discovery_candidates, run_discovery_and_label, run_label_candidates
from vkr_article_dataset.search_sources import (
    DiscoveryQuery,
    OpenAlexSearchSource,
    SearchCandidate,
    SearchPage,
    load_discovery_queries,
)
from vkr_article_dataset.train_baseline import run_baseline_pipeline


class FakeSearchSource:
    def __init__(self, candidates_by_query: dict[str, list[SearchCandidate]], pages_by_query: dict[str, list[SearchPage]]) -> None:
        self.candidates_by_query = candidates_by_query
        self.pages_by_query = pages_by_query

    def search(self, query: DiscoveryQuery):
        return self.candidates_by_query.get(query.query, []), self.pages_by_query.get(query.query, [])


class FakeHttpClient:
    def __init__(self, responses: list[dict] | None = None) -> None:
        self.responses = responses or []
        self.calls: list[tuple[str, dict]] = []

    def get_json(self, url: str, params=None, **kwargs):
        del kwargs
        self.calls.append((url, dict(params or {})))
        if not self.responses:
            return {"results": []}
        return self.responses.pop(0)


class FakeSettings:
    contact_email = None
    openalex_api_key = None


def _normalized_record(
    *,
    record_id: str,
    canonical_id: str | None,
    label: str,
    title: str,
    abstract: str,
) -> dict:
    return {
        "record_id": record_id,
        "identifiers": {"canonical_id": canonical_id},
        "bibliography": {"title": title},
        "content": {"abstract": abstract},
        "labels": {"gold_label": label},
    }


def _write_jsonl(path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _training_records() -> list[dict]:
    rows: list[dict] = []
    for index in range(12):
        rows.append(
            _normalized_record(
                record_id=f"rel-{index}",
                canonical_id=f"canon-rel-{index // 2}",
                label="relevant",
                title=f"Blockchain federated learning system {index}",
                abstract="Federated learning with blockchain verification and smart contracts",
            )
        )
    for index in range(12):
        rows.append(
            _normalized_record(
                record_id=f"irr-{index}",
                canonical_id=f"canon-irr-{index // 2}",
                label="irrelevant",
                title=f"Computer vision benchmark {index}",
                abstract="Image classification benchmark with convolutional networks",
            )
        )
    return rows


def _build_baseline_artifacts(tmp_path):
    input_path = tmp_path / "articles.jsonl"
    workdir = tmp_path / "baseline"
    _write_jsonl(input_path, _training_records())
    run_baseline_pipeline(input_path=input_path, workdir=workdir, text_mode="title_abstract")
    return workdir / "logreg" / "model.joblib", workdir / "logreg" / "vectorizer.joblib"


def _provider_result(*, title: str, abstract: str, doi: str | None, openalex_id: str, year: int = 2024):
    return {
        "provider_name": "openalex",
        "source_id": openalex_id,
        "confidence": 0.9,
        "payload": {
            "title": title,
            "abstract": abstract,
            "authors": ["Alice Smith", "Bob Jones"],
            "publication_year": year,
            "publication_date": f"{year}-01-01",
            "venue": "Test Venue",
            "document_type": "article",
            "doi": doi,
            "arxiv_id": None,
            "landing_page_url": f"https://example.com/{openalex_id.rsplit('/', 1)[-1]}",
            "pdf_url": f"https://example.com/{openalex_id.rsplit('/', 1)[-1]}.pdf",
            "language": "en",
            "is_open_access": True,
            "citation_count": 5,
            "openalex_id": openalex_id,
        },
        "raw": {"id": openalex_id},
        "match_details": {"matched_by": "discovery_search"},
    }


def _search_candidate(*, query: str, rank: int, title: str, abstract: str, doi: str | None, openalex_id: str):
    from vkr_article_dataset.models import ProviderResult

    payload = _provider_result(
        title=title,
        abstract=abstract,
        doi=doi,
        openalex_id=openalex_id,
    )
    provider_result = ProviderResult(
        provider_name=payload["provider_name"],
        source_id=payload["source_id"],
        confidence=payload["confidence"],
        payload=payload["payload"],
        raw=payload["raw"],
        match_details=payload["match_details"],
    )
    return SearchCandidate(
        provider_result=provider_result,
        query=query,
        search_source="openalex",
        search_rank=rank,
        retrieved_at="2026-04-10T12:00:00Z",
        mode="search",
        source_info={"page": 1, "page_rank": rank},
    )


def test_load_discovery_queries_supports_text_and_jsonl(tmp_path) -> None:
    txt_path = tmp_path / "queries.txt"
    txt_path.write_text("# comment\nblockchain federated learning\n\nsmart contracts\n", encoding="utf-8")
    jsonl_path = tmp_path / "queries.jsonl"
    jsonl_path.write_text(
        '{"query":"one","source":"openalex","max_results":5}\n'
        '{"query":"two","mode":"title_abstract"}\n',
        encoding="utf-8",
    )

    text_queries = load_discovery_queries(txt_path, default_max_results=10)
    jsonl_queries = load_discovery_queries(jsonl_path, default_max_results=10)

    assert [query.query for query in text_queries] == ["blockchain federated learning", "smart contracts"]
    assert text_queries[0].mode == "search"
    assert jsonl_queries[0].max_results == 5
    assert jsonl_queries[1].mode == "title_abstract"


def test_openalex_search_source_mode_mapping_and_pagination() -> None:
    first_page_results = []
    for index in range(200):
        first_page_results.append(
            {
                "id": f"https://openalex.org/W{index + 1}",
                "display_name": f"Work {index + 1}",
                "publication_year": 2024,
                "publication_date": "2024-01-01",
                "authorships": [{"author": {"display_name": f"Author {index + 1}"}}],
                "primary_location": {
                    "landing_page_url": f"https://example.com/{index + 1}",
                    "pdf_url": None,
                    "source": {"display_name": "Venue"},
                },
            }
        )
    http_client = FakeHttpClient(
        responses=[
            {"results": first_page_results},
            {
                "results": [
                    {
                        "id": "https://openalex.org/W201",
                        "display_name": "Work 201",
                        "publication_year": 2024,
                        "publication_date": "2024-01-01",
                        "authorships": [{"author": {"display_name": "Dan Poe"}}],
                        "primary_location": {"landing_page_url": "https://example.com/201", "pdf_url": None, "source": {"display_name": "Venue"}},
                    }
                ]
            },
        ]
    )
    source = OpenAlexSearchSource(http_client=http_client, settings=FakeSettings())

    candidates, pages = source.search(
        DiscoveryQuery(query="federated learning", mode="title_abstract", max_results=201, query_index=1)
    )

    assert len(candidates) == 201
    assert len(pages) == 2
    assert http_client.calls[0][1]["filter"] == "title_and_abstract.search:federated learning"
    assert http_client.calls[0][1]["page"] == 1
    assert http_client.calls[1][1]["page"] == 2


def test_deduplicate_discovery_candidates_merges_matched_queries() -> None:
    duplicate_candidates = [
        {
            "run_id": "run_001",
            "query": "blockchain federated learning",
            "matched_queries": ["blockchain federated learning"],
            "search_source": "openalex",
            "search_rank": 3,
            "retrieved_at": "2026-04-10T12:00:00Z",
            "search_matches": [{"query": "blockchain federated learning", "mode": "search"}],
            "record": {
                "record_id": "art_1",
                "identifiers": {"canonical_id": "doi:10.1000/example", "doi": "10.1000/example"},
                "bibliography": {"title": "Blockchain Federated Learning", "authors": ["Alice Smith"], "publication_year": 2024, "venue": "Venue"},
                "content": {"abstract": "Federated learning with blockchain", "language": "en"},
                "links": {"landing_page_url": "https://example.com/1", "pdf_url": "https://example.com/1.pdf"},
                "quality": {"has_abstract": True, "has_pdf_url": True, "citation_count": 5},
                "sources": {"primary_source": "openalex", "available_sources": ["openalex"], "source_candidates_count": 1},
                "source_candidates": [],
                "merge_decisions": {},
            },
        },
        {
            "run_id": "run_001",
            "query": "smart contracts",
            "matched_queries": ["smart contracts"],
            "search_source": "openalex",
            "search_rank": 1,
            "retrieved_at": "2026-04-10T12:01:00Z",
            "search_matches": [{"query": "smart contracts", "mode": "search"}],
            "record": {
                "record_id": "art_2",
                "identifiers": {"canonical_id": "doi:10.1000/example", "doi": "10.1000/example"},
                "bibliography": {"title": "Blockchain Federated Learning", "authors": ["Alice Smith"], "publication_year": 2024, "venue": "Venue"},
                "content": {"abstract": "Federated learning with blockchain", "language": "en"},
                "links": {"landing_page_url": "https://example.com/1", "pdf_url": "https://example.com/1.pdf"},
                "quality": {"has_abstract": True, "has_pdf_url": True, "citation_count": 5},
                "sources": {"primary_source": "openalex", "available_sources": ["openalex"], "source_candidates_count": 1},
                "source_candidates": [],
                "merge_decisions": {},
            },
        },
    ]

    deduplicated = deduplicate_discovery_candidates(duplicate_candidates)

    assert len(deduplicated) == 1
    assert deduplicated[0]["query"] == "smart contracts"
    assert deduplicated[0]["matched_queries"] == ["blockchain federated learning", "smart contracts"]
    assert "labels" not in deduplicated[0]["record"]


def test_discover_and_label_writes_full_run_outputs(tmp_path, monkeypatch) -> None:
    model_path, vectorizer_path = _build_baseline_artifacts(tmp_path)
    queries_path = tmp_path / "queries.txt"
    queries_path.write_text("blockchain federated learning\nsmart contracts\n", encoding="utf-8")
    output_dir = tmp_path / "discovery_run"

    source = FakeSearchSource(
        candidates_by_query={
            "blockchain federated learning": [
                _search_candidate(
                    query="blockchain federated learning",
                    rank=1,
                    title="Blockchain Federated Learning via Smart Contracts",
                    abstract="Federated learning with blockchain smart contracts and verification",
                    doi="10.1000/discovery-1",
                    openalex_id="https://openalex.org/W1",
                )
            ],
            "smart contracts": [
                _search_candidate(
                    query="smart contracts",
                    rank=1,
                    title="Blockchain Federated Learning via Smart Contracts",
                    abstract="Federated learning with blockchain smart contracts and verification",
                    doi="10.1000/discovery-1",
                    openalex_id="https://openalex.org/W1",
                ),
                _search_candidate(
                    query="smart contracts",
                    rank=2,
                    title="Vision dataset benchmarking",
                    abstract="Image classification benchmark with convolutional networks",
                    doi="10.1000/discovery-2",
                    openalex_id="https://openalex.org/W2",
                ),
            ],
        },
        pages_by_query={
            "blockchain federated learning": [SearchPage(page_number=1, payload={"results": [1]}, results_count=1)],
            "smart contracts": [SearchPage(page_number=1, payload={"results": [1, 2]}, results_count=2)],
        },
    )
    monkeypatch.setattr(
        "vkr_article_dataset.discovery.build_search_sources",
        lambda settings, http_client: {"openalex": source},
    )

    manifest = run_discovery_and_label(
        queries_path=queries_path,
        output_dir=output_dir,
        settings=object(),
        http_client=FakeHttpClient(),
        model_path=model_path,
        vectorizer_path=vectorizer_path,
        default_source="openalex",
        max_results_per_query=5,
        relevant_threshold=0.65,
    )

    assert manifest["raw_candidates"] == 3
    assert manifest["deduplicated_candidates"] == 2
    assert (output_dir / "manifest.json").exists()
    assert (output_dir / "candidates.jsonl").exists()
    assert (output_dir / "candidates.csv").exists()
    assert (output_dir / "predictions.jsonl").exists()
    assert (output_dir / "predictions.csv").exists()
    assert (output_dir / "relevant_predictions.jsonl").exists()
    assert (output_dir / "relevant_predictions.csv").exists()
    assert (output_dir / "logs" / "discovery.log").exists()
    assert len(list((output_dir / "raw_search").glob("*.json"))) == 2
    predictions = [json.loads(line) for line in (output_dir / "predictions.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(item["predicted_label"] == "predicted_relevant" for item in predictions)
    assert all("prediction_reason" in item for item in predictions)


def test_label_candidates_predict_only_and_rejects_nonempty_output_dir(tmp_path) -> None:
    model_path, vectorizer_path = _build_baseline_artifacts(tmp_path)
    candidates_path = tmp_path / "candidates.jsonl"
    candidates = [
        {
            "run_id": "run_001",
            "query": "blockchain federated learning",
            "matched_queries": ["blockchain federated learning"],
            "search_source": "openalex",
            "search_rank": 1,
            "retrieved_at": "2026-04-10T12:00:00Z",
            "search_matches": [{"query": "blockchain federated learning", "mode": "search"}],
            "record": {
                "record_id": "art_prediction",
                "identifiers": {"canonical_id": "doi:10.1000/discovery"},
                "bibliography": {"title": "Blockchain Federated Learning", "publication_year": 2024, "venue": "Venue"},
                "content": {"abstract": "Federated learning with blockchain and smart contracts"},
                "links": {"landing_page_url": "https://example.com", "pdf_url": "https://example.com/p.pdf"},
                "quality": {"has_abstract": True},
            },
        }
    ]
    _write_jsonl(candidates_path, candidates)

    output_dir = tmp_path / "relabel_run"
    manifest = run_label_candidates(
        input_path=candidates_path,
        output_dir=output_dir,
        model_path=model_path,
        vectorizer_path=vectorizer_path,
        relevant_threshold=0.65,
    )

    assert manifest["mode"] == "label_candidates"
    assert (output_dir / "predictions.csv").exists()
    assert (output_dir / "candidates.csv").exists()

    blocked_dir = tmp_path / "nonempty"
    blocked_dir.mkdir()
    (blocked_dir / "keep.txt").write_text("busy", encoding="utf-8")
    try:
        run_label_candidates(
            input_path=candidates_path,
            output_dir=blocked_dir,
            model_path=model_path,
            vectorizer_path=vectorizer_path,
            relevant_threshold=0.65,
        )
    except ValueError as exc:
        assert "new or empty" in str(exc)
    else:
        raise AssertionError("Expected ValueError for non-empty discovery output dir")


def test_discovery_cli_commands_smoke(tmp_path, monkeypatch, capsys) -> None:
    model_path, vectorizer_path = _build_baseline_artifacts(tmp_path)
    candidates_path = tmp_path / "candidates.jsonl"
    _write_jsonl(
        candidates_path,
        [
            {
                "run_id": "run_001",
                "query": "blockchain federated learning",
                "matched_queries": ["blockchain federated learning"],
                "search_source": "openalex",
                "search_rank": 1,
                "retrieved_at": "2026-04-10T12:00:00Z",
                "search_matches": [{"query": "blockchain federated learning", "mode": "search"}],
                "record": {
                    "record_id": "art_prediction",
                    "identifiers": {"canonical_id": "doi:10.1000/discovery"},
                    "bibliography": {"title": "Blockchain Federated Learning", "publication_year": 2024, "venue": "Venue"},
                    "content": {"abstract": "Federated learning with blockchain and smart contracts"},
                    "links": {"landing_page_url": "https://example.com", "pdf_url": "https://example.com/p.pdf"},
                    "quality": {"has_abstract": True},
                },
            }
        ],
    )
    output_dir = tmp_path / "cli_relabel"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "vkr-dataset",
            "label-candidates",
            "--input",
            str(candidates_path),
            "--model",
            str(model_path),
            "--vectorizer",
            str(vectorizer_path),
            "--output-dir",
            str(output_dir),
            "--relevant-threshold",
            "0.65",
        ],
    )

    exit_code = cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["predicted_relevant"] + payload["predicted_irrelevant"] == 1
