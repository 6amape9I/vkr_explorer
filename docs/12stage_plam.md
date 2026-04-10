# План для Codex: этапы 1 и 2

Ниже — конкретный план только для **этапа 1** и **этапа 2** развития проекта `vkr_explorer`.

Цель этих этапов:
1. перестроить текущую схему данных и логику резолва так, чтобы проект умел собирать **несколько результатов из разных источников** и готовился к качественному merge;
2. добавить **обработку PDF и хранение полного текста отдельно** от основного `articles.jsonl`, чтобы проект перестал быть только сборщиком `metadata + abstract`.

---

## Общие ограничения

Codex должен соблюдать следующие ограничения:

1. **Не ломать текущую команду `build`.**
2. **Не класть полный текст PDF внутрь основного `articles.jsonl`.**
3. Сохранять обратную совместимость формата настолько, насколько это возможно.
4. Все новые поля и изменения должны быть отражены в `docs/schema.md`.
5. Все новые критические части должны иметь тесты.

---

# Этап 1. Новая схема записи и подготовка к merge нескольких источников

## Зачем нужен этап

Сейчас в проекте используется схема:
- seed → первый успешный резолвер → одна итоговая запись.

Это создаёт сразу несколько проблем:
- качество записи зависит от того, **какой источник ответил первым**;
- хорошие поля из второго источника теряются;
- нет нормальной базы для будущего merge;
- provenance слишком слабый;
- невозможно понять, почему был выбран именно этот источник.

Этап 1 должен подготовить систему к модели:
- seed → **несколько source candidates** → одна нормализованная merged-запись.

На этом этапе ещё не нужно делать полный merge-пайплайн в идеальном виде, но нужно **перестроить структуру проекта**, чтобы merge стал естественным следующим шагом.

---

## Что должно появиться после этапа 1

После завершения этапа 1 проект должен уметь:

1. Запрашивать **все доступные резолверы**, а не останавливаться на первом успехе.
2. Сохранять список найденных кандидатов как `source_candidates`.
3. Формировать одну итоговую запись с новой схемой `schema_version=2`.
4. Указывать:
   - какой источник стал основным;
   - какие источники вообще дали данные;
   - какие поля пока ещё пустые;
   - какой статус у будущего fulltext.
5. Не хранить тяжёлые `raw` payload прямо внутри основной записи, если можно положить ссылку на файл.

---

## Новая схема основной записи

Codex должен обновить формат записи примерно до такого вида:

```json
{
  "schema_version": "2",
  "record_id": "art_xxx",
  "resolution_status": "resolved",
  "retrieved_at": "2026-04-10T12:00:00Z",
  "identifiers": {
    "doi": "...",
    "arxiv_id": "...",
    "openalex_id": "...",
    "canonical_id": "doi:..."
  },
  "sources": {
    "primary_source": "openalex",
    "available_sources": ["openalex", "arxiv"],
    "source_candidates_count": 2
  },
  "bibliography": {
    "title": "...",
    "authors": [],
    "publication_year": 2025,
    "publication_date": "2025-02-13",
    "venue": "...",
    "document_type": "article"
  },
  "content": {
    "abstract": "...",
    "combined_text": "...",
    "language": "en",
    "fulltext_ref": null,
    "fulltext_status": "not_attempted",
    "fulltext_quality": null
  },
  "labels": {
    "gold_label": "relevant",
    "is_hard_negative": false,
    "auto_topic_tags": [],
    "auto_method_tags": [],
    "manual_topic_tags": [],
    "manual_method_tags": [],
    "notes": "..."
  },
  "quality": {
    "has_abstract": true,
    "has_pdf_url": true,
    "is_open_access": true,
    "citation_count": 21
  },
  "links": {
    "landing_page_url": "...",
    "pdf_url": "..."
  },
  "provenance": {
    "seed_query": "...",
    "input_position": 1,
    "resolver_summary": {
      "attempted": ["arxiv", "openalex"],
      "successful": ["arxiv", "openalex"]
    }
  },
  "raw": {
    "seed_extra": {},
    "source_payload_refs": {
      "arxiv": "raw/arxiv/art_xxx.json",
      "openalex": "raw/openalex/art_xxx.json"
    }
  }
}
```

Допускаются мелкие отклонения по названиям полей, но смысл должен остаться тем же.

---

## Какие файлы нужно изменить

### Изменить существующие

