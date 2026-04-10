from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class Settings:
    contact_email: str | None = None
    openalex_api_key: str | None = None
    openalex_delay_seconds: float = 1.0
    openalex_max_retries: int = 3
    openalex_retry_backoff_seconds: float = 5.0
    arxiv_delay_seconds: float = 3.0
    timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            contact_email=_clean_env("CONTACT_EMAIL"),
            openalex_api_key=_clean_env("OPENALEX_API_KEY"),
            openalex_delay_seconds=float(os.getenv("OPENALEX_DELAY_SECONDS", "1.0")),
            openalex_max_retries=int(os.getenv("OPENALEX_MAX_RETRIES", "3")),
            openalex_retry_backoff_seconds=float(os.getenv("OPENALEX_RETRY_BACKOFF_SECONDS", "5.0")),
            arxiv_delay_seconds=float(os.getenv("ARXIV_DELAY_SECONDS", "3.0")),
            timeout_seconds=float(os.getenv("HTTP_TIMEOUT_SECONDS", "30.0")),
        )


def _clean_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None
