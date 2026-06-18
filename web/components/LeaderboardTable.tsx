import type { ResultRow } from "@/lib/types";
import { rankResults, formatMetricValue, isEloMetric, formatResultDate } from "@/lib/format";
import { RealmBadge } from "@/components/RealmBadge";
import { OriginBadge } from "@/components/OriginBadge";
import { EvalConditions } from "@/components/EvalConditions";

export function LeaderboardTable({
  metric,
  rows,
}: {
  metric: string;
  rows: ResultRow[];
}) {
  const ranked = rankResults(rows);
  const valueHeader = isEloMetric(metric) ? "Elo" : metric;

  return (
    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
      <thead>
        <tr style={{ textAlign: "left", borderBottom: "2px solid #333" }}>
          <th style={{ padding: "6px 8px" }}>#</th>
          <th style={{ padding: "6px 8px" }}>Method</th>
          <th style={{ padding: "6px 8px" }}>{valueHeader}</th>
          <th style={{ padding: "6px 8px" }}>Realm</th>
          <th style={{ padding: "6px 8px" }}>Origin</th>
          <th style={{ padding: "6px 8px" }}>Date</th>
          <th style={{ padding: "6px 8px" }}>Conditions</th>
          <th style={{ padding: "6px 8px" }}>Source</th>
        </tr>
      </thead>
      <tbody>
        {ranked.map((r, i) => (
          <tr key={r.id} style={{ borderBottom: "1px solid #eee" }}>
            <td style={{ padding: "6px 8px" }}>{i + 1}</td>
            <td style={{ padding: "6px 8px", fontWeight: 600 }}>{r.method_name}</td>
            <td style={{ padding: "6px 8px" }}>
              {formatMetricValue(r.metric, r.metric_value)}
            </td>
            <td style={{ padding: "6px 8px" }}>
              <RealmBadge realm={r.realm} />
            </td>
            <td style={{ padding: "6px 8px" }}>
              <OriginBadge origin={r.origin} />
            </td>
            <td style={{ padding: "6px 8px" }}>{formatResultDate(r.result_date)}</td>
            <td style={{ padding: "6px 8px" }}>
              <EvalConditions conditions={r.eval_conditions} />
            </td>
            <td style={{ padding: "6px 8px" }}>
              <a href={r.source_url} target="_blank" rel="noreferrer">
                source
              </a>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
