import Anthropic from "@anthropic-ai/sdk";
import { getSql } from "@/lib/db";
import { fetchTaskResults } from "@/lib/queries";
import { buildSynthesisPrompt } from "@/lib/format";

export const runtime = "nodejs";

export async function POST(req: Request): Promise<Response> {
  let body: { taskSlug?: string };
  try {
    body = await req.json();
  } catch {
    return Response.json({ error: "invalid JSON body" }, { status: 400 });
  }

  const taskSlug = body.taskSlug;
  if (!taskSlug || typeof taskSlug !== "string") {
    return Response.json({ error: "taskSlug is required" }, { status: 400 });
  }

  const result = await fetchTaskResults(getSql(), taskSlug);
  if (!result) {
    return Response.json({ error: "task not found" }, { status: 404 });
  }

  const { task, rows } = result;
  const { system, user } = buildSynthesisPrompt(task.name, rows);

  const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
  const message = await client.messages.create({
    model: "claude-opus-4-8",
    max_tokens: 1024,
    // Opus 4.8 supports adaptive thinking only. The pinned SDK (0.70.1) ships
    // types that predate "adaptive", so cast to keep the runtime value the API
    // expects while satisfying the older ThinkingConfigParam type.
    thinking: { type: "adaptive" } as unknown as Anthropic.ThinkingConfigParam,
    system,
    messages: [{ role: "user", content: user }],
  });

  if (message.stop_reason === "refusal") {
    return Response.json({ error: "synthesis refused" }, { status: 502 });
  }

  const synthesis = message.content
    .filter((b): b is Anthropic.TextBlock => b.type === "text")
    .map((b) => b.text)
    .join("\n")
    .trim();

  return Response.json({ synthesis, rows });
}
