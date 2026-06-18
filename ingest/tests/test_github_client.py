import json
from pathlib import Path

from sota_ingest.sources.github_client import CODE_COLUMNS, parse_repos

FIXTURE = Path(__file__).parent / "fixtures" / "github_repos.json"


def test_parses_non_null_repos():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    rows = parse_repos(payload)
    # r2 is null (e.g. renamed/deleted repo) -> skipped.
    assert len(rows) == 2
    urls = {r["repo_url"] for r in rows}
    assert urls == {
        "https://github.com/huggingface/lerobot",
        "https://github.com/openvla/openvla",
    }


def test_maps_stars_license_and_last_commit():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    rows = parse_repos(payload)
    lerobot = next(r for r in rows if r["repo_url"].endswith("lerobot"))
    assert lerobot["stars"] == 9800
    assert lerobot["license"] == "Apache-2.0"
    assert lerobot["last_commit"] == "2026-06-17"


def test_missing_license_becomes_none():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    rows = parse_repos(payload)
    openvla = next(r for r in rows if r["repo_url"].endswith("openvla"))
    assert openvla["license"] is None


def test_release_signal_carried_alongside():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    rows = parse_repos(payload)
    lerobot = next(r for r in rows if r["repo_url"].endswith("lerobot"))
    assert lerobot["release_count"] == 14
    assert lerobot["latest_release"] == "v0.4.0"


def test_writer_subset_is_only_code_columns():
    # Keys destined for db.upsert_code must be a subset of the code table.
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    rows = parse_repos(payload)
    for r in rows:
        subset = {k: v for k, v in r.items() if k in CODE_COLUMNS}
        assert set(subset).issubset(CODE_COLUMNS)
        assert "repo_url" in subset
