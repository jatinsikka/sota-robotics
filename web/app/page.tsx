import Link from "next/link";
import { getSql } from "@/lib/db";
import { listDomainsWithBenchmarks } from "@/lib/queries";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const domains = await listDomainsWithBenchmarks(getSql());

  return (
    <>
      <h1>sota-robotics</h1>
      <p style={{ color: "#555" }}>
        A robotics-native, full-embodiment live SOTA tracker. Rankings always
        surface eval conditions, sim vs real, and origin — leaderboards are
        saturated and gamed, so raw numbers never stand alone.
      </p>
      {domains.map((d) => (
        <section key={d.id}>
          <h2>{d.name}</h2>
          {d.benchmarks.length === 0 ? (
            <p style={{ color: "#999" }}>No benchmarks yet.</p>
          ) : (
            <ul>
              {d.benchmarks.map((b) => (
                <li key={b.id}>
                  <Link href={`/benchmarks/${b.slug}`}>{b.name}</Link>
                  {b.is_saturated && (
                    <span style={{ color: "#c80", marginLeft: 8, fontSize: 12 }}>
                      saturated
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      ))}
    </>
  );
}
