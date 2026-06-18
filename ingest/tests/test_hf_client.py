import json
from pathlib import Path

from sota_ingest.sources.hf_client import HfRecord, parse_hf_listing

FIXTURE = Path(__file__).parent / "fixtures" / "hf_models.json"


def test_parses_only_robotics_tagged_records():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    recs = parse_hf_listing(data, kind="model")
    # The text-generation entry has no 'robotics' tag -> dropped.
    assert len(recs) == 2
    assert all(isinstance(r, HfRecord) for r in recs)
    assert all("robotics" in r.tags for r in recs)


def test_captures_adoption_signal():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    recs = parse_hf_listing(data, kind="model")
    pi0 = next(r for r in recs if r.repo_id == "physical-intelligence/pi0")
    assert pi0.downloads == 18342
    assert pi0.likes == 540
    assert pi0.kind == "model"
    assert pi0.url == "https://huggingface.co/physical-intelligence/pi0"


def test_last_modified_date_truncated_to_iso():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    recs = parse_hf_listing(data, kind="model")
    pi0 = next(r for r in recs if r.repo_id == "physical-intelligence/pi0")
    assert pi0.last_modified == "2026-06-14"


def test_dataset_kind_builds_dataset_url():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    recs = parse_hf_listing(data, kind="dataset")
    ds = next(r for r in recs if r.repo_id == "lerobot/aloha_static_coffee")
    assert ds.url == "https://huggingface.co/datasets/lerobot/aloha_static_coffee"
