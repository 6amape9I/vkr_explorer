# План для Codex: этапы 3, 4 и 5

Ниже — конкретный план только для **этапа 3**, **этапа 4** и **этапа 5** развития проекта `vkr_explorer`.

Цель этих этапов:
1. перестать терять хорошие поля из разных источников и ввести **настоящий merge нескольких резолверов**;
2. заменить хрупкое сопоставление и слабый dedup на **match-aware и merge-aware pipeline**;
3. заменить шумные keyword-теги на **объяснимые score-based автотеги**.

---

## Общие ограничения

Codex должен соблюдать следующие ограничения:

1. **Не ломать текущую команду `build`.**
2. **Не возвращаться к модели “первый успешный резолвер победил”.**
3. **Не хранить весь full text в основном `articles.jsonl`.**
4. Все новые поля и изменения должны быть отражены в `docs/schema.md`.
5. Все новые критические части должны иметь тесты.
6. Автотеги и ручные теги должны храниться раздельно.
7. Результат merge и dedup должен быть объяснимым: должно быть видно, **почему** выбрано именно такое значение.

---

# Этап 3. Настоящий merge нескольких источников в одну лучшую запись

## Зачем нужен этап

После этапов 1 и 2 проект уже должен уметь:
- собирать несколько кандидатов из разных источников;
- хранить новую схему записи;
- быть готовым к fulltext enrichment.

Но этого недостаточно.

Если merge не сделать отдельно и явно, то проект всё равно будет страдать от тех же проблем:
- metadata из одного источника перекрывает более качественные поля из другого;
- provenance остаётся слабым;
- невозможно объяснить, почему выбрано именно это `title`, `abstract` или `venue`;
- качество записи будет нестабильным от seed к seed.

Этап 3 должен превратить список `source_candidates` в **одну устойчивую merged-запись** с понятными правилами выбора полей.

---

## Что должно появиться после этапа 3

После завершения этапа 3 проект должен уметь:

1. Брать **несколько source candidates** и объединять их в одну итоговую запись.
2. Выбирать **primary source** не по порядку резолверов, а по качеству данных.
3. Сливать поля **по правилам приоритета**, а не через “возьми payload победителя”.
4. Показывать, **какой источник победил по каждому важному полю**.
5. Сохранять решения merge в provenance, чтобы их можно было проверять и дебажить.

---

## Что считать merged-записью

Codex должен реализовать merge как отдельный слой.

На входе:
- `ArticleSeed`
- список `ProviderResult`

На выходе:
- `merged_record`
- `merge_decisions`
- `primary_source`

В merged-записи должны появиться как минимум такие блоки:

```json
{
  "sources": {
    "primary_source": "openalex",
    "available_sources": ["openalex", "arxiv"],
    "source_candidates_count": 2
  },
  "provenance": {
    "seed_query": "...",
    "input_position": 1,
    "resolver_summary": {
      "attempted": ["arxiv", "openalex"],
      "successful": ["arxiv", "openalex"]
    },
    "merge_summary": {
      "title_winner": "openalex",
      "abstract_winner": "arxiv",
      "pdf_url_winner": "arxiv",
      "citation_count_winner": "openalex"
    }
  }
}
```

Допускается другая точная форма, но логика должна быть такой же.

---

## Какие файлы нужно изменить

### Изменить существующие

- `src/vkr_article_dataset/models.py`
- `src/vkr_article_dataset/normalization.py`
- `src/vkr_article_dataset/io_utils.py`
- `docs/schema.md`
- `docs/example_record.json`

### Добавить новые

- `src/vkr_article_dataset/merge.py`

---

## Что именно должен сделать Codex на этапе 3

### 1. Вынести merge в отдельный модуль

В `merge.py` Codex должен создать отдельную сущность, например:

- `RecordMerger`
- `MergeDecision`
- `FieldDecision`

Минимальный интерфейс может быть таким:

