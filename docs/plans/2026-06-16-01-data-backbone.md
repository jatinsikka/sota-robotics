# Data Backbone & Seed Loaders — Implementation Plan (Sub-plan 1 of 5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the Supabase Postgres backbone (schema, RLS, indexes, seed taxonomy) and a tested Python data layer (typed models, PWC `sota-extractor` loader, deterministic `eval_conditions` hashing, idempotent upsert) that every later subsystem writes through.

**Architecture:** A normalized relational graph in Supabase Postgres — `domains, tasks, benchmarks, methods, papers, code` plus the load-bearing `results` join. Per-benchmark variance lives in a JSONB `eval_conditions` column (GIN-indexed); `metric_value` stays a real numeric column so leaderboards sort in SQL. A Python package (`ingest/`) holds Pydantic models mirroring the schema and pure, unit-tested functions for parsing/hashing/upserting. Migrations are applied via the Supabase MCP tools; the pure-function core is TDD'd with pytest and needs no live DB.

**Tech Stack:** Supabase Postgres + `citext`/`pgcrypto`; Python 3.12 managed by `uv`; Pydantic v2; pytest; Supabase MCP (`apply_migration`, `execute_sql`, `get_advisors`, `list_tables`).

---

## Decomposition (the 5 sub-plans)

| # | Plan | Delivers | Depends on |
|---|------|----------|------------|
| **1** | **Data Backbone & Seed Loaders** (this doc) | Schema + RLS + 8-domain/benchmark seed; Python models, sota-extractor loader, hashing, idempotent upsert | — |
| 2 | Phase-0 Backfill | Pull PWC archive (HF) + scrape 4 awesome-lists → cold-start corpus + taxonomy (numbers flagged stale) | 1 |
| 3 | Live Ingest Spine | arXiv + HF Hub + GitHub fetchers → `papers`/`code`; daily GitHub Actions cron | 1 |
| 4 | Agent Pipeline | Claude extractor → skeptic → publish/held gate; Batch API + prompt cache; writes `results` | 1, 3 |
| 5 | Web Views | Next.js on Vercel: Leaderboards (eval_conditions + sim/real + reproducible/vendor tags) + "Best for task X" synthesis | 1 (data from 2–4) |

**Sequencing:** 1 → (2 ∥ 3) → 4 → 5. The v1 thin-slice milestone is 1+3+4+5 wired for **one** domain (humanoid VLA manipulation) plus 2 for cold start. Each of plans 2–5 gets its own plan doc, written when we reach it.

---

## File Structure (this plan)

```
24_sota-robotics/
├── db/
│   └── migrations/
│       ├── 0001_extensions.sql        # citext, pgcrypto
│       ├── 0002_core_tables.sql        # domains..results + enums + indexes
│       ├── 0003_rls.sql                # RLS enable + read policies
│       └── 0004_seed_taxonomy.sql      # 8 domains + canonical benchmarks
├── ingest/
│   ├── pyproject.toml                  # uv project, deps: pydantic, pytest
│   ├── src/sota_ingest/
│   │   ├── __init__.py
│   │   ├── models.py                   # Pydantic: ResultClaim, PaperRec, ...
│   │   ├── eval_conditions.py          # canonical_hash()
│   │   ├── sota_extractor.py           # parse_evaluation_tables()
│   │   └── upsert.py                    # build_result_upsert()
│   └── tests/
│       ├── conftest.py
│       ├── fixtures/pwc_eval_table.json
│       ├── test_eval_conditions.py
│       ├── test_sota_extractor.py
│       └── test_upsert.py
├── .env.example
└── .github/workflows/                   # (added in Plan 3)
```

Boundaries: `eval_conditions.py`, `sota_extractor.py`, `upsert.py` are each pure (no I/O, no DB) so they unit-test in isolation; `models.py` is the shared contract; SQL migrations own the schema. DB I/O (the Supabase client) is deliberately deferred to Plans 3–4 so this plan stays fully unit-testable.

---

## Task 0: Project scaffold

