"""DB writer for gated claims. Resolves slugs->ids and builds upsert rows via
Plan 1's build_result_row + CONFLICT_TARGET. The pure row-assembly seam
(build_upsert_rows) is unit-tested; the live upsert (upsert_results) executes
those rows through a Supabase client/executor supplied by the cron entrypoint.

A method may be new (not yet in `methods`); resolving/creating method ids is
the caller's job (it owns the DB connection) — build_upsert_rows takes the
resolved maps so it stays pure and testable. Benchmarks must already exist in
the seeded taxonomy; an unknown benchmark_slug is skipped (can't FK it)."""

from typing import Any, Callable

from sota_ingest.models import ResultClaim
from sota_ingest.upsert import CONFLICT_TARGET, build_result_row


def build_upsert_rows(
    claims: list[ResultClaim],
    *,
    method_ids: dict[str, int],
    benchmark_ids: dict[str, int],
    task_ids: dict[str, int],
    paper_id: int | None,
    code_id: int | None,
    run_id: str,
) -> list[dict[str, Any]]:
    """Pure: gated claims + resolved id maps -> upsert payload rows.

    Skips a claim whose benchmark_slug isn't in the seeded taxonomy (no FK) or
    whose method_slug has no resolved id."""
    rows: list[dict[str, Any]] = []
    for claim in claims:
        benchmark_id = benchmark_ids.get(claim.benchmark_slug)
        method_id = method_ids.get(claim.method_slug)
        if benchmark_id is None or method_id is None:
            continue
        task_id = task_ids.get(claim.task_slug) if claim.task_slug else None
        rows.append(
            build_result_row(
                claim,
                method_id=method_id,
                benchmark_id=benchmark_id,
                task_id=task_id,
                paper_id=paper_id,
                code_id=code_id,
                run_id=run_id,
            )
        )
    return rows


def upsert_results(execute: Callable[[list[dict[str, Any]]], None], rows: list[dict[str, Any]]) -> int:
    """Execute the upsert. `execute` is supplied by the cron entrypoint and wraps
    a Supabase service-role upsert with on_conflict=CONFLICT_TARGET (idempotent).
    Returns the number of rows submitted."""
    if not rows:
        return 0
    execute(rows)
    return len(rows)


# Surfaced so the cron entrypoint configures the Supabase upsert with the right key.
ON_CONFLICT = ",".join(CONFLICT_TARGET)
