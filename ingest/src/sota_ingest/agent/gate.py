"""PURE gate: apply skeptic verdicts to extracted claims.

Policy (spec §11):
- publishable + reproducible  -> PUBLISHED (+ confidence + notes, tags kept)
- not publishable             -> HELD (+ confidence + notes)
- vendor_internal             -> NEVER published; forced to HELD even if the
                                 verdict says publishable.
- no verdict for a claim       -> HELD (fail-safe; unreviewed never publishes).
No I/O, no Claude, no DB — fully unit-testable in isolation."""

from sota_ingest.agent.skeptic import Verdict
from sota_ingest.models import Origin, ResultClaim, VerificationStatus

_VENDOR_NOTE = "Vendor-internal eval — held; never published as reproducible."
_NO_VERDICT_NOTE = "No skeptic verdict produced for this claim — held."


def apply_verdicts(claims: list[ResultClaim], verdicts: list[Verdict]) -> list[ResultClaim]:
    """Return a new gated ResultClaim per input claim (inputs never mutated)."""
    by_index: dict[int, Verdict] = {v.claim_index: v for v in verdicts}
    out: list[ResultClaim] = []

    for i, claim in enumerate(claims):
        verdict = by_index.get(i)

        if verdict is None:
            out.append(
                claim.model_copy(
                    update={
                        "verification_status": VerificationStatus.HELD,
                        "skeptic_notes": _NO_VERDICT_NOTE,
                    }
                )
            )
            continue

        # Hard rule: vendor-internal is never published as reproducible.
        if claim.origin == Origin.VENDOR_INTERNAL:
            note = f"{_VENDOR_NOTE} {verdict.skeptic_notes}".strip()
            out.append(
                claim.model_copy(
                    update={
                        "verification_status": VerificationStatus.HELD,
                        "confidence": verdict.confidence,
                        "skeptic_notes": note,
                    }
                )
            )
            continue

        status = (
            VerificationStatus.PUBLISHED if verdict.publishable else VerificationStatus.HELD
        )
        out.append(
            claim.model_copy(
                update={
                    "verification_status": status,
                    "confidence": verdict.confidence,
                    "skeptic_notes": verdict.skeptic_notes,
                }
            )
        )

    return out
