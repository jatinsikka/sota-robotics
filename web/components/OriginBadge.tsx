import type { Origin } from "@/lib/types";
import { originLabel } from "@/lib/format";

export function OriginBadge({ origin }: { origin: Origin }) {
  const isVendor = origin === "vendor_internal";
  return (
    <span
      data-origin={origin}
      style={{
        display: "inline-block",
        padding: "1px 6px",
        borderRadius: 4,
        fontSize: 12,
        fontWeight: 600,
        color: isVendor ? "#b50" : "#555",
        border: `1px solid ${isVendor ? "#b50" : "#999"}`,
      }}
    >
      {originLabel(origin)}
    </span>
  );
}
