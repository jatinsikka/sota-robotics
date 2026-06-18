# Agent Pipeline (Extractor → Skeptic → Gate) — Implementation Plan (Sub-plan 4 of 5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Follow TDD strictly: every code task is failing-test → run (FAIL) → minimal impl → run (PASS) → commit.

**Goal:** Turn ingested papers into **verified, published** `ResultClaim` rows. A two-stage Claude pipeline (Opus 4.8 extractor → Opus 4.8 skeptic) reads each paper, extracts explicit metric claims with `eval_conditions`, then adversarially refutes them; a **pure** gate applies the verdicts (survivors → `PUBLISHED` with confidence + realm/origin; failures → `HELD` with `skeptic_notes`; vendor-internal is never published as if reproducible). The daily set runs through the Message Batches API (50% off) with a prompt-cached stable prefix, and writes through `build_result_row` (Plan 1) + a thin `db.py`.

**Architecture:** Five new modules under `ingest/src/sota_ingest/agent/`. `prompts.py` holds the *stable, prompt-cacheable prefix* (extractor system prompt + result-claim JSON schema + few-shot + benchmark taxonomy) and the skeptic refutation prompt + verdict schema — this prefix is byte-frozen so prompt caching hits. `extractor.py` calls Claude with `output_config.format` (structured outputs, **no prefill**, `thinking={"type":"adaptive"}`, parse with `json.loads`, check `stop_reason`) and maps raw JSON → `list[ResultClaim]` (status left `PENDING`; the model never sets `verification_status`/`confidence`). `skeptic.py` calls Claude once per paper to refute each claim, returning a `Verdict` per claim. `gate.py` is **pure** (no I/O, no Claude) — it consumes claims + verdicts and emits gated `ResultClaim`s. `batch.py` assembles Message Batches API requests for the daily paper set with the cached prefix and persists results within the 29-day window. `db.py` resolves slugs→ids and executes `build_result_row` upserts. The two pure-ish testable seams — the gate, and the claim-schema/batch-payload assembly — are TDD'd with a **fake Anthropic client returning canned JSON**; the real API is never called in tests.

