import { describe, it, expect } from "vitest";
import { isEloMetric, formatMetricValue } from "@/lib/format";

describe("isEloMetric", () => {
  it("treats 'elo' as an Elo metric (case-insensitive)", () => {
    expect(isEloMetric("elo")).toBe(true);
    expect(isEloMetric("Elo")).toBe(true);
    expect(isEloMetric("ELO")).toBe(true);
  });

  it("treats 'roboarena_elo' as an Elo metric", () => {
    expect(isEloMetric("roboarena_elo")).toBe(true);
  });

  it("does not treat success_rate as Elo", () => {
    expect(isEloMetric("success_rate")).toBe(false);
  });
});

describe("formatMetricValue", () => {
  it("renders a fraction success_rate as a percentage", () => {
    expect(formatMetricValue("success_rate", 0.981)).toBe("98.1%");
  });

  it("renders a percent-scale success_rate without double-scaling", () => {
    expect(formatMetricValue("success_rate", 98.1)).toBe("98.1%");
  });

  it("renders Elo as a rounded integer with no percent sign", () => {
    expect(formatMetricValue("elo", 1432.7)).toBe("1433");
  });

  it("renders null as an em dash", () => {
    expect(formatMetricValue("success_rate", null)).toBe("—");
  });
});

import { rankResults } from "@/lib/format";
import type { ResultRow } from "@/lib/types";

function row(partial: Partial<ResultRow>): ResultRow {
  return {
    id: 1,
    method_id: 1,
    benchmark_id: 1,
    task_id: null,
    paper_id: null,
    code_id: null,
    metric: "success_rate",
    metric_value: 0.5,
    eval_conditions: {},
    eval_conditions_hash: "hash",
    realm: "sim",
    origin: "public_reproducible",
    source_url: "https://example.com",
    result_date: null,
    confidence: null,
    verification_status: "published",
    skeptic_notes: null,
    method_slug: "m",
    method_name: "M",
    ...partial,
  };
}

describe("rankResults", () => {
  it("sorts by metric_value descending", () => {
    const ranked = rankResults([
      row({ id: 1, metric_value: 0.7 }),
      row({ id: 2, metric_value: 0.9 }),
      row({ id: 3, metric_value: 0.8 }),
    ]);
    expect(ranked.map((r) => r.id)).toEqual([2, 3, 1]);
  });

  it("places null metric_value rows last", () => {
    const ranked = rankResults([
      row({ id: 1, metric_value: null }),
      row({ id: 2, metric_value: 0.4 }),
    ]);
    expect(ranked.map((r) => r.id)).toEqual([2, 1]);
  });

  it("keeps two rows for the same method when eval_conditions_hash differs", () => {
    const ranked = rankResults([
      row({ id: 1, method_id: 7, metric_value: 0.9, eval_conditions_hash: "a" }),
      row({ id: 2, method_id: 7, metric_value: 0.6, eval_conditions_hash: "b" }),
    ]);
    expect(ranked).toHaveLength(2);
    expect(ranked.map((r) => r.eval_conditions_hash)).toEqual(["a", "b"]);
  });

  it("does not mutate the input array", () => {
    const input = [row({ id: 1, metric_value: 0.1 }), row({ id: 2, metric_value: 0.9 })];
    rankResults(input);
    expect(input.map((r) => r.id)).toEqual([1, 2]);
  });
});

import { realmLabel, originLabel, formatResultDate } from "@/lib/format";

describe("realmLabel", () => {
  it("maps sim and real to display labels", () => {
    expect(realmLabel("sim")).toBe("Sim");
    expect(realmLabel("real")).toBe("Real");
  });
});

describe("originLabel", () => {
  it("maps origin enums to display labels", () => {
    expect(originLabel("public_reproducible")).toBe("Public · reproducible");
    expect(originLabel("vendor_internal")).toBe("Vendor · internal");
  });
});

describe("formatResultDate", () => {
  it("returns the date string unchanged when present", () => {
    expect(formatResultDate("2026-05-01")).toBe("2026-05-01");
  });

  it("returns em dash for null", () => {
    expect(formatResultDate(null)).toBe("—");
  });
});
