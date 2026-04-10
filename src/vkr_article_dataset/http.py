from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import requests

from .config import Settings


@dataclass(slots=True)
class HttpClient:
    settings: Settings
    session: requests.Session = field(init=False)
    _last_arxiv_request_at: float = field(init=False, default=0.0)

    def __post_init__(self) -> None:
        self.session = requests.Session()
        self._last_arxiv_request_at = 0.0
        user_agent = "vkr-article-dataset/0.1"
        if self.settings.contact_email:
            user_agent += f" ({self.settings.contact_email})"
        self.session.headers.update({"User-Agent": user_agent})

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self.session.get(url, params=params, timeout=self.settings.timeout_seconds)
        response.raise_for_status()
        return response.json()

    def get_text(self, url: str, params: dict[str, Any] | None = None, *, arxiv: bool = False) -> str:
        if arxiv:
            self._respect_arxiv_delay()
        response = self.session.get(url, params=params, timeout=self.settings.timeout_seconds)
        response.raise_for_status()
        return response.text

    def get_bytes(self, url: str, params: dict[str, Any] | None = None) -> bytes:
        response = self.session.get(url, params=params, timeout=self.settings.timeout_seconds)
        response.raise_for_status()
        return response.content

    def _respect_arxiv_delay(self) -> None:
        delay = max(0.0, self.settings.arxiv_delay_seconds)
        if delay <= 0:
            return
        elapsed = time.monotonic() - self._last_arxiv_request_at
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_arxiv_request_at = time.monotonic()
