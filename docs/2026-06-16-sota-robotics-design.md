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

---

## 11. Grounded Research Findings (2026-06-16)

Source: a 20-agent research workflow (7/8 domains researched + adversarially
verified at `overall_confidence: high`; data-sources, prior-art, tech-stack
agents complete). Two agents (sim2real-rl scout, auto-synthesis, critic) hit a
session API limit and did not run — synthesis done by hand from the rest. Full
raw output archived in the task transcript. **These findings change the design;
the changes are flagged below.**

### 11.1 Competitive reality — the wedge narrowed

The space is more crowded and better-resourced than the spec assumed:

- **AllenAI `vla-evaluation-harness` (vla-eval)** — the serious competitor. It
  *executes* VLA models (1,885 models × 18 sim benchmarks, ~657 published
  results), public leaderboard, AI-maintained, monthly cadence, ICRA-2026
  published, open-source + Docker repro. **It owns the "execution-verified
  manipulation SOTA" position** — which was our obvious differentiator.
  **Decision: do NOT compete here.** Ingest/cite their results as our
  manipulation-sim feed; spend our effort on what they ignore.
- **CodeSOTA** — live, weekly, has a dedicated robotics page + `/api/sota`, has
  ingested the PWC archive. But robotics is one tab of an all-AI registry;
  depth is thin and partly *qualitative* ("~70%", "80%+"). Study its API +
  signed-hash verification pattern; don't depend on a rival's live API.
- **HF Trending Papers / Emergent Mind / alphaXiv** — discovery/social feeds,
  zero SOTA leaderboards, zero robotics specialization. The biggest void PWC
  left (per-task quantitative SOTA) is still unfilled by these.
- **awesome-robotics lists** — breadth, taxonomy, links; no metrics, no
  freshness. Good cold-start seed only.