- `src/vkr_article_dataset/models.py`
- `src/vkr_article_dataset/normalization.py`
- `src/vkr_article_dataset/io_utils.py`
- `src/vkr_article_dataset/cli.py`
- `docs/schema.md`
- `docs/example_record.json`

### Добавить новые

- `src/vkr_article_dataset/schema.py`
- `src/vkr_article_dataset/merge.py`

---

## Что именно должен сделать Codex на этапе 1

### 1. Обновить модели данных

В `models.py`:

1. расширить `ProviderResult` так, чтобы он содержал:
   - `provider_name`
   - `source_id`
   - `confidence`
   - `payload`
   - `raw`
   - при необходимости `match_details`

2. при необходимости добавить новые dataclass-модели:
   - `SourceCandidate`
   - `MergeDecision`
   - `NormalizedRecordV2`

Не обязательно делать всё через dataclass, но структура должна стать явнее, чем сейчас.

---

### 2. Изменить логику `_resolve()`

Сейчас `DatasetBuilder._resolve()` возвращает один `ProviderResult | None`.

Нужно заменить это на поведение:
- метод собирает **все** успешные результаты от резолверов;
- ошибки отдельных резолверов не валят весь pipeline;
- возвращается список кандидатов.

Пример нового поведения:

```python
candidates = self._resolve_all(seed)
```

А не:

```python
candidate = self._resolve(seed)
```

---

### 3. Добавить черновой merge-слой

На этапе 1 merge может быть ещё простым, но он уже должен существовать как отдельная сущность.

Нужно добавить `merge.py` с чем-то вроде:

- `RecordMerger`
- `choose_primary_source(candidates)`
- `build_merged_payload(seed, candidates)`

Пока достаточно простого правила выбора primary source:
- DOI-based/OpenAlex record выше, чем title-only;
- structured metadata выше, чем минимальный ответ;
- arXiv полезен для PDF и abstract;
- OpenAlex полезен для citation count / venue / OA metadata.

Важно: даже если merge пока будет частично простым, он должен быть **отдельным модулем**, а не размазанным внутри `normalization.py`.

---

### 4. Подготовить хранение raw payload отдельно

Сейчас `raw.provider_payload` кладётся прямо в итоговый record.

Это нормально на маленьком датасете, но плохо масштабируется.

На этапе 1 нужно перевести проект к модели:
- сырой payload можно сохранять в отдельный файл;
- в основной записи хранится ссылка `source_payload_refs`.

Допускается промежуточный режим:
- для обратной совместимости payload можно временно дублировать,
- но новая схема должна уже поддерживать вынесение raw в файлы.

---

### 5. Обновить `labels`

Уже на этапе 1 надо перестать смешивать будущие ручные теги и автотеги.

Поэтому в записи нужно перейти от:
- `topic_tags`
- `method_tags`

к:
- `auto_topic_tags`
- `auto_method_tags`
- `manual_topic_tags`
- `manual_method_tags`

На этом этапе manual-теги могут быть пустыми.

---

### 6. Обновить `content`

Поле `content` должно сразу готовиться к fulltext-обогащению:

Добавить:
- `fulltext_ref`
- `fulltext_status`
- `fulltext_quality`

Начальные значения:
- `fulltext_ref = null`
- `fulltext_status = "not_attempted"`
- `fulltext_quality = null`

---

### 7. Обновить CLI без поломки `build`

Команда:

```bash
vkr-dataset build ...
```

должна продолжать работать.

Но результат должен уже писаться по схеме v2.

---

## Что считается успешным завершением этапа 1

Этап 1 считается завершённым, если:

1. один seed может породить **несколько source candidates**;
2. итоговая запись сохраняет информацию о нескольких источниках;
3. у записи есть `schema_version=2`;
4. структура готова к fulltext enrichment;
5. старый CLI не сломан;
6. `docs/schema.md` обновлён;
7. есть тесты хотя бы на:
   - multiple resolver collection,
   - merged record skeleton,
   - backward-compatible build.

---

## Тесты для этапа 1

Codex должен добавить минимум такие тесты:

### `test_collects_multiple_candidates()`
Проверяет, что при двух успешных резолверах builder сохраняет оба кандидата.

### `test_build_record_v2_contains_sources_block()`
Проверяет наличие:
- `schema_version`
- `sources.primary_source`
- `sources.available_sources`
- `content.fulltext_status`

### `test_labels_split_auto_manual_fields()`
Проверяет, что запись использует новые поля `auto_*` и `manual_*`.

---

# Этап 2. PDF pipeline и отдельное хранение полного текста

## Зачем нужен этап

