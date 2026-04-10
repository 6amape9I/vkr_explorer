# Baseline Plan

## Цель

Построить в репозитории `vkr_explorer` воспроизводимый baseline-пайплайн обучения **бинарной классификации статей**:

- `relevant = 1`
- `irrelevant = 0`

Исключить из обучения:
- `partial`
- `unknown`

Нужно получить **две обученные baseline-модели**:
1. `TF-IDF + Logistic Regression`
2. `TF-IDF + Linear SVM`

Обучение должно использовать только поля:
- `bibliography.title`
- `content.abstract`

Нужен фиксированный split:
- `train = 70%`
- `validation = 15%`
- `test = 15%`

---

## Общие принципы

1. **Строгий baseline**
   - использовать только clean binary labels:
     - `relevant`
     - `irrelevant`
   - `partial` и `unknown` полностью исключить из train/val/test baseline-наборов

2. **Без утечки**
   - split делать **после deduplication**
   - одна и та же статья или её дубль не должны попасть одновременно в разные выборки

3. **Минимум источников шума**
   - не использовать:
     - `seed_query`
     - `notes`
     - `source`
     - `resolver_summary`
     - `raw.*`
     - `auto tags`
     - `manual tags`
     - `pdf_url`
     - `landing_page_url`
   - baseline должен учиться только на тексте статьи, а не на артефактах пайплайна

4. **Воспроизводимость**
   - фиксированный `random_state`
   - сохранение split-файлов
   - сохранение обученных моделей
   - сохранение метрик и конфигов запуска

---

## Что должен сделать Codex

## Этап 1. Подготовка training dataset

### Задача
Собрать из существующего `articles.jsonl` чистый бинарный обучающий датасет.

### Что нужно реализовать
Создать модуль, например:

```text
src/vkr_article_dataset/training_dataset.py
```

### Логика подготовки
1. Загрузить нормализованный датасет `articles.jsonl`
2. Оставить только записи, где:
   - `labels.gold_label == "relevant"` или `labels.gold_label == "irrelevant"`
3. Исключить записи, где:
   - `labels.gold_label in {"partial", "unknown"}`
4. Проверить, что у записи есть хотя бы один из текстов:
   - `bibliography.title`
   - `content.abstract`
5. Сформировать целевой label:
   - `relevant -> 1`
   - `irrelevant -> 0`
6. Сформировать текстовые поля:
   - `title_text`
   - `abstract_text`
   - `title_abstract_text = title + "\n\n" + abstract`
7. Сохранить подготовленный dataset в отдельный JSONL/CSV

### Выход
Например:

```text
data/training/baseline_dataset.jsonl
data/training/baseline_dataset.csv
```

### Поля baseline dataset
Минимум:

```json
{
  "record_id": "...",
  "canonical_id": "...",
  "title": "...",
  "abstract": "...",
  "title_abstract_text": "...",
  "label": 1,
  "label_name": "relevant"
}
```

---

## Этап 2. Split train/validation/test

### Задача
Сделать фиксированный split:
- train 70%
- validation 15%
- test 15%

### Что нужно реализовать
Создать модуль:

```text
src/vkr_article_dataset/splitting.py
```

### Правила split
1. Использовать только baseline dataset из этапа 1
2. Делать **stratified split** по `label`
3. Делать split с фиксированным `random_state`, например `42`
4. Если возможно, split делать по `canonical_id`, чтобы избежать leakage
5. Сохранить индексы/файлы split отдельно

### Выход
Например:

```text
data/training/splits/train.jsonl
data/training/splits/val.jsonl
data/training/splits/test.jsonl
```

Дополнительно сохранить manifest:

```json
{
  "random_state": 42,
  "train_size": 0.70,
  "val_size": 0.15,
  "test_size": 0.15,
  "label_distribution": {
    "train": {"0": "...", "1": "..."},
    "val": {"0": "...", "1": "..."},
    "test": {"0": "...", "1": "..."}
  }
}
```

### Проверки
Codex должен добавить проверки:
- нет пересечений по `record_id`
- нет пересечений по `canonical_id`
- label distribution примерно сохранён