**Files:**
- Create: `24_sota-robotics/ingest/pyproject.toml`
- Create: `24_sota-robotics/ingest/src/sota_ingest/__init__.py`
- Create: `24_sota-robotics/.env.example`

- [ ] **Step 1: Create the Python project with uv**

Run (from `24_sota-robotics/`):
```bash
cd ingest && uv init --package --name sota-ingest --python 3.12 . && uv add pydantic && uv add --dev pytest
```
Expected: `pyproject.toml`, `src/sota_ingest/__init__.py`, and a `.venv` created.

- [ ] **Step 2: Pin the package layout**

Ensure `ingest/pyproject.toml` contains:
```toml
[project]
name = "sota-ingest"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["pydantic>=2.7"]

[dependency-groups]
dev = ["pytest>=8"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

- [ ] **Step 3: Add `.env.example`**

Create `24_sota-robotics/.env.example`:
```
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_PUBLISHABLE_KEY=
ANTHROPIC_API_KEY=
```

- [ ] **Step 4: Verify pytest runs (no tests yet)**

Run: `cd ingest && uv run pytest -q`
Expected: `no tests ran` (exit 0 or 5), no import errors.

- [ ] **Step 5: Commit**
```bash
git add ingest/pyproject.toml ingest/src/sota_ingest/__init__.py .env.example
git commit -m "chore: scaffold ingest python package"
```

---

## Task 1: `eval_conditions` deterministic hashing (pure, TDD)

Rationale: the `UNIQUE(method_id, benchmark_id, eval_conditions_hash)` constraint is what makes re-ingesting the same paper idempotent. The hash MUST be stable regardless of key order or whitespace.

**Files:**
- Create: `24_sota-robotics/ingest/src/sota_ingest/eval_conditions.py`
- Test: `24_sota-robotics/ingest/tests/test_eval_conditions.py`

- [ ] **Step 1: Write the failing test**
```python
# tests/test_eval_conditions.py
from sota_ingest.eval_conditions import canonical_hash

def test_key_order_does_not_change_hash():
    a = {"split": "test", "protocol": "visual_matching", "episodes": 50}
    b = {"episodes": 50, "protocol": "visual_matching", "split": "test"}
    assert canonical_hash(a) == canonical_hash(b)

def test_nested_key_order_stable():
    a = {"sim": {"engine": "mujoco", "seeds": [1, 2, 3]}}
    b = {"sim": {"seeds": [1, 2, 3], "engine": "mujoco"}}
    assert canonical_hash(a) == canonical_hash(b)

def test_different_values_change_hash():
    assert canonical_hash({"split": "test"}) != canonical_hash({"split": "train"})

def test_empty_dict_is_stable_nonempty_string():
    h = canonical_hash({})
    assert isinstance(h, str) and len(h) == 64  # sha256 hex
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ingest && uv run pytest tests/test_eval_conditions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sota_ingest.eval_conditions'`

- [ ] **Step 3: Write minimal implementation**
```python
# src/sota_ingest/eval_conditions.py
import hashlib
import json
from typing import Any

def canonical_hash(eval_conditions: dict[str, Any]) -> str:
    """SHA-256 of canonicalized eval_conditions.

    Keys are sorted recursively (json sort_keys handles nested dicts),
    separators are fixed, so logically-equal dicts hash identically.
    """
    canonical = json.dumps(
        eval_conditions, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ingest && uv run pytest tests/test_eval_conditions.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**
```bash
git add ingest/src/sota_ingest/eval_conditions.py ingest/tests/test_eval_conditions.py
git commit -m "feat: deterministic eval_conditions hashing"
```

---

## Task 2: Pydantic models (the shared contract)

**Files:**
- Create: `24_sota-robotics/ingest/src/sota_ingest/models.py`
- Test: `24_sota-robotics/ingest/tests/test_models.py`

- [ ] **Step 1: Write the failing test**
```python
# tests/test_models.py
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
    assert rc.realm == Realm.SIM            # default
    assert rc.origin == Origin.PUBLIC_REPRODUCIBLE
    assert rc.verification_status == VerificationStatus.PENDING

