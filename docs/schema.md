# Локальная схема записи статьи: schema v2 после этапов 3-5

Основной `data/normalized/articles.jsonl` хранит нормализованный summary-слой. Полный текст PDF остаётся во внешнем storage и подключается через `content.fulltext_ref`.

## Корневые поля

- `schema_version`: текущая версия схемы, сейчас `"2"`
- `record_id`: стабильный локальный идентификатор записи
- `resolution_status`: `resolved | partial | failed`
- `retrieved_at`: UTC ISO timestamp сборки
- `identifiers`
- `sources`
- `source_candidates`
- `merge_decisions`
- `bibliography`
- `content`
- `labels`
- `quality`
- `links`
- `provenance`
- `raw`
- `dedup`

## 1. identifiers

```json
{
  "doi": "10.1000/example",
  "arxiv_id": "2206.11641",
  "openalex_id": "https://openalex.org/W123",
  "canonical_id": "doi:10.1000/example",
  "source": "openalex"
}
```

- `canonical_id` строится по приоритету `doi -> arxiv_id -> openalex_id -> hash(title + first_author + year)`.
- `source` оставлен как backward-compatible alias; основным полем считается `sources.primary_source`.

## 2. sources

```json
{
  "primary_source": "openalex",
  "available_sources": ["openalex", "arxiv"],
  "source_candidates_count": 2
}
```

- `primary_source` выбирается по качеству данных, а не по порядку резолверов.

## 3. source_candidates

```json
[
  {
    "provider_name": "openalex",
    "source_id": "https://openalex.org/W123",
    "confidence": 0.95,
    "match_details": {
      "matched_by": "title_rerank",
      "strategy": "topn_rerank",
      "accepted_confidence": 0.91
    },
    "identifiers": {
      "doi": "10.1000/example",
      "arxiv_id": "2206.11641",
      "openalex_id": "https://openalex.org/W123"
    },
    "has_abstract": true,
    "has_pdf_url": false
  }
]
```

- Здесь хранится список всех успешных resolver candidates.
- `match_details` может содержать scorer/confidence trace и top-candidate summary.

## 4. merge_decisions

```json
{
  "bibliography.title": {
    "winner": "openalex",
    "candidates": ["openalex", "arxiv"],
    "reason": "structured metadata + exact title match"
  },
  "content.abstract": {
    "winner": "arxiv",
    "candidates": ["arxiv", "openalex"],
    "reason": "longer abstract"
  },
  "links.pdf_url": {
    "winner": "arxiv",
    "candidates": ["arxiv"],
    "reason": "direct arXiv PDF"
  }
}
```

- Это основной explainability-layer для merge.
- `provenance.merge_summary` хранит компактный winner-summary, а `merge_decisions` даёт trace по полям.

## 5. bibliography

```json
{
  "title": "Advancing Blockchain-Based Federated Learning Through Verifiable Off-Chain Computations",
  "authors": ["Author A", "Author B"],
  "publication_year": 2022,
  "publication_date": "2022-06-23",
  "venue": "OpenAlex Venue",
  "document_type": "article"
}
```

## 6. content

```json
{
  "abstract": "...",
  "combined_text": "title + abstract",
  "language": "en",
  "fulltext_ref": "fulltext/art_xxx.json.gz",
  "fulltext_status": "parsed",
  "fulltext_quality": {
    "char_count": 54231,
    "word_count": 8012,
    "page_count": 12,
    "empty_pages": 0,
    "suspected_ocr_noise": false
  },
  "fulltext_error": null
}
```

Правила:

- `combined_text` остаётся компактным и не превращается в полный PDF body.
- Допустимые статусы: `not_attempted`, `downloaded`, `parsed`, `failed`.
- При fulltext enrichment основной JSONL обновляет только `fulltext_ref`, `fulltext_status`, `fulltext_quality`, `fulltext_error` и auto-tag summary.

## 7. labels

```json
{
  "gold_label": "relevant",
  "is_hard_negative": false,
  "auto_topic_tags": ["federated_learning", "blockchain", "off_chain"],
  "auto_method_tags": ["verification"],
  "auto_topic_tag_scores": {
    "blockchain": 5,
    "federated_learning": 8
  },
  "auto_method_tag_scores": {
    "verification": 5
  },
  "auto_topic_tag_evidence": {
    "blockchain": [
      {"field": "title", "match": "blockchain", "count": 1, "weight": 3, "score": 3}
    ]
  },
  "auto_method_tag_evidence": {
    "verification": [
      {"field": "abstract", "match": "verifiable", "count": 1, "weight": 2, "score": 2}
    ]
  },
  "manual_topic_tags": [],
  "manual_method_tags": [],
  "notes": "manual review note"
}
```

- Auto и manual tags всегда хранятся раздельно.
- Auto-tagging строится по score/evidence.
- Fulltext-aware tagging использует только excerpt без references section.

## 8. quality

```json
{
  "has_abstract": true,
  "has_pdf_url": true,
  "is_open_access": true,
  "citation_count": 61
}
```

- `has_pdf_url` вычисляется из merged `links.pdf_url`, а не берётся из одного payload.

## 9. links

```json
{
  "landing_page_url": "https://doi.org/10.1000/example",
  "pdf_url": "https://arxiv.org/pdf/2206.11641.pdf"
}
```

## 10. provenance

```json
{
  "seed_query": "blockchain federated learning off-chain",
  "input_position": 1,
  "resolver_summary": {
    "attempted": ["arxiv", "openalex"],
    "successful": ["arxiv", "openalex"],
    "errors": {},
    "rejections": {}
  },
  "merge_summary": {
    "title_winner": "openalex",
    "abstract_winner": "arxiv",
    "pdf_url_winner": "arxiv",
    "citation_count_winner": "openalex"
  }
}
```

- `rejections` используется для explainable no-match сценариев, например low-confidence title match в OpenAlex.

## 11. raw

```json
{
  "seed_extra": {},
  "source_payload_refs": {
    "arxiv": "raw/arxiv/art_xxx.json",
    "openalex": "raw/openalex/art_xxx.json"
  }
}
```

- Raw provider payloads вынесены из основной записи в отдельные файлы.
- После dedup возможны значения-списки, если в duplicate group оказалось несколько raw refs для одного provider.

## 12. dedup

```json
{
  "duplicate_group_size": 3,
  "dedup_strategy": "doi",
  "merged_record_ids": ["art_a", "art_b", "art_c"]
}
```

- Exact dedup: `doi`, `arxiv_id`, `canonical_id`.
- Fuzzy dedup: `normalized title + publication_year + first author surname`.
- Duplicate groups объединяются через тот же merge-layer, а не просто отбрасываются.

## Отдельный fulltext-файл

Fulltext хранится отдельно, например в `data/fulltext/art_xxx.json.gz`.

```json
{
  "record_id": "art_xxx",
  "source": "pdf",
  "parser": "pymupdf",
  "download_url": "https://example.com/article.pdf",
  "pdf_sha256": "...",
  "text_sha256": "...",
  "page_count": 12,
  "extraction_status": "parsed",
  "quality": {
    "char_count": 54231,
    "word_count": 8012,
    "page_count": 12,
    "empty_pages": 0,
    "suspected_ocr_noise": false
  },
  "page_texts": ["..."],
  "full_text": "..."
}
```
