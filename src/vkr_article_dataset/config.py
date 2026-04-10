from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class Settings:
    contact_email: str | None = None
    openalex_api_key: str | None = None
    arxiv_delay_seconds: float = 3.0
    timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            contact_email=_clean_env("CONTACT_EMAIL"),
            openalex_api_key=_clean_env("OPENALEX_API_KEY"),
            arxiv_delay_seconds=float(os.getenv("ARXIV_DELAY_SECONDS", "3.0")),
            timeout_seconds=float(os.getenv("HTTP_TIMEOUT_SECONDS", "30.0")),
        )


def _clean_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None