def test_confidence_must_be_0_to_1():
    with pytest.raises(ValidationError):
        ResultClaim(
            method_slug="x", benchmark_slug="y", metric="m",
            metric_value=1.0, eval_conditions={}, source_url="u", confidence=1.4,
        )

def test_metric_value_optional_for_qualitative():
    rc = ResultClaim(
        method_slug="x", benchmark_slug="y", metric="elo",
        metric_value=None, eval_conditions={}, source_url="u",
    )
    assert rc.metric_value is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ingest && uv run pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sota_ingest.models'`

- [ ] **Step 3: Write minimal implementation**
```python
# src/sota_ingest/models.py
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field

class Realm(str, Enum):
    SIM = "sim"
    REAL = "real"

class Origin(str, Enum):
    PUBLIC_REPRODUCIBLE = "public_reproducible"
    VENDOR_INTERNAL = "vendor_internal"

class VerificationStatus(str, Enum):
    PENDING = "pending"
    PUBLISHED = "published"
    HELD = "held"
    REFUTED = "refuted"

class ResultClaim(BaseModel):
    method_slug: str
    benchmark_slug: str
    task_slug: str | None = None
    metric: str
    metric_value: float | None = None
    eval_conditions: dict[str, Any] = Field(default_factory=dict)
    realm: Realm = Realm.SIM
    origin: Origin = Origin.PUBLIC_REPRODUCIBLE
    source_url: str
    result_date: str | None = None          # ISO date string; validated downstream
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    verification_status: VerificationStatus = VerificationStatus.PENDING
    skeptic_notes: str | None = None

class PaperRec(BaseModel):
    arxiv_id: str | None = None
    title: str
    authors: str | None = None
    abstract: str | None = None
    published_date: str | None = None
    url: str | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ingest && uv run pytest tests/test_models.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**
```bash
git add ingest/src/sota_ingest/models.py ingest/tests/test_models.py
git commit -m "feat: pydantic contract models (ResultClaim, PaperRec, enums)"
```

---

## Task 3: PWC `sota-extractor` evaluation-table loader (pure, TDD)

Rationale: Plan 2 backfills from the PWC archive's `evaluation-tables` (sota-extractor JSON). This task makes a tested parser that maps that nested format into `ResultClaim`s, so the cold-start corpus loads through the same contract as live data.

**Files:**
- Create: `24_sota-robotics/ingest/src/sota_ingest/sota_extractor.py`
- Create: `24_sota-robotics/ingest/tests/fixtures/pwc_eval_table.json`
- Test: `24_sota-robotics/ingest/tests/test_sota_extractor.py`

- [ ] **Step 1: Create the fixture (a minimal real-shaped sota-extractor record)**
```json
// tests/fixtures/pwc_eval_table.json
[
  {
    "task": "Robot Manipulation",
    "datasets": [
      {
        "dataset": "LIBERO",
        "sota": {
          "metrics": ["Success Rate"],
          "rows": [
            {
              "model_name": "OpenVLA-OFT",
              "metrics": {"Success Rate": "97.1"},
              "paper_url": "https://arxiv.org/abs/2502.19645",
              "code_links": [{"url": "https://github.com/moojink/openvla-oft"}]
            },
            {
              "model_name": "pi0",
              "metrics": {"Success Rate": "94.2"},
              "paper_url": "https://arxiv.org/abs/2410.24164",
              "code_links": []
            }
          ]
        }
      }
    ]
  }
]
```

- [ ] **Step 2: Write the failing test**
```python
# tests/test_sota_extractor.py
import json
from pathlib import Path
from sota_ingest.sota_extractor import parse_evaluation_tables
from sota_ingest.models import Origin, VerificationStatus

FIXTURE = Path(__file__).parent / "fixtures" / "pwc_eval_table.json"

