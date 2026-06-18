// Pure presentation helpers. No I/O, no React. Unit-tested in tests/format.test.ts.

const ELO_METRICS = new Set(["elo", "roboarena_elo"]);

/** True when a benchmark is scored by Elo (e.g. RoboArena) rather than success-rate. */
export function isEloMetric(metric: string): boolean {
  return ELO_METRICS.has(metric.toLowerCase());
}

/**
 * Human-readable metric value.
 * - Elo metrics: rounded integer, no unit.
 * - Otherwise: percentage. Values in [0,1] are treated as fractions and scaled
 *   to percent; values > 1 are assumed already on a 0-100 percent scale.
 * - null -> em dash.
 */
export function formatMetricValue(metric: string, value: number | null): string {
  if (value === null) return "—";
  if (isEloMetric(metric)) return String(Math.round(value));
  const pct = value <= 1 ? value * 100 : value;
  return `${pct.toFixed(1)}%`;
}

import type { ResultRow } from "@/lib/types";

/**
 * Returns rows in display order: descending by metric_value, nulls last.
 * Crucially this does NOT dedupe by method — rows that share a method but differ
 * in eval_conditions_hash are both kept, so the table can surface conditions per
 * row rather than crowning one "winner". Pure: never mutates the input.
 */
export function rankResults(rows: ResultRow[]): ResultRow[] {
  return [...rows].sort((a, b) => {
    if (a.metric_value === null && b.metric_value === null) return 0;
    if (a.metric_value === null) return 1;
    if (b.metric_value === null) return -1;
    return b.metric_value - a.metric_value;
  });
}

import type { Realm, Origin } from "@/lib/types";

export function realmLabel(realm: Realm): string {
  return realm === "sim" ? "Sim" : "Real";
}

export function originLabel(origin: Origin): string {
  return origin === "public_reproducible"
    ? "Public · reproducible"
    : "Vendor · internal";
}

export function formatResultDate(date: string | null): string {
  return date ?? "—";
}

export interface SynthesisPrompt {
  system: string;
  user: string;
}

/**
 * Builds the Claude prompt for "best for task X" synthesis. Pure and tested.
 * The system prompt encodes the spec-locked rule: never crown a bare winner by
 * raw metric_value — weigh eval_conditions, realm (sim vs real), origin
 * (public_reproducible vs vendor_internal), and saturation.
 */
export function buildSynthesisPrompt(taskName: string, rows: ResultRow[]): SynthesisPrompt {
  const system = [
    "You are a skeptical robotics-evaluation analyst.",
    "You are given published, verified benchmark results for one task.",
    "Write ONE short paragraph (3-5 sentences) recommending what currently works best for this task.",
    "NEVER recommend a method on raw metric_value alone. You MUST weigh eval_conditions, realm (sim results are far weaker evidence than real), and origin (vendor_internal numbers are self-reported and less trustworthy than public_reproducible).",
    "Cite each method you mention by its exact name. Flag when the top number is sim-only or vendor-internal. If the evidence is thin or conflicting, say so plainly. Do not invent numbers beyond those provided.",
  ].join(" ");

  if (rows.length === 0) {
    return {
      system,
      user: `Task: ${taskName}\n\nNo published results are available for this task. Say that no recommendation can be made yet.`,
    };
  }

  const lines = rows.map(
    (r) =>
      `- ${r.method_name}: ${r.metric}=${r.metric_value ?? "n/a"} | realm=${r.realm} | origin=${r.origin} | conditions=${JSON.stringify(r.eval_conditions)} | source=${r.source_url}`,
  );

  const user = [
    `Task: ${taskName}`,
    "",
    "Published results:",
    ...lines,
  ].join("\n");

  return { system, user };
}
