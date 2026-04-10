# Discovery and Auto-Labeling Plan

## Goal

Implement the final stage of the project: an **open discovery pipeline** that

1. searches for new papers,
2. normalizes them into the internal dataset-compatible representation,
3. applies the trained baseline model,
4. assigns model-based labels,
5. stores model predictions **separately from the clean dataset**,
6. produces detailed logs for traceability.

---

## Core principle

**Do not modify the clean dataset and do not write model predictions into `gold_label`.**

That means:

- `data/normalized/articles.jsonl` — clean corpus
- `data/normalized/articles.reviewed.jsonl` — human-reviewed corpus
- `data/discovery_runs/run_XXX/...` — model-driven discovery outputs

Model predictions must always remain isolated from manually curated labels.

---

## Expected outcome

The project should provide a command like:

```bash
vkr-dataset discover-and-label \
  --queries data/discovery/queries.txt \
  --model artifacts/baseline_run_01/logreg/model.joblib \
  --vectorizer artifacts/baseline_run_01/logreg/vectorizer.joblib \
  --output-dir data/discovery_runs/run_001 \
  --source openalex \
  --max-results-per-query 200 \
  --relevant-threshold 0.65
```

This command should:

- fetch candidate papers from search sources,
- normalize and deduplicate them,
- run inference with the trained baseline classifier,
- save all predictions,
- save only predicted-relevant papers separately,
- generate logs and a run manifest.

---

## Search sources

## Required source

### OpenAlex

Use OpenAlex as the main discovery source.

Support:

- general `search`
- title search
- abstract search
- title+abstract search
- paginated retrieval across multiple pages

The system should support collecting several pages of results for each query and merge them into one candidate pool.

## Optional source

### arXiv

Add optional support for arXiv search for fresh preprints.

This can be implemented as a second source mode, not required for the first working version.

## Optional future source

### Semantic Scholar

Treat Semantic Scholar as an optional expansion source for future recommendation or similar-paper retrieval, not as a first mandatory implementation target.

---

## Query input

Support two query input formats.

### Plain text query file

```text
data/discovery/queries.txt
```

Example:

```text
blockchain federated learning
decentralized federated learning
federated learning off-chain verification
federated learning smart contracts
```

### Extended JSONL query file

```json
{"query": "blockchain federated learning", "source": "openalex", "max_results": 100}
{"query": "federated learning off-chain verification", "source": "openalex", "mode": "title_abstract"}
```

The JSONL format should allow future extensibility.

---

## Required modules

Create the following modules:

```text
src/vkr_article_dataset/discovery.py
src/vkr_article_dataset/search_sources.py
src/vkr_article_dataset/discovery_inference.py
```

Optional additional helper module:

```text
src/vkr_article_dataset/discovery_storage.py
```

---

## Stage 1. Search and collect raw candidates

### Responsibilities

For each query:

1. send the search request to the selected source,
2. fetch candidate papers,
3. save raw search responses separately,
4. normalize candidates into the internal article-compatible format,
5. annotate each candidate with discovery metadata.

### Required candidate metadata

Each candidate should preserve:

- `run_id`
- `query`
- `search_source`
- `search_rank`
- `retrieved_at`
- source-specific search info if available

---

## Stage 2. Per-run storage layout

Each run must create a separate output directory:

```text
data/discovery_runs/run_001/
```

Expected structure:

```text
data/discovery_runs/run_001/
  manifest.json
  queries.jsonl
  raw_search/
    openalex_query_001.json
    openalex_query_002.json
  candidates.jsonl
  candidates.csv
  predictions.jsonl
  predictions.csv
  relevant_predictions.jsonl
  relevant_predictions.csv
  logs/
    discovery.log
```

This separation is mandatory.

---

## Stage 3. Candidate format

### `candidates.jsonl`

This file stores normalized candidate papers **before model prediction**.

Minimal structure:

```json
{
  "run_id": "run_001",
  "query": "blockchain federated learning",
  "search_source": "openalex",
  "search_rank": 12,
  "retrieved_at": "...",
  "matched_queries": [
    "blockchain federated learning"
  ],
  "record": {
    "record_id": "...",
    "identifiers": {...},
    "bibliography": {...},
    "content": {...},
    "links": {...},
    "quality": {...}
  }
}
```

Important:

- this is **not** the clean dataset,
- this is a temporary candidate pool for a discovery run.

---

## Stage 4. Deduplication inside a discovery run

Deduplication is required in two places:

1. within one query result set,
2. across multiple queries inside the same run.

### Dedup rules

Use the same logic as the main pipeline:

- exact dedup by `canonical_id` if available,
- fallback dedup by title/year/author heuristic.

### Multi-query support

If a paper is found by multiple queries, keep one candidate record and store all matching queries:

```json
"matched_queries": [
  "blockchain federated learning",
  "federated learning smart contracts"
]
```

This is important for later analysis and debugging.

---

## Stage 5. Inference with the trained model

Implement inference in:

```text
src/vkr_article_dataset/discovery_inference.py
```

### Inputs

- trained model artifact
- trained vectorizer artifact
- `candidates.jsonl`

### Features

Use the same feature policy as the strict baseline:

- `bibliography.title`
- `content.abstract`
- combined as `title + "\n\n" + abstract`

### Model policy

For the first implementation:

- use **Logistic Regression** as the primary deployed model,
- `Linear SVM` support can be added later as an optional second scorer.

Reason: Logistic Regression provides probabilities and works better with threshold-based discovery.

---

## Stage 6. Prediction format

### Main rule

Model output must be stored separately from the clean dataset and separately from `gold_label`.