def test_parses_rows_into_result_claims():
    data = json.loads(FIXTURE.read_text())
    claims = parse_evaluation_tables(data)
    assert len(claims) == 2
    oft = next(c for c in claims if c.method_slug == "openvla-oft")
    assert oft.benchmark_slug == "libero"
    assert oft.metric == "success_rate"
    assert oft.metric_value == 97.1
    assert oft.source_url == "https://arxiv.org/abs/2502.19645"

def test_archive_rows_are_held_not_published():
    # PWC numbers are stale/self-reported -> must NOT auto-publish.
    data = json.loads(FIXTURE.read_text())
    claims = parse_evaluation_tables(data)
    assert all(c.verification_status == VerificationStatus.HELD for c in claims)
    assert all(c.origin == Origin.PUBLIC_REPRODUCIBLE for c in claims)

def test_non_numeric_metric_becomes_none():
    data = [{"task": "T", "datasets": [{"dataset": "B", "sota": {
        "metrics": ["Score"], "rows": [
            {"model_name": "M", "metrics": {"Score": "N/A"}, "paper_url": "u", "code_links": []}
        ]}}]}]
    claims = parse_evaluation_tables(data)
    assert claims[0].metric_value is None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd ingest && uv run pytest tests/test_sota_extractor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sota_ingest.sota_extractor'`

- [ ] **Step 4: Write minimal implementation**
```python
# src/sota_ingest/sota_extractor.py
import re
from typing import Any
from sota_ingest.models import ResultClaim, VerificationStatus

def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")

def _to_float(raw: str | None) -> float | None:
    if raw is None:
        return None
    m = re.search(r"-?\d+(\.\d+)?", str(raw))
    return float(m.group()) if m else None

def parse_evaluation_tables(data: list[dict[str, Any]]) -> list[ResultClaim]:
    """Map PWC sota-extractor evaluation-tables JSON -> ResultClaims.

    Archive numbers are stale/self-reported, so every claim is HELD
    (never auto-published) for later re-verification.
    """
    claims: list[ResultClaim] = []
    for task_block in data:
        task_slug = _slug(task_block.get("task", "")) or None
        for ds in task_block.get("datasets", []):
            bench_slug = _slug(ds["dataset"])
            sota = ds.get("sota") or {}
            metric_names = sota.get("metrics") or ["score"]
            primary_metric = _slug(metric_names[0])
            for row in sota.get("rows", []):
                metrics = row.get("metrics", {})
                raw_val = metrics.get(metric_names[0]) if metric_names else None
                code_links = row.get("code_links") or []
                claims.append(ResultClaim(
                    method_slug=_slug(row["model_name"]),
                    benchmark_slug=bench_slug,
                    task_slug=task_slug,
                    metric=primary_metric,
                    metric_value=_to_float(raw_val),
                    eval_conditions={"source": "pwc_archive"},
                    source_url=row.get("paper_url") or "",
                    verification_status=VerificationStatus.HELD,
                    skeptic_notes="Imported from frozen PWC archive (Sep 2025); unverified.",
                    confidence=None,
                ))
    return claims
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd ingest && uv run pytest tests/test_sota_extractor.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**
```bash
git add ingest/src/sota_ingest/sota_extractor.py ingest/tests/test_sota_extractor.py ingest/tests/fixtures/pwc_eval_table.json
git commit -m "feat: PWC sota-extractor evaluation-table loader (held by default)"
```

---

## Task 4: Idempotent upsert builder (pure, TDD)

Rationale: writers (Plans 2–4) must produce the exact upsert payload + conflict target so re-runs don't duplicate `results`. This builds and tests that payload as pure data (no DB), so the SQL/RPC layer in later plans just executes it.

**Files:**
- Create: `24_sota-robotics/ingest/src/sota_ingest/upsert.py`
- Test: `24_sota-robotics/ingest/tests/test_upsert.py`

- [ ] **Step 1: Write the failing test**
```python
# tests/test_upsert.py
from sota_ingest.models import ResultClaim
from sota_ingest.upsert import build_result_row
from sota_ingest.eval_conditions import canonical_hash