**Tech Stack:** Python 3.13 managed by `uv`; Pydantic v2; pytest; Anthropic Python SDK (`anthropic`) — Messages API + Message Batches API + Files API; Claude Opus 4.8 (`claude-opus-4-8`) for both extractor and skeptic in v1; Supabase Postgres (writes via service-role, reusing Plan 1's `build_result_row` + `CONFLICT_TARGET`). Reuses Plan 1 contracts verbatim (`ResultClaim`, `PaperRec`, `Realm`, `Origin`, `VerificationStatus`, `canonical_hash`, `build_result_row`).

---

## Decomposition (where this sits)

| # | Plan | Delivers | Depends on |
|---|------|----------|------------|
| 1 | Data Backbone & Seed Loaders | Schema + RLS + seed; Pydantic models, hashing, idempotent upsert | — |
| 3 | Live Ingest Spine | arXiv + HF + GitHub fetchers → `papers`/`code`; daily cron | 1 |
| **4** | **Agent Pipeline** (this doc) | Claude extractor → skeptic → publish/held **gate**; Batch API + prompt cache; writes `results` | 1, 3 |
| 5 | Web Views | Next.js leaderboards + "best for task X" | 1 (data from 2–4) |

This plan consumes `papers` rows produced by Plan 3 and writes `results` rows defined by Plan 1. It must not redefine any Plan 1 type.

---

## File Structure (this plan)

```
24_sota-robotics/
├── ingest/
│   ├── pyproject.toml                       # MODIFY: uv add anthropic
│   └── src/sota_ingest/
│       ├── models.py                        # (unchanged — Plan 1 contract)
│       ├── eval_conditions.py               # (unchanged — Plan 1)
│       ├── upsert.py                        # (unchanged — Plan 1: build_result_row, CONFLICT_TARGET)
│       └── agent/
│           ├── __init__.py                  # NEW: package marker
│           ├── prompts.py                   # NEW: cached prefix (extractor sys+schema+fewshot+taxonomy) + skeptic prompt+schema
│           ├── extractor.py                 # NEW: extract_claims(client, paper, ...) -> list[ResultClaim]
│           ├── skeptic.py                   # NEW: refute_claims(client, paper, claims) -> list[Verdict]
│           ├── gate.py                      # NEW (PURE): apply_verdicts(claims, verdicts) -> list[ResultClaim]
│           ├── batch.py                     # NEW: build_batch_requests(...) + collect_batch_results(...)
│           └── db.py                        # NEW: resolve ids + upsert via build_result_row
│   └── tests/
│       ├── conftest.py                      # NEW: FakeAnthropic client + canned-response helpers
│       ├── fixtures/
│       │   ├── extractor_response.json      # NEW: canned structured-output payload (claims)
│       │   └── skeptic_response.json        # NEW: canned structured-output payload (verdicts)
│       ├── test_agent_prompts.py            # NEW: prefix stability + schema shape
│       ├── test_agent_extractor.py          # NEW: parse + stop_reason + no-prefill (fake client)
│       ├── test_agent_skeptic.py            # NEW: verdict parse (fake client)
│       ├── test_agent_gate.py               # NEW (core): gate logic
│       └── test_agent_batch.py              # NEW: batch payload assembly + result collection
```

Boundaries: `gate.py` is **pure** (the moat's correctness lives here, fully unit-tested with zero mocks). `prompts.py` is pure data (frozen strings + dict schemas → cache-stable). `extractor.py`/`skeptic.py` take an injected `client` so tests pass a `FakeAnthropic`. `batch.py` assembles request payloads as pure data and collects results from an injected client. `db.py` is the only module that touches Supabase, and it delegates row-building to Plan 1's `build_result_row`.

---

## Task 0: Add the Anthropic SDK + agent package scaffold

**Files:**
- Modify: `24_sota-robotics/ingest/pyproject.toml`
- Create: `24_sota-robotics/ingest/src/sota_ingest/agent/__init__.py`

- [ ] **Step 1: Add the SDK dependency**

Run (from `24_sota-robotics/`):
```bash
cd ingest && uv add anthropic
```
Expected: `anthropic` appears under `[project] dependencies` in `pyproject.toml`; `uv.lock` updates; no error.

- [ ] **Step 2: Create the agent package marker**

Create `24_sota-robotics/ingest/src/sota_ingest/agent/__init__.py`:
```python
"""Claude agent pipeline: extractor -> skeptic -> gate, plus batch + db I/O."""
```

- [ ] **Step 3: Verify the package imports and the suite is still green**

Run: `cd ingest && uv run pytest -q`
Expected: existing Plan 1 tests still pass (~13 passed); no import errors from the new package.

- [ ] **Step 4: Commit**
```bash
git add ingest/pyproject.toml ingest/uv.lock ingest/src/sota_ingest/agent/__init__.py
git commit -m "chore: add anthropic SDK + agent package scaffold"
```

---

## Task 1: Prompts module — the prompt-cache prefix + skeptic prompt (pure data, TDD)

Rationale: the daily batch reuses one byte-identical system prefix (extractor system prompt + result-claim JSON schema + few-shot + benchmark taxonomy). Prompt caching is a **prefix match** — any byte change anywhere invalidates the cache, so this prefix must be frozen and deterministic (no timestamps, no per-paper text). The schema deliberately **excludes** `verification_status` and `confidence` — those are owned by the gate, not the model. This task builds and tests those strings/dicts as pure values; no Claude call.

**Files:**
- Create: `24_sota-robotics/ingest/src/sota_ingest/agent/prompts.py`
- Test: `24_sota-robotics/ingest/tests/test_agent_prompts.py`

- [ ] **Step 1: Write the failing test**
```python
# tests/test_agent_prompts.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ingest && uv run pytest tests/test_agent_prompts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sota_ingest.agent.prompts'`

- [ ] **Step 3: Write minimal implementation**
```python
# src/sota_ingest/agent/prompts.py
"""Stable, prompt-cacheable prefix for the extractor + the skeptic prompt/schema.

CACHE INVARIANT: build_cached_system() must be byte-identical across calls.
No datetime, no uuid, no per-paper text, no unsorted dict/set iteration here —
any drift breaks the prompt-cache prefix match and silently 0x's cache reads.
The volatile per-paper content goes in the user turn, never in this prefix.
"""

from typing import Any

# --- Benchmark taxonomy embedded in the prefix (canonical slugs + saturation) ---
# Mirrors db/migrations/0004_seed_taxonomy.sql so the extractor uses our slugs.
BENCHMARK_TAXONOMY = """\
Canonical benchmark slugs you MUST use when a result matches one of these
(map free-text benchmark names to the slug; otherwise slugify the name with hyphens):
- libero            (LIBERO; manipulation success_rate; SATURATED >97% — a high raw number is NOT impressive here)
- robocasa          (RoboCasa; household manipulation success_rate; discriminating)
- simplerenv        (SimplerEnv; real-to-sim manipulation success_rate)
- maniskill3        (ManiSkill3; GPU-parallel manipulation success_rate)
- roboarena         (RoboArena; cross-lab REAL-WORLD pairwise Elo — the anti-gaming signal)
- bop               (BOP; 6-DoF pose average_recall)
- humanoidbench     (HumanoidBench; whole-body loco+manip success_rate)
- habitat           (Habitat/ObjectNav; navigation spl)
- open-x-embodiment (Open X-Embodiment; dataset, not a leaderboard)
"""

EXTRACTOR_SYSTEM = """\
You are a meticulous robotics-results extractor for a live SOTA tracker.
Given a single paper (PDF or text), extract every quantitative benchmark
result the paper REPORTS, as structured claims.

Hard rules:
- Extract ONLY numbers the paper actually states. DO NOT INVENT, round, or
  infer a metric value that is not written in the paper. If a value is given
  as a range or qualitative, set metric_value to null.
- For every claim, record the eval_conditions that make the number comparable:
  benchmark suite/variant, data split (train/val/test), number of episodes or
  trials, protocol (e.g. visual_matching vs variant_aggregation), camera/obs
  setup, and whether it is in simulation (realm="sim") or on real hardware
  (realm="real"). Be explicit — vague conditions make a claim unverifiable.
- Set origin="vendor_internal" when the number comes from a private/vendor
  eval (no public protocol, closed data, or "internal benchmark"); otherwise
  origin="public_reproducible".
- source_url is the paper's canonical URL (arXiv abstract URL preferred).
- Use the canonical benchmark slugs in the taxonomy below when they match.
- DO NOT set verification_status or confidence — those are assigned later by
  a separate verification step. You only report what the paper claims.

Return JSON matching the provided schema exactly.
"""

# Result-claim schema for output_config.format. NOTE: no verification_status,
# no confidence — the gate owns those. Keys mirror ResultClaim (Plan 1).
RESULT_CLAIM_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "method_slug": {"type": "string"},
                        "benchmark_slug": {"type": "string"},
                        "task_slug": {"type": ["string", "null"]},
                        "metric": {"type": "string"},
                        "metric_value": {"type": ["number", "null"]},
                        "eval_conditions": {"type": "object"},
                        "realm": {"type": "string", "enum": ["sim", "real"]},
                        "origin": {
                            "type": "string",
                            "enum": ["public_reproducible", "vendor_internal"],
                        },
                        "source_url": {"type": "string"},
                        "result_date": {"type": ["string", "null"]},
                    },
                    "required": [
                        "method_slug",
                        "benchmark_slug",
                        "task_slug",
                        "metric",
                        "metric_value",
                        "eval_conditions",
                        "realm",
                        "origin",
                        "source_url",
                        "result_date",
                    ],
                },
            }
        },
        "required": ["claims"],
    },
}

SKEPTIC_SYSTEM = """\
You are an adversarial robotics-results skeptic. Given a paper and a numbered
list of extracted claims, try to REFUTE each claim. For each claim decide
whether it is safe to publish on a public leaderboard.

Refute a claim (publishable=false) when any of these hold:
- WRONG SPLIT: the number is on train/val, or the split is unstated/ambiguous.
- CHERRY-PICKED: best-of-N, hand-picked episodes, or a non-standard subset
  presented as the headline number.
- UNVERIFIABLE: eval_conditions are too vague to reproduce or compare, or no
  protocol is given.
- VENDOR-INTERNAL: the number is a private/vendor eval (origin=vendor_internal)
  with no public, reproducible protocol — never treat as a reproducible SOTA.
- A clearly-saturated benchmark (e.g. libero >97%) reported as a headline win
  without a robustness/real-world caveat: lower confidence, note the caveat.

For each claim output: claim_index (0-based), publishable (bool),
confidence (0..1, your calibrated confidence the number is real and comparable),
and skeptic_notes (one terse sentence: why refuted, or why it stands).
Return JSON matching the provided schema exactly.
"""

VERDICT_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "verdicts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "claim_index": {"type": "integer"},
                        "publishable": {"type": "boolean"},
                        "confidence": {"type": "number"},
                        "skeptic_notes": {"type": "string"},
                    },
                    "required": [
                        "claim_index",
                        "publishable",
                        "confidence",
                        "skeptic_notes",
                    ],
                },
            }
        },
        "required": ["verdicts"],
    },
}


def build_cached_system() -> list[dict[str, Any]]:
    """The stable extractor prefix as cache-control text blocks.

    Order: system prompt -> embedded JSON schema (as text, so it's part of the
    cached bytes) -> taxonomy. A SINGLE cache_control breakpoint sits on the
    LAST block so tools+system cache together. Deterministic by construction.
    """
    import json

    schema_text = json.dumps(RESULT_CLAIM_SCHEMA, sort_keys=True, separators=(",", ":"))
    return [
        {"type": "text", "text": EXTRACTOR_SYSTEM},
        {"type": "text", "text": "Output JSON schema:\n" + schema_text},
        {
            "type": "text",
            "text": BENCHMARK_TAXONOMY,
            "cache_control": {"type": "ephemeral"},
        },
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ingest && uv run pytest tests/test_agent_prompts.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**
```bash
git add ingest/src/sota_ingest/agent/prompts.py ingest/tests/test_agent_prompts.py
git commit -m "feat(agent): cache-stable extractor prefix + skeptic prompt/schema"
```

---

## Task 2: Fake Anthropic client + canned fixtures (test harness, no real API)

Rationale: the extractor/skeptic/batch tests must never hit the network. A `FakeAnthropic` returns canned structured-output payloads and records the kwargs each call received, so we can assert on `stop_reason` handling, **no-prefill** (last message must be `user`), the cached system prefix, and the model id — all without an API key.

**Files:**
- Create: `24_sota-robotics/ingest/tests/conftest.py`
- Create: `24_sota-robotics/ingest/tests/fixtures/extractor_response.json`
- Create: `24_sota-robotics/ingest/tests/fixtures/skeptic_response.json`

- [ ] **Step 1: Create the extractor canned response fixture**

Create `24_sota-robotics/ingest/tests/fixtures/extractor_response.json` (the JSON string the model would return under `output_config.format`):
```json
{
  "claims": [
    {
      "method_slug": "openvla-oft",
      "benchmark_slug": "libero",
      "task_slug": "libero-long",
      "metric": "success_rate",
      "metric_value": 97.1,
      "eval_conditions": {"suite": "LIBERO-LONG", "split": "test", "episodes": 50, "protocol": "rollout"},
      "realm": "sim",
      "origin": "public_reproducible",
      "source_url": "https://arxiv.org/abs/2502.19645",
      "result_date": "2025-02-27"
    },
    {
      "method_slug": "vendorbot-x",
      "benchmark_slug": "internal-pick",
      "task_slug": null,
      "metric": "success_rate",
      "metric_value": 99.0,
      "eval_conditions": {"note": "internal benchmark, protocol undisclosed"},
      "realm": "real",
      "origin": "vendor_internal",
      "source_url": "https://example.com/vendorbot",
      "result_date": null
    }
  ]
}
```

- [ ] **Step 2: Create the skeptic canned response fixture**

Create `24_sota-robotics/ingest/tests/fixtures/skeptic_response.json`:
```json
{
  "verdicts": [
    {
      "claim_index": 0,
      "publishable": true,
      "confidence": 0.82,
      "skeptic_notes": "Test split, 50 episodes, standard LIBERO-LONG protocol; saturated bench but conditions are explicit."
    },
    {
      "claim_index": 1,
      "publishable": false,
      "confidence": 0.2,
      "skeptic_notes": "Vendor-internal eval with undisclosed protocol; not reproducible."
    }
  ]
}
```

- [ ] **Step 3: Write the fake client + helpers in conftest**

Create `24_sota-robotics/ingest/tests/conftest.py`:
```python
# tests/conftest.py
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def _message(text: str, stop_reason: str = "end_turn") -> SimpleNamespace:
    """Mimic an anthropic Message: .content is a list of blocks, each with
    .type and .text; .stop_reason mirrors the API field."""
    block = SimpleNamespace(type="text", text=text)
    return SimpleNamespace(content=[block], stop_reason=stop_reason, stop_details=None)


class FakeMessages:
    def __init__(self, response_text: str, stop_reason: str):
        self._response_text = response_text
        self._stop_reason = stop_reason
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        return _message(self._response_text, self._stop_reason)


class FakeAnthropic:
    """Drop-in stand-in for anthropic.Anthropic. Records every create() call's
    kwargs and returns a canned structured-output message."""

    def __init__(self, response_text: str, stop_reason: str = "end_turn"):
        self.messages = FakeMessages(response_text, stop_reason)

    @property
    def calls(self) -> list[dict[str, Any]]:
        return self.messages.calls


@pytest.fixture
def extractor_payload() -> str:
    return (FIXTURES / "extractor_response.json").read_text()


@pytest.fixture
def skeptic_payload() -> str:
    return (FIXTURES / "skeptic_response.json").read_text()


@pytest.fixture
def fake_extractor_client(extractor_payload: str) -> FakeAnthropic:
    return FakeAnthropic(extractor_payload)


@pytest.fixture
def fake_skeptic_client(skeptic_payload: str) -> FakeAnthropic:
    return FakeAnthropic(skeptic_payload)
```

- [ ] **Step 4: Verify conftest imports cleanly (collection only)**

Run: `cd ingest && uv run pytest tests/ -q --collect-only`
Expected: collection succeeds (no `ImportError`); fixtures register. Existing tests still listed.

- [ ] **Step 5: Commit**
```bash
git add ingest/tests/conftest.py ingest/tests/fixtures/extractor_response.json ingest/tests/fixtures/skeptic_response.json
git commit -m "test(agent): FakeAnthropic client + canned extractor/skeptic fixtures"
```

---

## Task 3: Extractor — paper → list[ResultClaim] (TDD, fake client)

Rationale: the extractor is the front of the moat. It calls Claude Opus 4.8 with the cached prefix and `output_config.format`, **no assistant prefill** (prefill 400s on 4.8), `thinking={"type":"adaptive"}`, parses the first text block with `json.loads`, and **checks `stop_reason`** (refusal/max_tokens → raise, don't silently return junk). It maps raw JSON → `ResultClaim` leaving `verification_status=PENDING` and `confidence=None` (gate-owned).

**Files:**
- Create: `24_sota-robotics/ingest/src/sota_ingest/agent/extractor.py`
- Test: `24_sota-robotics/ingest/tests/test_agent_extractor.py`

- [ ] **Step 1: Write the failing test**
```python
# tests/test_agent_extractor.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ingest && uv run pytest tests/test_agent_extractor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sota_ingest.agent.extractor'`

- [ ] **Step 3: Write minimal implementation**
```python
# src/sota_ingest/agent/extractor.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ingest && uv run pytest tests/test_agent_extractor.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**
```bash
git add ingest/src/sota_ingest/agent/extractor.py ingest/tests/test_agent_extractor.py
git commit -m "feat(agent): extractor (Opus 4.8 structured outputs -> ResultClaims)"
```

---

## Task 4: Skeptic — claims + paper → list[Verdict] (TDD, fake client)

Rationale: the skeptic is the second half of the moat. It receives the extractor's claims and the paper, and refutes each one (wrong split / cherry-picked / unverifiable / vendor-internal), returning a `Verdict` per claim. Same SDK discipline: structured outputs, no prefill, adaptive thinking, `stop_reason` check, `json.loads`.

**Files:**
- Create: `24_sota-robotics/ingest/src/sota_ingest/agent/skeptic.py`
- Test: `24_sota-robotics/ingest/tests/test_agent_skeptic.py`

- [ ] **Step 1: Write the failing test**
```python
# tests/test_agent_skeptic.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ingest && uv run pytest tests/test_agent_skeptic.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sota_ingest.agent.skeptic'`

- [ ] **Step 3: Write minimal implementation**
```python
# src/sota_ingest/agent/skeptic.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ingest && uv run pytest tests/test_agent_skeptic.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**
```bash
git add ingest/src/sota_ingest/agent/skeptic.py ingest/tests/test_agent_skeptic.py
git commit -m "feat(agent): skeptic (refute claims -> per-claim Verdict)"
```

---

## Task 5: Gate — apply verdicts (PURE, TDD) — the correctness core

Rationale: this is where the moat's policy lives, so it's pure and exhaustively tested. Given claims + verdicts, it:
- **Survivors** (`publishable=true`): `verification_status=PUBLISHED`, set `confidence` from the verdict, append `skeptic_notes`, keep `realm`/`origin` tags.
- **Failures** (`publishable=false`): `verification_status=HELD`, set `skeptic_notes`, `confidence` from the verdict (so low-confidence is recorded), do **not** publish.
- **Hard rule:** a `vendor_internal` claim is **never** published as reproducible — even if the verdict says publishable, it is downgraded to `HELD` with a forced note. This encodes spec §11: never present vendor-internal as public/reproducible.
- Verdicts are matched by `claim_index`; a claim with **no** verdict defaults to `HELD` (fail-safe — unreviewed never auto-publishes).

**Files:**
- Create: `24_sota-robotics/ingest/src/sota_ingest/agent/gate.py`
- Test: `24_sota-robotics/ingest/tests/test_agent_gate.py`

- [ ] **Step 1: Write the failing test**
```python
# tests/test_agent_gate.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ingest && uv run pytest tests/test_agent_gate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sota_ingest.agent.gate'`

- [ ] **Step 3: Write minimal implementation**
```python
# src/sota_ingest/agent/gate.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ingest && uv run pytest tests/test_agent_gate.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**
```bash
git add ingest/src/sota_ingest/agent/gate.py ingest/tests/test_agent_gate.py
git commit -m "feat(agent): pure verdict gate (publish/held; vendor-internal never published)"
```

---

## Task 6: Batch runner — assemble Message Batches requests + collect results (TDD, fake client)

Rationale: the daily pass runs through the Message Batches API (50% off) so we don't pay synchronous rates for a whole day of papers. `build_batch_requests` is **pure** — it turns a list of papers into `Request(custom_id=..., params=MessageCreateParamsNonStreaming(...))` objects carrying the *same cached system prefix* (so the prefix caches across all requests in the batch) and the structured-output schema. `collect_batch_results` reads succeeded results back, parses each with `json.loads`, and returns `{custom_id: list[ResultClaim]}` (errored/expired entries are skipped, surfaced in a separate error map). Results stay retrievable for 29 days; we collect within that window. The real `batches.create`/`results` calls are exercised against the fake client; no network.

**Files:**
- Create: `24_sota-robotics/ingest/src/sota_ingest/agent/batch.py`
- Test: `24_sota-robotics/ingest/tests/test_agent_batch.py`

- [ ] **Step 1: Write the failing test**
```python
# tests/test_agent_batch.py
import json
from types import SimpleNamespace

from sota_ingest.agent.batch import (
    MODEL,
    build_batch_requests,
    collect_batch_results,
    paper_custom_id,
)
from sota_ingest.models import PaperRec


def _papers() -> list[PaperRec]:
    return [
        PaperRec(arxiv_id="2502.19645", title="A", url="https://arxiv.org/abs/2502.19645"),
        PaperRec(arxiv_id="2410.24164", title="B", url="https://arxiv.org/abs/2410.24164"),
    ]


def test_build_requests_one_per_paper_with_cached_prefix():
    reqs = build_batch_requests(_papers(), paper_texts={"2502.19645": "txt", "2410.24164": "txt2"})
    assert len(reqs) == 2
    r0 = reqs[0]
    # custom_id is deterministic + recoverable from the paper
    assert r0["custom_id"] == paper_custom_id(_papers()[0])
    params = r0["params"]
    assert params["model"] == MODEL == "claude-opus-4-8"
    assert params["thinking"] == {"type": "adaptive"}
    assert params["output_config"]["format"]["type"] == "json_schema"
    # NO prefill in a batch request either.
    assert params["messages"][-1]["role"] == "user"
    # cached prefix breakpoint present so the prefix caches across the batch.
    assert params["system"][-1]["cache_control"] == {"type": "ephemeral"}


def test_custom_id_is_stable_and_unique():
    p = _papers()
    assert paper_custom_id(p[0]) != paper_custom_id(p[1])
    assert paper_custom_id(p[0]) == paper_custom_id(p[0])


class _FakeBatches:
    """Mimics client.messages.batches with a canned results() iterator."""

    def __init__(self, results):
        self._results = results
        self.created = None

    def create(self, requests):
        self.created = requests
        return SimpleNamespace(id="msgbatch_123", processing_status="in_progress")

    def results(self, batch_id):
        return iter(self._results)


def _succeeded(custom_id, claims_json):
    msg = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=claims_json)],
        stop_reason="end_turn",
    )
    return SimpleNamespace(
        custom_id=custom_id,
        result=SimpleNamespace(type="succeeded", message=msg),
    )


