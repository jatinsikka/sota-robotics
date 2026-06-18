# tests/test_fetch.py
import httpx
import pytest

from sota_ingest.fetch import fetch_text, fetch_json


def _client_returning(*responses):
    """Build an httpx.Client whose transport replays the given responses."""
    seq = list(responses)

    def handler(request):
        return seq.pop(0)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_text_returns_body():
    client = _client_returning(httpx.Response(200, text="# hello"))
    assert fetch_text("https://x/readme.md", client=client) == "# hello"


def test_fetch_json_parses_body():
    client = _client_returning(httpx.Response(200, json=[{"task": "Robot Manipulation"}]))
    data = fetch_json("https://x/data.json", client=client)
    assert data == [{"task": "Robot Manipulation"}]


def test_fetch_text_retries_then_succeeds():
    client = _client_returning(
        httpx.Response(503, text="busy"),
        httpx.Response(200, text="ok"),
    )
    assert fetch_text("https://x", client=client, retries=2, backoff=0.0) == "ok"


def test_fetch_text_raises_after_exhausting_retries():
    client = _client_returning(
        httpx.Response(500), httpx.Response(500), httpx.Response(500)
    )
    with pytest.raises(httpx.HTTPStatusError):
        fetch_text("https://x", client=client, retries=2, backoff=0.0)
