# Phase-0 Backfill — Implementation Plan (Sub-plan 2 of 5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. This plan depends on Plan 1 (Data Backbone) being merged: it reuses `ResultClaim`, `PaperRec`, `canonical_hash`, `parse_evaluation_tables`, `build_result_row`, and `CONFLICT_TARGET` **exactly as defined there** — do not redefine them.

**Goal:** Cold-start the corpus from **frozen** sources so the DB is never empty before live ingest (Plan 3) and the agent pipeline (Plan 4) come online. Three feeds: (a) the Papers-with-Code archive on Hugging Face (`huggingface.co/pwc-archive`) → `results` (every row imported `HELD`, never auto-published); (b) four community "awesome-lists" → `papers` + `code` + domain taxonomy mapping for cold-start coverage. All DB writes go through a single **service-role** Supabase writer and are **idempotent** (the `UNIQUE(method_id, benchmark_id, eval_conditions_hash)` constraint plus natural-key upserts on reference tables). A `python -m sota_ingest.backfill` CLI runs the whole pass.

**Architecture:** Pure, unit-tested logic is split from thin I/O wrappers. Pure modules — `awesome_lists.py` (markdown link/section parsing → `PaperRec` + repo records, section-header → domain-slug mapping) and the upsert-payload builders — are TDD'd against fixtures with **zero** network/DB. I/O modules — `fetch.py` (httpx GET with retry) and `db.py` (the service-role Supabase client that resolves/creates `method`/`benchmark`/`paper`/`code` rows by slug/natural-key and upserts `results` via `build_result_row` + `CONFLICT_TARGET`) — are tested with mocks and recorded fixtures, never a live network or live DB. `backfill.py` is a thin orchestrator: fetch → parse (pure) → resolve+upsert (I/O). The PWC feed reuses Plan 1's `parse_evaluation_tables` verbatim; we only add a robotics-task filter in front of it.

**Tech Stack:** Python 3.13 managed by `uv`; Pydantic v2; `httpx` (sync client, retries); `supabase` (supabase-py v2, service-role client); pytest (mocks + recorded JSON/markdown fixtures). No live network or DB in the test suite. CC-BY-SA sources are attributed in `eval_conditions` / `skeptic_notes` and in `db/ATTRIBUTION.md`.

---

## Where this sits in the 5-plan sequence

| # | Plan | This plan's relationship |
|---|------|--------------------------|
| 1 | Data Backbone & Seed Loaders | **Dependency.** Provides models, hashing, `parse_evaluation_tables`, `build_result_row`, `CONFLICT_TARGET`, schema, seed taxonomy. |
| **2** | **Phase-0 Backfill** (this doc) | Fills the empty DB from frozen feeds. First code to actually `INSERT`/`UPSERT` against Supabase. |
| 3 | Live Ingest Spine | Reuses `db.py` (this plan) as its write path for arXiv/HF/GitHub fetchers. |
| 4 | Agent Pipeline | Re-verifies the `HELD` rows this plan imports (`HELD` → `published`/`refuted`). |
| 5 | Web Views | Reads only `published` rows; backfilled `HELD` rows stay invisible until Plan 4 promotes them. |

**Key invariant carried from the spec:** PWC archive numbers are stale/self-reported and leaderboards are gamed (LIBERO ~98% = memorization). This plan therefore imports **everything as `HELD`** and records provenance; it never ranks or publishes. Promotion is exclusively Plan 4's job.

---

## File Structure (this plan)

```
24_sota-robotics/
├── db/
│   └── ATTRIBUTION.md                              # NEW: CC-BY-SA source credits
├── ingest/
│   ├── pyproject.toml                              # MODIFIED: add httpx, supabase deps
│   ├── src/sota_ingest/
│   │   ├── fetch.py                                # NEW: httpx GET with retry (thin I/O)
│   │   ├── awesome_lists.py                        # NEW: pure markdown parsing + taxonomy map
│   │   ├── pwc_backfill.py                         # NEW: robotics filter -> parse_evaluation_tables
│   │   ├── db.py                                   # NEW: service-role Supabase writer (thin I/O)
│   │   └── backfill.py                             # NEW: `python -m sota_ingest.backfill` CLI
│   └── tests/
│       ├── conftest.py                             # NEW: shared fixtures + fake supabase client
│       ├── fixtures/
│       │   ├── awesome_embodied_ai.md              # NEW: recorded markdown sample
│       │   ├── awesome_vla.md                      # NEW: recorded markdown sample
│       │   ├── pwc_robotics_tasks.json             # NEW: recorded PWC sample (mixed tasks)
│       │   └── pwc_eval_table.json                 # (exists, Plan 1)
│       ├── test_awesome_lists.py                   # NEW
│       ├── test_pwc_backfill.py                    # NEW
│       ├── test_fetch.py                           # NEW (mocked httpx)
│       ├── test_db.py                              # NEW (fake supabase client)
│       └── test_backfill.py                        # NEW (orchestration, all I/O mocked)
└── docs/plans/2026-06-18-02-phase0-backfill.md     # this doc
```

**Boundaries.** `awesome_lists.py`, `pwc_backfill.py` are pure (parse text → records); they unit-test against fixtures with no I/O. `fetch.py` and `db.py` are the *only* modules that touch the network or DB, and both are tested with mocks/fakes. `backfill.py` wires them together and is tested with every boundary mocked. Reference-table resolution (slug → id) lives in `db.py`; the idempotency contract (`build_result_row` + `CONFLICT_TARGET`) comes from Plan 1 untouched.

---

## Task 0: Add dependencies (httpx + supabase)

**Files:**
- Modify: `24_sota-robotics/ingest/pyproject.toml`

- [ ] **Step 1: Add runtime deps via uv**

Run (from `24_sota-robotics/ingest/`):
```bash
cd ingest && uv add httpx "supabase>=2.15.0"
```
Expected: `pyproject.toml` `dependencies` now lists `httpx` and `supabase`; `uv.lock` updates; a `.venv` resolve succeeds.

- [ ] **Step 2: Verify the deps import**

Run:
```bash
cd ingest && uv run python -c "import httpx, supabase; print(httpx.__version__, supabase.__version__)"
```
Expected: two version strings print, no `ModuleNotFoundError`.

- [ ] **Step 3: Confirm the existing suite still green**

Run:
```bash
cd ingest && uv run pytest -q
```
Expected: PASS — the 13 Plan-1 tests still pass (adding deps changes nothing).

- [ ] **Step 4: Commit**
```bash
git add ingest/pyproject.toml ingest/uv.lock
git commit -m "build: add httpx + supabase deps for Phase-0 backfill"
```

---

## Task 1: Shared test fixtures and a fake Supabase client

We need a fake that mimics the tiny slice of supabase-py we use (`.table(name).select(...).eq(...).limit(1).execute()` for reads and `.insert(...).execute()` / `.upsert(..., on_conflict=...).execute()` for writes), recording calls so tests can assert on them. We also record real-shaped markdown + PWC fixtures.

**Files:**
- Create: `24_sota-robotics/ingest/tests/conftest.py`
- Create: `24_sota-robotics/ingest/tests/fixtures/awesome_embodied_ai.md`
- Create: `24_sota-robotics/ingest/tests/fixtures/awesome_vla.md`
- Create: `24_sota-robotics/ingest/tests/fixtures/pwc_robotics_tasks.json`

