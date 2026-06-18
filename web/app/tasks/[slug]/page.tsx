import { notFound } from "next/navigation";
import Link from "next/link";
import { createServerClient } from "@/lib/supabase/server";
import { fetchTaskResults } from "@/lib/queries";
import { LeaderboardTable } from "@/components/LeaderboardTable";
import { SynthesisPanel } from "@/components/SynthesisPanel";

export const dynamic = "force-dynamic";

export default async function TaskPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const supabase = createServerClient();
  const data = await fetchTaskResults(supabase, slug);
  if (!data) notFound();

  const { task, rows } = data;
  // Use the per-row metric for display; tasks may aggregate multiple benchmarks.
  const metric = rows[0]?.metric ?? "success_rate";

  return (
    <>
      <p style={{ fontSize: 13 }}>
        <Link href="/">← all domains</Link>
      </p>
      <h1>Best for: {task.name}</h1>
      <h2>Recommendation</h2>
      <SynthesisPanel taskSlug={slug} />
      <h2>Cited evidence</h2>
      {rows.length === 0 ? (
        <p style={{ color: "#999" }}>No published results for this task yet.</p>
      ) : (
        <LeaderboardTable metric={metric} rows={rows} />
      )}
    </>
  );
}
