"""Stage 2: refute each extracted claim. Claude Opus 4.8, structured outputs,
no prefill, adaptive thinking, stop_reason-checked, json.loads-parsed."""

import json
from typing import Any

from pydantic import BaseModel

from sota_ingest.agent.prompts import SKEPTIC_SYSTEM, VERDICT_SCHEMA
from sota_ingest.models import ResultClaim

MODEL = "claude-opus-4-8"
MAX_TOKENS = 8000


class Verdict(BaseModel):
    claim_index: int
    publishable: bool
    confidence: float
    skeptic_notes: str


def _render_claims(claims: list[ResultClaim]) -> str:
    lines = []
    for i, c in enumerate(claims):
        lines.append(
            f"[{i}] method={c.method_slug} benchmark={c.benchmark_slug} "
            f"metric={c.metric} value={c.metric_value} realm={c.realm.value} "
            f"origin={c.origin.value} eval_conditions={json.dumps(c.eval_conditions, sort_keys=True)}"
        )
    return "\n".join(lines)


def _first_text(message: Any) -> str:
    for block in message.content:
        if block.type == "text":
            return block.text
    raise RuntimeError("no text block in response")


def refute_claims(client: Any, paper: ResultClaim | Any, claims: list[ResultClaim]) -> list[Verdict]:
    """Return one Verdict per claim. Skips the API entirely for an empty list."""
    if not claims:
        return []

    paper_hdr = f"Paper: {getattr(paper, 'title', '')}\nURL: {getattr(paper, 'url', '') or ''}"
    user_text = (
        paper_hdr
        + "\n\nClaims to refute (0-based index):\n"
        + _render_claims(claims)
        + "\n\nReturn one verdict per claim_index."
    )

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        thinking={"type": "adaptive"},
        system=SKEPTIC_SYSTEM,
        output_config={"format": VERDICT_SCHEMA},
        messages=[{"role": "user", "content": user_text}],
    )

    if response.stop_reason == "refusal":
        raise RuntimeError("skeptic refused (stop_reason=refusal)")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("skeptic truncated (stop_reason=max_tokens)")

    data = json.loads(_first_text(response))
    return [Verdict(**v) for v in data.get("verdicts", [])]
