import { createClient, type SupabaseClient } from "@supabase/supabase-js";

/**
 * Server-side Supabase client for Server Components and route handlers.
 * Uses the SAME publishable key — the web app never holds the service-role key;
 * RLS restricts reads to reference tables + published results. A fresh client is
 * created per request (no shared session state on the server).
 */
export function createServerClient(): SupabaseClient {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  if (!url || !key) {
    throw new Error(
      "Missing NEXT_PUBLIC_SUPABASE_URL or NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
    );
  }
  return createClient(url, key, { auth: { persistSession: false } });
}
