import json

from sota_ingest.agent.prompts import (
    EXTRACTOR_SYSTEM,
    RESULT_CLAIM_SCHEMA,
    SKEPTIC_SYSTEM,
    VERDICT_SCHEMA,
    build_cached_system,
)


def test_extractor_schema_is_strict_object():
    s = RESULT_CLAIM_SCHEMA
    assert s["type"] == "json_schema"
    inner = s["schema"]
    assert inner["type"] == "object"
    assert inner["additionalProperties"] is False
    # The model returns a list of claims under "claims".
    assert "claims" in inner["properties"]
    item = inner["properties"]["claims"]["items"]
    assert item["additionalProperties"] is False


def test_extractor_schema_excludes_gate_owned_fields():
    # The gate owns verification_status + confidence; the model must NOT set them.
    item = RESULT_CLAIM_SCHEMA["schema"]["properties"]["claims"]["items"]
    props = item["properties"]
    assert "verification_status" not in props
    assert "confidence" not in props
    # But it MUST surface the discriminators we rank by.
    for required in ("method_slug", "benchmark_slug", "metric", "eval_conditions", "realm", "origin"):
        assert required in props


def test_realm_and_origin_enums_match_plan1_values():
    props = RESULT_CLAIM_SCHEMA["schema"]["properties"]["claims"]["items"]["properties"]
    assert props["realm"]["enum"] == ["sim", "real"]
    assert props["origin"]["enum"] == ["public_reproducible", "vendor_internal"]


def test_verdict_schema_has_publishable_flag():
    item = VERDICT_SCHEMA["schema"]["properties"]["verdicts"]["items"]
    props = item["properties"]
    for required in ("claim_index", "publishable", "confidence", "skeptic_notes"):
        assert required in props
    assert props["confidence"]["type"] == "number"


def test_cached_system_is_deterministic_and_serializable():
    # Cache stability: two builds must be byte-identical (no datetime/uuid/set ordering).
    a = build_cached_system()
    b = build_cached_system()
    assert a == b
    # It is a list of text blocks with a cache_control breakpoint on the LAST block.
    assert isinstance(a, list) and a[-1]["cache_control"] == {"type": "ephemeral"}
    # No earlier block carries cache_control (single breakpoint at the end of the prefix).
    assert all("cache_control" not in blk for blk in a[:-1])
    # Taxonomy is embedded so the model knows the canonical benchmark slugs.
    joined = "".join(blk["text"] for blk in a)
    assert "libero" in joined and "roboarena" in joined
    json.dumps(a)  # must be JSON-serializable for the Batches API


def test_extractor_system_forbids_inventing_numbers():
    assert "do not invent" in EXTRACTOR_SYSTEM.lower()


def test_skeptic_system_lists_refutation_axes():
    low = SKEPTIC_SYSTEM.lower()
    for axis in ("split", "cherry", "vendor", "unverifiable"):
        assert axis in low