def _errored(custom_id):
    return SimpleNamespace(
        custom_id=custom_id,
        result=SimpleNamespace(type="errored", error=SimpleNamespace(type="invalid_request")),
    )


def test_collect_parses_succeeded_and_skips_errored():
    p = _papers()
    cid0, cid1 = paper_custom_id(p[0]), paper_custom_id(p[1])
    claims_json = json.dumps({"claims": [{
        "method_slug": "openvla-oft", "benchmark_slug": "libero", "task_slug": None,
        "metric": "success_rate", "metric_value": 97.1, "eval_conditions": {"split": "test"},
        "realm": "sim", "origin": "public_reproducible",
        "source_url": "https://arxiv.org/abs/2502.19645", "result_date": None,
    }]})
    fake_batches = _FakeBatches([_succeeded(cid0, claims_json), _errored(cid1)])
    client = SimpleNamespace(messages=SimpleNamespace(batches=fake_batches))

    ok, errors = collect_batch_results(client, "msgbatch_123")
    assert set(ok) == {cid0}
    assert len(ok[cid0]) == 1
    assert ok[cid0][0].benchmark_slug == "libero"
    assert ok[cid0][0].metric_value == 97.1
    assert errors == {cid1: "invalid_request"}


def test_submit_batch_passes_requests_to_client():
    fake_batches = _FakeBatches([])
    client = SimpleNamespace(messages=SimpleNamespace(batches=fake_batches))
    reqs = build_batch_requests(_papers(), paper_texts={"2502.19645": "t", "2410.24164": "t2"})
    from sota_ingest.agent.batch import submit_batch

    batch = submit_batch(client, reqs)
    assert batch.id == "msgbatch_123"
    assert fake_batches.created == reqs
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ingest && uv run pytest tests/test_agent_batch.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sota_ingest.agent.batch'`

