import type { Realm } from "@/lib/types";
import { realmLabel } from "@/lib/format";

export function RealmBadge({ realm }: { realm: Realm }) {
  return (
    <span
      data-realm={realm}
      style={{
        display: "inline-block",
        padding: "1px 6px",
        borderRadius: 4,
        fontSize: 12,
        fontWeight: 600,
        color: realm === "real" ? "#0a5" : "#06c",
        border: `1px solid ${realm === "real" ? "#0a5" : "#06c"}`,
      }}
    >
      {realmLabel(realm)}
    </span>
  );
}
