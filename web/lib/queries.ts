import type { SupabaseClient } from "@supabase/supabase-js";
import type { ResultRow, Benchmark, Domain, Task, Method } from "@/lib/types";

const RESULT_SELECT =
  "id, method_id, benchmark_id, task_id, paper_id, code_id, metric, metric_value, eval_conditions, eval_conditions_hash, realm, origin, source_url, result_date, confidence, verification_status, skeptic_notes, methods!inner(slug, name)";

const BENCHMARK_SELECT = "id, domain_id, slug, name, metric, is_saturated";

function shapeRow(raw: Record<string, unknown>): ResultRow {
  const method = raw.methods as { slug: string; name: string };
  return {
    ...(raw as unknown as ResultRow),
    method_slug: method.slug,
    method_name: method.name,
  };
}

export async function listBenchmarksByDomain(
  supabase: SupabaseClient,
  domainId: number,
): Promise<Benchmark[]> {
  const { data, error } = await supabase
    .from("benchmarks")
    .select(BENCHMARK_SELECT)
    .eq("domain_id", domainId)
    .order("name");
  if (error) throw error;
  return (data as Benchmark[]) ?? [];
}

export interface DomainWithBenchmarks extends Domain {
  benchmarks: Benchmark[];
}

export async function listDomainsWithBenchmarks(
  supabase: SupabaseClient,
): Promise<DomainWithBenchmarks[]> {
  const { data, error } = await supabase
    .from("domains")
    .select("id, slug, name")
    .order("name");
  if (error) throw error;
  const domains = (data as Domain[]) ?? [];

  const out: DomainWithBenchmarks[] = [];
  for (const d of domains) {
    const benchmarks = await listBenchmarksByDomain(supabase, d.id);
    out.push({ ...d, benchmarks });
  }
  return out;
}

export async function fetchBenchmarkWithResults(
  supabase: SupabaseClient,
  benchmarkSlug: string,
): Promise<{ benchmark: Benchmark; rows: ResultRow[] } | null> {
  const { data: benchmark, error: bErr } = await supabase
    .from("benchmarks")
    .select(BENCHMARK_SELECT)
    .eq("slug", benchmarkSlug)
    .maybeSingle();
  if (bErr) throw bErr;
  if (!benchmark) return null;

  const { data, error } = await supabase
    .from("results")
    .select(RESULT_SELECT)
    .eq("benchmark_id", (benchmark as Benchmark).id)
    .order("metric_value", { ascending: false });
  if (error) throw error;

  return {
    benchmark: benchmark as Benchmark,
    rows: ((data as Record<string, unknown>[]) ?? []).map(shapeRow),
  };
}

export async function fetchTaskResults(
  supabase: SupabaseClient,
  taskSlug: string,
): Promise<{ task: Task; rows: ResultRow[] } | null> {
  const { data: task, error: taskErr } = await supabase
    .from("tasks")
    .select("id, domain_id, slug, name")
    .eq("slug", taskSlug)
    .maybeSingle();
  if (taskErr) throw taskErr;
  if (!task) return null;

  const { data, error } = await supabase
    .from("results")
    .select(RESULT_SELECT)
    .eq("task_id", (task as Task).id);
  if (error) throw error;

  return {
    task: task as Task,
    rows: ((data as Record<string, unknown>[]) ?? []).map(shapeRow),
  };
}

export async function fetchMethodResults(
  supabase: SupabaseClient,
  methodSlug: string,
): Promise<{ method: Method; rows: ResultRow[] } | null> {
  const { data: method, error: mErr } = await supabase
    .from("methods")
    .select("id, slug, name")
    .eq("slug", methodSlug)
    .maybeSingle();
  if (mErr) throw mErr;
  if (!method) return null;

  const { data, error } = await supabase
    .from("results")
    .select(RESULT_SELECT)
    .eq("method_id", (method as Method).id);
  if (error) throw error;

  return {
    method: method as Method,
    rows: ((data as Record<string, unknown>[]) ?? []).map(shapeRow),
  };
}

export { RESULT_SELECT, BENCHMARK_SELECT, shapeRow };
export type { ResultRow, Benchmark, Domain, Task, Method };
