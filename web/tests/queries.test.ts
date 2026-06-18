import { describe, it, expect, vi } from "vitest";
import {
  listDomainsWithBenchmarks,
  listBenchmarksByDomain,
  fetchBenchmarkWithResults,
  fetchMethodResults,
} from "@/lib/queries";
import type { SupabaseClient } from "@supabase/supabase-js";

// Minimal chainable mock. Each from() call returns a builder whose terminal
// promise resolves to the queued { data, error }. order()/eq()/select() return
// the builder; the builder is awaitable.
function makeSupabase(responses: Record<string, { data: unknown; error: unknown }>) {
  const calls: { table: string; method: string; args: unknown[] }[] = [];
  function builder(table: string) {
    const resp = responses[table] ?? { data: null, error: null };
    const b: any = {
      select: (...a: unknown[]) => {
        calls.push({ table, method: "select", args: a });
        return b;
      },
      eq: (...a: unknown[]) => {
        calls.push({ table, method: "eq", args: a });
        return b;
      },
      order: (...a: unknown[]) => {
        calls.push({ table, method: "order", args: a });
        return b;
      },
      maybeSingle: () => Promise.resolve(resp),
      then: (resolve: (v: unknown) => void) => resolve(resp),
    };
    return b;
  }
  const client = {
    from: (table: string) => {
      calls.push({ table, method: "from", args: [] });
      return builder(table);
    },
  } as unknown as SupabaseClient;
  return { client, calls };
}

describe("listBenchmarksByDomain", () => {
  it("queries benchmarks filtered by domain_id and returns rows", async () => {
    const { client, calls } = makeSupabase({
      benchmarks: {
        data: [{ id: 1, domain_id: 2, slug: "libero", name: "LIBERO", metric: "success_rate", is_saturated: true }],
        error: null,
      },
    });
    const rows = await listBenchmarksByDomain(client, 2);
    expect(rows).toHaveLength(1);
    expect(rows[0].slug).toBe("libero");
    expect(calls.some((c) => c.method === "eq" && c.args[0] === "domain_id" && c.args[1] === 2)).toBe(true);
  });
});

describe("listDomainsWithBenchmarks", () => {
  it("returns each domain with its benchmarks nested", async () => {
    const { client } = makeSupabase({
      domains: {
        data: [{ id: 2, slug: "manip", name: "Manipulation" }],
        error: null,
      },
      benchmarks: {
        data: [{ id: 1, domain_id: 2, slug: "libero", name: "LIBERO", metric: "success_rate", is_saturated: true }],
        error: null,
      },
    });
    const domains = await listDomainsWithBenchmarks(client);
    expect(domains).toHaveLength(1);
    expect(domains[0].name).toBe("Manipulation");
    expect(domains[0].benchmarks[0].slug).toBe("libero");
  });
});

describe("fetchBenchmarkWithResults", () => {
  it("returns null when the benchmark slug does not exist", async () => {
    const { client } = makeSupabase({
      benchmarks: { data: null, error: null },
    });
    const out = await fetchBenchmarkWithResults(client, "ghost");
    expect(out).toBeNull();
  });

  it("returns the benchmark plus shaped result rows", async () => {
    const { client } = makeSupabase({
      benchmarks: {
        data: { id: 1, domain_id: 2, slug: "libero", name: "LIBERO", metric: "success_rate", is_saturated: true },
        error: null,
      },
      results: {
        data: [
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
            methods: { slug: "openvla", name: "OpenVLA" },
          },
        ],
        error: null,
      },
    });
    const out = await fetchBenchmarkWithResults(client, "libero");
    expect(out).not.toBeNull();
    expect(out!.benchmark.is_saturated).toBe(true);
    expect(out!.rows[0].method_name).toBe("OpenVLA");
    expect(out!.rows[0].method_slug).toBe("openvla");
  });

  it("throws when the results query errors", async () => {
    const { client } = makeSupabase({
      benchmarks: {
        data: { id: 1, domain_id: 2, slug: "libero", name: "LIBERO", metric: "success_rate", is_saturated: true },
        error: null,
      },
      results: { data: null, error: { message: "boom" } },
    });
    await expect(fetchBenchmarkWithResults(client, "libero")).rejects.toBeTruthy();
  });
});

describe("fetchMethodResults", () => {
  it("returns shaped rows for a method slug", async () => {
    const { client } = makeSupabase({
      methods: { data: { id: 5, slug: "pi0", name: "Pi0" }, error: null },
      results: {
        data: [
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
            methods: { slug: "pi0", name: "Pi0" },
          },
        ],
        error: null,
      },
    });
    const out = await fetchMethodResults(client, "pi0");
    expect(out).not.toBeNull();
    expect(out!.method.name).toBe("Pi0");
    expect(out!.rows[0].realm).toBe("real");
  });

  it("returns null for an unknown method", async () => {
    const { client } = makeSupabase({ methods: { data: null, error: null } });
    expect(await fetchMethodResults(client, "ghost")).toBeNull();
  });
});