def _claim(**kw):
    base = dict(method_slug="m", benchmark_slug="b", metric="success_rate",
                metric_value=90.0, eval_conditions={"split": "test"}, source_url="u")
    base.update(kw)
    return ResultClaim(**base)

def test_row_includes_eval_conditions_hash():
    row = build_result_row(_claim(), method_id=1, benchmark_id=2, task_id=None,
                           paper_id=None, code_id=None, run_id="run-123")
    assert row["eval_conditions_hash"] == canonical_hash({"split": "test"})
    assert row["method_id"] == 1 and row["benchmark_id"] == 2
    assert row["ingested_run_id"] == "run-123"
    assert row["verification_status"] == "pending"

def test_same_claim_same_conflict_key():
    a = build_result_row(_claim(), 1, 2, None, None, None, "r1")
    b = build_result_row(_claim(eval_conditions={"split": "test"}), 1, 2, None, None, None, "r2")
    key = ("method_id", "benchmark_id", "eval_conditions_hash")
    assert tuple(a[k] for k in key) == tuple(b[k] for k in key)

def test_enum_values_serialized_as_strings():
    row = build_result_row(_claim(), 1, 2, None, None, None, "r1")
    assert row["realm"] == "sim"
    assert row["origin"] == "public_reproducible"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ingest && uv run pytest tests/test_upsert.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sota_ingest.upsert'`

- [ ] **Step 3: Write minimal implementation**
```python
# src/sota_ingest/upsert.py
from typing import Any
from sota_ingest.models import ResultClaim
from sota_ingest.eval_conditions import canonical_hash

# Postgres unique constraint target on the results table.
CONFLICT_TARGET = ("method_id", "benchmark_id", "eval_conditions_hash")

def build_result_row(
    claim: ResultClaim,
    method_id: int,
    benchmark_id: int,
    task_id: int | None,
    paper_id: int | None,
    code_id: int | None,
    run_id: str,
) -> dict[str, Any]:
    """Build the DB row for an upsert. Pure: resolving slugs->ids is the
    caller's job (DB layer in Plans 3-4). Idempotency key = CONFLICT_TARGET."""
    return {
        "method_id": method_id,
        "benchmark_id": benchmark_id,
        "task_id": task_id,
        "paper_id": paper_id,
        "code_id": code_id,
        "metric": claim.metric,
        "metric_value": claim.metric_value,
        "eval_conditions": claim.eval_conditions,
        "eval_conditions_hash": canonical_hash(claim.eval_conditions),
        "realm": claim.realm.value,
        "origin": claim.origin.value,
        "source_url": claim.source_url,
        "result_date": claim.result_date,
        "confidence": claim.confidence,
        "verification_status": claim.verification_status.value,
        "skeptic_notes": claim.skeptic_notes,
        "ingested_run_id": run_id,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ingest && uv run pytest tests/test_upsert.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Full suite green + commit**

Run: `cd ingest && uv run pytest -q`
Expected: PASS (all tasks' tests, ~13 passed)
```bash
git add ingest/src/sota_ingest/upsert.py ingest/tests/test_upsert.py
git commit -m "feat: idempotent result-row builder with conflict target"
```

---

## Task 5: Schema migrations — extensions + core tables

Applied via the Supabase MCP. If no project exists yet, create one first (`supabase` MCP `create_project`, or the dashboard) and put its URL + keys in `.env`.

**Files:**
- Create: `24_sota-robotics/db/migrations/0001_extensions.sql`
- Create: `24_sota-robotics/db/migrations/0002_core_tables.sql`

- [ ] **Step 1: Write `0001_extensions.sql`**
```sql
-- 0001_extensions.sql
create extension if not exists citext;
create extension if not exists pgcrypto;
```

- [ ] **Step 2: Write `0002_core_tables.sql`**
```sql
-- 0002_core_tables.sql
create type verification_status as enum ('pending','published','held','refuted');
create type result_origin       as enum ('public_reproducible','vendor_internal');
create type eval_realm          as enum ('sim','real');

create table domains (
  id          bigint generated always as identity primary key,
  slug        citext unique not null,
  name        text   not null,
  description text,
  created_at  timestamptz not null default now()
);

