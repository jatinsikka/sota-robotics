# tests/test_backfill.py
import json

from sota_ingest.backfill import run_pwc_backfill, run_awesome_backfill, BackfillStats
from sota_ingest.db import SotaWriter
from sota_ingest.awesome_lists import AwesomeSource


def test_run_pwc_backfill_upserts_filtered_claims(fixtures_dir, fake_db):
    data = json.loads((fixtures_dir / "pwc_robotics_tasks.json").read_text())

    def fake_fetch_json(url, **kw):
        return data

    writer = SotaWriter(fake_db())
    stats = run_pwc_backfill(writer, run_id="run-1", fetch_json=fake_fetch_json, source_url="https://hf/pwc.json")

    # VQAv2 dropped -> 2 results stored (LIBERO + Habitat ObjectNav)
    assert stats.results_upserted == 2
    stored = writer.conn._store_rows.get("results", [])
    assert len(stored) == 2
    assert all(r["verification_status"] == "held" for r in stored)


def test_run_pwc_backfill_is_idempotent(fixtures_dir, fake_db):
    data = json.loads((fixtures_dir / "pwc_robotics_tasks.json").read_text())
    writer = SotaWriter(fake_db())
    run_pwc_backfill(writer, "run-1", fetch_json=lambda url, **kw: data, source_url="u")
    run_pwc_backfill(writer, "run-2", fetch_json=lambda url, **kw: data, source_url="u")
    assert len(writer.conn._store_rows.get("results", [])) == 2  # not 4


def test_run_awesome_backfill_creates_papers_and_code(fixtures_dir, fake_db):
    md = (fixtures_dir / "awesome_embodied_ai.md").read_text()
    src = AwesomeSource("test-list", "https://raw/x/README.md", "CC-BY-SA-4.0")

    writer = SotaWriter(fake_db())
    stats = run_awesome_backfill(writer, [src], fetch_text=lambda url, **kw: md)

    papers = writer.conn._store_rows.get("papers", [])
    code = writer.conn._store_rows.get("code", [])
    # 4 list items with links -> 4 papers; 2 have github repos
    assert len(papers) == 4
    assert len(code) == 2
    assert stats.papers_upserted == 4
    assert stats.code_upserted == 2
    # CC-BY-SA attribution propagated onto code rows
    assert all(c["license"] == "CC-BY-SA-4.0" for c in code)


def test_run_awesome_backfill_dedupes_repeated_paper(fixtures_dir, fake_db):
    md = (fixtures_dir / "awesome_vla.md").read_text()
    src = AwesomeSource("a", "https://raw/a", "CC-BY-SA-4.0")
    writer = SotaWriter(fake_db())
    # run the SAME source twice -> arxiv-id dedupe means no duplicate papers
    run_awesome_backfill(writer, [src, src], fetch_text=lambda url, **kw: md)
    arxiv_ids = [p["arxiv_id"] for p in writer.conn._store_rows.get("papers", [])]
    assert sorted(arxiv_ids) == sorted(set(arxiv_ids))


def test_backfill_stats_sum():
    s = BackfillStats(results_upserted=2, papers_upserted=4, code_upserted=2)
    assert s.total() == 8
