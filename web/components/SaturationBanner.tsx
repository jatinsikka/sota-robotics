export function SaturationBanner({
  isSaturated,
  benchmarkName,
}: {
  isSaturated: boolean;
  benchmarkName: string;
}) {
  if (!isSaturated) return null;
  return (
    <div
      role="alert"
      style={{
        border: "1px solid #c80",
        background: "#fff8e6",
        color: "#7a4d00",
        padding: "10px 14px",
        borderRadius: 6,
        marginBottom: 16,
        fontSize: 14,
      }}
    >
      <strong>{benchmarkName} is saturated.</strong> Top scores here largely
      reflect memorization and gamed evaluation, not real capability. Read the
      eval conditions, realm (sim vs real), and origin before trusting any rank —
      and prefer real-world Elo (RoboArena) where available.
    </div>
  );
}
