"""Stage 1: paper -> list[ResultClaim] via Claude Opus 4.8 structured outputs.

No prefill (400s on 4.8). thinking=adaptive. Parse with json.loads. Always
check stop_reason before trusting content."""

import json
from typing import Any

from sota_ingest.agent.prompts import RESULT_CLAIM_SCHEMA, build_cached_system
from sota_ingest.models import Origin, PaperRec, Realm, ResultClaim, VerificationStatus

MODEL = "claude-opus-4-8"
MAX_TOKENS = 16000


def _user_content(paper: PaperRec, paper_text: str | None, file_id: str | None) -> list[dict[str, Any]]:
    """Volatile per-paper content goes in the USER turn (never the cached prefix).
    Prefer a Files-API PDF (file_id) when available; else fall back to text."""
    header = (
        f"Paper: {paper.title}\n"
        f"arXiv: {paper.arxiv_id or 'n/a'}\n"
        f"URL: {paper.url or 'n/a'}\n"
        "Extract every reported benchmark result as claims."
    )
    if file_id is not None:
        return [
            {"type": "document", "source": {"type": "file", "file_id": file_id}},
            {"type": "text", "text": header},
        ]
    body = paper_text if paper_text is not None else (paper.abstract or "")
    return [{"type": "text", "text": header + "\n\n--- PAPER TEXT ---\n" + body}]


def _first_text(message: Any) -> str:
    for block in message.content:
        if block.type == "text":
            return block.text
    raise RuntimeError("no text block in response")


def extract_claims(
    client: Any,
    paper: PaperRec,
    *,
    paper_text: str | None = None,
    file_id: str | None = None,
) -> list[ResultClaim]:
    """Call Claude to extract ResultClaims from one paper.

    `client` is an anthropic.Anthropic (or a fake in tests). Supply EITHER
    paper_text OR a Files-API file_id (for a PDF)."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        thinking={"type": "adaptive"},
        system=build_cached_system(),
        output_config={"format": RESULT_CLAIM_SCHEMA},
        messages=[{"role": "user", "content": _user_content(paper, paper_text, file_id)}],
    )

    if response.stop_reason == "refusal":
        raise RuntimeError(f"extractor refused (stop_reason=refusal) for {paper.url}")
    if response.stop_reason == "max_tokens":
        raise RuntimeError(f"extractor truncated (stop_reason=max_tokens) for {paper.url}")

    data = json.loads(_first_text(response))
    claims: list[ResultClaim] = []
    for raw in data.get("claims", []):
        claims.append(
            ResultClaim(
                method_slug=raw["method_slug"],
                benchmark_slug=raw["benchmark_slug"],
                task_slug=raw.get("task_slug"),
                metric=raw["metric"],
                metric_value=raw.get("metric_value"),
                eval_conditions=raw.get("eval_conditions") or {},
                realm=Realm(raw.get("realm", "sim")),
                origin=Origin(raw.get("origin", "public_reproducible")),
                source_url=raw.get("source_url") or (paper.url or ""),
                result_date=raw.get("result_date"),
                # gate-owned — never set by the model:
                confidence=None,
                verification_status=VerificationStatus.PENDING,
            )
        )
    return claims