```python
merged_record, merge_decisions = RecordMerger().merge(seed, candidates)
```

Главная цель: убрать field-selection логику из `normalization.py` и собрать её в одном месте.

---

### 2. Ввести явные правила выбора по полям

Codex должен реализовать **field-level merge rules**.

#### Для `identifiers`

Правила:
- `doi`: брать exact DOI, если он есть хотя бы у одного кандидата;
- `arxiv_id`: брать exact arXiv id;
- `openalex_id`: брать exact OpenAlex id;
- `canonical_id`:
  - `doi:<doi>`, если DOI существует;
  - иначе `arxiv:<arxiv_id>`;
  - иначе стабильный hash по title + author + year.

---

#### Для `bibliography.title`

Приоритет:
1. exact title из более структурированного scholarly источника;
2. arXiv title;
3. seed title.

Если есть различия только в регистре, пунктуации или Unicode-символах, это должен решать normalizer, а не пользователь.

---

#### Для `bibliography.authors`

Правила:
- предпочитать более полный список авторов;
- если один источник даёт 5 авторов, а второй 2 — брать 5;
- если списки почти совпадают, выбирать более длинный и более чистый;
- если есть конфликт форматов имён, не терять исходный raw.

---

#### Для `content.abstract`

Правила:
- брать более длинный non-empty abstract;
- если один abstract явно обрезан, брать второй;
- если один источник даёт `None`, а другой текст — побеждает текст.

---

#### Для `links.pdf_url`

Правила:
- если есть прямой PDF от arXiv — это сильный кандидат;
- если scholarly source даёт PDF и он валиден — он тоже может победить;
- `pdf_url` должен быть отдельным решением merge, а не побочным эффектом выбора primary source.

---

#### Для `quality`

Правила:
- `citation_count` — предпочитать OpenAlex/structured source;
- `is_open_access` — предпочитать structured OA metadata;
- `has_pdf_url` — вычислять из merged `links.pdf_url`, а не из одного payload.

---

### 3. Добавить trace merge-решений

У итоговой записи должна быть объяснимость.

Codex должен добавить в provenance или отдельный блок что-то вроде:

```json
"merge_decisions": {
  "title": {
    "winner": "openalex",
    "candidates": ["openalex", "arxiv"],
    "reason": "structured metadata + exact title match"
  },
  "abstract": {
    "winner": "arxiv",
    "candidates": ["arxiv", "openalex"],
    "reason": "longer abstract"
  }
}
```

Текстовые `reason` можно сделать краткими. Главное — чтобы решения были доступны.

---

### 4. Перестроить `normalization.py`

Сейчас `normalization.py` фактически сам собирает итоговую запись.

После этапа 3 он должен:
- собирать seed;
- получать кандидатов;
- передавать кандидатов в merger;
- получать готовую merged-запись;
- делать только orchestration.

Иными словами: `normalization.py` должен стать тоньше, а merge — самостоятельным слоем.

---

## Что считается успешным завершением этапа 3

Этап 3 считается завершённым, если:

1. итоговая запись строится из **нескольких кандидатов**, а не из одного payload;
2. merge сделан как отдельный модуль;
3. есть правила выбора хотя бы для:
   - identifiers,
   - title,
   - authors,
   - abstract,
   - venue,
   - pdf_url,
   - citation_count;
4. итоговая запись хранит `primary_source`;
5. есть trace merge-решений;
6. `normalization.py` больше не содержит основную field-selection логику.

---

## Тесты для этапа 3

Codex должен добавить минимум такие тесты:

### `test_merge_prefers_structured_title_when_candidates_exist()`
Проверяет, что title берётся из более сильного источника, если совпадение подтверждено.

### `test_merge_prefers_longer_nonempty_abstract()`
Проверяет, что из двух abstract выбирается более содержательный.

### `test_merge_builds_primary_source_and_decision_trace()`
Проверяет наличие:
- `sources.primary_source`
- `sources.available_sources`
- `merge_decisions`