---

## Этап 3. Фичи baseline

### Задача
Подготовить baseline-признаки только из:
- `bibliography.title`
- `content.abstract`

### Что нужно реализовать
Создать модуль:

```text
src/vkr_article_dataset/features.py
```

### Поддерживаемые текстовые режимы
Сделать поддержку трёх режимов, но baseline по умолчанию обучать на основном:

1. `title`
2. `abstract`
3. `title_abstract` ← **основной baseline**

### TF-IDF настройки
Codex должен сделать конфигурируемый vectorizer, например:
- `lowercase=True`
- `strip_accents="unicode"`
- `ngram_range=(1, 2)`
- `min_df=2`
- `max_df=0.95`
- `sublinear_tf=True`

Не надо пока усложнять char n-grams, stemmers и т.п.

### Важно
- vectorizer фитится **только на train**
- на `val` и `test` используется только `transform`

---

## Этап 4. Обучение моделей

### Задача
Обучить две baseline-модели:
1. Logistic Regression
2. Linear SVM

### Что нужно реализовать
Создать модуль:

```text
src/vkr_article_dataset/train_baseline.py
```

### Модель 1
**TF-IDF + Logistic Regression**

Примерные параметры:
- `max_iter=2000`
- `class_weight="balanced"` — допустимо, если классы неравны
- `random_state=42`

### Модель 2
**TF-IDF + Linear SVM**

Например:
- `LinearSVC`
- `class_weight="balanced"` при дисбалансе

### Что важно
Обучение должно запускаться по одному и тому же split и одинаковым текстовым режимам.

### Что сохранить
Для каждой модели:
- fitted vectorizer
- fitted classifier
- конфиг обучения
- результаты на train/val/test

### Папка
Например:

```text
artifacts/baseline/logreg/
artifacts/baseline/linear_svm/
```

---

## Этап 5. Оценка качества

### Задача
Считать метрики на:
- validation
- test

### Что нужно реализовать
Создать модуль:

```text
src/vkr_article_dataset/evaluation.py
```

### Метрики
Для каждой модели считать:
- accuracy
- precision
- recall
- f1
- confusion matrix

### Дополнительно
Для Logistic Regression:
- сохранить вероятности класса
- сохранить PR-таблицу по threshold, если просто реализуется

Для Linear SVM:
- если вероятностей нет, достаточно decision scores и обычных метрик

### Что сохранить
Например:

```text
artifacts/baseline/logreg/metrics_val.json
artifacts/baseline/logreg/metrics_test.json
artifacts/baseline/logreg/confusion_matrix_test.json

artifacts/baseline/linear_svm/metrics_val.json
artifacts/baseline/linear_svm/metrics_test.json
artifacts/baseline/linear_svm/confusion_matrix_test.json
```

---

## Этап 6. Инференс на test и выгрузка ошибок

### Задача
Сделать удобный анализ ошибок baseline.

### Что нужно реализовать
Сохранить предсказания по validation/test в таблицы:

```text
artifacts/baseline/logreg/predictions_val.csv
artifacts/baseline/logreg/predictions_test.csv
artifacts/baseline/linear_svm/predictions_val.csv
artifacts/baseline/linear_svm/predictions_test.csv
```

### Поля в prediction table
Минимум:
- `record_id`
- `canonical_id`
- `label`
- `pred_label`
- `correct`
- `title`
- `abstract`
- `text_mode`
- для logreg: `pred_proba`
- для svm: `decision_score`

Это нужно, чтобы потом вручную смотреть ошибки.

---

## Этап 7. CLI-команда для baseline

### Задача
Добавить удобную CLI-команду, чтобы baseline можно было запускать одной командой.

### Что нужно реализовать
Добавить в `cli.py` новую команду, например:

```bash
vkr-dataset train-baseline \
  --input data/normalized/articles.jsonl \
  --workdir artifacts/baseline_run_01 \
  --text-mode title_abstract \
  --random-state 42
```

### Что должна делать команда
1. подготовить baseline dataset
2. сделать split
3. обучить Logistic Regression
4. обучить Linear SVM
5. посчитать метрики
6. сохранить модели, split, predictions, manifest

