# tests/test_db.py
import pytest

from sota_ingest.db import SotaWriter, CONFLICT_ON
from sota_ingest.models import PaperRec, ResultClaim, VerificationStatus
from sota_ingest.upsert import CONFLICT_TARGET


def test_conflict_on_matches_plan1_target():
    # db.py must upsert results on EXACTLY the Plan 1 constraint columns.
    assert CONFLICT_ON == ",".join(CONFLICT_TARGET)
    assert CONFLICT_ON == "method_id,benchmark_id,eval_conditions_hash"


def test_resolve_method_creates_when_absent(fake_supabase):
    w = SotaWriter(fake_supabase())
    mid = w.resolve_method("openvla-oft")
    assert isinstance(mid, int)
    # second call returns the SAME id (idempotent: select hit, no new insert)
    assert w.resolve_method("openvla-oft") == mid
    inserts = [c for c in w.client.calls if c["table"] == "methods" and c["op"] == "insert"]
    assert len(inserts) == 1


def test_resolve_benchmark_links_domain_when_known(fake_supabase):
    seed = {("domains", "humanoid-vla-manip"): {"id": 7, "slug": "humanoid-vla-manip"}}
    w = SotaWriter(fake_supabase(seed))
    bid = w.resolve_benchmark("robocasa", domain_slug="humanoid-vla-manip")
    assert isinstance(bid, int)
    bench_insert = next(c for c in w.client.calls if c["table"] == "benchmarks" and c["op"] == "insert")
    assert bench_insert["payload"]["domain_id"] == 7


def test_resolve_benchmark_without_domain_is_ok(fake_supabase):
    w = SotaWriter(fake_supabase())
    bid = w.resolve_benchmark("simplerenv", domain_slug=None)
    assert isinstance(bid, int)


def test_resolve_paper_dedupes_on_arxiv_id(fake_supabase):
    w = SotaWriter(fake_supabase())
    p = PaperRec(arxiv_id="2406.09246", title="OpenVLA", url="https://arxiv.org/abs/2406.09246")
    pid = w.resolve_paper(p)
    assert w.resolve_paper(p) == pid
    inserts = [c for c in w.client.calls if c["table"] == "papers" and c["op"] == "insert"]
    assert len(inserts) == 1


def test_resolve_code_dedupes_on_repo_url(fake_supabase):
    w = SotaWriter(fake_supabase())
    cid = w.resolve_code("https://github.com/openvla/openvla", license="CC-BY-SA-4.0")
    assert w.resolve_code("https://github.com/openvla/openvla") == cid


def test_upsert_result_uses_build_result_row_and_conflict_target(fake_supabase):
    w = SotaWriter(fake_supabase())
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
    call = next(c for c in w.client.calls if c["table"] == "results")
    assert call["op"] == "upsert"
    assert call["on_conflict"] == "method_id,benchmark_id,eval_conditions_hash"
    row = call["payload"][0] if isinstance(call["payload"], list) else call["payload"]
    assert row["method_id"] == 1 and row["benchmark_id"] == 2
    assert row["verification_status"] == "held"
    assert row["ingested_run_id"] == "run-x"
    # eval_conditions_hash present (idempotency key from Plan 1)
    assert len(row["eval_conditions_hash"]) == 64


def test_upsert_result_is_idempotent_across_runs(fake_supabase):
    client = fake_supabase()
    w = SotaWriter(client)
    claim = ResultClaim(
        method_slug="m", benchmark_slug="b", metric="success_rate",
        metric_value=90.0, eval_conditions={"source": "pwc_archive"}, source_url="u",
    )
    w.upsert_result(claim, 1, 2, None, None, None, "run-1")
    w.upsert_result(claim, 1, 2, None, None, None, "run-2")
    # same conflict key -> one stored results row, not two
    stored = client._store.get("results", [])
    assert len(stored) == 1
