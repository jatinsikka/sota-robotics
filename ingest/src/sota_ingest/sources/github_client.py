import os
from typing import Any

import httpx

GRAPHQL_URL = "https://api.github.com/graphql"

# Columns that exist on the `code` table (Plan 1 / db migration 0002).
# Only these keys are forwarded to db.upsert_code(); the rest are signal.
CODE_COLUMNS = ("repo_url", "stars", "last_commit", "license")

# Curated repo watchlist (owner, name) for stars / velocity / releases.
REPO_WATCHLIST = (
    ("huggingface", "lerobot"),
    ("openvla", "openvla"),
    ("NVIDIA", "Isaac-GR00T"),
    ("google-deepmind", "open_x_embodiment"),
)

_REPO_FIELDS = """
    nameWithOwner
    url
    stargazerCount
    licenseInfo { spdxId }
    defaultBranchRef {
      target {
        ... on Commit { history(first: 1) { edges { node { committedDate } } } }
      }
    }
    releases(first: 1, orderBy: {field: CREATED_AT, direction: DESC}) {
      totalCount
      nodes { tagName publishedAt }
    }
"""


def build_query(watchlist: tuple[tuple[str, str], ...] = REPO_WATCHLIST) -> str:
    """Build an aliased multi-repo GraphQL query (one round-trip)."""
    blocks = [
        f'    r{i}: repository(owner: "{owner}", name: "{name}") {{{_REPO_FIELDS}}}'
        for i, (owner, name) in enumerate(watchlist)
    ]
    return "query {\n" + "\n".join(blocks) + "\n}"


def _last_commit(repo: dict[str, Any]) -> str | None:
    ref = repo.get("defaultBranchRef") or {}
    target = ref.get("target") or {}
    edges = ((target.get("history") or {}).get("edges")) or []
    if not edges:
        return None
    date = (edges[0].get("node") or {}).get("committedDate")
    return date[:10] if date else None


def parse_repos(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Pure parser: GitHub GraphQL response -> code rows.

    Each row carries the `code`-column subset (repo_url/stars/last_commit/
    license) plus release signal (release_count/latest_release) for the
    orchestrator to log. Null aliases (deleted/renamed repos) are skipped.
    Natural key for dedup/upsert is repo_url.
    """
    data = payload.get("data") or {}
    rows: list[dict[str, Any]] = []
    for repo in data.values():
        if not repo:
            continue
        license_info = repo.get("licenseInfo") or {}
        releases = repo.get("releases") or {}
        nodes = releases.get("nodes") or []
        latest = nodes[0] if nodes else {}
        rows.append(
            {
                "repo_url": repo["url"],
                "stars": repo.get("stargazerCount"),
                "last_commit": _last_commit(repo),
                "license": license_info.get("spdxId"),
                # signal (not forwarded to db.upsert_code):
                "release_count": releases.get("totalCount", 0),
                "latest_release": latest.get("tagName"),
                "latest_release_at": (latest.get("publishedAt") or "")[:10] or None,
            }
        )
    return rows


def fetch_raw(
    token: str | None = None,
    client: httpx.Client | None = None,
    watchlist: tuple[tuple[str, str], ...] = REPO_WATCHLIST,
) -> dict[str, Any]:
    """Thin HTTP wrapper (untested): POST the GraphQL query.

    token defaults to env GITHUB_TOKEN (required by the GraphQL endpoint).
    """
    token = token or os.environ["GITHUB_TOKEN"]
    owns = client is None
    client = client or httpx.Client(timeout=30.0)
    try:
        resp = client.post(
            GRAPHQL_URL,
            headers={"Authorization": f"Bearer {token}"},
            json={"query": build_query(watchlist)},
        )
        resp.raise_for_status()
        return resp.json()
    finally:
        if owns:
            client.close()


def fetch() -> list[dict[str, Any]]:
    """Convenience: fetch + parse. Used by the orchestrator."""
    return parse_repos(fetch_raw())
