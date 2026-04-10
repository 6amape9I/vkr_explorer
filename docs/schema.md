# Локальная схема записи статьи: schema v2

После этапов 1 и 2 основная запись в `data/normalized/articles.jsonl` хранит только нормализованный summary-слой. Полный текст PDF не инлайнится в основной dataset и хранится отдельно.

## Корневые поля

- `schema_version` — текущая версия схемы, сейчас `"2"`
- `record_id` — стабильный локальный идентификатор записи
- `resolution_status` — `resolved | partial | failed`
- `retrieved_at` — время сборки записи в UTC ISO
- `identifiers`
- `sources`
- `source_candidates`
- `bibliography`
- `content`
- `labels`
- `quality`
- `links`
- `provenance`
- `raw`

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

`source` сохранён как backward-compatible alias. Основным источником теперь считается `sources.primary_source`.

## 2. sources

```json
{
  "primary_source": "openalex",
  "available_sources": ["openalex", "arxiv"],
  "source_candidates_count": 2
}
```

## 3. source_candidates

```json
[
  {
    "provider_name": "openalex",
    "source_id": "https://openalex.org/W123",
    "confidence": 0.99,
    "match_details": {
      "matched_by": "doi"
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

Эта секция показывает все успешные resolver candidates, а не только выбранный итоговый источник.

## 4. bibliography

```json
{
  "title": "Advancing Blockchain-based Federated Learning through Verifiable Off-chain Computations",
  "authors": ["Author A", "Author B"],
  "publication_year": 2022,
  "publication_date": "2022-06-23",
  "venue": "arXiv",
  "document_type": "article"
}
```

## 5. content

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

Важные правила:

- `combined_text` остаётся компактным и не должен превращаться в полный PDF.
- `fulltext_ref` указывает на отдельный fulltext-файл.
- Допустимые статусы:
  - `not_attempted`
  - `downloaded`
  - `parsed`
  - `failed`

## 6. labels

```json
{
  "gold_label": "relevant",
  "is_hard_negative": false,
  "auto_topic_tags": ["federated_learning", "blockchain", "off_chain", "zk_proof"],
  "auto_method_tags": ["verification"],
  "manual_topic_tags": [],
  "manual_method_tags": [],
  "notes": "manually reviewed"
}
```

Автотеги и ручные теги хранятся раздельно.

## 7. quality

```json
{
  "has_abstract": true,
  "has_pdf_url": true,
  "is_open_access": true,
  "citation_count": 61
}
```

## 8. links

```json
{
  "landing_page_url": "https://arxiv.org/abs/2206.11641",
  "pdf_url": "https://arxiv.org/pdf/2206.11641.pdf"
}
```

## 9. provenance

```json
{
  "seed_query": "blockchain federated learning off-chain",
  "input_position": 1,
  "resolver_summary": {
    "attempted": ["arxiv", "openalex"],
    "successful": ["arxiv", "openalex"],
    "errors": {}
  }
}
```

## 10. raw

```json
{
  "seed_extra": {},
  "source_payload_refs": {
    "arxiv": "raw/arxiv/art_xxx.json",
    "openalex": "raw/openalex/art_xxx.json"
  }
}
```

Сырые provider payloads вынесены из основной записи в отдельные файлы под `data/raw/`.

## Отдельный fulltext-файл

Полный текст хранится отдельно, например в `data/fulltext/art_xxx.json.gz`.

Минимально ожидаемая структура:

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

## Минимально полезный набор полей в основной записи

- `schema_version`
- `record_id`
- `resolution_status`
- `identifiers.canonical_id`
- `sources.primary_source`
- `bibliography.title`
- `labels.gold_label`
- `content.combined_text`
- `content.fulltext_status`
- `provenance.input_position`
