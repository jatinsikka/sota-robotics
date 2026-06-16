# Robotics SOTA Tracker — Design Spec

**Date:** 2026-06-16
**Status:** Design approved, pending spec review
**Codename:** `sota-robotics` (brand name TBD — originality check pending)
**Venture:** #24

---

## 1. Problem & Why Now

Finding the state of the art in robotics is painful and scattered. There is no
single trustworthy place to answer *"what's the leading method for task X right
now, and what's the evidence?"* The closest thing — **Papers with Code** — was
sunset by Meta in July 2025 and redirected to Hugging Face Trending Papers,
which deliberately does **not** do SOTA leaderboards. The replacements that
appeared (CodeSOTA, Papers With Code 2, OpenCodePapers, PapersWithCodePlus) have
not recaptured the leaderboard function, and none focus on robotics.

Robotics specifically is underserved: SOTA lives in scattered benchmark repos
(LIBERO, ManiSkill, HumanoidBench, Open-X-Embodiment), rotting "awesome-X"
GitHub lists, and individual paper PDFs. CodeSOTA shipped a thin VLA leaderboard
(RT-2/OpenVLA/Pi0/Octo) — proof of demand, but shallow and not defensible.

**Why now / why us:** the hard part of a SOTA tracker is not scraping — it's
*curation and judgment* (which number, under which eval conditions, not gamed).
That judgment is now automatable with agent pipelines. The founder already owns
that machinery (a `deep-research` skill, Workflow orchestration, and the
quant-terminal ingest/verify pattern), and is a robotics PhD who can act as
editor-in-chief / auditor. The moat is the **gated extraction + synthesis
layer**, not the scraper.

## 2. Editorial Principle (the scope guard)

> Track the load-bearing canon every roboticist must know — and refuse the long
> tail of niche subfields.

Broad in *coverage* (all core robotics subfields), narrow in *depth bar* (only
canonical, well-benchmarked subfields with verifiable results get in). This is
the YAGNI guard that prevents recreating PWC's unbounded maintenance burden.

## 3. v1 Domain Canon (8 subfields)

1. Humanoid VLA & manipulation (incl. dexterous)
2. Locomotion & whole-body control (legged / bipedal)
3. World models
4. World-action models (WAM)
5. Sim-to-real & RL for control
6. Robot perception (3D vision, grasping, pose estimation)
7. Learning from demonstration & robot data (teleop, Open-X-style datasets)
8. Navigation / VLN

Explicitly out of scope for v1: RAG / general LLM infra, pure CV, pure NLP,
anything without an accepted robotics benchmark.

## 4. Architecture — One Backbone, Gated Ingest, Three Views

```
SOURCES                  INGEST PIPELINE (scheduled)          STORE            VIEWS (Next.js / Vercel)
arXiv (cs.RO, VLA)   ->   1. fetch new papers/results     ->  Postgres      ->  - Leaderboards (tables)      [v1]
GitHub (code/stars)       2. extract: task->method->          (Supabase):       - "Best for task X"          [v1]
benchmark repos              result->eval-conditions           tasks,             (LLM synthesis over graph)
(LIBERO, ManiSkill,       3. SKEPTIC agent refutes ->          methods,          - Field map (graph view)    [phase 2]
 HumanoidBench, Open-X)      publish only if survives          results,
 paper PDFs               4. periodic audit (anti-gaming)      papers, code
```

**Core idea:** the three "products" are three *renderers* over one structured
graph. Build the backbone once; views are additive and need no rework.

- **Leaderboards** = table view of `results` grouped by `benchmark`.
- **"Best for task X"** = LLM synthesis query over the same graph, returning
  leading methods + evidence + caveats. This is the differentiator PWC lacked.
- **Field map** = graph visualization of `task -> method -> result` (phase 2;
  most viz effort, least urgent).

## 5. Data Model (backbone)

Relational graph in Postgres (Supabase). Minimum entities:

- `domains` — the 8 canon subfields.
- `tasks` — e.g. "dexterous in-hand reorientation", "bipedal locomotion".
- `benchmarks` — LIBERO, ManiSkill, HumanoidBench, Open-X, etc. (name, splits,
  metric, eval protocol).
- `methods` / `models` — RT-2, OpenVLA, Pi0, Octo, etc. (params, org, date).
- `results` — the join: (method, benchmark, metric value, eval_conditions,
  source paper, code link, date, **confidence**, **verification status**).
- `papers` — arXiv id, title, authors, date, abstract, links.
- `code` — repo URL, stars, last-commit, license.

`results` is the load-bearing table; `eval_conditions` (split, protocol,
sim-vs-real, hardware) is what competitors omit and what makes the data
trustworthy.

## 6. Curation Engine (the make-or-break)

**Mode:** automated ingest with a **write-time verification gate**, plus periodic
audits. Decided against fully-automated-publish (wrong/gamed numbers go live
before any check) and against per-item human approval (doesn't scale solo).

Pipeline stages (each a scheduled agent step):

1. **Fetch** — new arXiv (cs.RO + VLA/world-model tags), watched benchmark
   repos, GitHub releases.
2. **Extract** — agent parses paper/repo into structured `result` claims with
   explicit `eval_conditions`.
3. **Skeptic gate** — a second agent tries to *refute* each claim: wrong eval
   conditions? cherry-picked split? unverifiable / no reproducible source?
   Survives -> publish with confidence score. Fails -> hold for audit queue.
4. **Periodic audit** — scheduled sweep for gaming, stale results, and drift;
   founder reviews flagged items as editor-in-chief.

Reuses the adversarial-verify pattern from the quant backtest harness.

## 7. Stack

- **Frontend:** Next.js + godmodeUI on Vercel.
- **Store:** Supabase Postgres.
- **Ingest:** Python pipeline reusing quant-terminal patterns; Claude as
  extractor + skeptic; scheduled via cron.
- **Hosting/CI:** Vercel (web), scheduled job runner for ingest.

## 8. v1 Scope (what ships first) vs Later

**v1:** backbone (data model + ingest + skeptic gate) + **Leaderboards** view +
**"Best for task X"** synthesis. Populate data for 2-3 domains the founder can
personally audit first (humanoid VLA/manip, world models), schema covering all 8.

**Phase 2:** Field map view; broaden auto-population to all 8 domains;
community-submitted results layer on top of agent curation.

**Out of scope (now):** user accounts, paid tiers, API product, RAG/non-robotics.

## 9. Moat & Risks

**Moat:** gated extraction + synthesis layer, powered by agent machinery already
owned. Not the scraper.

**Risks:**
- *Trust/gaming* — mitigated by write-time skeptic gate + audits + visible
  `eval_conditions` and confidence.
- *Maintenance burnout* — mitigated by automation + editorial principle bounding
  scope.
- *First mover (CodeSOTA)* — beaten on depth (eval conditions, synthesis) and
  robotics focus, not on having-a-table.
- *Audience* — robotics PhD network + Sequent Robotics adjacency for distribution.

## 10. Open Items

- Brand name (originality check pending — separate step before any public artifact).
- Confirm "Navigation / VLN" is the intended 8th domain (was inferred from
  "Veevon").
- Exact source list + scrape cadence for ingest v1.
