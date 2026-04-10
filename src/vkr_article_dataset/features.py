from __future__ import annotations

from typing import Iterable

from sklearn.feature_extraction.text import TfidfVectorizer


TEXT_MODES = {"title", "abstract", "title_abstract"}
DEFAULT_TEXT_MODE = "title_abstract"
DEFAULT_TFIDF_CONFIG = {
    "lowercase": True,
    "strip_accents": "unicode",
    "ngram_range": (1, 2),
    "min_df": 2,
    "max_df": 0.95,
    "sublinear_tf": True,
}


def build_vectorizer(**overrides: object) -> TfidfVectorizer:
    config = dict(DEFAULT_TFIDF_CONFIG)
    config.update(overrides)
    return TfidfVectorizer(**config)


def select_texts(rows: Iterable[dict], text_mode: str) -> list[str]:
    if text_mode not in TEXT_MODES:
        raise ValueError(f"Unsupported text_mode: {text_mode}")
    rows = list(rows)
    if text_mode == "title":
        return [str(row.get("title_text") or row.get("title") or "") for row in rows]
    if text_mode == "abstract":
        return [str(row.get("abstract_text") or row.get("abstract") or "") for row in rows]
    return [str(row.get("title_abstract_text") or "") for row in rows]


def fit_vectorizer(
    rows: Iterable[dict],
    *,
    text_mode: str = DEFAULT_TEXT_MODE,
    **vectorizer_overrides: object,
):
    rows = list(rows)
    vectorizer = build_vectorizer(**vectorizer_overrides)
    matrix = vectorizer.fit_transform(select_texts(rows, text_mode))
    return vectorizer, matrix


def transform_rows(vectorizer: TfidfVectorizer, rows: Iterable[dict], *, text_mode: str = DEFAULT_TEXT_MODE):
    rows = list(rows)
    return vectorizer.transform(select_texts(rows, text_mode))