Сейчас проект собирает только:
- metadata
- abstract

Это ещё не литература “в полном смысле”. Для реального анализа статей нужно:
- скачивать PDF;
- извлекать текст;
- сохранять его отдельно;
- связывать этот текст с записью в основном датасете.

Главная задача этапа 2:
**добавить fulltext ingestion, не раздувая `articles.jsonl`.**

---

## Архитектурное решение

Полный текст должен храниться **в отдельном слое данных**, а не внутри основной записи.

### Рекомендуемая структура каталогов

```text
data/
  normalized/
    articles.jsonl
  pdfs/
    art_xxx.pdf
  fulltext/
    art_xxx.json.gz
    index.jsonl
  raw/
    arxiv/
      art_xxx.json
    openalex/
      art_xxx.json
```

---

## Что должно появиться после этапа 2

После этапа 2 проект должен уметь:

1. брать `pdf_url` из итоговой записи;
2. скачивать PDF;
3. сохранять PDF на диск;
4. извлекать текст;
5. сохранять extracted full text в отдельный `json.gz`;
6. записывать в основную запись только ссылку на fulltext;
7. выставлять статус:
   - `not_attempted`
   - `downloaded`
   - `parsed`
   - `failed`

---

## Формат отдельного fulltext файла

Каждый fulltext-файл должен храниться отдельно, например:

`data/fulltext/art_xxx.json.gz`

Пример структуры:

```json
{
  "record_id": "art_xxx",
  "source": "pdf",
  "parser": "pymupdf",
  "download_url": "https://...pdf",
  "pdf_sha256": "...",
  "text_sha256": "...",
  "page_count": 12,
  "extraction_status": "parsed",
  "quality": {
    "char_count": 54231,
    "word_count": 8012,
    "suspected_ocr_noise": false,
    "empty_pages": 0
  },
  "sections": {
    "title": "...",
    "abstract": "...",
    "body_text": "...",
    "references": "..."
  },
  "full_text": "..."
}
```

Если section splitting пока сделать сложно, допустим промежуточный вариант:
- `full_text`
- `page_texts`

Но структура должна быть пригодна для дальнейшего анализа.

---

## Какие библиотеки использовать

Рекомендуемый стек:

### Основной PDF parser
- `pymupdf`

### Fallback parser
- `pypdf`

Почему так:
- `pymupdf` обычно лучше для извлечения текста;
- `pypdf` полезен как fallback;
- OCR пока не обязателен на этом этапе.

---

## Какие файлы нужно изменить

### Добавить новые

- `src/vkr_article_dataset/pdf_pipeline.py`
- `src/vkr_article_dataset/storage.py`

### Изменить существующие

- `src/vkr_article_dataset/cli.py`
- `src/vkr_article_dataset/http.py`
- `src/vkr_article_dataset/io_utils.py`
- `docs/schema.md`
- `pyproject.toml`
- `requirements.txt`

---

## Что именно должен сделать Codex на этапе 2

### 1. Добавить загрузку PDF

Нужен модуль, который:
- получает `record_id` и `pdf_url`;
- скачивает PDF;
- сохраняет файл как `data/pdfs/<record_id>.pdf`;
- возвращает путь и checksum.

Нужно предусмотреть:
- timeout;
- обработку 404/403/500;
- корректный `failed` статус;
- не падать всем pipeline из-за одного плохого PDF.

---

### 2. Добавить извлечение текста

Нужен pipeline:
1. открыть PDF;
2. извлечь текст по страницам;
3. склеить текст;
4. оценить качество извлечения.

Минимальные quality-метрики:
- `char_count`
- `word_count`
- `page_count`
- `empty_pages`
- флаг `suspected_ocr_noise`

Простейшая эвристика для `suspected_ocr_noise` допустима, например:
- слишком много мусорных символов;
- слишком мало слов при большом page count;
- высокий процент одиночных букв.

---

### 3. Сохранять extracted text отдельно

Нужен storage-layer, который:
- пишет fulltext в `data/fulltext/<record_id>.json.gz`;
- умеет возвращать `fulltext_ref`;
- при необходимости ведёт `index.jsonl`.

В основном `articles.jsonl` нужно хранить только:

```json
"content": {
  "fulltext_ref": "data/fulltext/art_xxx.json.gz",
  "fulltext_status": "parsed",
  "fulltext_quality": {
    "char_count": 54231,
    "page_count": 12
  }
}
```

А не сам `full_text`.

---

### 4. Добавить новую CLI-команду

