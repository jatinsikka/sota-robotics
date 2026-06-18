from typing import Any, Literal

import httpx
from pydantic import BaseModel

API_BASE = "https://huggingface.co/api"
HUB_BASE = "https://huggingface.co"
ROBOTICS_TAG = "robotics"

# Watchlist of robotics orgs to scan (in addition to the global robotics tag).
ORG_WATCHLIST = (
    "physical-intelligence",
    "lerobot",
    "nvidia",
    "google-deepmind",
)

HfKind = Literal["model", "dataset"]


class HfRecord(BaseModel):
    repo_id: str
    kind: HfKind
    author: str | None = None
    downloads: int = 0
    likes: int = 0
    tags: list[str] = []
    last_modified: str | None = None  # ISO date string
    url: str


def _url(repo_id: str, kind: HfKind) -> str:
    if kind == "dataset":
        return f"{HUB_BASE}/datasets/{repo_id}"
    return f"{HUB_BASE}/{repo_id}"


def parse_hf_listing(data: list[dict[str, Any]], kind: HfKind) -> list[HfRecord]:
    """Pure parser: HF Hub list JSON -> robotics-tagged HfRecords.

    Drops anything not tagged 'robotics' so non-robotics assets returned by
    an org scan don't pollute the adoption signal. downloads/likes are the
    adoption signal we keep.
    """
    recs: list[HfRecord] = []
    for item in data:
        tags = list(item.get("tags") or [])
        if ROBOTICS_TAG not in tags and item.get("pipeline_tag") != ROBOTICS_TAG:
            continue
        if ROBOTICS_TAG not in tags:
            tags.append(ROBOTICS_TAG)
        repo_id = item["id"]
        last_mod = item.get("lastModified")
        recs.append(
            HfRecord(
                repo_id=repo_id,
                kind=kind,
                author=item.get("author"),
                downloads=int(item.get("downloads") or 0),
                likes=int(item.get("likes") or 0),
                tags=tags,
                last_modified=last_mod[:10] if last_mod else None,
                url=_url(repo_id, kind),
            )
        )
    return recs


def fetch_raw(
    kind: HfKind,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    """Thin HTTP wrapper (untested): list robotics-tagged models/datasets."""
    owns = client is None
    client = client or httpx.Client(timeout=30.0)
    endpoint = f"{API_BASE}/{'datasets' if kind == 'dataset' else 'models'}"
    try:
        resp = client.get(
            endpoint,
            params={
                "filter": ROBOTICS_TAG,
                "sort": "lastModified",
                "direction": "-1",
                "limit": 100,
            },
        )
        resp.raise_for_status()
        return resp.json()
    finally:
        if owns:
            client.close()


def fetch() -> list[HfRecord]:
    """Convenience: fetch models + datasets and parse. Used by orchestrator."""
    recs: list[HfRecord] = []
    recs.extend(parse_hf_listing(fetch_raw("model"), kind="model"))
    recs.extend(parse_hf_listing(fetch_raw("dataset"), kind="dataset"))
    return recs