- [ ] **Step 1: Write the markdown fixtures**

`tests/fixtures/awesome_embodied_ai.md`:
```markdown
# Awesome Embodied AI

A curated list. License: CC-BY-SA-4.0.

## Manipulation
- [OpenVLA: An Open-Source Vision-Language-Action Model](https://arxiv.org/abs/2406.09246) | [code](https://github.com/openvla/openvla)
- [pi0: A Vision-Language-Action Flow Model](https://arxiv.org/abs/2410.24164)

## Locomotion and Whole-Body Control
- [Humanoid Locomotion as Next Token Prediction](https://arxiv.org/abs/2402.19469) [[github]](https://github.com/facebookresearch/humanoid)

## Navigation
- [NaVid: Video-based VLM Plans the Next Step for Vision-and-Language Navigation](https://arxiv.org/abs/2402.15852)

## Misc
- Not a link, just prose that must be ignored.
```

`tests/fixtures/awesome_vla.md`:
```markdown
# Awesome Embodied VLA / VA / VLN

> Sources reused under CC-BY-SA.

### World Models
* [Genie: Generative Interactive Environments](https://arxiv.org/abs/2402.15391)

### Sim-to-Real
* [DrEureka: Language Model Guided Sim-to-Real Transfer](https://arxiv.org/abs/2406.01967) ([Code](https://github.com/eureka-research/DrEureka))
```

- [ ] **Step 2: Write the PWC robotics-tasks fixture (mixed tasks, to prove filtering)**

`tests/fixtures/pwc_robotics_tasks.json`:
```json
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
            }
          ]
        }
      }
    ]
  },
  {
    "task": "Visual Question Answering",
    "datasets": [
      {
        "dataset": "VQAv2",
        "sota": {
          "metrics": ["Accuracy"],
          "rows": [
            {
              "model_name": "PaLI",
              "metrics": {"Accuracy": "84.3"},
              "paper_url": "https://arxiv.org/abs/2209.06794",
              "code_links": []
            }
          ]
        }
      }
    ]
  },
  {
    "task": "Visual Navigation",
    "datasets": [
      {
        "dataset": "Habitat ObjectNav",
        "sota": {
          "metrics": ["SPL"],
          "rows": [
            {
              "model_name": "OVRL-V2",
              "metrics": {"SPL": "0.29"},
              "paper_url": "https://arxiv.org/abs/2204.13226",
              "code_links": []
            }
          ]
        }
      }
    ]
  }
]
```

- [ ] **Step 3: Write `conftest.py` with the fake Supabase client**
```python
# tests/conftest.py
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


class _FakeQuery:
    """Mimics the chainable supabase-py PostgREST query builder.

    Only the slice of the API our db.py uses is implemented:
      .select(cols).eq(col, val).limit(n).execute()      -> reads
      .insert(row).execute()                              -> single insert
      .upsert(rows, on_conflict=...).execute()            -> idempotent upsert
    Every terminal .execute() returns an object with a `.data` list,
    mirroring supabase-py's APIResponse.
    """

    def __init__(self, table: "_FakeTable"):
        self._table = table
        self._op = None
        self._payload = None
        self._on_conflict = None
        self._filters: list[tuple[str, object]] = []

    def select(self, *_cols):
        self._op = "select"
        return self

    def eq(self, col, val):
        self._filters.append((col, val))
        return self

    def limit(self, _n):
        return self

    def insert(self, row):
        self._op = "insert"
        self._payload = row
        return self

    def upsert(self, rows, on_conflict=None):
        self._op = "upsert"
        self._payload = rows
        self._on_conflict = on_conflict
        return self

    def execute(self):
        self._table.calls.append(
            {
                "table": self._table.name,
                "op": self._op,
                "payload": self._payload,
                "on_conflict": self._on_conflict,
                "filters": self._filters,
            }
        )
        if self._op == "select":
            data = self._table.select_handler(self._table.name, self._filters)
            return _FakeResponse(data)
        if self._op in ("insert", "upsert"):
            data = self._table.write_handler(
                self._table.name, self._op, self._payload, self._on_conflict
            )
            return _FakeResponse(data)
        return _FakeResponse([])


class _FakeResponse:
    def __init__(self, data):
        self.data = data


class _FakeTable:
    def __init__(self, name, calls, select_handler, write_handler):
        self.name = name
        self.calls = calls
        self.select_handler = select_handler
        self.write_handler = write_handler

    def select(self, *cols):
        return _FakeQuery(self).select(*cols)

    def insert(self, row):
        return _FakeQuery(self).insert(row)

    def upsert(self, rows, on_conflict=None):
        return _FakeQuery(self).upsert(rows, on_conflict=on_conflict)


class FakeSupabase:
    """Stand-in for supabase.Client.

    `seed` pre-populates existing rows keyed by (table, slug-or-natural-key);
    selects look up there, writes assign incrementing ids and remember rows.
    """

    def __init__(self, seed: dict | None = None):
        self.calls: list[dict] = []
        self._store: dict[str, list[dict]] = {}
        self._next_id = 1
        for (table, _key), row in (seed or {}).items():
            self._store.setdefault(table, []).append(row)
            self._next_id = max(self._next_id, int(row.get("id", 0)) + 1)

    def table(self, name):
        return _FakeTable(name, self.calls, self._select, self._write)

    def _select(self, table, filters):
        rows = self._store.get(table, [])
        out = []
        for r in rows:
            if all(r.get(c) == v for c, v in filters):
                out.append(r)
        return out

    def _write(self, table, op, payload, on_conflict):
        rows = payload if isinstance(payload, list) else [payload]
        written = []
        bucket = self._store.setdefault(table, [])
        for row in rows:
            existing = None
            if op == "upsert" and on_conflict:
                keys = [k.strip() for k in on_conflict.split(",")]
                for r in bucket:
                    if all(r.get(k) == row.get(k) for k in keys):
                        existing = r
                        break
            if existing is not None:
                existing.update(row)
                written.append(existing)
            else:
                new = dict(row)
                new.setdefault("id", self._next_id)
                self._next_id += 1
                bucket.append(new)
                written.append(new)
        return written


@pytest.fixture
def fake_supabase():
    return FakeSupabase
```

- [ ] **Step 4: Sanity-check the fixtures load**

Run:
```bash
cd ingest && uv run python -c "import json,pathlib; p=pathlib.Path('tests/fixtures'); json.loads((p/'pwc_robotics_tasks.json').read_text()); print('ok', len(list(p.glob('*.md'))), 'md files')"
```
Expected: `ok 2 md files`.

- [ ] **Step 5: Commit**
```bash
git add ingest/tests/conftest.py ingest/tests/fixtures/awesome_embodied_ai.md ingest/tests/fixtures/awesome_vla.md ingest/tests/fixtures/pwc_robotics_tasks.json
git commit -m "test: fixtures + fake supabase client for backfill"
```

---

## Task 2: PWC robotics filter (pure)

`parse_evaluation_tables` (Plan 1) already maps PWC JSON → `HELD` `ResultClaim`s. We only need a **pure** filter that keeps robotics-relevant task blocks before handing them to it, so we don't ingest VQA/captioning rows.

