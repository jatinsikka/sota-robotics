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
