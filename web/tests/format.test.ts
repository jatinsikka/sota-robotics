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
