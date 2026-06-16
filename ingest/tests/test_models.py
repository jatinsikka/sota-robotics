import pytest
from pydantic import ValidationError

from sota_ingest.models import ResultClaim, Realm, Origin, VerificationStatus


def test_result_claim_minimal_valid():
    rc = ResultClaim(
        method_slug="openvla-oft",
        benchmark_slug="libero",
        metric="success_rate",
        metric_value=97.1,
        eval_conditions={"suite": "LIBERO-LONG", "episodes": 50},
        source_url="https://arxiv.org/abs/2502.19645",
    )
    assert rc.realm == Realm.SIM  # default
    assert rc.origin == Origin.PUBLIC_REPRODUCIBLE
    assert rc.verification_status == VerificationStatus.PENDING


def test_confidence_must_be_0_to_1():
    with pytest.raises(ValidationError):
        ResultClaim(
            method_slug="x",
            benchmark_slug="y",
            metric="m",
            metric_value=1.0,
            eval_conditions={},
            source_url="u",
            confidence=1.4,
        )


def test_metric_value_optional_for_qualitative():
    rc = ResultClaim(
        method_slug="x",
        benchmark_slug="y",
        metric="elo",
        metric_value=None,
        eval_conditions={},
        source_url="u",
    )
    assert rc.metric_value is None
