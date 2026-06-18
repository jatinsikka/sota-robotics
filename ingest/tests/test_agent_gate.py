from sota_ingest.agent.gate import apply_verdicts
from sota_ingest.agent.skeptic import Verdict
from sota_ingest.models import Origin, Realm, ResultClaim, VerificationStatus


def _claim(**kw) -> ResultClaim:
    base = dict(
        method_slug="m", benchmark_slug="b", metric="success_rate",
        metric_value=90.0, eval_conditions={"split": "test"},
        realm=Realm.SIM, origin=Origin.PUBLIC_REPRODUCIBLE, source_url="u",
    )
    base.update(kw)
    return ResultClaim(**base)


def test_publishable_claim_becomes_published_with_confidence():
    claims = [_claim()]
    verdicts = [Verdict(claim_index=0, publishable=True, confidence=0.8, skeptic_notes="solid")]
    out = apply_verdicts(claims, verdicts)
    assert out[0].verification_status == VerificationStatus.PUBLISHED
    assert out[0].confidence == 0.8
    assert out[0].skeptic_notes == "solid"
    # tags preserved
    assert out[0].realm == Realm.SIM
    assert out[0].origin == Origin.PUBLIC_REPRODUCIBLE


def test_refuted_claim_becomes_held_with_notes():
    claims = [_claim()]
    verdicts = [Verdict(claim_index=0, publishable=False, confidence=0.1, skeptic_notes="wrong split")]
    out = apply_verdicts(claims, verdicts)
    assert out[0].verification_status == VerificationStatus.HELD
    assert out[0].confidence == 0.1
    assert out[0].skeptic_notes == "wrong split"


def test_vendor_internal_never_published_even_if_verdict_says_so():
    claims = [_claim(origin=Origin.VENDOR_INTERNAL)]
    verdicts = [Verdict(claim_index=0, publishable=True, confidence=0.95, skeptic_notes="looks great")]
    out = apply_verdicts(claims, verdicts)
    assert out[0].verification_status == VerificationStatus.HELD  # downgraded
    assert "vendor-internal" in out[0].skeptic_notes.lower()
    assert out[0].origin == Origin.VENDOR_INTERNAL  # tag kept


def test_claim_with_no_verdict_defaults_to_held():
    claims = [_claim(), _claim(method_slug="m2")]
    verdicts = [Verdict(claim_index=0, publishable=True, confidence=0.7, skeptic_notes="ok")]
    out = apply_verdicts(claims, verdicts)
    assert out[0].verification_status == VerificationStatus.PUBLISHED
    assert out[1].verification_status == VerificationStatus.HELD  # unreviewed -> held
    assert "no skeptic verdict" in (out[1].skeptic_notes or "").lower()


def test_gate_does_not_mutate_inputs():
    claims = [_claim()]
    verdicts = [Verdict(claim_index=0, publishable=True, confidence=0.8, skeptic_notes="ok")]
    apply_verdicts(claims, verdicts)
    assert claims[0].verification_status == VerificationStatus.PENDING  # original untouched
    assert claims[0].confidence is None


def test_returns_one_output_per_input_claim():
    claims = [_claim(), _claim(method_slug="m2"), _claim(method_slug="m3")]
    verdicts = [Verdict(claim_index=1, publishable=True, confidence=0.6, skeptic_notes="ok")]
    out = apply_verdicts(claims, verdicts)
    assert len(out) == 3
