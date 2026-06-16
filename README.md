# sota-robotics

> A live, trustworthy map of the state of the art in robotics — *whatever you're
> working on, you should know this.*

Finding the SOTA in robotics is scattered and painful. The closest thing —
[Papers with Code](https://paperswithcode.com) — was sunset in July 2025, and
nothing has replaced its leaderboards, least of all for robotics. This project
fills that gap for the **canonical robotics subfields every roboticist must
know**.

## What it does

One structured backbone, three views:

- **Leaderboards** — benchmark results per task, with the *eval conditions* most
  trackers omit (split, protocol, sim-vs-real, hardware).
- **"Best method for task X"** — synthesis over the backbone: leading approaches,
  evidence, and caveats. The thing Papers with Code never had.
- **Field map** *(phase 2)* — a visual map of how subfields, methods, and results
  connect.

## Domain canon (v1)

1. Humanoid VLA & manipulation (incl. dexterous)
2. Locomotion & whole-body control (legged / bipedal)
3. World models
4. World-action models (WAM)
5. Sim-to-real & RL for control
6. Robot perception (3D vision, grasping, pose)
7. Learning from demonstration & robot data (teleop, Open-X-style)
8. Navigation / VLN

Broad in coverage, narrow in depth bar: only canonical, well-benchmarked
subfields with verifiable results get in.

## How it stays trustworthy

Automated ingest with a **write-time verification gate** — an extractor agent
parses new papers/repos into structured results, then a *skeptic* agent tries to
refute each one (wrong eval conditions? cherry-picked split? unverifiable?).
Only results that survive get published, with a confidence score. Periodic
audits guard against gaming and drift.

## Status

Design spec approved (`docs/2026-06-16-sota-robotics-design.md`). Implementation
plan and scaffolding next. Brand name is a working slug, pending an originality
check.

## Stack

Next.js on Vercel · Supabase Postgres · Python ingest pipeline · Claude as
extractor + skeptic.
