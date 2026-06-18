"""Stable, prompt-cacheable prefix for the extractor + the skeptic prompt/schema.

CACHE INVARIANT: build_cached_system() must be byte-identical across calls.
No datetime, no uuid, no per-paper text, no unsorted dict/set iteration here —
any drift breaks the prompt-cache prefix match and silently 0x's cache reads.
The volatile per-paper content goes in the user turn, never in this prefix.
"""

import json
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
