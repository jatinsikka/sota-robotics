from typing import Any

from sota_ingest.models import ResultClaim
from sota_ingest.eval_conditions import canonical_hash

# Postgres unique constraint target on the results table.
CONFLICT_TARGET = ("method_id", "benchmark_id", "eval_conditions_hash")


def build_result_row(
    claim: ResultClaim,
    method_id: int,
    benchmark_id: int,
    task_id: int | None,
    paper_id: int | None,
    code_id: int | None,
    run_id: str,
) -> dict[str, Any]:
    """Build the DB row for an upsert. Pure: resolving slugs->ids is the
    caller's job (DB layer in Plans 3-4). Idempotency key = CONFLICT_TARGET."""
    return {
        "method_id": method_id,
        "benchmark_id": benchmark_id,
        "task_id": task_id,
        "paper_id": paper_id,
        "code_id": code_id,
        "metric": claim.metric,
        "metric_value": claim.metric_value,
        "eval_conditions": claim.eval_conditions,
        "eval_conditions_hash": canonical_hash(claim.eval_conditions),
        "realm": claim.realm.value,
        "origin": claim.origin.value,
        "source_url": claim.source_url,
        "result_date": claim.result_date,
        "confidence": claim.confidence,
        "verification_status": claim.verification_status.value,
        "skeptic_notes": claim.skeptic_notes,
        "ingested_run_id": run_id,
    }