create table tasks (
  id         bigint generated always as identity primary key,
  domain_id  bigint not null references domains(id) on delete restrict,
  slug       citext unique not null,
  name       text   not null,
  description text,
  created_at timestamptz not null default now()
);

create table benchmarks (
  id           bigint generated always as identity primary key,
  domain_id    bigint references domains(id) on delete set null,
  slug         citext unique not null,
  name         text   not null,
  measures     text,
  metric       text,
  results_url  text,
  is_saturated boolean not null default false,
  notes        text,
  created_at   timestamptz not null default now()
);

create table methods (
  id         bigint generated always as identity primary key,
  slug       citext unique not null,
  name       text   not null,
  org        text,
  params     text,
  created_at timestamptz not null default now()
);

create table papers (
  id             bigint generated always as identity primary key,
  arxiv_id       text unique,
  title          text not null,
  authors        text,
  abstract       text,
  published_date date,
  url            text,
  created_at     timestamptz not null default now()
);

create table code (
  id          bigint generated always as identity primary key,
  repo_url    text unique not null,
  stars       int,
  last_commit date,
  license     text,
  created_at  timestamptz not null default now()
);

create table results (
  id                   bigint generated always as identity primary key,
  method_id            bigint not null references methods(id)    on delete cascade,
  benchmark_id         bigint not null references benchmarks(id) on delete cascade,
  task_id              bigint references tasks(id)  on delete set null,
  paper_id             bigint references papers(id) on delete set null,
  code_id              bigint references code(id)   on delete set null,
  metric               text   not null,
  metric_value         numeric,
  eval_conditions      jsonb  not null default '{}'::jsonb,
  eval_conditions_hash text   not null,
  realm                eval_realm          not null default 'sim',
  origin               result_origin       not null default 'public_reproducible',
  source_url           text,
  result_date          date,
  confidence           numeric check (confidence is null or (confidence >= 0 and confidence <= 1)),
  verification_status  verification_status not null default 'pending',
  skeptic_notes        text,
  ingested_run_id      text,
  created_at           timestamptz not null default now(),
  unique (method_id, benchmark_id, eval_conditions_hash)
);

create index results_published_idx
  on results (benchmark_id, metric_value desc)
  where verification_status = 'published';

create index results_eval_conditions_gin
  on results using gin (eval_conditions);
```

- [ ] **Step 3: Apply both migrations via Supabase MCP**

Use the `apply_migration` tool twice (name: `0001_extensions`, then `0002_core_tables`) with the SQL above.
Expected: both succeed, no error.

- [ ] **Step 4: Verify tables exist**

Use the `list_tables` MCP tool (schema `public`).
Expected: `domains, tasks, benchmarks, methods, papers, code, results` all present; `results` has the `unique` constraint and both indexes.

- [ ] **Step 5: Commit the migration files**
```bash
git add db/migrations/0001_extensions.sql db/migrations/0002_core_tables.sql
git commit -m "feat: core schema (domains..results) with enums, indexes, idempotency constraint"
```

---

## Task 6: Row-Level Security

Rationale: RLS is **off by default** on new Supabase tables — every table is world-readable via the anon key until enabled. This is the #1 Supabase security finding. The Next.js client uses the publishable key and must read ONLY published results; the Python writer uses the service-role key (bypasses RLS).

**Files:**
- Create: `24_sota-robotics/db/migrations/0003_rls.sql`

- [ ] **Step 1: Write `0003_rls.sql`**
```sql
-- 0003_rls.sql
alter table domains    enable row level security;
alter table tasks      enable row level security;
alter table benchmarks enable row level security;
alter table methods    enable row level security;
alter table papers     enable row level security;
alter table code       enable row level security;
alter table results    enable row level security;

-- Reference tables: world-readable (no secrets in taxonomy/paper metadata).
create policy "public read domains"    on domains    for select using (true);
create policy "public read tasks"      on tasks      for select using (true);
create policy "public read benchmarks" on benchmarks for select using (true);
create policy "public read methods"    on methods    for select using (true);
create policy "public read papers"     on papers     for select using (true);
create policy "public read code"       on code       for select using (true);