**Files:**
- Create: `24_sota-robotics/ingest/src/sota_ingest/pwc_backfill.py`
- Test: `24_sota-robotics/ingest/tests/test_pwc_backfill.py`

- [ ] **Step 1: Write the failing test**
```python
# tests/test_pwc_backfill.py
import json

from sota_ingest.pwc_backfill import filter_robotics_tasks, claims_from_pwc
from sota_ingest.models import VerificationStatus


def test_filter_keeps_only_robotics_tasks(fixtures_dir):
    data = json.loads((fixtures_dir / "pwc_robotics_tasks.json").read_text())
    kept = filter_robotics_tasks(data)
    tasks = {b["task"] for b in kept}
    assert "Robot Manipulation" in tasks
    assert "Visual Navigation" in tasks      # navigation is in-scope
    assert "Visual Question Answering" not in tasks


def test_claims_from_pwc_are_held_and_filtered(fixtures_dir):
    data = json.loads((fixtures_dir / "pwc_robotics_tasks.json").read_text())
    claims = claims_from_pwc(data)
    # VQAv2 row dropped -> 2 claims (LIBERO + Habitat ObjectNav)
    assert len(claims) == 2
    assert all(c.verification_status == VerificationStatus.HELD for c in claims)
    slugs = {c.benchmark_slug for c in claims}
    assert "libero" in slugs and "habitat-objectnav" in slugs


def test_empty_input_yields_no_claims():
    assert claims_from_pwc([]) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ingest && uv run pytest tests/test_pwc_backfill.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sota_ingest.pwc_backfill'`.

- [ ] **Step 3: Write minimal implementation**
```python
# src/sota_ingest/pwc_backfill.py
"""Filter the frozen PWC archive down to robotics tasks, then reuse
Plan 1's parse_evaluation_tables (imports everything HELD)."""
from typing import Any

from sota_ingest.models import ResultClaim
from sota_ingest.sota_extractor import parse_evaluation_tables

# Substrings (lowercased) that mark a PWC task block as in-scope for a
# robotics-native SOTA tracker. Conservative: manipulation, locomotion,
# navigation, grasping, pose, sim2real, world models, embodied control.
ROBOTICS_TASK_KEYWORDS = (
    "robot",
    "manipulation",
    "grasp",
    "locomotion",
    "humanoid",
    "navigation",
    "vision-and-language navigation",
    "pose estimation",
    "sim-to-real",
    "sim2real",
    "world model",
    "embodied",
    "whole-body",
    "dexterous",
)


def _is_robotics_task(task_name: str) -> bool:
    name = (task_name or "").lower()
    return any(kw in name for kw in ROBOTICS_TASK_KEYWORDS)


def filter_robotics_tasks(data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only task blocks whose task name matches a robotics keyword."""
    return [block for block in data if _is_robotics_task(block.get("task", ""))]


def claims_from_pwc(data: list[dict[str, Any]]) -> list[ResultClaim]:
    """Robotics-filtered PWC archive -> HELD ResultClaims (Plan 1 contract)."""
    return parse_evaluation_tables(filter_robotics_tasks(data))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ingest && uv run pytest tests/test_pwc_backfill.py -v`
Expected: PASS (3 passed).

> Note: `claims_from_pwc` produces `benchmark_slug="habitat-objectnav"` because `parse_evaluation_tables` slugifies the dataset name `"Habitat ObjectNav"`. The seed benchmark slug is `habitat`; reconciling that alias is **not** this task's job — `db.py` (Task 5) creates any benchmark slug it doesn't find, and Plan 4's skeptic merges aliases. We do not silently remap here.

- [ ] **Step 5: Commit**
```bash
git add ingest/src/sota_ingest/pwc_backfill.py ingest/tests/test_pwc_backfill.py
git commit -m "feat: robotics-task filter over frozen PWC archive (HELD import)"
```

---

## Task 3: Awesome-list markdown parsing (pure)

Parse the four awesome-list READMEs into structured records: section header → domain slug, and each list item → an arXiv-derived `PaperRec` plus an optional repo URL. Pure string work, fixture-tested.

**Files:**
- Create: `24_sota-robotics/ingest/src/sota_ingest/awesome_lists.py`
- Test: `24_sota-robotics/ingest/tests/test_awesome_lists.py`

- [ ] **Step 1: Write the failing test**
```python
# tests/test_awesome_lists.py
from sota_ingest.awesome_lists import (
    AwesomeRecord,
    map_section_to_domain,
    parse_awesome_markdown,
    SOURCES,
)
from sota_ingest.models import PaperRec


def test_section_header_maps_to_domain_slug():
    assert map_section_to_domain("Manipulation") == "humanoid-vla-manip"
    assert map_section_to_domain("Locomotion and Whole-Body Control") == "locomotion-wbc"
    assert map_section_to_domain("World Models") == "world-models"
    assert map_section_to_domain("Sim-to-Real") == "sim2real-rl"
    assert map_section_to_domain("Navigation") == "navigation-vln"


def test_unmappable_section_returns_none():
    assert map_section_to_domain("Misc") is None
    assert map_section_to_domain("Acknowledgements") is None


def test_parse_extracts_papers_repos_and_domain(fixtures_dir):
    md = (fixtures_dir / "awesome_embodied_ai.md").read_text()
    records = parse_awesome_markdown(md, source_url="https://example.com/list")
    by_arxiv = {r.paper.arxiv_id: r for r in records if r.paper.arxiv_id}

    # OpenVLA: arxiv id parsed, repo captured, domain = manipulation
    openvla = by_arxiv["2406.09246"]
    assert isinstance(openvla.paper, PaperRec)
    assert openvla.paper.title.startswith("OpenVLA")
    assert openvla.paper.url == "https://arxiv.org/abs/2406.09246"
    assert openvla.repo_url == "https://github.com/openvla/openvla"
    assert openvla.domain_slug == "humanoid-vla-manip"

    # pi0: no code link -> repo_url is None
    pi0 = by_arxiv["2410.24164"]
    assert pi0.repo_url is None

    # Locomotion item picks up the [[github]] style link + locomotion domain
    ntp = by_arxiv["2402.19469"]
    assert ntp.repo_url == "https://github.com/facebookresearch/humanoid"
    assert ntp.domain_slug == "locomotion-wbc"


def test_prose_lines_without_links_are_ignored(fixtures_dir):
    md = (fixtures_dir / "awesome_embodied_ai.md").read_text()
    records = parse_awesome_markdown(md, source_url="x")
    # the "Misc" prose line is not a link -> excluded
    assert all(r.paper.url is not None for r in records)
    assert all("Not a link" not in (r.paper.title or "") for r in records)


def test_second_list_parses_world_and_sim2real(fixtures_dir):
    md = (fixtures_dir / "awesome_vla.md").read_text()
    records = parse_awesome_markdown(md, source_url="x")
    domains = {r.domain_slug for r in records}
    assert "world-models" in domains
    assert "sim2real-rl" in domains
    dreureka = next(r for r in records if r.paper.arxiv_id == "2406.01967")
    assert dreureka.repo_url == "https://github.com/eureka-research/DrEureka"


def test_sources_registry_has_four_lists():
    # The four awesome-lists named in the Phase-0 spec.
    assert len(SOURCES) == 4
    urls = " ".join(s.raw_url for s in SOURCES)
    assert "wadeKeith/Awesome-Embodied-AI" in urls
    assert "jonyzhang2023/awesome-embodied-vla-va-vln" in urls
    assert "natnew/awesome-physical-ai" in urls
    assert "zchoi/Awesome-Embodied-Robotics-and-Agent" in urls
    assert all(s.license == "CC-BY-SA-4.0" for s in SOURCES)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ingest && uv run pytest tests/test_awesome_lists.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sota_ingest.awesome_lists'`.

