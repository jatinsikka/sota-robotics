from sota_ingest.agent.db import build_upsert_rows
from sota_ingest.models import Origin, Realm, ResultClaim, VerificationStatus
from sota_ingest.upsert import CONFLICT_TARGET


def _gated_claim(**kw) -> ResultClaim:
    base = dict(
        method_slug="openvla-oft", benchmark_slug="libero", task_slug="libero-long",
        metric="success_rate", metric_value=97.1, eval_conditions={"split": "test"},
        realm=Realm.SIM, origin=Origin.PUBLIC_REPRODUCIBLE, source_url="u",
        confidence=0.8, verification_status=VerificationStatus.PUBLISHED,
        skeptic_notes="solid",
    )
    base.update(kw)
    return ResultClaim(**base)


def test_build_upsert_rows_resolves_ids_and_carries_run_id():
    method_ids = {"openvla-oft": 11}
    benchmark_ids = {"libero": 2}
    task_ids = {"libero-long": 5}
    rows = build_upsert_rows(
        [_gated_claim()],
        method_ids=method_ids, benchmark_ids=benchmark_ids, task_ids=task_ids,
        paper_id=7, code_id=None, run_id="run-2026-06-18",
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["method_id"] == 11
    assert row["benchmark_id"] == 2
    assert row["task_id"] == 5
    assert row["paper_id"] == 7
    assert row["ingested_run_id"] == "run-2026-06-18"
    assert row["verification_status"] == "published"
    assert row["confidence"] == 0.8
    # idempotency key present (Plan 1 contract)
    for k in CONFLICT_TARGET:
        assert k in row


def test_skips_claims_with_unknown_benchmark_slug():
    # benchmark not in the seeded taxonomy -> skip (can't FK it), don't crash.
    rows = build_upsert_rows(
        [_gated_claim(benchmark_slug="never-seeded")],
        method_ids={"openvla-oft": 11}, benchmark_ids={"libero": 2}, task_ids={},
        paper_id=None, code_id=None, run_id="r",
    )
    assert rows == []


def test_null_task_slug_yields_null_task_id():
    rows = build_upsert_rows(
        [_gated_claim(task_slug=None)],
        method_ids={"openvla-oft": 11}, benchmark_ids={"libero": 2}, task_ids={},
        paper_id=None, code_id=None, run_id="r",
    )
    assert rows[0]["task_id"] is None
