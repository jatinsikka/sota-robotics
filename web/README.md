# sota-robotics web

Public, read-only SOTA tracker UI. Next.js (App Router) on Vercel Hobby.

## Environment variables

Set these in the Vercel project (Settings → Environment Variables) and locally in `.env.local`:

| Var | Scope | Notes |
| --- | --- | --- |
| `DATABASE_URL` | server only | Neon pooled Postgres connection string. The app reads the DB **server-side only** (App Router server components / route handlers). NEVER prefix with `NEXT_PUBLIC_`. There is no RLS — access control comes from queries hardcoding `verification_status='published'`. |
| `ANTHROPIC_API_KEY` | server only | Used only in `app/api/synthesis/route.ts`. NEVER prefix with `NEXT_PUBLIC_`. |

## Local dev

    cp .env.local.example .env.local   # fill in values
    npm install
    npm run dev

## Tests / build

    npm run test       # vitest
    npx tsc --noEmit   # typecheck
    npm run build      # production build

## Deploy

Vercel auto-deploys on push. Set the project root to `web/`. The ingest pipeline
(GitHub Actions cron) is independent and does NOT deploy here.
