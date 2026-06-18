"use client";

import { useEffect, useState } from "react";

export function SynthesisPanel({ taskSlug }: { taskSlug: string }) {
  const [state, setState] = useState<
    { status: "loading" } | { status: "done"; text: string } | { status: "error" }
  >({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    fetch("/api/synthesis", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ taskSlug }),
    })
      .then(async (r) => {
        if (!r.ok) throw new Error(`status ${r.status}`);
        return r.json();
      })
      .then((json: { synthesis: string }) => {
        if (!cancelled) setState({ status: "done", text: json.synthesis });
      })
      .catch(() => {
        if (!cancelled) setState({ status: "error" });
      });
    return () => {
      cancelled = true;
    };
  }, [taskSlug]);

  if (state.status === "loading")
    return <p style={{ color: "#888" }}>Synthesizing a recommendation…</p>;
  if (state.status === "error")
    return <p style={{ color: "#c00" }}>Could not generate a synthesis right now.</p>;
  return (
    <p style={{ background: "#f6f8ff", border: "1px solid #cdd", padding: 12, borderRadius: 6 }}>
      {state.text}
    </p>
  );
}
