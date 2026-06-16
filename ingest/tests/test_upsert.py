from sota_ingest.models import ResultClaim
from sota_ingest.upsert import build_result_row
from sota_ingest.eval_conditions import canonical_hash


def _claim(**kw):
    base = dict(
        method_slug="m",
        benchmark_slug="b",
        metric="success_rate",
        metric_value=90.0,
        eval_conditions={"split": "test"},
        source_url="u",
    )
    base.update(kw)
    return ResultClaim(**base)


def test_row_includes_eval_conditions_hash():
    row = build_result_row(
        _claim(), method_id=1, benchmark_id=2, task_id=None,
        paper_id=None, code_id=None, run_id="run-123",
    )
    assert row["eval_conditions_hash"] == canonical_hash({"split": "test"})
    assert row["method_id"] == 1 and row["benchmark_id"] == 2
    assert row["ingested_run_id"] == "run-123"
    assert row["verification_status"] == "pending"


def test_same_claim_same_conflict_key():
    a = build_result_row(_claim(), 1, 2, None, None, None, "r1")
    b = build_result_row(
        _claim(eval_conditions={"split": "test"}), 1, 2, None, None, None, "r2"
    )
    key = ("method_id", "benchmark_id", "eval_conditions_hash")
    assert tuple(a[k] for k in key) == tuple(b[k] for k in key)


def test_enum_values_serialized_as_strings():
    row = build_result_row(_claim(), 1, 2, None, None, None, "r1")
    assert row["realm"] == "sim"
    assert row["origin"] == "public_reproducible"
