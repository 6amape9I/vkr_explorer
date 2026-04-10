from vkr_article_dataset.config import Settings
from vkr_article_dataset.http import HttpClient


def test_http_client_initializes_session_for_slots_dataclass() -> None:
    client = HttpClient(settings=Settings())

    assert client.session is not None
    assert client._last_arxiv_request_at == 0.0
