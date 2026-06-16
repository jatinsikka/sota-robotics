import re
from typing import Any

from sota_ingest.models import ResultClaim, VerificationStatus


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")


def _to_float(raw: str | None) -> float | None:
    if raw is None:
        return None
    m = re.search(r"-?\d+(\.\d+)?", str(raw))
    return float(m.group()) if m else None


def parse_evaluation_tables(data: list[dict[str, Any]]) -> list[ResultClaim]:
    """Map PWC sota-extractor evaluation-tables JSON -> ResultClaims.

    Archive numbers are stale/self-reported, so every claim is HELD
    (never auto-published) for later re-verification.
    """
    claims: list[ResultClaim] = []
    for task_block in data:
        task_slug = _slug(task_block.get("task", "")) or None
        for ds in task_block.get("datasets", []):
            bench_slug = _slug(ds["dataset"])
            sota = ds.get("sota") or {}
            metric_names = sota.get("metrics") or ["score"]
            primary_metric = _slug(metric_names[0])
            for row in sota.get("rows", []):
                metrics = row.get("metrics", {})
                raw_val = metrics.get(metric_names[0]) if metric_names else None
                claims.append(
                    ResultClaim(
                        method_slug=_slug(row["model_name"]),
                        benchmark_slug=bench_slug,
                        task_slug=task_slug,
                        metric=primary_metric,
                        metric_value=_to_float(raw_val),
                        eval_conditions={"source": "pwc_archive"},
                        source_url=row.get("paper_url") or "",
                        verification_status=VerificationStatus.HELD,
                        skeptic_notes="Imported from frozen PWC archive (Sep 2025); unverified.",
                        confidence=None,
                    )
                )
    return claims