---

# Этап 4. Более надёжное сопоставление и новый dedup

## Зачем нужен этап

Даже хороший merge бесполезен, если в `source_candidates` попадают плохие совпадения.

Сейчас одна из самых опасных проблем — хрупкое сопоставление по title, особенно в OpenAlex. Если брать первый поисковый результат или доверять слишком простому slug-match, то проект начнёт:
- подтягивать не ту статью;
- смешивать публикации с похожими названиями;
- плодить дубль-записи;
- создавать грязный датасет для последующей классификации.

Этап 4 должен решить две задачи:
1. сделать **устойчивый matching** кандидатов;
2. сделать **настоящий dedup**, который умеет не только отбрасывать, но и объединять дубликаты.

---

## Что должно появиться после этапа 4

После завершения этапа 4 проект должен уметь:

1. Искать в OpenAlex не один результат, а набор кандидатов.
2. Пересчитывать кандидатов локальным scorer’ом.
3. Отвергать слабые совпадения.
4. Строить `canonical_id` на основе сильных идентификаторов.
5. Группировать дубликаты по точным и приблизительным признакам.
6. Объединять дубликаты через merge, а не просто сохранять “первый resolved”.

---

## Какие файлы нужно изменить

### Изменить существующие

- `src/vkr_article_dataset/providers/openalex_provider.py`
- `src/vkr_article_dataset/normalization.py`
- `src/vkr_article_dataset/models.py`
- `src/vkr_article_dataset/utils.py`

### Добавить новые

- `src/vkr_article_dataset/matching.py`

---

## Что именно должен сделать Codex на этапе 4

### 1. Добавить локальный scorer для matching

Codex должен создать `matching.py` и вынести туда логику оценки кандидатов.

Нужен механизм, который получает:
- seed,
- candidate work,
- при наличии уже найденные идентификаторы,

и возвращает:
- score,
- confidence bucket,
- match details.

---

### 2. Реализовать weighted scoring

Минимальный scoring должен включать такие сигналы:

#### Сильные сигналы
- exact DOI match: `+100`
- exact arXiv ID match: `+100`

#### Средние сигналы
- exact normalized title match: `+40`
- strong title similarity: `+25`
- publication year exact: `+10`
- year difference <= 1: `+5`
- first author surname match: `+10`
- multiple author overlap: `+5`
- наличие arXiv-landing-page при arXiv seed: `+10`

#### Штрафы
- низкая title similarity: `-20`
- year difference > 2: `-10`
- отсутствие author overlap при наличии авторов: `-10`

Числа могут быть скорректированы, но логика должна остаться такой.

---

### 3. Ввести confidence buckets

Codex должен ввести хотя бы такие buckets:

- `exact`
- `strong`
- `probable`
- `weak`
- `reject`

Пример порогов:
- `>=100`: exact
- `>=70`: strong
- `>=50`: probable
- `<50`: reject

Точные пороги можно изменить, но reject-поведение обязательно должно быть.

---

### 4. Переписать OpenAlex title matching

Сейчас title-only matching слишком хрупкий.

Нужно заменить его на поведение:
- запросить несколько top candidates, например 10;
- прогнать все через local scorer;
- выбрать лучшего кандидата только если confidence достаточный;
- если confidence слабый — вернуть `None`, а не “что-то похожее”.

Это критически важно.

---

### 5. Обновить dedup

Сейчас dedup фактически работает как:
- сгруппируй по `record_id`;
- если новый resolved, а старый нет — замени.

Это слишком слабая логика.

Нужно заменить её на двухуровневую схему:

#### Уровень 1. Точный dedup
- по DOI
- по arXiv ID
- по canonical_id

#### Уровень 2. Fuzzy dedup
Если точных идентификаторов нет, использовать composite key:
- normalized title
- publication year
- first author surname

Если записи попадают в одну fuzzy-группу, их нельзя просто отбрасывать. Их нужно передавать в merge.