---

## Структура файлов, которую нужно добавить

### Новые файлы

```text
src/vkr_article_dataset/
  training_dataset.py
  splitting.py
  features.py
  train_baseline.py
  evaluation.py
```

### Изменить

```text
src/vkr_article_dataset/cli.py
requirements.txt
pyproject.toml
README.md
```

### Зависимости
Добавить:
- `scikit-learn`
- `joblib`
- `pandas` — по желанию, но желательно для удобных prediction tables

---

## Что нельзя делать

1. **Не использовать `partial` в baseline train**
2. **Не использовать `unknown`**
3. **Не использовать fulltext в baseline**
4. **Не использовать auto/manual tags**
5. **Не использовать metadata leakage-поля**
6. **Не делать split до dedup**
7. **Не фитить TF-IDF на всём датасете**
8. **Не сравнивать модели на разных split**

---

## Критерий готовности

Codex считается выполнившим задачу, если:

1. Есть команда обучения baseline
2. Есть clean binary dataset
3. Есть train/val/test split 70/15/15
4. Есть две обученные модели:
   - Logistic Regression
   - Linear SVM
5. Для обеих моделей сохранены:
   - vectorizer
   - classifier
   - metrics
   - predictions
6. Можно повторно запустить обучение и получить тот же split при том же `random_state`
7. В prediction files можно руками разбирать ошибки

---

## Готовый текст для Codex

```text
You are working on repo 6amape9I/vkr_explorer.

Task:
Implement a strict binary baseline training pipeline for article relevance classification.

Goal:
Train two baseline classifiers:
1. TF-IDF + Logistic Regression
2. TF-IDF + Linear SVM

Strict baseline rules:
- Use only gold labels:
  - relevant -> 1
  - irrelevant -> 0
- Exclude:
  - partial
  - unknown
- Use only the following text fields:
  - bibliography.title
  - content.abstract
- Do not use tags, notes, seed_query, source fields, raw payloads, or fulltext.

Required split:
- train = 70%
- validation = 15%
- test = 15%
- stratified by label
- fixed random_state = 42
- split only after deduped normalized dataset is ready
- avoid leakage by respecting canonical_id when available

Implement:
1. training_dataset.py
   - load normalized articles.jsonl
   - keep only relevant/irrelevant
   - build:
     - title
     - abstract
     - title_abstract_text
     - label
   - save clean baseline dataset

2. splitting.py
   - create reproducible train/val/test split
   - stratified by label
   - save split files and manifest
   - verify no overlap across splits by record_id and canonical_id

3. features.py
   - implement TF-IDF features
   - support text modes:
     - title
     - abstract
     - title_abstract
   - default baseline mode = title_abstract
   - fit vectorizer on train only

4. train_baseline.py
   - train Logistic Regression baseline
   - train Linear SVM baseline
   - save fitted vectorizers and models
   - use same split for both models

5. evaluation.py
   - compute:
     - accuracy
     - precision
     - recall
     - f1
     - confusion matrix
   - save metrics for validation and test
   - save per-record predictions tables

6. cli.py
   - add command:
     vkr-dataset train-baseline --input <articles.jsonl> --workdir <dir> --text-mode title_abstract --random-state 42

Artifacts to save:
- clean dataset
- split files
- split manifest
- fitted vectorizer(s)
- fitted model(s)
- metrics JSON
- confusion matrix JSON
- predictions CSV

Recommended defaults:
- TF-IDF:
  - lowercase=True
  - strip_accents="unicode"
  - ngram_range=(1, 2)
  - min_df=2
  - max_df=0.95
  - sublinear_tf=True
- LogisticRegression:
  - max_iter=2000
  - random_state=42
  - class_weight="balanced" if needed
- LinearSVC:
  - class_weight="balanced" if needed

Do not:
- include partial or unknown
- use fulltext in baseline
- use auto/manual tags
- fit TF-IDF on val/test
- create separate splits for different models

Definition of done:
- one command trains both baselines
- both models are saved
- metrics are saved
- predictions are saved
- pipeline is reproducible
```