- [ ] **Step 3: Write minimal implementation**
```python
# src/sota_ingest/awesome_lists.py
"""Pure parsers for the four community 'awesome-lists' we cold-start from.

All four are CC-BY-SA; we record attribution in db/ATTRIBUTION.md and stamp
each derived paper/code record's provenance in db.py. This module does NO I/O:
it turns raw markdown into AwesomeRecord objects only.
"""
import re
from dataclasses import dataclass

from sota_ingest.models import PaperRec

# --- Source registry (raw GitHub README URLs; CC-BY-SA-4.0) -----------------


@dataclass(frozen=True)
class AwesomeSource:
    name: str
    raw_url: str
    license: str


SOURCES: tuple[AwesomeSource, ...] = (
    AwesomeSource(
        "Awesome-Embodied-AI",
        "https://raw.githubusercontent.com/wadeKeith/Awesome-Embodied-AI/main/README.md",
        "CC-BY-SA-4.0",
    ),
    AwesomeSource(
        "awesome-embodied-vla-va-vln",
        "https://raw.githubusercontent.com/jonyzhang2023/awesome-embodied-vla-va-vln/main/README.md",
        "CC-BY-SA-4.0",
    ),
    AwesomeSource(
        "awesome-physical-ai",
        "https://raw.githubusercontent.com/natnew/awesome-physical-ai/main/README.md",
        "CC-BY-SA-4.0",
    ),
    AwesomeSource(
        "Awesome-Embodied-Robotics-and-Agent",
        "https://raw.githubusercontent.com/zchoi/Awesome-Embodied-Robotics-and-Agent/main/README.md",
        "CC-BY-SA-4.0",
    ),
)


# --- Output record ----------------------------------------------------------


@dataclass
class AwesomeRecord:
    paper: PaperRec
    repo_url: str | None
    domain_slug: str | None
    source_url: str


# --- Section header -> our 8 domain slugs -----------------------------------

# Each (keyword tuple) -> domain slug. Matched case-insensitively as a
# substring of the section header, first match wins. Order matters: more
# specific phrases must precede generic ones.
_SECTION_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("world-action", "world action", "action-conditioned"), "world-action-models"),
    (("world model",), "world-models"),
    (("locomotion", "whole-body", "whole body", "legged", "bipedal"), "locomotion-wbc"),
    (("sim-to-real", "sim2real", "domain randomization", "real-world rl"), "sim2real-rl"),
    (("navigation", "vln"), "navigation-vln"),
    (("perception", "grasp", "pose estimation", "3d vision"), "robot-perception"),
    (
        ("demonstration", "imitation", "teleop", "dataset", "cross-embodiment", "learning from"),
        "lfd-robot-data",
    ),
    (
        ("manipulation", "vla", "vision-language-action", "dexterous", "bimanual", "humanoid"),
        "humanoid-vla-manip",
    ),
)


def map_section_to_domain(header: str) -> str | None:
    """Map an awesome-list section header to one of our 8 domain slugs."""
    h = (header or "").lower()
    for keywords, slug in _SECTION_RULES:
        if any(kw in h for kw in keywords):
            return slug
    return None


# --- Markdown parsing -------------------------------------------------------

_HEADER_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
_LIST_ITEM_RE = re.compile(r"^\s*[-*+]\s+(.*\S.*)$")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_ARXIV_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", re.IGNORECASE)
_REPO_RE = re.compile(r"https?://(?:www\.)?github\.com/[^)\s\]]+", re.IGNORECASE)


def _arxiv_id(url: str) -> str | None:
    m = _ARXIV_RE.search(url)
    return m.group(1) if m else None


def parse_awesome_markdown(md: str, source_url: str) -> list[AwesomeRecord]:
    """Parse one awesome-list README into AwesomeRecords.

    Rules:
      - Track the current section header; map it to a domain slug.
      - Each list item that contains at least one markdown link becomes a
        record. The first arxiv link (or first link) is the paper; the first
        github link anywhere in the item is the repo.
      - Prose lines without links are ignored.
    """
    records: list[AwesomeRecord] = []
    current_domain: str | None = None

    for line in md.splitlines():
        header = _HEADER_RE.match(line)
        if header:
            current_domain = map_section_to_domain(header.group(1))
            continue

        item = _LIST_ITEM_RE.match(line)
        if not item:
            continue
        text = item.group(1)
        links = _MD_LINK_RE.findall(text)  # [(label, url), ...]
        if not links:
            continue

        # Pick the paper link: prefer an arxiv link, else the first link.
        paper_label, paper_url = links[0]
        for label, url in links:
            if _arxiv_id(url):
                paper_label, paper_url = label, url
                break

        # Repo: first github URL anywhere in the raw item text.
        repo_match = _REPO_RE.search(text)
        repo_url = repo_match.group(0).rstrip(").]") if repo_match else None
        # Don't let the paper link double as the repo.
        if repo_url == paper_url:
            repo_url = None

        arxiv = _arxiv_id(paper_url)
        normalized_url = (
            f"https://arxiv.org/abs/{arxiv}" if arxiv else paper_url
        )
        records.append(
            AwesomeRecord(
                paper=PaperRec(
                    arxiv_id=arxiv,
                    title=paper_label.strip(),
                    url=normalized_url,
                ),
                repo_url=repo_url,
                domain_slug=current_domain,
                source_url=source_url,
            )
        )
    return records
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ingest && uv run pytest tests/test_awesome_lists.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**
```bash
git add ingest/src/sota_ingest/awesome_lists.py ingest/tests/test_awesome_lists.py
git commit -m "feat: pure awesome-list markdown parser + section->domain mapping"
```

---

## Task 4: HTTP fetcher (thin I/O, mocked)

A single retrying GET so both feeds share one network code path. Tested with a mocked transport — no real network.

**Files:**
- Create: `24_sota-robotics/ingest/src/sota_ingest/fetch.py`
- Test: `24_sota-robotics/ingest/tests/test_fetch.py`

- [ ] **Step 1: Write the failing test**
```python
# tests/test_fetch.py
import httpx
import pytest

from sota_ingest.fetch import fetch_text, fetch_json


def _client_returning(*responses):
    """Build an httpx.Client whose transport replays the given responses."""
    seq = list(responses)

    def handler(request):
        return seq.pop(0)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_text_returns_body():
    client = _client_returning(httpx.Response(200, text="# hello"))
    assert fetch_text("https://x/readme.md", client=client) == "# hello"


def test_fetch_json_parses_body():
    client = _client_returning(httpx.Response(200, json=[{"task": "Robot Manipulation"}]))
    data = fetch_json("https://x/data.json", client=client)
    assert data == [{"task": "Robot Manipulation"}]


