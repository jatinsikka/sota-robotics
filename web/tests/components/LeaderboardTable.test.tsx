import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { LeaderboardTable } from "@/components/LeaderboardTable";
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

describe("LeaderboardTable", () => {
  it("ranks rows by metric value and renders percent for success_rate", () => {
    render(
      <LeaderboardTable
        metric="success_rate"
        rows={[
          row({ id: 1, method_name: "Lower", metric_value: 0.6 }),
          row({ id: 2, method_name: "Higher", metric_value: 0.9 }),
        ]}
      />,
    );
    const bodyRows = screen.getAllByRole("row").slice(1); // drop header
    expect(within(bodyRows[0]).getByText("Higher")).toBeInTheDocument();
    expect(within(bodyRows[0]).getByText("90.0%")).toBeInTheDocument();
    expect(within(bodyRows[1]).getByText("Lower")).toBeInTheDocument();
  });

  it("renders Elo values (no percent) for an Elo benchmark", () => {
    render(
      <LeaderboardTable
        metric="elo"
        rows={[row({ id: 1, metric: "elo", metric_value: 1432.7, method_name: "Pi0" })]}
      />,
    );
    expect(screen.getByText("1433")).toBeInTheDocument();
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });

  it("always shows realm, origin, and eval conditions for each row", () => {
    render(
      <LeaderboardTable
        metric="success_rate"
        rows={[
          row({
            id: 1,
            realm: "real",
            origin: "vendor_internal",
            eval_conditions: { camera: "wrist", episodes: 50 },
          }),
        ]}
      />,
    );
    expect(screen.getByText("Real")).toHaveAttribute("data-realm", "real");
    expect(screen.getByText("Vendor · internal")).toHaveAttribute(
      "data-origin",
      "vendor_internal",
    );
    expect(screen.getByText("camera: wrist")).toBeInTheDocument();
    expect(screen.getByText("episodes: 50")).toBeInTheDocument();
  });

  it("links each row to its source_url", () => {
    render(
      <LeaderboardTable
        metric="success_rate"
        rows={[row({ id: 1, source_url: "https://arxiv.org/abs/1234" })]}
      />,
    );
    expect(screen.getByRole("link", { name: /source/i })).toHaveAttribute(
      "href",
      "https://arxiv.org/abs/1234",
    );
  });
});
