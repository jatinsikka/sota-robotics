import pytest

from sota_ingest.agent.skeptic import MODEL, Verdict, refute_claims
from sota_ingest.models import Origin, PaperRec, Realm, ResultClaim
from tests.conftest import FakeAnthropic


def _paper() -> PaperRec:
    return PaperRec(title="OpenVLA-OFT", url="https://arxiv.org/abs/2502.19645")


def _claims() -> list[ResultClaim]:
    return [
        ResultClaim(
            method_slug="openvla-oft", benchmark_slug="libero", metric="success_rate",
            metric_value=97.1, eval_conditions={"split": "test"}, realm=Realm.SIM,
            origin=Origin.PUBLIC_REPRODUCIBLE, source_url="u1",
        ),
        ResultClaim(
            method_slug="vendorbot-x", benchmark_slug="internal-pick", metric="success_rate",
            metric_value=99.0, eval_conditions={"note": "internal"}, realm=Realm.REAL,
            origin=Origin.VENDOR_INTERNAL, source_url="u2",
        ),
    ]


def test_returns_one_verdict_per_claim(fake_skeptic_client):
    verdicts = refute_claims(fake_skeptic_client, _paper(), _claims())
    assert len(verdicts) == 2
    assert all(isinstance(v, Verdict) for v in verdicts)
    assert verdicts[0].claim_index == 0
    assert verdicts[0].publishable is True
    assert verdicts[0].confidence == 0.82
    assert verdicts[1].publishable is False
    assert "vendor" in verdicts[1].skeptic_notes.lower()


def test_uses_opus_48_no_prefill_adaptive_thinking(fake_skeptic_client):
    refute_claims(fake_skeptic_client, _paper(), _claims())
    call = fake_skeptic_client.calls[0]
    assert call["model"] == MODEL == "claude-opus-4-8"
    assert call["thinking"] == {"type": "adaptive"}
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert call["messages"][-1]["role"] == "user"
    assert all(m["role"] != "assistant" for m in call["messages"])
    # the numbered claims must appear in the user turn so the skeptic can index them
    user_text = call["messages"][-1]["content"]
    assert "vendorbot-x" in user_text and "[1]" in user_text


def test_empty_claims_skips_the_api_call(fake_skeptic_client):
    verdicts = refute_claims(fake_skeptic_client, _paper(), [])
    assert verdicts == []
    assert fake_skeptic_client.calls == []  # don't pay for an empty paper


def test_refusal_stop_reason_raises():
    client = FakeAnthropic('{"verdicts": []}', stop_reason="refusal")
    with pytest.raises(RuntimeError, match="refusal"):
        refute_claims(client, _paper(), _claims())