- [ ] **Step 3: Write minimal implementation**
```python
# src/sota_ingest/agent/batch.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ingest && uv run pytest tests/test_agent_batch.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**
```bash
git add ingest/src/sota_ingest/agent/batch.py ingest/tests/test_agent_batch.py
git commit -m "feat(agent): Message Batches assembly + result collection (cached prefix)"
```

---

## Task 7: DB writer — resolve ids + upsert via build_result_row (thin I/O)

Rationale: the gated claims must land in `results`. This module is the only one touching Supabase. It resolves `method_slug`/`benchmark_slug`/`task_slug` → ids (creating `methods`/looking up seeded `benchmarks`), then delegates row construction to Plan 1's `build_result_row` and upserts on Plan 1's `CONFLICT_TARGET`. We don't TDD a live DB here (no Supabase in unit tests, per Plan 1's boundary) — instead we unit-test the **pure** id-resolution + row-assembly seam against an injected fake DB executor, so the SQL layer just runs the payload.

**Files:**
- Create: `24_sota-robotics/ingest/src/sota_ingest/agent/db.py`
- Test: `24_sota-robotics/ingest/tests/test_agent_db.py`

- [ ] **Step 1: Write the failing test**
```python
# tests/test_agent_db.py
from sota_ingest.agent.db import build_upsert_rows
from sota_ingest.models import Origin, Realm, ResultClaim, VerificationStatus
from sota_ingest.upsert import CONFLICT_TARGET


