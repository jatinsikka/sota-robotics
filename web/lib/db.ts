import postgres, { type Sql } from "postgres";

/**
 * Server-only Postgres (Neon) client.
 *
 * Imported ONLY by server components and route handlers — never by client
 * components. Reads DATABASE_URL, a SERVER-ONLY env var. It MUST NOT be
 * prefixed with NEXT_PUBLIC_, so it can never reach the browser bundle. No RLS:
 * access control is enforced by the query layer, which hardcodes
 * `verification_status = 'published'` on every results read.
 *
 * `postgres()` is lazy — it opens no socket until the first query runs — so a
 * dummy DATABASE_URL is fine for build/typecheck. The client is memoised per
 * server process.
 */
let client: Sql | undefined;

export function getSql(): Sql {
  if (client) return client;
  const connectionString = process.env.DATABASE_URL;
  if (!connectionString) {
    throw new Error("Missing DATABASE_URL (server-only Neon connection string)");
  }
  client = postgres(connectionString, {
    // Neon's pooled endpoint terminates TLS; keep the pool small for serverless.
    max: 5,
    prepare: false,
  });
  return client;
}

export type { Sql };
