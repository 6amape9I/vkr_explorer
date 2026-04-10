# VKR Article Dataset Builder

Небольшой Python-проект для нормализации списка научных статей в локальный датасет для отбора литературы по теме ВКР:

**federated learning + distributed learning + blockchain/on-chain учёт + off-chain вычисления**.

## Что делает проект

1. Читает входной список статей из `jsonl` или `csv`.
2. Пытается обогатить записи через `arXiv` и `OpenAlex`.
3. Нормализует результат в единый JSON-формат.
4. Сохраняет:
   - `JSONL` как основной датасет;
   - `CSV` как плоский экспорт для ручной проверки и фильтрации.
5. Ставит первичные тематические теги по заголовку и abstract.

## Требования

- Windows 10/11
- Python 3.10+
- Доступ в интернет для запросов к `arXiv` и `OpenAlex`

## Установка на Windows

Ниже приведён рабочий сценарий для PowerShell.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
```

Если PowerShell блокирует активацию окружения, можно либо временно разрешить скрипты:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

либо вообще не активировать окружение и вызывать интерпретатор напрямую:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -e .
```

## Почему нужен `pip install -e .`

Проект использует `src`-layout:

```text
src/vkr_article_dataset/...
```

Поэтому команда:

```powershell
python -m vkr_article_dataset.cli
```

не будет работать из корня репозитория, пока пакет не установлен в окружение через:

```powershell
python -m pip install -e .
```

После этого доступны оба варианта запуска:

- `vkr-dataset ...`
- `python -m vkr_article_dataset.cli ...`

## Переменные окружения

Опционально можно задать:

```powershell
$env:CONTACT_EMAIL = "you@example.com"
$env:OPENALEX_API_KEY = ""
$env:ARXIV_DELAY_SECONDS = "3.0"
$env:HTTP_TIMEOUT_SECONDS = "30.0"
```

`CONTACT_EMAIL` полезно передавать в OpenAlex как контактный адрес. Если `OPENALEX_API_KEY` не задан, используется публичный доступ.

## Формат входного файла

Поддерживаются `jsonl` и `csv`.

У каждой записи должно быть хотя бы одно из полей:

- `arxiv_id`
- `doi`
- `title`
- `url`

Дополнительные поля:

- `seed_query`
- `gold_label`
- `is_hard_negative`
- `notes`

### Пример `jsonl`

```json
{"arxiv_id": "2206.11641", "gold_label": "relevant", "seed_query": "blockchain federated learning off-chain computation", "notes": "Ключевая статья по verifiable off-chain computations"}
{"title": "A Survey on Decentralized Federated Learning", "gold_label": "relevant"}
{"title": "Parameter Box: High Performance Parameter Servers for Efficient Distributed Deep Neural Network Training", "gold_label": "irrelevant", "is_hard_negative": true}
```

Готовый пример лежит в `data/input/test_articles.jsonl`.

## Запуск CLI на Windows

### Вариант 1: через console script

```powershell
vkr-dataset build `
  --input data\input\test_articles.jsonl `
  --output data\normalized\articles.jsonl `
  --csv data\normalized\articles.csv
```

### Вариант 2: через модуль Python

```powershell
python -m vkr_article_dataset.cli build `
  --input data\input\test_articles.jsonl `
  --output data\normalized\articles.jsonl `
  --csv data\normalized\articles.csv
```

### Вариант без активации `.venv`

```powershell
.\.venv\Scripts\vkr-dataset.exe build `
  --input data\input\test_articles.jsonl `
  --output data\normalized\articles.jsonl `
  --csv data\normalized\articles.csv
```

После выполнения команда печатает краткую сводку в JSON, например:

```json
{
  "input": "data\\input\\test_articles.jsonl",
  "output": "data\\normalized\\articles.jsonl",
  "records": 5,
  "csv": "data\\normalized\\articles.csv"
}
```

## Что лежит в выходе

### `articles.jsonl`

Основной формат для пайплайна. Каждая строка содержит нормализованную запись со следующими блоками:

- `identifiers`
- `bibliography`
- `content`
- `labels`
- `quality`
- `links`
- `provenance`
- `raw`

Пример структуры есть в [docs/schema.md](docs/schema.md) и [docs/example_record.json](docs/example_record.json).

### `articles.csv`

Плоский экспорт для:

- ручной проверки;
- сортировки в Excel/LibreOffice;
- быстрой разметки;
- последующей сборки train/dev/test.

## Теги

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

## UI для проверки датасета

Для ручной проверки собранного датасета теперь есть локальный интерфейс на `Streamlit`.

По умолчанию приложение:

- читает `data/normalized/articles.jsonl`;
- если существует `data/normalized/articles.reviewed.jsonl`, накладывает из него сохранённые метки;
- позволяет менять только `gold_label`;
- сохраняет результат в отдельный `data/normalized/articles.reviewed.jsonl`, не переписывая исходный `articles.jsonl`.

### Запуск на Windows

```powershell
python -m streamlit run src\vkr_article_dataset\review_app.py -- `
  --input data\normalized\articles.jsonl `
  --output data\normalized\articles.reviewed.jsonl
```

### Что умеет интерфейс

- поиск по заголовку;
- фильтр по `gold_label`;
- фильтр по `is_hard_negative`;
- список статей в формате `gold_label | year | title`;
- просмотр заголовка, метки, авторов, ссылок и текста статьи;
- кнопки `Previous` / `Next`;
- явное сохранение через `Save review`.

## Тесты

```powershell
python -m pytest -q
```

## Ограничения текущей версии

- Полные тексты PDF не парсятся.
- Основной упор сделан на `metadata + abstract`.
- Сейчас используются два источника: `arXiv` и `OpenAlex`.
- Для `arXiv` в клиенте есть задержка между запросами.
