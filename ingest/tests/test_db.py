# tests/test_db.py
import pytest

from sota_ingest.db import SotaWriter, CONFLICT_ON
from sota_ingest.models import PaperRec, ResultClaim, VerificationStatus
from sota_ingest.upsert import CONFLICT_TARGET


def _inserts(calls, table):
    """Calls that INSERT into <table> (vs. selects)."""
    return [c for c in calls if c["sql"].lower().startswith(f"insert into {table}")]


def test_conflict_on_matches_plan1_target():
    # db.py must upsert results on EXACTLY the Plan 1 constraint columns.
    assert CONFLICT_ON == ",".join(CONFLICT_TARGET)
    assert CONFLICT_ON == "method_id,benchmark_id,eval_conditions_hash"


def test_resolve_method_creates_when_absent(fake_db):
    w = SotaWriter(fake_db())
    mid = w.resolve_method("openvla-oft")
    assert isinstance(mid, int)
    # second call returns the SAME id (idempotent: insert no-ops, select hits)
    assert w.resolve_method("openvla-oft") == mid
    # exactly one row landed in methods
    assert len(w.conn._store_rows.get("methods", [])) == 1


def test_resolve_method_slugifies(fake_db):
    w = SotaWriter(fake_db())
    w.resolve_method("OpenVLA OFT")
    ins = _inserts(w.conn.calls, "methods")
    # slug param is the slugified form
    assert ins[0]["params"][0] == "openvla-oft"


def test_resolve_benchmark_links_domain_when_known(fake_db):
    seed = {("domains", "humanoid-vla-manip"): {"id": 7, "slug": "humanoid-vla-manip"}}
    w = SotaWriter(fake_db(seed))
    bid = w.resolve_benchmark("robocasa", domain_slug="humanoid-vla-manip")
    assert isinstance(bid, int)
    stored = w.conn._store_rows["benchmarks"][0]
    assert stored["domain_id"] == 7


def test_resolve_benchmark_without_domain_is_ok(fake_db):
    w = SotaWriter(fake_db())
    bid = w.resolve_benchmark("simplerenv", domain_slug=None)
    assert isinstance(bid, int)
    assert w.conn._store_rows["benchmarks"][0]["domain_id"] is None


def test_resolve_paper_dedupes_on_arxiv_id(fake_db):
    w = SotaWriter(fake_db())
    p = PaperRec(arxiv_id="2406.09246", title="OpenVLA", url="https://arxiv.org/abs/2406.09246")
    pid = w.resolve_paper(p)
    assert w.resolve_paper(p) == pid
    assert len(w.conn._store_rows.get("papers", [])) == 1


def test_resolve_code_dedupes_on_repo_url(fake_db):
    w = SotaWriter(fake_db())
    cid = w.resolve_code("https://github.com/openvla/openvla", license="CC-BY-SA-4.0")
    assert w.resolve_code("https://github.com/openvla/openvla") == cid
    assert len(w.conn._store_rows.get("code", [])) == 1


def test_upsert_result_uses_build_result_row_and_conflict_target(fake_db):
    w = SotaWriter(fake_db())
    claim = ResultClaim(
        method_slug="openvla-oft",
        benchmark_slug="libero",
        metric="success_rate",
        metric_value=97.1,
        eval_conditions={"source": "pwc_archive"},
        source_url="https://arxiv.org/abs/2502.19645",
        verification_status=VerificationStatus.HELD,
    )
    w.upsert_result(claim, method_id=1, benchmark_id=2, task_id=None, paper_id=None, code_id=None, run_id="run-x")
    call = next(c for c in w.conn.calls if c["sql"].lower().startswith("insert into results"))
    # upsert targets EXACTLY the Plan 1 constraint columns
    assert f"on conflict ({CONFLICT_ON})".lower() in call["sql"].lower()
    assert "do update set" in call["sql"].lower()
    stored = w.conn._store_rows["results"][0]
    assert stored["method_id"] == 1 and stored["benchmark_id"] == 2
    assert stored["verification_status"] == "held"
    assert stored["ingested_run_id"] == "run-x"
    # eval_conditions_hash present (idempotency key from Plan 1)
    assert len(stored["eval_conditions_hash"]) == 64


def test_upsert_result_is_idempotent_across_runs(fake_db):
    conn = fake_db()
    w = SotaWriter(conn)
    claim = ResultClaim(
        method_slug="m", benchmark_slug="b", metric="success_rate",
        metric_value=90.0, eval_conditions={"source": "pwc_archive"}, source_url="u",
    )
    w.upsert_result(claim, 1, 2, None, None, None, "run-1")
    w.upsert_result(claim, 1, 2, None, None, None, "run-2")
    # same conflict key -> one stored results row, not two
    stored = conn._store_rows.get("results", [])
    assert len(stored) == 1
    # second run's run_id overwrote in place (DO UPDATE)
    assert stored[0]["ingested_run_id"] == "run-2"
