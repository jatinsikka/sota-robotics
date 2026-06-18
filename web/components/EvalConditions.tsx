export function EvalConditions({
  conditions,
}: {
  conditions: Record<string, unknown>;
}) {
  const entries = Object.entries(conditions);
  if (entries.length === 0) {
    return <span style={{ color: "#999", fontSize: 12 }}>no conditions reported</span>;
  }
  return (
    <span style={{ display: "inline-flex", flexWrap: "wrap", gap: 4 }}>
      {entries.map(([k, v]) => (
        <span
          key={k}
          data-cond-key={k}
          style={{
            fontSize: 11,
            background: "#f0f0f0",
            border: "1px solid #ddd",
            borderRadius: 3,
            padding: "0 5px",
          }}
        >
          {k}: {String(v)}
        </span>
      ))}
    </span>
  );
}
