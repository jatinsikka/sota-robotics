"""Thin retrying HTTP layer shared by both Phase-0 feeds.

The only network-touching module besides db.py. A caller may inject an
httpx.Client (tests pass a MockTransport-backed one); otherwise we make a
short-lived client per call. retries/backoff are explicit so tests run fast.
"""
import time
from typing import Any

import httpx

DEFAULT_HEADERS = {"User-Agent": "sota-robotics-backfill/0.1 (+https://github.com/jatinsikka)"}
DEFAULT_TIMEOUT = 30.0


def _get(url: str, client: httpx.Client, retries: int, backoff: float) -> httpx.Response:
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        resp = client.get(url, headers=DEFAULT_HEADERS, timeout=DEFAULT_TIMEOUT, follow_redirects=True)
        try:
            resp.raise_for_status()
            return resp
        except httpx.HTTPStatusError as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(backoff)
                continue
            raise
    assert last_exc is not None
    raise last_exc


def fetch_text(url: str, client: httpx.Client | None = None, retries: int = 3, backoff: float = 1.0) -> str:
    if client is not None:
        return _get(url, client, retries, backoff).text
    with httpx.Client() as owned:
        return _get(url, owned, retries, backoff).text


def fetch_json(url: str, client: httpx.Client | None = None, retries: int = 3, backoff: float = 1.0) -> Any:
    if client is not None:
        return _get(url, client, retries, backoff).json()
    with httpx.Client() as owned:
        return _get(url, owned, retries, backoff).json()