**Sharpened wedge (replaces §9's "execution + synthesis"):** a *robotics-native,
full-embodiment* SOTA tracker — manipulation + dexterous + **humanoid
whole-body + legged locomotion + real-robot deployment + navigation/VLN** —
unifying **sim AND real** results in one taxonomy, plus a **weekly trend-synthesis
layer** ("what's SOTA on X right now, what changed this month, why"). AllenAI is
manipulation-sim-only; no one covers the other embodiments or does synthesis.
**Uncomfortable truth:** out-executing AI2 on manipulation numbers is a losing
game. Our moat is breadth + real-robot + synthesis + UX, not execution.

### 11.2 Data reality — leaderboards are saturated, gamed, and PDF-only

- **LIBERO is saturated** (SOTA >97–98%); high scores reflect memorization, not
  generalization. `LIBERO-Plus` / `LIBERO-PRO` exist specifically to expose
  this. **Implication:** a naive "highest number wins" leaderboard is useless
  and misleading. We must surface *discriminating* benchmarks (RoboCasa ~50–57%,
  SimplerEnv), robustness/generalization, and `eval_conditions`.
- **RoboArena** — distributed, double-blind, cross-lab *real-world* Elo ranking
  (>8,500 human judgments), built to defeat gamed sim leaderboards. Runs through
  Dec 2026. This is the credible real-world signal and a flagship data source.
- **Vendor-internal benchmarks** (pi-0.5, Gemini Robotics, GR00T) report on
  proprietary, non-reproducible evals. The tracker MUST tag results as
  `public-reproducible` vs `vendor-claimed-internal`.
- **No machine-readable cross-benchmark feed exists** since PWC died. Results are
  fragmented, self-reported, often PDF-only. **This validates the agent
  thesis:** LLM extraction from PDFs is not optional — there is no clean API to
  scrape. Budget PDF table-extraction as a first-class pipeline.

### 11.3 Reuse strategy — seed, don't fork

- **PWC archive** (`huggingface.co/pwc-archive`, frozen Sep 2025, CC-BY-SA 4.0):
  pull as one-time cold-start corpus for paper/method/dataset index + the
  paper↔code linkage table; **adopt its `sota-extractor` JSON schema + loaders
  as our ingestion format.** Treat its robotics numbers as stale placeholders,
  NOT ground truth (predates the 2025–26 VLA wave). *CC-BY-SA share-alike means
  a derived public dataset must stay open — fine now, a constraint if we ever
  want a closed proprietary dataset.*
- **4 awesome-lists** (Awesome-Embodied-AI, awesome-embodied-vla-va-vln,
  awesome-physical-ai, Awesome-Embodied-Robotics-and-Agent): scrape for the
  embodiment taxonomy + initial paper/model/repo corpus.
- **AllenAI vla-eval**: ingest/cite as the manipulation-sim results feed.
- **CodeSOTA**: study as design reference only.

### 11.4 Data sources — ingest priority (validated)

- **Phase 0 (one-time backfill):** PWC archive → Open-X-Embodiment metadata.
- **Phase 1 (live spine, poll daily):** arXiv API (cs.RO + cross-lists; the
  primary `arxiv_id` key generator + discovery firehose) → HF Hub API
  (models/datasets; downloads/likes = cleanest adoption signal) → GitHub GraphQL
  API (star-velocity/releases on a curated watchlist).
- **Phase 2 (enrichment):** HF Daily Papers (upvote re-ranking) → Semantic
  Scholar (citation signal; free key, 500/batch).
- **Phase 3 (ground-truth numbers, highest value/effort):** per-benchmark
  scrapers + LLM PDF table-extraction — BOP first (real online eval server/API),
  then LIBERO/-PRO, ManiSkill3, HumanoidBench, Habitat, RoboArena.
- **Deprioritize:** OpenAlex live API (metered since Feb 2026; use bulk snapshot
  if needed).

### 11.5 Stack — concrete decisions (validated)

- **DB:** Supabase Postgres, *normalized relational graph* (not triple-store /
  JSONB blob). Tables: `domains, tasks, benchmarks, methods, papers, code`, and
  the load-bearing `results` join. `results` columns: FKs +
  `metric` text, `metric_value` **numeric** (so leaderboards sort in SQL),
  `eval_conditions` **JSONB + GIN** (split/protocol/sim_vs_real/hardware —
  per-benchmark variance), `source_url`, `result_date`, `confidence` numeric,
  `verification_status` enum(`pending|published|held|refuted`), `skeptic_notes`,
  `ingested_run_id`. Partial index `WHERE verification_status='published'`.
  **RLS on every table** (off by default — #1 security footgun; run
  `get_advisors` after migrations); service-role key for the Python writer,
  publishable key with read-only-published policy for Next.js. UNIQUE on
  `(method_id, benchmark_id, hash(eval_conditions))` for idempotent re-runs.
- **Ingest runtime:** **GitHub Actions scheduled cron** (`0 6 * * *` daily), NOT
  Vercel (Hobby 60s / Pro 300s function caps would blow up a multi-paper Claude
  run; Actions = 6h timeout, native Python, free minutes, secrets). Connect via
  pooled string (port 6543). Vercel (Hobby) hosts the Next.js site only.
- **Agent pipeline:** two Claude calls/paper — extractor → skeptic, both
  **Opus 4.8** in v1 while founder calibrates prompts; later cost lever = drop
  EXTRACTOR to Sonnet 4.6, keep SKEPTIC on Opus (skeptic is the trust gate).
  Use `output_config.format` (JSON schema) — NOT assistant prefill (400s on
  4.8); `thinking:{type:'adaptive'}`; `json.loads` parsing; check
  `stop_reason=='refusal'`. DB is queried by code, not Claude — "Best for task
  X" = parameterized SELECT over published rows, fed to Claude only for the
  final synthesis prose.
- **Cost:** Message Batches API (flat 50% off; ingest is latency-insensitive) +
  prompt-cache the large stable prefix (system + schema + few-shot + taxonomy).
  Don't bank on per-paper PDF caching across the extractor→skeptic boundary
  inside batch (5-min TTL won't survive batch queue latency). Est. **~$35–65/mo**
  at v1 scale (150–300 candidate papers/mo), dominated by Claude inference;
  Supabase free + Vercel Hobby = $0.

### 11.6 Spec deltas (what changed vs §1–10)

1. **§9 moat rewritten** → breadth + real-robot + synthesis, NOT
   execution-verified manipulation (AllenAI owns that).
2. **New design requirement:** every result tagged `public-reproducible` vs
   `vendor-internal`, and `sim` vs `real`. Leaderboards must not rank by raw
   number alone (saturation/gaming) — surface eval_conditions + robustness +
   RoboArena Elo for real-world.
3. **New v1 work:** Phase-0 backfill (PWC archive + awesome-lists) as cold start;
   ingest AllenAI vla-eval as the manipulation feed.
4. **Confirmed:** automated ingest + write-time skeptic gate is the right call —
   the data being PDF-only/self-reported makes LLM extraction mandatory.

### 11.7 Remaining gaps (honest)

- **Domain #5 (sim-to-real & RL)** scout didn't run (session limit). Heavily
  overlaps locomotion + manipulation findings, but needs its own pass before
  populating that domain.
- Auto-synthesis + completeness-critic agents didn't run; this section is a
  hand synthesis. A critic pass (riskiest assumptions, missing research) is
  still owed before coding — re-run after the API limit resets (9:20pm).
- License path decision (CC-BY-SA share-alike) if a closed dataset is ever
  wanted.