### `predictions.jsonl`

Minimal record structure:

```json
{
  "run_id": "run_001",
  "record_id": "art_xxx",
  "canonical_id": "doi:...",
  "query": "blockchain federated learning",
  "matched_queries": [
    "blockchain federated learning",
    "federated learning smart contracts"
  ],
  "search_source": "openalex",
  "search_rank": 12,
  "title": "...",
  "abstract": "...",
  "predicted_label": "predicted_relevant",
  "predicted_binary": 1,
  "score": 0.8123,
  "threshold": 0.65,
  "model_name": "logreg",
  "model_version": "baseline_run_01",
  "text_mode": "title_abstract",
  "prediction_reason": {
    "top_positive_terms": ["blockchain", "federated learning", "smart contract"],
    "top_negative_terms": []
  }
}
```

### Separate relevant-only export

Save a filtered subset:

```text
relevant_predictions.jsonl
relevant_predictions.csv
```

These files must contain only entries where:

- `score >= relevant_threshold`

---

## Stage 7. Logging requirements

Detailed logging is required.

Each run must save a file:

```text
data/discovery_runs/run_001/logs/discovery.log
```

### Log every discovered and scored paper

Each log line should include at least:

- timestamp
- query
- source
- search rank
- title
- `record_id` or `canonical_id`
- predicted label
- score
- threshold

Example:

```text
2026-04-10T18:42:11Z | query="blockchain federated learning" | source=openalex | rank=12 | title="Advancing Blockchain-Based Federated Learning..." | canonical_id=doi:10.xxxx/... | pred=predicted_relevant | score=0.8123 | threshold=0.65
```

### Also log run-level summaries

For each query and for the full run, log:

- number of raw results fetched
- number of candidates after normalization
- number of duplicates removed
- number of predicted relevant
- number of predicted irrelevant
- missing abstracts
- API errors, timeouts, parse failures

---

## Stage 8. Manifest requirements

Each run must save a `manifest.json` with at least:

```json
{
  "run_id": "run_001",
  "started_at": "...",
  "finished_at": "...",
  "queries_count": 12,
  "source": "openalex",
  "max_results_per_query": 200,
  "raw_candidates": 840,
  "deduplicated_candidates": 512,
  "predicted_relevant": 74,
  "predicted_irrelevant": 438,
  "threshold": 0.65,
  "model_name": "logreg",
  "model_version": "baseline_run_01"
}
```

This file is required for reproducibility.

---

## Stage 9. CSV exports for manual inspection

The system must export:

- `candidates.csv`
- `predictions.csv`
- `relevant_predictions.csv`

Recommended columns:

- `record_id`
- `canonical_id`
- `title`
- `publication_year`
- `venue`
- `query`
- `matched_queries`
- `predicted_label`
- `score`
- `search_source`
- `search_rank`
- `landing_page_url`
- `pdf_url`

These exports should make manual review easy.

---

## Stage 10. Operating modes

Implement two modes.

### Mode A — search + predict

This mode:

- searches remote sources,
- creates candidates,
- runs the classifier,
- saves outputs.

### Mode B — predict-only

This mode:

- takes an existing `candidates.jsonl`,
- runs the classifier again,
- writes a fresh labeled run.

This is important for reproducible re-labeling after model retraining.

---

## Stage 11. CLI commands

### Command 1: search and label

```bash
vkr-dataset discover-and-label \
  --queries data/discovery/queries.txt \
  --model artifacts/baseline_run_01/logreg/model.joblib \
  --vectorizer artifacts/baseline_run_01/logreg/vectorizer.joblib \
  --output-dir data/discovery_runs/run_001 \
  --source openalex \
  --max-results-per-query 200 \
  --relevant-threshold 0.65
```

### Command 2: label existing candidates only

```bash
vkr-dataset label-candidates \
  --input data/discovery_runs/run_001/candidates.jsonl \
  --model artifacts/baseline_run_01/logreg/model.joblib \
  --vectorizer artifacts/baseline_run_01/logreg/vectorizer.joblib \
  --output-dir data/discovery_runs/run_001_relabel \
  --relevant-threshold 0.65
```

---

## Stage 12. Required file additions

Create at least:

```text
src/vkr_article_dataset/discovery.py
src/vkr_article_dataset/search_sources.py
src/vkr_article_dataset/discovery_inference.py
```

Optional helper modules are allowed if they make the implementation cleaner.

Update:

```text
src/vkr_article_dataset/cli.py
README.md
requirements.txt
pyproject.toml
```

---

## What must never happen

1. Do not write `predicted_label` into `gold_label`
2. Do not modify `data/normalized/articles.jsonl`
3. Do not mix human review and model predictions in one file
4. Do not discard raw search responses
5. Do not save only predicted relevant papers; always keep the full prediction ledger
6. Do not deduplicate only by `record_id`
7. Do not log only failures; log successful predictions too

---

## Definition of done

The task is complete if:

1. there is a command that searches papers by query,
2. found papers are normalized into `candidates.jsonl`,
3. the trained model labels them into `predictions.jsonl`,
4. predicted relevant records are saved separately,
5. the clean dataset is unchanged,
6. a `manifest.json` is written,
7. a detailed `discovery.log` is written,
8. CSV exports are produced for manual inspection.

---

## Recommended first implementation scope

To keep the first version reliable:

- source: **OpenAlex only**
- classifier: **Logistic Regression only**
- text features: **title + abstract**
- threshold: **0.65**
- save all predictions
- save relevant subset separately
- postpone promotion into reviewed corpus to a later phase

This scope is enough to implement the final stage of the system without risking corruption of the curated dataset.

