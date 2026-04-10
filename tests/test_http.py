import requests

from vkr_article_dataset.config import Settings
from vkr_article_dataset.http import HttpClient


def test_http_client_initializes_session_for_slots_dataclass() -> None:
    client = HttpClient(settings=Settings())

    assert client.session is not None
    assert client._last_arxiv_request_at == 0.0
    assert client._last_openalex_request_at == 0.0


class DummyResponse:
    def __init__(self, *, status_code: int = 200, payload=None, headers=None) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error", response=self)

    def json(self):
        return self._payload


class DummySession:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.calls = []
        self.headers = {}

    def request(self, method, url, params=None, timeout=None):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "params": params,
                "timeout": timeout,
            }
        )
        return self.responses.pop(0)


def test_http_client_retries_openalex_429_and_honors_retry_after(monkeypatch) -> None:
    client = HttpClient(
        settings=Settings(
            openalex_delay_seconds=0.0,
            openalex_max_retries=2,
            openalex_retry_backoff_seconds=5.0,
        )
    )
    client.session = DummySession(
        [
            DummyResponse(status_code=429, headers={"Retry-After": "2"}),
            DummyResponse(status_code=200, payload={"results": []}),
        ]
    )
    sleeps = []
    monotonic_values = iter([10.0, 10.0, 12.0, 12.0])
    monkeypatch.setattr("vkr_article_dataset.http.time.sleep", lambda value: sleeps.append(value))
    monkeypatch.setattr("vkr_article_dataset.http.time.monotonic", lambda: next(monotonic_values))

    payload = client.get_json("https://api.openalex.org/works", openalex=True)

    assert payload == {"results": []}
    assert len(client.session.calls) == 2
    assert sleeps == [2.0]


def test_http_client_respects_openalex_delay_between_requests(monkeypatch) -> None:
    client = HttpClient(
        settings=Settings(
            openalex_delay_seconds=1.0,
            openalex_max_retries=0,
        )
    )
    client.session = DummySession([DummyResponse(status_code=200, payload={"ok": True})])
    client._last_openalex_request_at = 10.0
    sleeps = []
    monotonic_values = iter([10.4, 12.0])
    monkeypatch.setattr("vkr_article_dataset.http.time.sleep", lambda value: sleeps.append(round(value, 2)))
    monkeypatch.setattr("vkr_article_dataset.http.time.monotonic", lambda: next(monotonic_values))

    payload = client.get_json("https://api.openalex.org/works", openalex=True)

    assert payload == {"ok": True}
    assert sleeps == [0.6]
