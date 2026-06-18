import { describe, it, expect } from "vitest";
import {
  listDomainsWithBenchmarks,
  listBenchmarksByDomain,
  fetchBenchmarkWithResults,
  fetchMethodResults,
} from "@/lib/queries";
import type { Sql } from "postgres";

// Fake porsager/postgres `sql` tagged-template client. Each call inspects the
// SQL text to pick which table's queued rows to resolve. It records every
// query (joined SQL text + interpolated params) so tests can assert on the
// published filter and the interpolated ids.
type Resp = unknown[];

function makeSql(responses: Record<string, Resp>) {
  const queries: { sql: string; params: unknown[] }[] = [];

  function pick(text: string): Resp {
    // order matters: results before the singular reference tables it joins
    if (/from\s+results/i.test(text)) return responses.results ?? [];
    if (/from\s+benchmarks/i.test(text)) return responses.benchmarks ?? [];
    if (/from\s+domains/i.test(text)) return responses.domains ?? [];
    if (/from\s+tasks/i.test(text)) return responses.tasks ?? [];
    if (/from\s+methods/i.test(text)) return responses.methods ?? [];
    return [];
  }

  const sql = ((strings: TemplateStringsArray, ...params: unknown[]) => {
    const text = strings.join(" ");
    queries.push({ sql: text, params });
    return Promise.resolve(pick(text));
  }) as unknown as Sql;

  return { sql, queries };
}

describe("listBenchmarksByDomain", () => {
  it("queries benchmarks filtered by domain_id and returns rows", async () => {
    const { sql, queries } = makeSql({
      benchmarks: [
        { id: 1, domain_id: 2, slug: "libero", name: "LIBERO", metric: "success_rate", is_saturated: true },
      ],
    });
    const rows = await listBenchmarksByDomain(sql, 2);
    expect(rows).toHaveLength(1);
    expect(rows[0].slug).toBe("libero");
    // domain_id was interpolated as a query parameter
    const q = queries.find((x) => /from\s+benchmarks/i.test(x.sql));
    expect(q?.params).toContain(2);
  });
});

describe("listDomainsWithBenchmarks", () => {
  it("returns each domain with its benchmarks nested", async () => {
    const { sql } = makeSql({
      domains: [{ id: 2, slug: "manip", name: "Manipulation" }],
      benchmarks: [
        { id: 1, domain_id: 2, slug: "libero", name: "LIBERO", metric: "success_rate", is_saturated: true },
      ],
    });
    const domains = await listDomainsWithBenchmarks(sql);
    expect(domains).toHaveLength(1);
    expect(domains[0].name).toBe("Manipulation");
    expect(domains[0].benchmarks[0].slug).toBe("libero");
  });
});

describe("fetchBenchmarkWithResults", () => {
  it("returns null when the benchmark slug does not exist", async () => {
    const { sql } = makeSql({ benchmarks: [] });
    const out = await fetchBenchmarkWithResults(sql, "ghost");
    expect(out).toBeNull();
  });

  it("returns the benchmark plus result rows and filters to published", async () => {
    const { sql, queries } = makeSql({
      benchmarks: [
        { id: 1, domain_id: 2, slug: "libero", name: "LIBERO", metric: "success_rate", is_saturated: true },
      ],
      results: [
        {
          id: 9,
          method_id: 5,
          benchmark_id: 1,
          task_id: null,
          paper_id: null,
          code_id: null,
          metric: "success_rate",
          metric_value: 0.98,
          eval_conditions: { episodes: 50 },
          eval_conditions_hash: "h",
          realm: "sim",
          origin: "public_reproducible",
          source_url: "https://x",
          result_date: "2026-01-01",
          confidence: null,
          verification_status: "published",
          skeptic_notes: null,
          method_slug: "openvla",
          method_name: "OpenVLA",
        },
      ],
    });
    const out = await fetchBenchmarkWithResults(sql, "libero");
    expect(out).not.toBeNull();
    expect(out!.benchmark.is_saturated).toBe(true);
    expect(out!.rows[0].method_name).toBe("OpenVLA");
    expect(out!.rows[0].method_slug).toBe("openvla");
    // SECURITY: the results query MUST hardcode the published filter.
    const resultsQuery = queries.find((q) => /from\s+results/i.test(q.sql));
    expect(resultsQuery?.sql).toMatch(/verification_status\s*=\s*'published'/i);
  });

  it("rejects when the results query errors", async () => {
    // postgres rejects the query promise on failure; the error must propagate.
    const sql = ((strings: TemplateStringsArray) => {
      const text = strings.join(" ");
      if (/from\s+results/i.test(text)) return Promise.reject(new Error("boom"));
      return Promise.resolve([
        { id: 1, domain_id: 2, slug: "libero", name: "LIBERO", metric: "success_rate", is_saturated: true },
      ]);
    }) as unknown as Sql;
    await expect(fetchBenchmarkWithResults(sql, "libero")).rejects.toThrow("boom");
  });
});

describe("fetchMethodResults", () => {
  it("returns rows for a method slug", async () => {
    const { sql } = makeSql({
      methods: [{ id: 5, slug: "pi0", name: "Pi0" }],
      results: [
        {
          id: 9,
          method_id: 5,
          benchmark_id: 1,
          task_id: null,
          paper_id: null,
          code_id: null,
          metric: "success_rate",
          metric_value: 0.7,
          eval_conditions: {},
          eval_conditions_hash: "h",
          realm: "real",
          origin: "vendor_internal",
          source_url: "https://x",
          result_date: null,
          confidence: null,
          verification_status: "published",
          skeptic_notes: null,
          method_slug: "pi0",
          method_name: "Pi0",
        },
      ],
    });
    const out = await fetchMethodResults(sql, "pi0");
    expect(out).not.toBeNull();
    expect(out!.method.name).toBe("Pi0");
    expect(out!.rows[0].realm).toBe("real");
  });

  it("returns null for an unknown method", async () => {
    const { sql } = makeSql({ methods: [] });
    expect(await fetchMethodResults(sql, "ghost")).toBeNull();
  });
});
