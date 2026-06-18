import { notFound } from "next/navigation";
import Link from "next/link";
import { getSql } from "@/lib/db";
import { fetchBenchmarkWithResults } from "@/lib/queries";
import { SaturationBanner } from "@/components/SaturationBanner";
import { LeaderboardTable } from "@/components/LeaderboardTable";

export const dynamic = "force-dynamic";

export default async function BenchmarkPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const data = await fetchBenchmarkWithResults(getSql(), slug);
  if (!data) notFound();

  const { benchmark, rows } = data;

  return (
    <>
      <p style={{ fontSize: 13 }}>
        <Link href="/">← all domains</Link>
      </p>
      <h1>{benchmark.name}</h1>
      <SaturationBanner
        isSaturated={benchmark.is_saturated}
        benchmarkName={benchmark.name}
      />
      {rows.length === 0 ? (
        <p style={{ color: "#999" }}>No published results yet for this benchmark.</p>
      ) : (
        <LeaderboardTable metric={benchmark.metric} rows={rows} />
      )}
    </>
  );
}