Нужен новый subcommand, например:

```bash
vkr-dataset enrich-fulltext \
  --input data/normalized/articles.jsonl \
  --output data/normalized/articles_with_fulltext.jsonl
```

Логика:
- читаем основной dataset;
- для записей с `pdf_url` пытаемся скачать и распарсить PDF;
- обновляем `content.fulltext_*` поля;
- сохраняем новый JSONL.

Важно:
- `build` остаётся отдельно;
- fulltext enrichment — отдельный шаг.

---

### 5. Не перегружать `combined_text`

На этапе 2 нельзя превращать `combined_text` в полный текст статьи.

`combined_text` должен остаться компактным, например:
- `title + abstract`
- или `title + abstract + short_excerpt`

Но не:
- весь PDF;
- весь body_text;
- references.

Иначе потом основной dataset станет тяжёлым и неудобным.

---

### 6. Добавить статус-модель fulltext enrichment

Codex должен явно реализовать следующие статусы:

- `not_attempted`
- `downloaded`
- `parsed`
- `failed`

Желательно также добавить `fulltext_error` или `processing_notes`, чтобы было понятно, почему не удалось обработать файл.

---

## Что считается успешным завершением этапа 2

Этап 2 считается завершённым, если:

1. проект умеет скачивать PDF по `pdf_url`;
2. умеет извлекать текст хотя бы базовым способом;
3. текст сохраняется отдельно в `data/fulltext/*.json.gz`;
4. основной `articles.jsonl` не раздувается полным текстом;
5. запись получает `fulltext_ref`, `fulltext_status`, `fulltext_quality`;
6. добавлена отдельная CLI-команда fulltext enrichment;
7. есть тесты на успех и неуспех PDF pipeline.

---

## Тесты для этапа 2

Codex должен добавить минимум такие тесты:

### `test_pdf_download_failure_sets_failed_status()`
Если PDF не скачался, запись получает:
- `fulltext_status = "failed"`
- `fulltext_ref = null`

### `test_pdf_parsing_success_writes_fulltext_file()`
Если PDF успешно скачан и распарсен:
- создаётся `data/fulltext/<record_id>.json.gz`
- в записи прописан `fulltext_ref`
- `fulltext_status = "parsed"`

### `test_main_dataset_does_not_inline_full_text()`
Проверяет, что после enrichment в основной записи **нет поля `full_text`**.

### `test_fulltext_quality_metrics_present()`
Проверяет наличие хотя бы:
- `char_count`
- `page_count`

---

# Рекомендуемый порядок выполнения

## PR 1
Сделать полностью **этап 1**:
- schema v2
- multiple source candidates
- sources block
- labels split
- fulltext placeholders
- docs update
- tests

## PR 2
Сделать полностью **этап 2**:
- pdf download
- text extraction
- fulltext storage
- CLI subcommand
- tests

Не надо смешивать оба этапа в один PR.

---

# Краткая формулировка задания для Codex

```text
Implement stages 1 and 2 for repo 6amape9I/vkr_explorer.

Stage 1:
- Refactor the normalization pipeline to collect all successful resolver outputs instead of stopping at the first successful one.
- Introduce schema_version=2.
- Add sources.primary_source, sources.available_sources, source_candidates_count.
- Split labels into auto_topic_tags, auto_method_tags, manual_topic_tags, manual_method_tags.
- Add content.fulltext_ref, content.fulltext_status, content.fulltext_quality placeholders.
- Prepare raw payload storage through source_payload_refs.
- Keep build CLI backward-compatible.
- Update docs/schema.md and example_record.json.
- Add tests for multiple resolver collection and v2 record structure.

Stage 2:
- Add PDF download and parsing pipeline.
- Use pymupdf as primary parser and pypdf as fallback.
- Store PDFs under data/pdfs/<record_id>.pdf.
- Store extracted full text separately under data/fulltext/<record_id>.json.gz.
- Do not inline full text into main articles.jsonl.
- Add enrich-fulltext CLI command.
- Update main record with fulltext_ref/fulltext_status/fulltext_quality.
- Add tests for PDF download failure, parse success, and no inline full_text in main dataset.
```

---

# Результат, который должен быть после этих двух этапов

Если Codex всё сделает правильно, то после этапов 1 и 2 проект станет:

- не просто сборщиком metadata/abstract;
- а полноценным ingest-пайплайном для литературы;
- с несколькими источниками на одну статью;
- с отдельным storage для полного текста;
- с основным JSONL, который остаётся лёгким и удобным.