-- results: only PUBLISHED rows are visible to anon/publishable key.
create policy "public read published results"
  on results for select
  using (verification_status = 'published');

-- No insert/update/delete policies => only the service-role key (which
-- bypasses RLS) can write. The publishable key is read-only by construction.
```

- [ ] **Step 2: Apply via Supabase MCP**

Use `apply_migration` (name: `0003_rls`).
Expected: success.

- [ ] **Step 3: Verify with the security advisor**

Use the `get_advisors` MCP tool (type: `security`).
Expected: NO "RLS disabled in public" findings for any of the 7 tables. If any table still flags, RLS wasn't enabled — fix before proceeding.

- [ ] **Step 4: Smoke-test the policy boundary**

Use `execute_sql` to insert one `pending` and one `published` result via service role (after seed in Task 7 gives valid FK ids; if running before Task 7, skip to Task 7 then return). Then query as documented in Plan 5. For now, assert the policy exists:
```sql
select polname from pg_policies where tablename = 'results';
```
Expected: `public read published results` present.

- [ ] **Step 5: Commit**
```bash
git add db/migrations/0003_rls.sql
git commit -m "feat: RLS — public reads reference tables + published results only"
```

---

## Task 7: Seed the 8-domain taxonomy + canonical benchmarks

Uses the research-verified domain canon (spec §3) and benchmarks (spec §11.2/§11.4). `is_saturated=true` on LIBERO encodes the "don't rank by raw number" insight.

**Files:**
- Create: `24_sota-robotics/db/migrations/0004_seed_taxonomy.sql`

- [ ] **Step 1: Write `0004_seed_taxonomy.sql`**
```sql
-- 0004_seed_taxonomy.sql
insert into domains (slug, name, description) values
 ('humanoid-vla-manip','Humanoid VLA & manipulation','VLA foundation models, dexterous & bimanual manipulation'),
 ('locomotion-wbc','Locomotion & whole-body control','Legged/bipedal locomotion, whole-body control'),
 ('world-models','World models','Learned world/video predictors used for control'),
 ('world-action-models','World-action models','Action-conditioned world prediction (WAM)'),
 ('sim2real-rl','Sim-to-real & RL for control','Domain randomization, real-world RL, sim2real transfer'),
 ('robot-perception','Robot perception','3D vision, grasping, 6-DoF pose estimation'),
 ('lfd-robot-data','Learning from demonstration & robot data','Imitation learning, teleop, cross-embodiment datasets'),
 ('navigation-vln','Navigation / VLN','Embodied & vision-language navigation')
on conflict (slug) do nothing;

