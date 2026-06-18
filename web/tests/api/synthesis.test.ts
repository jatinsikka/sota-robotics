import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock the server supabase client factory and the queries module.
const fakeRows = [
  {
    id: 1,
    method_id: 1,
    benchmark_id: 1,
    task_id: 3,
    paper_id: null,
    code_id: null,
    metric: "success_rate",
    metric_value: 0.82,
    eval_conditions: { episodes: 50 },
    eval_conditions_hash: "h",
    realm: "real",
    origin: "vendor_internal",
    source_url: "https://example.com",
    result_date: "2026-05-01",
    confidence: null,
    verification_status: "published",
    skeptic_notes: null,
    method_slug: "pi0",
    method_name: "Pi0",
  },
];

vi.mock("@/lib/supabase/server", () => ({
  createServerClient: vi.fn(() => ({})),
}));

vi.mock("@/lib/queries", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/queries")>();
  return {
    ...actual,
    fetchTaskResults: vi.fn(),
  };
});

// Mock the Anthropic SDK.
const createMock = vi.fn();
vi.mock("@anthropic-ai/sdk", () => {
  return {
    default: class {
      messages = { create: createMock };
    },
  };
});

import { POST } from "@/app/api/synthesis/route";
import { fetchTaskResults } from "@/lib/queries";

function makeRequest(body: unknown): Request {
  return new Request("http://localhost/api/synthesis", {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "content-type": "application/json" },
  });
}

describe("POST /api/synthesis", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    process.env.ANTHROPIC_API_KEY = "sk-ant-test";
  });

  it("400s when taskSlug is missing", async () => {
    const res = await POST(makeRequest({}));
    expect(res.status).toBe(400);
  });

  it("404s when the task has no published results record", async () => {
    vi.mocked(fetchTaskResults).mockResolvedValue(null);
    const res = await POST(makeRequest({ taskSlug: "ghost" }));
    expect(res.status).toBe(404);
  });

  it("returns synthesis prose and the cited rows on success", async () => {
    vi.mocked(fetchTaskResults).mockResolvedValue({
      task: { id: 3, domain_id: 1, slug: "pick-and-place", name: "Pick-and-place" },
      rows: fakeRows as any,
    });
    createMock.mockResolvedValue({
      stop_reason: "end_turn",
      content: [{ type: "text", text: "Pi0 leads, but the 82% is vendor-internal and real-world." }],
    });

    const res = await POST(makeRequest({ taskSlug: "pick-and-place" }));
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.synthesis).toContain("Pi0");
    expect(json.rows).toHaveLength(1);
    // Claude was called with opus 4.8 + adaptive thinking.
    const callArg = createMock.mock.calls[0][0];
    expect(callArg.model).toBe("claude-opus-4-8");
    expect(callArg.thinking).toEqual({ type: "adaptive" });
  });

  it("502s when Claude refuses", async () => {
    vi.mocked(fetchTaskResults).mockResolvedValue({
      task: { id: 3, domain_id: 1, slug: "pick-and-place", name: "Pick-and-place" },
      rows: fakeRows as any,
    });
    createMock.mockResolvedValue({
      stop_reason: "refusal",
      stop_details: { category: "other" },
      content: [],
    });
    const res = await POST(makeRequest({ taskSlug: "pick-and-place" }));
    expect(res.status).toBe(502);
  });
});