---

### 6. Сделать dedup merge-aware

Deduplicator должен:
- собирать duplicate groups;
- объединять записи в группе;
- сохранять один итоговый record;
- по возможности хранить информацию:

```json
"dedup": {
  "duplicate_group_size": 3,
  "dedup_strategy": "canonical_id",
  "merged_record_ids": ["art_a", "art_b", "art_c"]
}
```

---

## Что считается успешным завершением этапа 4

Этап 4 считается завершённым, если:

1. OpenAlex matching больше не берёт первый результат вслепую;
2. у matching есть scorer и confidence;
3. слабые совпадения отклоняются;
4. dedup работает не только по `record_id`;
5. дубликаты объединяются через merge;
6. итоговая запись знает размер duplicate-group.

---

## Тесты для этапа 4

Codex должен добавить минимум такие тесты:

### `test_matching_accepts_exact_title_year_author_candidate()`
Проверяет, что сильное совпадение принимается.

### `test_matching_rejects_low_confidence_title_only_candidate()`
Проверяет, что похожий, но слабый match отклоняется.

### `test_dedup_merges_records_with_same_doi()`
Проверяет, что записи с одинаковым DOI становятся одной записью.

### `test_dedup_merges_fuzzy_duplicates_without_exact_ids()`
Проверяет, что схожие title+author+year записи объединяются, а не сохраняются как дубликаты.

---

# Этап 5. Автотеги v2: меньше шума, больше объяснимости

## Зачем нужен этап

Сейчас `tagger.py` работает по простой keyword-логике:
- встретилось слово → поставь тег.

Такой подход удобен как черновик, но он даёт шум:
- статья может упомянуть `parameter server` как фон, а тег станет основным;
- обзорные статьи получают лишние специфические теги;
- невозможно понять, почему тег вообще был поставлен;
- ручная экспертная разметка смешивается с auto-tagging.

Этап 5 должен сделать теги:
- **score-based**,
- **объяснимыми**,
- **разделёнными на auto и manual**,
- готовыми к использованию с abstract и fulltext.

---

## Что должно появиться после этапа 5

После завершения этапа 5 проект должен уметь:

1. Считать score для каждого автотега.
2. Сохранять evidence по тегам.
3. Разделять auto и manual tags.
4. Подавлять шумные теги через negative rules.
5. Использовать `title + abstract + fulltext excerpt`, если fulltext доступен.
6. Не учитывать references section как полноценный источник тематических тегов.

---

## Какие файлы нужно изменить

### Изменить существующие

- `src/vkr_article_dataset/tagger.py`
- `src/vkr_article_dataset/normalization.py`
- `docs/schema.md`
- `docs/example_record.json`

### Добавить новые

- `src/vkr_article_dataset/tag_rules.py`

---

## Что именно должен сделать Codex на этапе 5

### 1. Разделить auto и manual tags окончательно

Если на этапе 1 были добавлены новые поля, то на этапе 5 они должны стать реально рабочими.

В итоговой записи должно быть что-то вроде:

```json
"labels": {
  "gold_label": "relevant",
  "is_hard_negative": false,
  "auto_topic_tags": ["blockchain", "federated_learning"],
  "auto_method_tags": ["verification"],
  "manual_topic_tags": [],
  "manual_method_tags": [],
  "notes": "..."
}
```

При желании Codex может хранить не только массив тегов, но и score-object рядом.

---

### 2. Добавить score-based tagging

Вместо “keyword found = tag” нужен score.

Например:
- `blockchain`: +3 за title match, +2 за abstract match, +1 за body match;
- `federated_learning`: +3 за title, +2 за abstract;
- `parameter_server`: +3 если в title, +2 если многократно в abstract/body, +1 если единичное упоминание.

После этого тег проставляется только если score выше порога.

---

### 3. Сохранять evidence по каждому тегу

Нужен блок вроде:

