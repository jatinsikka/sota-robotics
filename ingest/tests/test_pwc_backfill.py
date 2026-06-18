# tests/test_pwc_backfill.py
import json

from sota_ingest.pwc_backfill import filter_robotics_tasks, claims_from_pwc
from sota_ingest.models import VerificationStatus


def test_filter_keeps_only_robotics_tasks(fixtures_dir):
    data = json.loads((fixtures_dir / "pwc_robotics_tasks.json").read_text())
    kept = filter_robotics_tasks(data)
    tasks = {b["task"] for b in kept}
    assert "Robot Manipulation" in tasks
    assert "Visual Navigation" in tasks      # navigation is in-scope
    assert "Visual Question Answering" not in tasks


def test_claims_from_pwc_are_held_and_filtered(fixtures_dir):
    data = json.loads((fixtures_dir / "pwc_robotics_tasks.json").read_text())
    claims = claims_from_pwc(data)
    # VQAv2 row dropped -> 2 claims (LIBERO + Habitat ObjectNav)
    assert len(claims) == 2
    assert all(c.verification_status == VerificationStatus.HELD for c in claims)
    slugs = {c.benchmark_slug for c in claims}
    assert "libero" in slugs and "habitat-objectnav" in slugs


def test_empty_input_yields_no_claims():
    assert claims_from_pwc([]) == []
