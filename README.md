# VKR Article Dataset Builder

Небольшой проект на Python для нормализации списка научных статей в локальный датасет под тему ВКР:

**Федеративное обучение + распределённое обучение + blockchain/on-chain учёт + off-chain вычисления**.

## Что делает проект

1. Читает список входных статей (`jsonl` или `csv`).
2. Пытается получить метаданные по `arXiv ID`, `DOI`, `title` или `URL`.
3. Преобразует результат в единый локальный формат.
4. Сохраняет:
   - `JSONL` — основной датасет
   - `CSV` — удобный плоский экспорт для ручной разметки и фильтрации
5. Проставляет первичные тематические метки по ключевым словам.

## Почему формат именно такой

Для ВКР почти всегда быстро выясняется, что одной только таблицы мало. Нужны одновременно:

- поля для библиографии;
- поля для текста;
- поля для ручной разметки;
- поля для происхождения записи;
- метки для последующей сборки обучающих данных.

Поэтому запись хранится как **нормализованный JSON-объект** с блоками:

- `identifiers`
- `bibliography`
- `content`
- `labels`
- `quality`
- `provenance`

## Структура проекта

```text
vkr_article_dataset_project/
├── README.md
├── pyproject.toml
├── requirements.txt
├── .env.example
├── docs/
│   ├── schema.md
│   └── example_record.json
├── data/
│   ├── input/
│   │   └── test_articles.jsonl
│   └── normalized/
│       └── .gitkeep
├── src/
│   └── vkr_article_dataset/
│       ├── __init__.py
│       ├── cli.py
│       ├── config.py
│       ├── http.py
│       ├── io_utils.py
│       ├── models.py
│       ├── normalization.py
│       ├── tagger.py
│       ├── utils.py
│       └── providers/
│           ├── __init__.py
│           ├── arxiv_provider.py
│           └── openalex_provider.py
└── tests/
    ├── test_normalization.py
    └── test_tagger.py
```

## Установка

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Формат входного файла

Поддерживаются `jsonl` и `csv`.

Минимально желательно давать хотя бы одно из:

- `arxiv_id`
- `doi`
- `title`
- `url`

Дополнительные поля:

- `seed_query`
- `gold_label`
- `is_hard_negative`
- `notes`

### Пример JSONL

```json
{"arxiv_id": "2206.11641", "gold_label": "relevant", "seed_query": "blockchain federated learning off-chain", "notes": "Ключевая статья про verifiable off-chain computation"}
{"title": "A Survey on Decentralized Federated Learning", "gold_label": "relevant"}
{"title": "Parameter Box: High Performance Parameter Servers for Efficient Distributed Deep Neural Network Training", "gold_label": "irrelevant", "is_hard_negative": true}
```

## Запуск

```bash
export CONTACT_EMAIL="you@example.com"
export OPENALEX_API_KEY=""

python -m vkr_article_dataset.cli build \
  --input data/input/test_articles.jsonl \
  --output data/normalized/articles.jsonl \
  --csv data/normalized/articles.csv
```

## Что будет в выходе

### `articles.jsonl`
Основной формат для пайплайна.

### `articles.csv`
Плоский экспорт для:

- ручной проверки;
- сортировки в Excel/LibreOffice;
- быстрой разметки;
- последующей сборки train/dev/test.

## Предлагаемые метки

### Основная метка релевантности

- `relevant`
- `partial`
- `irrelevant`
- `unknown`

### Тематические теги

- `federated_learning`
- `decentralized_learning`
- `blockchain`
- `on_chain`
- `off_chain`
- `zk_proof`
- `security_privacy`
- `incentives`
- `survey`
- `distributed_training`
- `parameter_server`

### Зачем нужен `partial`

Это полезная категория. Для ВКР по смешанной теме она спасает корпус от грубых решений:

- чистое FL без blockchain — часто `partial`
- чистый blockchain для ML без FL — часто `partial`
- классическое распределённое обучение без FL — обычно `irrelevant`

## Что потом делать с этим датасетом

Следующий этап после нормализации:

1. Ручная чистка 100–300 записей.
2. Формирование train/dev/test.
3. Отдельная сборка `hard negatives`.
4. Обучение базового классификатора по `title + abstract`.
5. Active learning / iterative labeling.

## Ограничения текущей версии

- Полный текст PDF не парсится.
- Сейчас сделан упор на **metadata + abstract**.
- Основные провайдеры: `arXiv` и `OpenAlex`.
- Для arXiv в коде есть пауза между запросами, чтобы не долбить API слишком агрессивно.

## Идеи для следующей версии

- поддержка Semantic Scholar;
- дедупликация по эмбеддингам заголовков;
- извлечение цитирований и references;
- полуавтоматическая разметка по правилам;
- экспорт в HuggingFace Dataset.
