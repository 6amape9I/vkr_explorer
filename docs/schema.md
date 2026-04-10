# Локальная схема записи статьи

Каждая запись хранится как JSON-объект.

## Корневые поля

- `record_id` — стабильный локальный идентификатор
- `resolution_status` — `resolved | partial | failed`
- `retrieved_at` — ISO datetime UTC
- `identifiers`
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
  "openalex_id": "https://openalex.org/W...",
  "source": "arxiv"
}
```

## 2. bibliography

```json
{
  "title": "Advancing Blockchain-based Federated Learning through Verifiable Off-chain Computations",
  "authors": ["Author A", "Author B"],
  "publication_year": 2022,
  "publication_date": "2022-06-23",
  "venue": "arXiv",
  "document_type": "preprint"
}
```

## 3. content

```json
{
  "abstract": "...",
  "combined_text": "title + abstract",
  "language": "en"
}
```

## 4. labels

```json
{
  "gold_label": "relevant",
  "is_hard_negative": false,
  "topic_tags": ["federated_learning", "blockchain", "off_chain", "zk_proof"],
  "method_tags": ["consensus", "verification"],
  "notes": "manually reviewed"
}
```

## 5. quality

```json
{
  "has_abstract": true,
  "has_pdf_url": true,
  "is_open_access": true,
  "citation_count": 61
}
```

## 6. links

```json
{
  "landing_page_url": "https://arxiv.org/abs/2206.11641",
  "pdf_url": "https://arxiv.org/pdf/2206.11641.pdf"
}
```

## 7. provenance

```json
{
  "seed_query": "blockchain federated learning off-chain",
  "input_position": 1,
  "resolver": "arxiv",
  "resolver_confidence": 0.99
}
```

## 8. raw

Сюда кладётся исходный ответ провайдера, чтобы не терять метаданные и иметь возможность пересобрать нормализацию.

---

## Какие поля обязательно заполнять

Минимальный полезный набор:

- `record_id`
- `resolution_status`
- `identifiers.source`
- `bibliography.title`
- `labels.gold_label`
- `content.combined_text`
- `provenance.input_position`

## Почему это удобно для обучения

Такой формат позволяет потом быстро собрать:

- бинарную классификацию `relevant / irrelevant`;
- трёхклассовую задачу `relevant / partial / irrelevant`;
- multi-label задачу по тегам;
- retrieval-датасет по `seed_query -> relevant papers`.
