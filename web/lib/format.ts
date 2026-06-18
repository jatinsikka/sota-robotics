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