```json
"tag_evidence": {
  "blockchain": [
    {"field": "title", "match": "blockchain", "weight": 3}
  ],
  "federated_learning": [
    {"field": "abstract", "match": "federated learning", "weight": 2}
  ]
}
```

Можно хранить это либо внутри `labels`, либо в соседнем блоке. Главное — не потерять объяснимость.

---

### 4. Добавить negative rules для шумных тегов

Это обязательный пункт.

Примеры правил:
- не ставить `parameter_server`, если phrase встретилась один раз в обзорной BC-FL статье и не подтверждается title/body density;
- не ставить `distributed_training`, если основной сигнал текста — federated learning / decentralized FL;
- не ставить узкоспециализированный методический тег, если он появился только в references или related work.

Negative rules можно хранить в `tag_rules.py`.

---

### 5. Сделать fulltext-aware tagging

Если `fulltext_ref` существует и `fulltext_status == parsed`, tagger должен уметь использовать:
- `title`
- `abstract`
- короткий body excerpt

Но не должен:
- использовать references section как полноценный тематический сигнал;
- без ограничений прогонять весь мусорный текст через keyword matcher.

Простейший рабочий вариант:
- использовать `title + abstract + первые N символов body_text`
- references игнорировать полностью.

---

### 6. Добавить `tag_scores`

Кроме списков тегов полезно хранить scores, например:

```json
"tag_scores": {
  "blockchain": 0.95,
  "federated_learning": 0.99,
  "parameter_server": 0.18
}
```

Нормировка может быть любой:
- 0–1,
- 0–100,
- raw integer scores.

Главное — чтобы можно было видеть уверенность.

---

## Что считается успешным завершением этапа 5

Этап 5 считается завершённым, если:

1. `tagger.py` больше не является чистым keyword OR-matcher;
2. авто-теги вычисляются по score;
3. у тегов есть evidence;
4. шумные теги подавляются negative rules;
5. manual и auto tags разделены;
6. при наличии fulltext tagger умеет использовать body excerpt;
7. references не загрязняют теги.

---

## Тесты для этапа 5

Codex должен добавить минимум такие тесты:

### `test_tagger_assigns_blockchain_and_fl_for_bcfl_paper()`
Проверяет, что релевантная BC-FL статья получает базовые теги.

### `test_tagger_does_not_assign_parameter_server_on_single_background_mention()`
Проверяет подавление шумного `parameter_server`.

### `test_tagger_uses_fulltext_excerpt_when_available()`
Проверяет, что при наличии parsed fulltext tagger может усилить уверенность по тегу.

### `test_tagger_keeps_manual_tags_separate_from_auto_tags()`
Проверяет, что ручные теги не смешиваются с auto.

---

# Что должно получиться после этапов 3–5

Если Codex корректно выполнит этапы 3–5, проект должен перейти в состояние, где:

1. одна статья из нескольких scholarly источников превращается в **одну действительно качественную запись**;
2. matching в OpenAlex и других источниках становится заметно устойчивее;
3. dedup перестаёт быть косметическим и начинает реально объединять дубликаты;
4. теговая система становится пригодной для анализа и последующего ML;
5. весь pipeline становится ближе к задаче **сбора литературы**, а не только metadata scraping.

---

# Минимальный итоговый чек-лист для Codex

Codex должен считать работу по этапам 3–5 завершённой только если выполнены все пункты:

- [ ] merge вынесен в отдельный модуль;
- [ ] merged record строится из нескольких источников;
- [ ] OpenAlex matching использует reranking и confidence;
- [ ] слабые matches отклоняются;
- [ ] dedup стал merge-aware;
- [ ] duplicate groups объединяются;
- [ ] auto/manual tags разделены;
- [ ] теги имеют score и evidence;
- [ ] шумные теги подавляются;
- [ ] добавлены тесты на merge, matching, dedup и tagging;
- [ ] `docs/schema.md` и `docs/example_record.json` обновлены.
