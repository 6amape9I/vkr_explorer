from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
from sklearn.linear_model import LogisticRegression


class DiscoveryInference:
    def __init__(
        self,
        *,
        model_path: str | Path,
        vectorizer_path: str | Path,
        threshold: float,
    ) -> None:
        self.model_path = Path(model_path)
        self.vectorizer_path = Path(vectorizer_path)
        self.threshold = float(threshold)
        self.model = joblib.load(self.model_path)
        self.vectorizer = joblib.load(self.vectorizer_path)
        self._validate_model()
        self.feature_names = list(self.vectorizer.get_feature_names_out())

    @property
    def model_name(self) -> str:
        return self.model_path.parent.name or "logreg"

    @property
    def model_version(self) -> str:
        parent = self.model_path.parent.parent
        return parent.name or self.model_path.parent.name

    @property
    def text_mode(self) -> str:
        return "title_abstract"

    def score_candidates(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not candidates:
            return []
        texts = [_candidate_text(candidate) for candidate in candidates]
        matrix = self.vectorizer.transform(texts)
        probabilities = self.model.predict_proba(matrix)[:, 1]
        predictions: list[dict[str, Any]] = []
        for index, candidate in enumerate(candidates):
            score = float(probabilities[index])
            predictions.append(self._prediction_record(candidate, matrix[index], score))
        return predictions

    def _prediction_record(self, candidate: dict[str, Any], row_matrix, score: float) -> dict[str, Any]:
        record = candidate.get("record") or {}
        bibliography = record.get("bibliography") or {}
        content = record.get("content") or {}
        links = record.get("links") or {}
        identifiers = record.get("identifiers") or {}
        predicted_binary = int(score >= self.threshold)
        predicted_label = "predicted_relevant" if predicted_binary else "predicted_irrelevant"
        reason = self._prediction_reason(row_matrix)
        return {
            "run_id": candidate.get("run_id"),
            "record_id": record.get("record_id"),
            "canonical_id": identifiers.get("canonical_id"),
            "query": candidate.get("query"),
            "matched_queries": candidate.get("matched_queries") or [],
            "search_source": candidate.get("search_source"),
            "search_rank": candidate.get("search_rank"),
            "title": bibliography.get("title"),
            "abstract": content.get("abstract"),
            "publication_year": bibliography.get("publication_year"),
            "venue": bibliography.get("venue"),
            "landing_page_url": links.get("landing_page_url"),
            "pdf_url": links.get("pdf_url"),
            "predicted_label": predicted_label,
            "predicted_binary": predicted_binary,
            "score": round(score, 6),
            "threshold": self.threshold,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "text_mode": self.text_mode,
            "prediction_reason": reason,
        }

    def _prediction_reason(self, row_matrix) -> dict[str, list[str]]:
        coefficients = self.model.coef_[0]
        if row_matrix.nnz == 0:
            return {
                "top_positive_terms": [],
                "top_negative_terms": [],
            }

        contributions = []
        for feature_index, value in zip(row_matrix.indices, row_matrix.data, strict=True):
            contributions.append((self.feature_names[feature_index], float(value * coefficients[feature_index])))

        positive_terms = [
            term
            for term, contribution in sorted(
                (item for item in contributions if item[1] > 0),
                key=lambda item: item[1],
                reverse=True,
            )[:5]
        ]
        negative_terms = [
            term
            for term, contribution in sorted(
                (item for item in contributions if item[1] < 0),
                key=lambda item: item[1],
            )[:5]
        ]
        return {
            "top_positive_terms": positive_terms,
            "top_negative_terms": negative_terms,
        }

    def _validate_model(self) -> None:
        if not isinstance(self.model, LogisticRegression):
            raise ValueError("Discovery v1 supports only LogisticRegression models")
        if not hasattr(self.model, "predict_proba") or not hasattr(self.model, "coef_"):
            raise ValueError("Discovery model must provide predict_proba and coef_")


def _candidate_text(candidate: dict[str, Any]) -> str:
    record = candidate.get("record") or {}
    bibliography = record.get("bibliography") or {}
    content = record.get("content") or {}
    title = str(bibliography.get("title") or "").strip()
    abstract = str(content.get("abstract") or "").strip()
    if title and abstract:
        return f"{title}\n\n{abstract}"
    return title or abstract
