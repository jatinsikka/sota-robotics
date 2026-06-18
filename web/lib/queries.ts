import type { Sql } from "postgres";
import type { ResultRow, Benchmark, Domain, Task, Method } from "@/lib/types";

// Server-side read layer over Neon Postgres. There is NO row-level security:
// every results query below hardcodes `verification_status = 'published'`, so
// pending/held/refuted rows never leave the server. Reference tables hold no
// secrets and are read in full.

export interface DomainWithBenchmarks extends Domain {
  benchmarks: Benchmark[];
}

export async function listBenchmarksByDomain(
  sql: Sql,
  domainId: number,
): Promise<Benchmark[]> {
  const rows = await sql<Benchmark[]>`
    select id, domain_id, slug, name, metric, is_saturated
    from benchmarks
    where domain_id = ${domainId}
    order by name
  `;
  return rows as unknown as Benchmark[];
}

export async function listDomainsWithBenchmarks(
  sql: Sql,
): Promise<DomainWithBenchmarks[]> {
  const domains = await sql<Domain[]>`
    select id, slug, name
    from domains
    order by name
  `;

  const out: DomainWithBenchmarks[] = [];
  for (const d of domains) {
    const benchmarks = await listBenchmarksByDomain(sql, d.id);
    out.push({ ...d, benchmarks });
  }
  return out;
}

export async function fetchBenchmarkWithResults(
  sql: Sql,
  benchmarkSlug: string,
): Promise<{ benchmark: Benchmark; rows: ResultRow[] } | null> {
  const benchmarks = await sql<Benchmark[]>`
    select id, domain_id, slug, name, metric, is_saturated
    from benchmarks
    where slug = ${benchmarkSlug}
    limit 1
  `;
  const benchmark = benchmarks[0];
  if (!benchmark) return null;

  const rows = await sql<ResultRow[]>`
    select
      r.id, r.method_id, r.benchmark_id, r.task_id, r.paper_id, r.code_id,
      r.metric, r.metric_value, r.eval_conditions, r.eval_conditions_hash,
      r.realm, r.origin, r.source_url, r.result_date, r.confidence,
      r.verification_status, r.skeptic_notes,
      m.slug as method_slug, m.name as method_name
    from results r
    join methods m on m.id = r.method_id
    where r.benchmark_id = ${benchmark.id}
      and r.verification_status = 'published'
    order by r.metric_value desc nulls last
  `;

  return { benchmark, rows: rows as unknown as ResultRow[] };
}

export async function fetchTaskResults(
  sql: Sql,
  taskSlug: string,
): Promise<{ task: Task; rows: ResultRow[] } | null> {
  const tasks = await sql<Task[]>`
    select id, domain_id, slug, name
    from tasks
    where slug = ${taskSlug}
    limit 1
  `;
  const task = tasks[0];
  if (!task) return null;

  const rows = await sql<ResultRow[]>`
    select
      r.id, r.method_id, r.benchmark_id, r.task_id, r.paper_id, r.code_id,
      r.metric, r.metric_value, r.eval_conditions, r.eval_conditions_hash,
      r.realm, r.origin, r.source_url, r.result_date, r.confidence,
      r.verification_status, r.skeptic_notes,
      m.slug as method_slug, m.name as method_name
    from results r
    join methods m on m.id = r.method_id
    where r.task_id = ${task.id}
      and r.verification_status = 'published'
  `;

  return { task, rows: rows as unknown as ResultRow[] };
}

export async function fetchMethodResults(
  sql: Sql,
  methodSlug: string,
): Promise<{ method: Method; rows: ResultRow[] } | null> {
  const methods = await sql<Method[]>`
    select id, slug, name
    from methods
    where slug = ${methodSlug}
    limit 1
  `;
  const method = methods[0];
  if (!method) return null;

  const rows = await sql<ResultRow[]>`
    select
      r.id, r.method_id, r.benchmark_id, r.task_id, r.paper_id, r.code_id,
      r.metric, r.metric_value, r.eval_conditions, r.eval_conditions_hash,
      r.realm, r.origin, r.source_url, r.result_date, r.confidence,
      r.verification_status, r.skeptic_notes,
      m.slug as method_slug, m.name as method_name
    from results r
    join methods m on m.id = r.method_id
    where r.method_id = ${method.id}
      and r.verification_status = 'published'
  `;

  return { method, rows: rows as unknown as ResultRow[] };
}

export type { ResultRow, Benchmark, Domain, Task, Method };
