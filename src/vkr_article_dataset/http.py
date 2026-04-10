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
    _last_openalex_request_at: float = field(init=False, default=0.0)

    def __post_init__(self) -> None:
        self.session = requests.Session()
        self._last_arxiv_request_at = 0.0
        self._last_openalex_request_at = 0.0
        user_agent = "vkr-article-dataset/0.1"
        if self.settings.contact_email:
            user_agent += f" ({self.settings.contact_email})"
        self.session.headers.update({"User-Agent": user_agent})

    def get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        *,
        openalex: bool = False,
    ) -> dict[str, Any]:
        response = self._request("get", url, params=params, openalex=openalex)
        return response.json()

    def get_text(self, url: str, params: dict[str, Any] | None = None, *, arxiv: bool = False) -> str:
        response = self._request("get", url, params=params, arxiv=arxiv)
        return response.text

    def get_bytes(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        *,
        openalex: bool = False,
    ) -> bytes:
        response = self._request("get", url, params=params, openalex=openalex)
        return response.content

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        arxiv: bool = False,
        openalex: bool = False,
    ):
        if arxiv:
            self._respect_arxiv_delay()

        attempts = 1
        if openalex:
            attempts += max(0, int(self.settings.openalex_max_retries))

        last_error: Exception | None = None
        for attempt_index in range(attempts):
            if openalex:
                self._respect_openalex_delay()
            response = self.session.request(method, url, params=params, timeout=self.settings.timeout_seconds)
            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                last_error = exc
                if not openalex or response.status_code != 429 or attempt_index == attempts - 1:
                    raise
                retry_delay = self._openalex_retry_delay(response, attempt_index)
                time.sleep(retry_delay)
                self._last_openalex_request_at = time.monotonic()
                continue
            if openalex:
                self._last_openalex_request_at = time.monotonic()
            return response

        if last_error is not None:
            raise last_error
        raise RuntimeError("HTTP request failed without an explicit exception")

    def _respect_arxiv_delay(self) -> None:
        delay = max(0.0, self.settings.arxiv_delay_seconds)
        if delay <= 0:
            return
        elapsed = time.monotonic() - self._last_arxiv_request_at
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_arxiv_request_at = time.monotonic()

    def _respect_openalex_delay(self) -> None:
        delay = max(0.0, self.settings.openalex_delay_seconds)
        if delay <= 0:
            return
        elapsed = time.monotonic() - self._last_openalex_request_at
        if elapsed < delay:
            time.sleep(delay - elapsed)

    def _openalex_retry_delay(self, response, attempt_index: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                pass
        base = max(0.0, self.settings.openalex_retry_backoff_seconds)
        return base * (2 ** attempt_index)
