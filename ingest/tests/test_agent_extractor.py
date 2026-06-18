import pytest

from sota_ingest.agent.extractor import MODEL, extract_claims
from sota_ingest.models import Origin, PaperRec, Realm, VerificationStatus
from tests.conftest import FakeAnthropic


def _paper() -> PaperRec:
    return PaperRec(
        arxiv_id="2502.19645",
        title="OpenVLA-OFT",
        abstract="We report 97.1% on LIBERO-LONG ...",
        url="https://arxiv.org/abs/2502.19645",
    )


def test_extracts_claims_into_result_claims(fake_extractor_client):
    claims = extract_claims(fake_extractor_client, _paper(), paper_text="full text here")
    assert len(claims) == 2
    oft = claims[0]
    assert oft.method_slug == "openvla-oft"
    assert oft.benchmark_slug == "libero"
    assert oft.metric == "success_rate"
    assert oft.metric_value == 97.1
    assert oft.realm == Realm.SIM
    assert oft.origin == Origin.PUBLIC_REPRODUCIBLE
    assert oft.eval_conditions["split"] == "test"
    # gate-owned fields untouched by the extractor:
    assert oft.verification_status == VerificationStatus.PENDING
    assert oft.confidence is None


def test_vendor_internal_origin_preserved(fake_extractor_client):
    claims = extract_claims(fake_extractor_client, _paper(), paper_text="x")
    vendor = claims[1]
    assert vendor.origin == Origin.VENDOR_INTERNAL
    assert vendor.realm == Realm.REAL


def test_uses_opus_48_no_prefill_adaptive_thinking_and_cached_prefix(fake_extractor_client):
    extract_claims(fake_extractor_client, _paper(), paper_text="x")
    call = fake_extractor_client.calls[0]
    assert call["model"] == MODEL == "claude-opus-4-8"
    # adaptive thinking, NOT enabled+budget_tokens (4.8 400s on budget_tokens)
    assert call["thinking"] == {"type": "adaptive"}
    # structured outputs via output_config.format (not the deprecated output_format)
    assert call["output_config"]["format"]["type"] == "json_schema"
    # NO prefill: the final message must be a user turn, never assistant.
    assert call["messages"][-1]["role"] == "user"
    assert all(m["role"] != "assistant" for m in call["messages"])
    # cached system prefix is passed and its last block carries the breakpoint.
    assert call["system"][-1]["cache_control"] == {"type": "ephemeral"}


def test_refusal_stop_reason_raises():
    client = FakeAnthropic('{"claims": []}', stop_reason="refusal")
    with pytest.raises(RuntimeError, match="refusal"):
        extract_claims(client, _paper(), paper_text="x")


def test_max_tokens_stop_reason_raises():
    client = FakeAnthropic('{"claims": []}', stop_reason="max_tokens")
    with pytest.raises(RuntimeError, match="max_tokens"):
        extract_claims(client, _paper(), paper_text="x")
