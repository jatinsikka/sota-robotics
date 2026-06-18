// Mirrors Plan 1 contracts (sota_ingest/models.py) and db/migrations enums.
export type Realm = "sim" | "real";
export type Origin = "public_reproducible" | "vendor_internal";
export type VerificationStatus = "pending" | "published" | "held" | "refuted";

export interface Domain {
  id: number;
  slug: string;
  name: string;
}

export interface Task {
  id: number;
  domain_id: number;
  slug: string;
  name: string;
}

export interface Benchmark {
  id: number;
  domain_id: number;
  slug: string;
  name: string;
  // metric identifier the benchmark is scored on, e.g. "success_rate" or "elo".
  metric: string;
  is_saturated: boolean;
}

export interface Method {
  id: number;
  slug: string;
  name: string;
}

// A published result row joined with the human-readable method + benchmark names
// the leaderboard needs. Column names match the `results` table from Plan 1.
export interface ResultRow {
  id: number;
  method_id: number;
  benchmark_id: number;
  task_id: number | null;
  paper_id: number | null;
  code_id: number | null;
  metric: string;
  metric_value: number | null;
  eval_conditions: Record<string, unknown>;
  eval_conditions_hash: string;
  realm: Realm;
  origin: Origin;
  source_url: string;
  result_date: string | null;
  confidence: number | null;
  verification_status: VerificationStatus;
  skeptic_notes: string | null;
  // Joined display fields (from PostgREST embedded selects):
  method_slug: string;
  method_name: string;
}