insert into benchmarks (domain_id, slug, name, measures, metric, results_url, is_saturated, notes)
select d.id, v.slug, v.name, v.measures, v.metric, v.results_url, v.is_saturated, v.notes
from (values
 ('humanoid-vla-manip','libero','LIBERO','Lifelong language-conditioned tabletop manipulation','success_rate','https://libero-project.github.io', true,  'Saturated >97%; rank by robustness (LIBERO-Plus), not raw score'),
 ('humanoid-vla-manip','robocasa','RoboCasa','Large-scale household manipulation (GR-1 tabletop)','success_rate','https://robocasa.ai', false, 'Discriminating: SOTA ~50-57%'),
 ('humanoid-vla-manip','simplerenv','SimplerEnv','Real-to-sim manipulation reproduction','success_rate','https://github.com/simpler-env/SimplerEnv', false, 'Visual Matching / Variant Aggregation'),
 ('humanoid-vla-manip','maniskill3','ManiSkill3','GPU-parallel manipulation suite','success_rate','https://github.com/haosulab/ManiSkill', false, null),
 ('humanoid-vla-manip','roboarena','RoboArena','Cross-lab real-world pairwise policy ranking','elo','https://robo-arena.github.io', false, 'Real-world Elo; credible anti-gaming signal; runs through Dec 2026'),
 ('robot-perception','bop','BOP','6-DoF object pose estimation','average_recall','https://bop.felk.cvut.cz/leaderboards', false, 'Has a live online eval server/API (gold standard)'),
 ('locomotion-wbc','humanoidbench','HumanoidBench','Simulated humanoid whole-body loco+manip','success_rate','https://humanoid-bench.github.io', false, null),
 ('navigation-vln','habitat','Habitat / ObjectNav','Embodied navigation','spl','https://aihabitat.org', false, 'EvalAI-hosted challenge'),
 ('lfd-robot-data','open-x-embodiment','Open X-Embodiment','Cross-embodiment robot dataset (taxonomy seed)','dataset','https://github.com/google-deepmind/open_x_embodiment', false, 'Dataset, not a leaderboard')
) as v(domain_slug, slug, name, measures, metric, results_url, is_saturated, notes)
join domains d on d.slug = v.domain_slug
on conflict (slug) do nothing;
```

- [ ] **Step 2: Apply via Supabase MCP**

Use `apply_migration` (name: `0004_seed_taxonomy`).
Expected: success.

- [ ] **Step 3: Verify seed counts**

Use `execute_sql`:
```sql
select (select count(*) from domains) as domains,
       (select count(*) from benchmarks) as benchmarks;
```
Expected: `domains = 8`, `benchmarks = 9`.

- [ ] **Step 4: Re-run idempotency check**

Apply `0004_seed_taxonomy` a second time.
Expected: success, counts unchanged (8 / 9) — `on conflict do nothing` works.

- [ ] **Step 5: Commit**
```bash
git add db/migrations/0004_seed_taxonomy.sql
git commit -m "feat: seed 8-domain canon + 9 canonical benchmarks (LIBERO flagged saturated)"
```

---

## Task 8: Backbone README + plan close-out

**Files:**
- Create: `24_sota-robotics/db/README.md`

- [ ] **Step 1: Document the backbone**

Create `db/README.md` covering: how to apply migrations (Supabase MCP or `supabase db push`), the `results` idempotency key, the RLS boundary (service-role writes / publishable-key reads published only), and that PWC-archive rows enter as `held`.

- [ ] **Step 2: Final green check**

Run: `cd ingest && uv run pytest -q`
Expected: all pass (~13 tests).
Use `get_advisors` (security) once more — expected: no RLS findings.

- [ ] **Step 3: Commit + push**
```bash
git add db/README.md
git commit -m "docs: data backbone README"
git push origin main
```

---

## Self-Review (completed against spec)

**Spec coverage (§ → task):** §5 data model → Tasks 2,5; §6 verification_status/skeptic gate fields → Tasks 2,5 (enum + columns; the *agent* gate is Plan 4); §11.2 saturation/realm/origin tags → Tasks 2,5,7 (`is_saturated`, `realm`, `origin`); §11.3 PWC sota-extractor reuse → Task 3; §11.5 schema/RLS/idempotency → Tasks 5,6,7. **Not in this plan (correctly — later plans):** ingest scheduling/GitHub Actions (Plan 3), Claude extractor+skeptic + Batch/cache (Plan 4), web views (Plan 5), Phase-0 backfill execution (Plan 2 — Task 3 here builds only the parser it uses).

**Placeholder scan:** none — every code/SQL step is complete and runnable.

**Type consistency:** `ResultClaim` fields (Task 2) match `build_result_row` keys (Task 4) and the `results` columns (Task 5); enum string values (`sim`, `public_reproducible`, `pending`) match across Pydantic (Task 2), upsert (Task 4), and SQL enums (Task 5); `CONFLICT_TARGET` (Task 4) == `unique(method_id,benchmark_id,eval_conditions_hash)` (Task 5); `parse_evaluation_tables` returns `ResultClaim`s consumed by `build_result_row`.

**Known external dependency:** Tasks 5–7 require a Supabase project + the Supabase MCP connected (or `supabase` CLI). The Python core (Tasks 0–4) is fully testable with zero external services.
