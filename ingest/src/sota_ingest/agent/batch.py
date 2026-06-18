"""Daily pass via the Message Batches API (50% off).

build_batch_requests is pure (papers -> request payloads, all sharing the
cached system prefix so it caches across the batch). submit_batch creates the
batch. collect_batch_results reads succeeded results back (within the 29-day
retention window), parses each with json.loads, and maps custom_id ->
list[ResultClaim]; errored/expired are surfaced separately."""

import json
from typing import Any

from sota_ingest.agent.extractor import MAX_TOKENS, MODEL, _user_content
from sota_ingest.agent.prompts import RESULT_CLAIM_SCHEMA, build_cached_system
from sota_ingest.models import Origin, PaperRec, Realm, ResultClaim, VerificationStatus

# re-export so callers/tests import MODEL from here too
__all__ = [
    "MODEL",
    "paper_custom_id",
    "build_batch_requests",
    "submit_batch",
    "collect_batch_results",
]


def paper_custom_id(paper: PaperRec) -> str:
    """Deterministic, recoverable per-paper id (<=64 chars, batch-API safe)."""
    key = paper.arxiv_id or paper.url or paper.title
    safe = "".join(ch if ch.isalnum() else "-" for ch in key).strip("-")
    return f"paper-{safe}"[:64]


def build_batch_requests(
    papers: list[PaperRec],
    *,
    paper_texts: dict[str, str] | None = None,
    file_ids: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """One batch request per paper. Each carries the SAME cached system prefix
    + the structured-output schema. Volatile per-paper content is in the user
    turn (no prefill). `paper_texts`/`file_ids` are keyed by arxiv_id|url|title
    (the same key paper_custom_id derives from)."""
    paper_texts = paper_texts or {}
    file_ids = file_ids or {}
    system = build_cached_system()
    requests: list[dict[str, Any]] = []

    for paper in papers:
        key = paper.arxiv_id or paper.url or paper.title
        params: dict[str, Any] = {
            "model": MODEL,
            "max_tokens": MAX_TOKENS,
            "thinking": {"type": "adaptive"},
            "system": system,
            "output_config": {"format": RESULT_CLAIM_SCHEMA},
            "messages": [
                {
                    "role": "user",
                    "content": _user_content(
                        paper, paper_texts.get(key), file_ids.get(key)
                    ),
                }
            ],
        }
        requests.append({"custom_id": paper_custom_id(paper), "params": params})

    return requests


def submit_batch(client: Any, requests: list[dict[str, Any]]) -> Any:
    """Create the batch. Returns the batch object (carries .id / processing_status)."""
    return client.messages.batches.create(requests=requests)


def _first_text(message: Any) -> str:
    for block in message.content:
        if block.type == "text":
            return block.text
    raise RuntimeError("no text block in batch result message")


def _to_claims(claims_json: str) -> list[ResultClaim]:
    data = json.loads(claims_json)
    out: list[ResultClaim] = []
    for raw in data.get("claims", []):
        out.append(
            ResultClaim(
                method_slug=raw["method_slug"],
                benchmark_slug=raw["benchmark_slug"],
                task_slug=raw.get("task_slug"),
                metric=raw["metric"],
                metric_value=raw.get("metric_value"),
                eval_conditions=raw.get("eval_conditions") or {},
                realm=Realm(raw.get("realm", "sim")),
                origin=Origin(raw.get("origin", "public_reproducible")),
                source_url=raw.get("source_url") or "",
                result_date=raw.get("result_date"),
                confidence=None,
                verification_status=VerificationStatus.PENDING,
            )
        )
    return out


def collect_batch_results(
    client: Any, batch_id: str
) -> tuple[dict[str, list[ResultClaim]], dict[str, str]]:
    """Iterate batch results. Returns (ok, errors):
    ok[custom_id]   -> parsed ResultClaims for succeeded requests
    errors[custom_id] -> error type string for errored/expired requests."""
    ok: dict[str, list[ResultClaim]] = {}
    errors: dict[str, str] = {}

    for result in client.messages.batches.results(batch_id):
        rtype = result.result.type
        if rtype == "succeeded":
            msg = result.result.message
            if msg.stop_reason in ("refusal", "max_tokens"):
                errors[result.custom_id] = f"stop_{msg.stop_reason}"
                continue
            ok[result.custom_id] = _to_claims(_first_text(msg))
        elif rtype == "errored":
            errors[result.custom_id] = result.result.error.type
        else:  # canceled / expired
            errors[result.custom_id] = rtype

    return ok, errors