def _gated_claim(**kw) -> ResultClaim:
    base = dict(
        method_slug="openvla-oft", benchmark_slug="libero", task_slug="libero-long",
        metric="success_rate", metric_value=97.1, eval_conditions={"split": "test"},
        realm=Realm.SIM, origin=Origin.PUBLIC_REPRODUCIBLE, source_url="u",
        confidence=0.8, verification_status=VerificationStatus.PUBLISHED,
        skeptic_notes="solid",
    )
    base.update(kw)
    return ResultClaim(**base)


def test_build_upsert_rows_resolves_ids_and_carries_run_id():
    method_ids = {"openvla-oft": 11}
    benchmark_ids = {"libero": 2}
    task_ids = {"libero-long": 5}
    rows = build_upsert_rows(
        [_gated_claim()],
        method_ids=method_ids, benchmark_ids=benchmark_ids, task_ids=task_ids,
        paper_id=7, code_id=None, run_id="run-2026-06-18",
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["method_id"] == 11
    assert row["benchmark_id"] == 2
    assert row["task_id"] == 5
    assert row["paper_id"] == 7
    assert row["ingested_run_id"] == "run-2026-06-18"
    assert row["verification_status"] == "published"
    assert row["confidence"] == 0.8
    # idempotency key present (Plan 1 contract)
    for k in CONFLICT_TARGET:
        assert k in row


def test_skips_claims_with_unknown_benchmark_slug():
    # benchmark not in the seeded taxonomy -> skip (can't FK it), don't crash.
    rows = build_upsert_rows(
        [_gated_claim(benchmark_slug="never-seeded")],
        method_ids={"openvla-oft": 11}, benchmark_ids={"libero": 2}, task_ids={},
        paper_id=None, code_id=None, run_id="r",
    )
    assert rows == []


def test_null_task_slug_yields_null_task_id():
    rows = build_upsert_rows(
        [_gated_claim(task_slug=None)],
        method_ids={"openvla-oft": 11}, benchmark_ids={"libero": 2}, task_ids={},
        paper_id=None, code_id=None, run_id="r",
    )
    assert rows[0]["task_id"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ingest && uv run pytest tests/test_agent_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sota_ingest.agent.db'`

- [ ] **Step 3: Write minimal implementation**
```python
# src/sota_ingest/agent/db.py
"""DB writer for gated claims. Resolves slugs->ids and builds upsert rows via
Plan 1's build_result_row + CONFLICT_TARGET. The pure row-assembly seam
(build_upsert_rows) is unit-tested; the live upsert (upsert_results) executes
those rows through a Supabase client/executor supplied by the cron entrypoint.

A method may be new (not yet in `methods`); resolving/creating method ids is
the caller's job (it owns the DB connection) — build_upsert_rows takes the
resolved maps so it stays pure and testable. Benchmarks must already exist in
the seeded taxonomy; an unknown benchmark_slug is skipped (can't FK it)."""

from typing import Any, Callable

from sota_ingest.models import ResultClaim
from sota_ingest.upsert import CONFLICT_TARGET, build_result_row


def build_upsert_rows(
    claims: list[ResultClaim],
    *,
    method_ids: dict[str, int],
    benchmark_ids: dict[str, int],
    task_ids: dict[str, int],
    paper_id: int | None,
    code_id: int | None,
    run_id: str,
) -> list[dict[str, Any]]:
    """Pure: gated claims + resolved id maps -> upsert payload rows.

    Skips a claim whose benchmark_slug isn't in the seeded taxonomy (no FK) or
    whose method_slug has no resolved id."""
    rows: list[dict[str, Any]] = []
    for claim in claims:
        benchmark_id = benchmark_ids.get(claim.benchmark_slug)
        method_id = method_ids.get(claim.method_slug)
        if benchmark_id is None or method_id is None:
            continue
        task_id = task_ids.get(claim.task_slug) if claim.task_slug else None
        rows.append(
            build_result_row(
                claim,
                method_id=method_id,
                benchmark_id=benchmark_id,
                task_id=task_id,
                paper_id=paper_id,
                code_id=code_id,
                run_id=run_id,
            )
        )
    return rows


def upsert_results(execute: Callable[[list[dict[str, Any]]], None], rows: list[dict[str, Any]]) -> int:
    """Execute the upsert. `execute` is supplied by the cron entrypoint and wraps
    a Supabase service-role upsert with on_conflict=CONFLICT_TARGET (idempotent).
    Returns the number of rows submitted."""
    if not rows:
        return 0
    execute(rows)
    return len(rows)


# Surfaced so the cron entrypoint configures the Supabase upsert with the right key.
ON_CONFLICT = ",".join(CONFLICT_TARGET)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ingest && uv run pytest tests/test_agent_db.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**
```bash
git add ingest/src/sota_ingest/agent/db.py ingest/tests/test_agent_db.py
git commit -m "feat(agent): db writer (resolve ids + build_result_row upsert payload)"
```

---

## Task 8: Full-suite green + plan close-out

**Files:**
- (no new files)

- [ ] **Step 1: Run the full suite**

Run: `cd ingest && uv run pytest -q`
Expected: all pass — Plan 1's ~13 + this plan's new tests (prompts 7 + extractor 5 + skeptic 4 + gate 6 + batch 5 + db 3 = 30), ~43 total. No skips, no errors.

- [ ] **Step 2: Sanity-check the imports wire end-to-end**

Run:
```bash
cd ingest && uv run python -c "from sota_ingest.agent import prompts, extractor, skeptic, gate, batch, db; print('ok')"
```
Expected: `ok` (no ImportError; the whole agent package imports).

- [ ] **Step 3: Commit + push**
```bash
git add -A
git commit -m "test(agent): full agent-pipeline suite green"
git push origin main
```

---

## Self-Review (completed against spec)

**Spec coverage (§ → task):**
- §11 *never rank by raw metric_value alone; surface eval_conditions, realm, origin, saturation, RoboArena Elo* → the extractor schema **requires** `eval_conditions`, `realm`, `origin` (Task 1, 3); the cached prefix embeds the taxonomy with LIBERO flagged saturated and RoboArena as the anti-gaming Elo (Task 1); the skeptic explicitly down-weights saturated-benchmark headline numbers (Task 1).
- §11 *never publish vendor_internal as reproducible* → the **pure gate** forces any `vendor_internal` claim to `HELD` even on a publishable verdict (Task 5, `test_vendor_internal_never_published_even_if_verdict_says_so`).
- *Extractor → skeptic, both Opus 4.8; structured outputs (`output_config.format`), NOT prefill; `thinking:{type:"adaptive"}`; parse with `json.loads`; check `stop_reason`* → Tasks 3 + 4 assert `model=="claude-opus-4-8"`, `thinking=={"type":"adaptive"}`, `output_config.format.type=="json_schema"`, last message `role=="user"` and no assistant message (no prefill), and raise on `refusal`/`max_tokens`.
- *Daily pass via Message Batches API (50% off); prompt-cache the stable system+schema+taxonomy prefix; persist within 29 days* → Task 6 builds `Request`/`MessageCreateParamsNonStreaming`-shaped payloads sharing one `build_cached_system()` prefix with a single `cache_control` breakpoint on the last block; `collect_batch_results` reads succeeded results (retrievable 29 days) and parses with `json.loads`.
- *DB queried by code, not Claude; writes via `build_result_row`* → Task 7 builds rows through Plan 1's `build_result_row` and exposes `ON_CONFLICT` from `CONFLICT_TARGET`; Claude is never handed the DB.
- *Files API (PDF) or text input* → `_user_content` (Task 3) takes either a Files-API `file_id` (`{"type":"document","source":{"type":"file","file_id":...}}`) or `paper_text`; batch requests carry the same (Task 6).
- *Depends on Plan 1 (contracts) + Plan 3 (papers)* → consumes `PaperRec` (Plan 3 output) and writes `ResultClaim`→`results` (Plan 1). No Plan 1 type redefined.

**Placeholder scan:** none — every code/test step is complete and runnable; no `TODO`, no "similar to above", no elided bodies. The only deliberately-deferred live wiring is the actual Supabase upsert *executor* and a real Anthropic API key, both injected at the cron entrypoint (Plan 3 owns the scheduler); the testable seams (`build_upsert_rows`, `upsert_results(execute, rows)`) are present and tested.

**Type consistency:**
- `extract_claims` and `batch._to_claims` both produce `ResultClaim` with exactly Plan 1's fields; `verification_status=VerificationStatus.PENDING`, `confidence=None` left for the gate.
- `apply_verdicts` returns `list[ResultClaim]` with `verification_status ∈ {PUBLISHED, HELD}` (string values `"published"`/`"held"` match the SQL enum from Plan 1 Task 5) and sets `confidence ∈ [0,1]` (Pydantic `ge=0,le=1` validator from Plan 1 enforces it).
- `Verdict` (skeptic) → consumed by `gate.apply_verdicts` by `claim_index`; the verdict schema's `claim_index/publishable/confidence/skeptic_notes` (Task 1) match the `Verdict` Pydantic model (Task 4).
- `build_upsert_rows` calls `build_result_row(claim, method_id, benchmark_id, task_id, paper_id, code_id, run_id)` with the **exact** Plan 1 signature; `ON_CONFLICT` is derived from `CONFLICT_TARGET = ("method_id","benchmark_id","eval_conditions_hash")`.
- `realm`/`origin` JSON enums (`["sim","real"]`, `["public_reproducible","vendor_internal"]`) match `Realm`/`Origin` enum values from Plan 1 `models.py`.

**SDK-correctness notes (per claude-api reference):** structured outputs use `output_config={"format": {"type":"json_schema","schema":...}}` (not the deprecated top-level `output_format`); `thinking={"type":"adaptive"}` (never `budget_tokens` — 400s on Opus 4.8); no assistant-turn prefill (400s on 4.8); `stop_reason` is checked before reading `content`; the Files API PDF path uses `{"type":"document","source":{"type":"file","file_id":...}}` and requires the `files-api-2025-04-14` beta header on the *real* client (wired at the entrypoint, out of unit scope); the cached prefix follows the prefix-match rule (frozen strings, single breakpoint on the last block).

**Known external dependency:** the live daily run needs `ANTHROPIC_API_KEY`, a real `anthropic.Anthropic()` client (with `betas=["files-api-2025-04-14"]` when sending PDFs), and the Supabase service-role connection for the upsert executor — all supplied by the GitHub Actions cron entrypoint (Plan 3's scheduler). Every module in this plan is fully unit-testable with the `FakeAnthropic` client and pure functions; no network or DB is touched in tests.
