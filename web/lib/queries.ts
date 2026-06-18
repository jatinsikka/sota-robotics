import type { SupabaseClient } from "@supabase/supabase-js";
import type { ResultRow, Benchmark, Domain, Task } from "@/lib/types";

const RESULT_SELECT =
  "id, method_id, benchmark_id, task_id, paper_id, code_id, metric, metric_value, eval_conditions, eval_conditions_hash, realm, origin, source_url, result_date, confidence, verification_status, skeptic_notes, methods!inner(slug, name)";

function shapeRow(raw: Record<string, unknown>): ResultRow {
  const method = raw.methods as { slug: string; name: string };
  return {
    ...(raw as unknown as ResultRow),
    method_slug: method.slug,
    method_name: method.name,
  };
}

/** Published results for a task slug, newest-by-value not applied here (UI ranks). */
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

export { RESULT_SELECT, shapeRow };
export type { ResultRow, Benchmark, Domain, Task };