def test_fetch_text_retries_then_succeeds():
    client = _client_returning(
        httpx.Response(503, text="busy"),
        httpx.Response(200, text="ok"),
    )
    assert fetch_text("https://x", client=client, retries=2, backoff=0.0) == "ok"


def test_fetch_text_raises_after_exhausting_retries():
    client = _client_returning(
        httpx.Response(500), httpx.Response(500), httpx.Response(500)
    )
    with pytest.raises(httpx.HTTPStatusError):
        fetch_text("https://x", client=client, retries=2, backoff=0.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ingest && uv run pytest tests/test_fetch.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sota_ingest.fetch'`.

- [ ] **Step 3: Write minimal implementation**
```python
# src/sota_ingest/fetch.py
"""Thin retrying HTTP layer shared by both Phase-0 feeds.

The only network-touching module besides db.py. A caller may inject an
httpx.Client (tests pass a MockTransport-backed one); otherwise we make a
short-lived client per call. retries/backoff are explicit so tests run fast.
"""
import time
from typing import Any

import httpx

DEFAULT_HEADERS = {"User-Agent": "sota-robotics-backfill/0.1 (+https://github.com/jatinsikka)"}
DEFAULT_TIMEOUT = 30.0


def _get(url: str, client: httpx.Client, retries: int, backoff: float) -> httpx.Response:
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        resp = client.get(url, headers=DEFAULT_HEADERS, timeout=DEFAULT_TIMEOUT, follow_redirects=True)
        try:
            resp.raise_for_status()
            return resp
        except httpx.HTTPStatusError as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(backoff)
                continue
            raise
    assert last_exc is not None
    raise last_exc


def fetch_text(url: str, client: httpx.Client | None = None, retries: int = 3, backoff: float = 1.0) -> str:
    if client is not None:
        return _get(url, client, retries, backoff).text
    with httpx.Client() as owned:
        return _get(url, owned, retries, backoff).text


def fetch_json(url: str, client: httpx.Client | None = None, retries: int = 3, backoff: float = 1.0) -> Any:
    if client is not None:
        return _get(url, client, retries, backoff).json()
    with httpx.Client() as owned:
        return _get(url, owned, retries, backoff).json()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ingest && uv run pytest tests/test_fetch.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**
```bash
git add ingest/src/sota_ingest/fetch.py ingest/tests/test_fetch.py
git commit -m "feat: retrying httpx fetcher (text + json) for backfill feeds"
```

---

## Task 5: Service-role Supabase writer (thin I/O, faked)

`db.py` is the only DB module. It resolves/creates `methods`, `benchmarks`, `papers`, `code` by natural key (slug for methods/benchmarks, `arxiv_id`/title for papers, `repo_url` for code) and upserts `results` via Plan 1's `build_result_row` + `CONFLICT_TARGET`. It builds the service-role client from `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`. Tests inject the `FakeSupabase` from `conftest.py`; the real client constructor is exercised only by the never-run-in-CI `client_from_env`.

**Files:**
- Create: `24_sota-robotics/ingest/src/sota_ingest/db.py`
- Test: `24_sota-robotics/ingest/tests/test_db.py`

- [ ] **Step 1: Write the failing test**
```python
# tests/test_db.py
import pytest

from sota_ingest.db import SotaWriter, CONFLICT_ON
from sota_ingest.models import PaperRec, ResultClaim, VerificationStatus
from sota_ingest.upsert import CONFLICT_TARGET


def test_conflict_on_matches_plan1_target():
    # db.py must upsert results on EXACTLY the Plan 1 constraint columns.
    assert CONFLICT_ON == ",".join(CONFLICT_TARGET)
    assert CONFLICT_ON == "method_id,benchmark_id,eval_conditions_hash"


def test_resolve_method_creates_when_absent(fake_supabase):
    w = SotaWriter(fake_supabase())
    mid = w.resolve_method("openvla-oft")
    assert isinstance(mid, int)
    # second call returns the SAME id (idempotent: select hit, no new insert)
    assert w.resolve_method("openvla-oft") == mid
    inserts = [c for c in w.client.calls if c["table"] == "methods" and c["op"] == "insert"]
    assert len(inserts) == 1


def test_resolve_benchmark_links_domain_when_known(fake_supabase):
    seed = {("domains", "humanoid-vla-manip"): {"id": 7, "slug": "humanoid-vla-manip"}}
    w = SotaWriter(fake_supabase(seed))
    bid = w.resolve_benchmark("robocasa", domain_slug="humanoid-vla-manip")
    assert isinstance(bid, int)
    bench_insert = next(c for c in w.client.calls if c["table"] == "benchmarks" and c["op"] == "insert")
    assert bench_insert["payload"]["domain_id"] == 7


def test_resolve_benchmark_without_domain_is_ok(fake_supabase):
    w = SotaWriter(fake_supabase())
    bid = w.resolve_benchmark("simplerenv", domain_slug=None)
    assert isinstance(bid, int)


def test_resolve_paper_dedupes_on_arxiv_id(fake_supabase):
    w = SotaWriter(fake_supabase())
    p = PaperRec(arxiv_id="2406.09246", title="OpenVLA", url="https://arxiv.org/abs/2406.09246")
    pid = w.resolve_paper(p)
    assert w.resolve_paper(p) == pid
    inserts = [c for c in w.client.calls if c["table"] == "papers" and c["op"] == "insert"]
    assert len(inserts) == 1


def test_resolve_code_dedupes_on_repo_url(fake_supabase):
    w = SotaWriter(fake_supabase())
    cid = w.resolve_code("https://github.com/openvla/openvla", license="CC-BY-SA-4.0")
    assert w.resolve_code("https://github.com/openvla/openvla") == cid


def test_upsert_result_uses_build_result_row_and_conflict_target(fake_supabase):
    w = SotaWriter(fake_supabase())
    claim = ResultClaim(
        method_slug="openvla-oft",
        benchmark_slug="libero",
        metric="success_rate",
        metric_value=97.1,
        eval_conditions={"source": "pwc_archive"},
        source_url="https://arxiv.org/abs/2502.19645",
        verification_status=VerificationStatus.HELD,
    )
    w.upsert_result(claim, method_id=1, benchmark_id=2, task_id=None, paper_id=None, code_id=None, run_id="run-x")
    call = next(c for c in w.client.calls if c["table"] == "results")
    assert call["op"] == "upsert"
    assert call["on_conflict"] == "method_id,benchmark_id,eval_conditions_hash"
    row = call["payload"][0] if isinstance(call["payload"], list) else call["payload"]
    assert row["method_id"] == 1 and row["benchmark_id"] == 2
    assert row["verification_status"] == "held"
    assert row["ingested_run_id"] == "run-x"
    # eval_conditions_hash present (idempotency key from Plan 1)
    assert len(row["eval_conditions_hash"]) == 64


def test_upsert_result_is_idempotent_across_runs(fake_supabase):
    client = fake_supabase()
    w = SotaWriter(client)
    claim = ResultClaim(
        method_slug="m", benchmark_slug="b", metric="success_rate",
        metric_value=90.0, eval_conditions={"source": "pwc_archive"}, source_url="u",
    )
    w.upsert_result(claim, 1, 2, None, None, None, "run-1")
    w.upsert_result(claim, 1, 2, None, None, None, "run-2")
    # same conflict key -> one stored results row, not two
    stored = client._store.get("results", [])
    assert len(stored) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ingest && uv run pytest tests/test_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sota_ingest.db'`.

- [ ] **Step 3: Write minimal implementation**
```python
# src/sota_ingest/db.py
"""Service-role Supabase writer for Phase-0 backfill.

The ONLY module that writes to Postgres. Reference rows (methods/benchmarks/
papers/code) are resolved-or-created by natural key; results are upserted on
the Plan 1 UNIQUE constraint so re-runs are idempotent.

Auth: service-role client from SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY
(RLS allows writes only to the service role; the publishable key is read-only).
Tests inject a fake client implementing the same chainable .table(...) API.
"""
import os
import re
from typing import Any

from supabase import Client, create_client

from sota_ingest.models import PaperRec, ResultClaim
from sota_ingest.upsert import CONFLICT_TARGET, build_result_row

# Postgres on_conflict string must match Plan 1's CONFLICT_TARGET exactly.
CONFLICT_ON = ",".join(CONFLICT_TARGET)


def client_from_env() -> Client:
    """Build the service-role client. Never run in the test suite (would
    require real creds); used by backfill.py at runtime only."""
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(url, key)


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")


class SotaWriter:
    """Resolve/create reference rows and upsert results via a Supabase client."""

    def __init__(self, client: Any):
        self.client = client

    # --- generic helpers ---------------------------------------------------

    def _find_id(self, table: str, col: str, val: Any) -> int | None:
        resp = self.client.table(table).select("id").eq(col, val).limit(1).execute()
        rows = resp.data or []
        return int(rows[0]["id"]) if rows else None

    def _insert_returning_id(self, table: str, row: dict[str, Any]) -> int:
        resp = self.client.table(table).insert(row).execute()
        rows = resp.data or []
        if not rows:
            raise RuntimeError(f"insert into {table} returned no row: {row!r}")
        return int(rows[0]["id"])

    # --- reference resolvers (natural-key, idempotent) ---------------------

    def resolve_method(self, slug: str, name: str | None = None, org: str | None = None) -> int:
        slug = _slugify(slug)
        existing = self._find_id("methods", "slug", slug)
        if existing is not None:
            return existing
        return self._insert_returning_id("methods", {"slug": slug, "name": name or slug, "org": org})

    def resolve_benchmark(self, slug: str, domain_slug: str | None = None, name: str | None = None) -> int:
        slug = _slugify(slug)
        existing = self._find_id("benchmarks", "slug", slug)
        if existing is not None:
            return existing
        domain_id = self._find_id("domains", "slug", domain_slug) if domain_slug else None
        return self._insert_returning_id(
            "benchmarks", {"slug": slug, "name": name or slug, "domain_id": domain_id}
        )

    def resolve_paper(self, paper: PaperRec) -> int:
        if paper.arxiv_id:
            existing = self._find_id("papers", "arxiv_id", paper.arxiv_id)
            if existing is not None:
                return existing
        else:
            existing = self._find_id("papers", "title", paper.title)
            if existing is not None:
                return existing
        return self._insert_returning_id(
            "papers",
            {
                "arxiv_id": paper.arxiv_id,
                "title": paper.title,
                "authors": paper.authors,
                "abstract": paper.abstract,
                "published_date": paper.published_date,
                "url": paper.url,
            },
        )

    def resolve_code(self, repo_url: str, license: str | None = None) -> int:
        existing = self._find_id("code", "repo_url", repo_url)
        if existing is not None:
            return existing
        return self._insert_returning_id("code", {"repo_url": repo_url, "license": license})

    # --- results upsert (idempotent via Plan 1 constraint) -----------------

    def upsert_result(
        self,
        claim: ResultClaim,
        method_id: int,
        benchmark_id: int,
        task_id: int | None,
        paper_id: int | None,
        code_id: int | None,
        run_id: str,
    ) -> None:
        row = build_result_row(claim, method_id, benchmark_id, task_id, paper_id, code_id, run_id)
        self.client.table("results").upsert([row], on_conflict=CONFLICT_ON).execute()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ingest && uv run pytest tests/test_db.py -v`
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**
```bash
git add ingest/src/sota_ingest/db.py ingest/tests/test_db.py
git commit -m "feat: service-role Supabase writer (natural-key resolve + idempotent results upsert)"
```

---

## Task 6: Backfill orchestrator + CLI (`python -m sota_ingest.backfill`)

Wire the feeds: for PWC, fetch JSON → `claims_from_pwc` → resolve method/benchmark → `upsert_result`. For awesome-lists, fetch each README → `parse_awesome_markdown` → resolve paper (+ code). The orchestrator takes a `writer` and a `fetch_json`/`fetch_text` pair so tests mock all I/O. A `main()` builds the real writer from env and runs it.

**Files:**
- Create: `24_sota-robotics/ingest/src/sota_ingest/backfill.py`
- Test: `24_sota-robotics/ingest/tests/test_backfill.py`

- [ ] **Step 1: Write the failing test**
```python
# tests/test_backfill.py
import json

from sota_ingest.backfill import run_pwc_backfill, run_awesome_backfill, BackfillStats
from sota_ingest.db import SotaWriter
from sota_ingest.awesome_lists import AwesomeSource


def test_run_pwc_backfill_upserts_filtered_claims(fixtures_dir, fake_supabase):
    data = json.loads((fixtures_dir / "pwc_robotics_tasks.json").read_text())

    def fake_fetch_json(url, **kw):
        return data

    writer = SotaWriter(fake_supabase())
    stats = run_pwc_backfill(writer, run_id="run-1", fetch_json=fake_fetch_json, source_url="https://hf/pwc.json")

    # VQAv2 dropped -> 2 results stored (LIBERO + Habitat ObjectNav)
    assert stats.results_upserted == 2
    stored = writer.client._store.get("results", [])
    assert len(stored) == 2
    assert all(r["verification_status"] == "held" for r in stored)


def test_run_pwc_backfill_is_idempotent(fixtures_dir, fake_supabase):
    data = json.loads((fixtures_dir / "pwc_robotics_tasks.json").read_text())
    writer = SotaWriter(fake_supabase())
    run_pwc_backfill(writer, "run-1", fetch_json=lambda url, **kw: data, source_url="u")
    run_pwc_backfill(writer, "run-2", fetch_json=lambda url, **kw: data, source_url="u")
    assert len(writer.client._store.get("results", [])) == 2  # not 4


def test_run_awesome_backfill_creates_papers_and_code(fixtures_dir, fake_supabase):
    md = (fixtures_dir / "awesome_embodied_ai.md").read_text()
    src = AwesomeSource("test-list", "https://raw/x/README.md", "CC-BY-SA-4.0")

    writer = SotaWriter(fake_supabase())
    stats = run_awesome_backfill(writer, [src], fetch_text=lambda url, **kw: md)

    papers = writer.client._store.get("papers", [])
    code = writer.client._store.get("code", [])
    # 4 list items with links -> 4 papers; 2 have github repos
    assert len(papers) == 4
    assert len(code) == 2
    assert stats.papers_upserted == 4
    assert stats.code_upserted == 2
    # CC-BY-SA attribution propagated onto code rows
    assert all(c["license"] == "CC-BY-SA-4.0" for c in code)


def test_run_awesome_backfill_dedupes_repeated_paper(fixtures_dir, fake_supabase):
    md = (fixtures_dir / "awesome_vla.md").read_text()
    src = AwesomeSource("a", "https://raw/a", "CC-BY-SA-4.0")
    writer = SotaWriter(fake_supabase())
    # run the SAME source twice -> arxiv-id dedupe means no duplicate papers
    run_awesome_backfill(writer, [src, src], fetch_text=lambda url, **kw: md)
    arxiv_ids = [p["arxiv_id"] for p in writer.client._store.get("papers", [])]
    assert sorted(arxiv_ids) == sorted(set(arxiv_ids))


def test_backfill_stats_sum():
    s = BackfillStats(results_upserted=2, papers_upserted=4, code_upserted=2)
    assert s.total() == 8
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ingest && uv run pytest tests/test_backfill.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sota_ingest.backfill'`.

- [ ] **Step 3: Write minimal implementation**
```python
# src/sota_ingest/backfill.py
"""Phase-0 backfill orchestrator + CLI.

Run:  python -m sota_ingest.backfill            (both feeds)
      python -m sota_ingest.backfill --pwc      (PWC only)
      python -m sota_ingest.backfill --awesome  (awesome-lists only)

I/O is injected (fetch_json/fetch_text, writer) so the orchestration logic is
unit-tested with everything mocked. main() wires the real httpx fetchers and
the service-role Supabase writer.
"""
import argparse
import uuid
from dataclasses import dataclass
from typing import Callable

from sota_ingest.awesome_lists import SOURCES, AwesomeSource, parse_awesome_markdown
from sota_ingest.db import SotaWriter, client_from_env
from sota_ingest.fetch import fetch_json as _fetch_json
from sota_ingest.fetch import fetch_text as _fetch_text
from sota_ingest.pwc_backfill import claims_from_pwc

# Frozen PWC archive evaluation-tables JSON (CC-BY-SA on huggingface.co/pwc-archive).
PWC_ARCHIVE_URL = (
    "https://huggingface.co/datasets/pwc-archive/evaluation-tables/resolve/main/evaluation-tables.json"
)


@dataclass
class BackfillStats:
    results_upserted: int = 0
    papers_upserted: int = 0
    code_upserted: int = 0

    def total(self) -> int:
        return self.results_upserted + self.papers_upserted + self.code_upserted


def run_pwc_backfill(
    writer: SotaWriter,
    run_id: str,
    fetch_json: Callable = _fetch_json,
    source_url: str = PWC_ARCHIVE_URL,
) -> BackfillStats:
    """Fetch frozen PWC archive -> filter robotics -> HELD claims -> upsert."""
    data = fetch_json(source_url)
    claims = claims_from_pwc(data)
    stats = BackfillStats()
    for claim in claims:
        method_id = writer.resolve_method(claim.method_slug)
        benchmark_id = writer.resolve_benchmark(claim.benchmark_slug)
        writer.upsert_result(
            claim,
            method_id=method_id,
            benchmark_id=benchmark_id,
            task_id=None,
            paper_id=None,
            code_id=None,
            run_id=run_id,
        )
        stats.results_upserted += 1
    return stats


def run_awesome_backfill(
    writer: SotaWriter,
    sources: list[AwesomeSource] = list(SOURCES),
    fetch_text: Callable = _fetch_text,
) -> BackfillStats:
    """Fetch each awesome-list README -> parse -> resolve papers + code.

    Attribution: each source is CC-BY-SA; we stamp its license on every code
    row and credit the lists in db/ATTRIBUTION.md. (No results rows here —
    these feeds give corpus/taxonomy, not benchmark numbers.)
    """
    stats = BackfillStats()
    for src in sources:
        md = fetch_text(src.raw_url)
        for rec in parse_awesome_markdown(md, source_url=src.raw_url):
            writer.resolve_paper(rec.paper)
            stats.papers_upserted += 1
            if rec.repo_url:
                writer.resolve_code(rec.repo_url, license=src.license)
                stats.code_upserted += 1
    return stats


def run_all(writer: SotaWriter, run_id: str) -> BackfillStats:
    p = run_pwc_backfill(writer, run_id)
    a = run_awesome_backfill(writer)
    return BackfillStats(
        results_upserted=p.results_upserted,
        papers_upserted=a.papers_upserted,
        code_upserted=a.code_upserted,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Phase-0 backfill from frozen sources")
    parser.add_argument("--pwc", action="store_true", help="run only the PWC archive feed")
    parser.add_argument("--awesome", action="store_true", help="run only the awesome-list feeds")
    args = parser.parse_args(argv)

    writer = SotaWriter(client_from_env())
    run_id = f"backfill-{uuid.uuid4().hex[:12]}"

    if args.pwc and not args.awesome:
        stats = run_pwc_backfill(writer, run_id)
    elif args.awesome and not args.pwc:
        stats = run_awesome_backfill(writer)
    else:
        stats = run_all(writer, run_id)

    print(
        f"[{run_id}] results={stats.results_upserted} "
        f"papers={stats.papers_upserted} code={stats.code_upserted} total={stats.total()}"
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ingest && uv run pytest tests/test_backfill.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Verify the CLI is wired (no DB call, just arg parsing + missing-env error)**

Run:
```bash
cd ingest && uv run python -m sota_ingest.backfill --help
```
Expected: argparse usage text prints listing `--pwc` and `--awesome`; exit 0. (Running without `--help` would raise `KeyError: 'SUPABASE_URL'` until env is set — that is correct; do not run it in CI.)

- [ ] **Step 6: Commit**
```bash
git add ingest/src/sota_ingest/backfill.py ingest/tests/test_backfill.py
git commit -m "feat: phase-0 backfill orchestrator + `python -m sota_ingest.backfill` CLI"
```

---

## Task 7: CC-BY-SA attribution doc

The four awesome-lists and the PWC archive are CC-BY-SA; record attribution.

**Files:**
- Create: `24_sota-robotics/db/ATTRIBUTION.md`

- [ ] **Step 1: Write the attribution file**

`db/ATTRIBUTION.md`:
```markdown
# Source Attribution (Phase-0 Backfill)

The cold-start corpus is derived from the following sources. Per their licenses,
we attribute and share-alike. Benchmark numbers from the PWC archive are imported
with `verification_status = 'held'` (never auto-published) because they are
stale/self-reported; the agent pipeline (Plan 4) re-verifies before publishing.

## Papers with Code — archive
- Source: https://huggingface.co/pwc-archive (evaluation-tables.json)
- License: CC-BY-SA-4.0
- Use: robotics-filtered evaluation tables -> `results` (HELD).

## Awesome-lists (taxonomy + paper/repo cold start)
- wadeKeith/Awesome-Embodied-AI — https://github.com/wadeKeith/Awesome-Embodied-AI — CC-BY-SA-4.0
- jonyzhang2023/awesome-embodied-vla-va-vln — https://github.com/jonyzhang2023/awesome-embodied-vla-va-vln — CC-BY-SA-4.0
- natnew/awesome-physical-ai — https://github.com/natnew/awesome-physical-ai — CC-BY-SA-4.0
- zchoi/Awesome-Embodied-Robotics-and-Agent — https://github.com/zchoi/Awesome-Embodied-Robotics-and-Agent — CC-BY-SA-4.0

Derived works (this repository's database content seeded from the above) are
likewise offered under CC-BY-SA-4.0.
```

- [ ] **Step 2: Commit**
```bash
git add db/ATTRIBUTION.md
git commit -m "docs: CC-BY-SA attribution for Phase-0 backfill sources"
```

---

## Task 8: Full suite green + one real backfill run (manual, gated on env)

**Files:** none (verification only)

- [ ] **Step 1: Run the entire test suite**

Run:
```bash
cd ingest && uv run pytest -q
```
Expected: PASS — all tests green (13 from Plan 1 + 26 new: 3 pwc + 6 awesome + 4 fetch + 8 db + 5 backfill). No network, no DB touched.

- [ ] **Step 2: (Manual, only with real creds) Dry the live backfill**

Prereq: `.env` has `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`, and Plan 1 Tasks 5–7 (schema/RLS/seed) are applied. Then:
```bash
cd ingest && set -a && . ../.env && set +a && uv run python -m sota_ingest.backfill --awesome
```
Expected: prints `[backfill-...] results=0 papers=N code=M total=...` with N>0; re-running prints the same N (idempotent — `arxiv_id`/`repo_url` unique constraints suppress dupes).

- [ ] **Step 3: (Manual) Run the PWC feed, then re-run to prove idempotency**

```bash
cd ingest && set -a && . ../.env && set +a && uv run python -m sota_ingest.backfill --pwc
cd ingest && set -a && . ../.env && set +a && uv run python -m sota_ingest.backfill --pwc
```
Expected: both runs report the same `results=K`; a `select count(*) from results` (via Supabase MCP `execute_sql`) is unchanged between runs, confirming the `UNIQUE(method_id,benchmark_id,eval_conditions_hash)` upsert is idempotent. Spot-check via MCP: `select verification_status, count(*) from results group by 1;` shows every backfilled row is `held`.

- [ ] **Step 4: Commit any lockfile drift (if `uv` updated `uv.lock`)**
```bash
git add ingest/uv.lock
git commit -m "build: lockfile after phase-0 backfill verification" || echo "nothing to commit"
```

---

## Self-Review

**Spec coverage (every clause of the Plan 2 scope):**
- (a) Supabase writer module `ingest/src/sota_ingest/db.py` — Task 5. Resolves/creates `method`/`benchmark`/`paper`/`code` by slug/natural-key (`resolve_method`, `resolve_benchmark`, `resolve_paper`, `resolve_code`) and upserts `results` via `build_result_row` + `CONFLICT_TARGET` (`CONFLICT_ON = ",".join(CONFLICT_TARGET)`). Service-role client from `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` (`client_from_env`). ✓
- (b) PWC-archive backfill — Tasks 2 (`pwc_backfill.py`: `filter_robotics_tasks` → `claims_from_pwc`) + 6 (`run_pwc_backfill` downloads JSON from `huggingface.co/...pwc-archive...`, filters robotics, runs `parse_evaluation_tables` via `claims_from_pwc`, upserts). Numbers stay HELD (Plan 1 sets HELD; verified by `test_run_pwc_backfill_upserts_filtered_claims`). ✓
- (c) Awesome-list scrapers — Task 3 (`awesome_lists.py`: 4 sources in `SOURCES` registry — wadeKeith, jonyzhang2023, natnew, zchoi; `parse_awesome_markdown` extracts paper + repo links; `map_section_to_domain` maps headers to the 8 domain slugs). ✓
- (d) CLI `python -m sota_ingest.backfill` — Task 6 (`backfill.py` `main()` with `--pwc`/`--awesome`; `if __name__ == "__main__": main()`). ✓
- TDD on PURE logic against fixtures (markdown link/section parsing, taxonomy mapping, upsert-payload building) — Tasks 2, 3 are fully pure + fixture-tested; the upsert-payload key (`build_result_row`) is Plan 1's, re-asserted in `test_db.py`. ✓
- Network fetch + DB writes as thin I/O wrappers tested with mocks/recorded fixtures — `fetch.py` tested with `httpx.MockTransport` (Task 4); `db.py` + `backfill.py` tested with `FakeSupabase` and injected fetch callables (Tasks 5, 6). No live network/DB in the suite. ✓
- All DB writes idempotent + via service role — reference resolvers select-before-insert; results upsert on the UNIQUE constraint; `test_upsert_result_is_idempotent_across_runs` + `test_run_pwc_backfill_is_idempotent` prove it; client built from the service-role key only. ✓
- CC-BY-SA respected — `SOURCES[*].license == "CC-BY-SA-4.0"`, license stamped onto `code` rows in `run_awesome_backfill`, and `db/ATTRIBUTION.md` (Task 7). ✓
- httpx + supabase added via uv — Task 0 (`uv add httpx "supabase>=2.15.0"`). ✓

**Placeholder / TODO check:** No `TODO`, no "similar to above", no stubbed bodies. Every TDD step shows complete, runnable test and implementation code. The two manual steps in Task 8 are explicitly gated on real creds and labeled "do not run in CI"; they are verification, not unimplemented code.

**Type consistency with Plan 1 contracts:**
- `ResultClaim`, `PaperRec`, `Realm`, `Origin`, `VerificationStatus` imported from `sota_ingest.models`, never redefined. `claims_from_pwc` returns `list[ResultClaim]`; `parse_awesome_markdown` returns `list[AwesomeRecord]` whose `.paper` is a `PaperRec`. ✓
- `canonical_hash` used only transitively via `build_result_row` (Plan 1) — not reimplemented. ✓
- `parse_evaluation_tables(list[dict]) -> list[ResultClaim]` called with its exact signature; all imported rows are HELD (its behavior). ✓
- `build_result_row(claim, method_id, benchmark_id, task_id, paper_id, code_id, run_id) -> dict` called positionally/by-keyword with the exact parameter names; `upsert_result` forwards them unchanged. ✓
- `CONFLICT_TARGET = ("method_id","benchmark_id","eval_conditions_hash")` imported and joined into the PostgREST `on_conflict` string; `test_conflict_on_matches_plan1_target` pins the equality. ✓
- DB columns written (`methods.slug/name/org`, `benchmarks.slug/name/domain_id`, `papers.arxiv_id/title/authors/abstract/published_date/url`, `code.repo_url/license`, all `results.*`) match migration `0002_core_tables.sql`. ✓

**Boundary integrity:** Only `fetch.py` and `db.py` perform I/O; both are injected into `backfill.py`, so the orchestrator and all pure parsers are tested with zero external dependencies. Test suite is hermetic and fast (retries use `backoff=0.0` in tests).

**One honest caveat (radical candor):** `claims_from_pwc` emits `benchmark_slug` by slugifying the PWC dataset name (e.g. `"Habitat ObjectNav"` → `habitat-objectnav`), which will NOT match the seed slug `habitat`. This plan deliberately does **not** remap aliases — `resolve_benchmark` will create a new `habitat-objectnav` benchmark row. That is acceptable for cold start (no data lost, all HELD), but it means the seed taxonomy and the PWC import can diverge on naming until Plan 4's skeptic merges aliases. If you want alias collapse earlier, add a slug-alias table in Plan 3; do not bolt it onto this plan's pure parser.
