"""Service-role Postgres writer for Phase-0 backfill.

The ONLY module that writes to Postgres. Reference rows (methods/benchmarks/
papers/code) are resolved-or-created by natural key; results are upserted on
the Plan 1 UNIQUE constraint so re-runs are idempotent.

Backend: psycopg (v3). `client_from_env()` returns a psycopg Connection from
`DATABASE_URL` (Neon pooled connection string). There is no Supabase RLS:
the web app reads server-side and filters `verification_status='published'`
in its queries, and this writer holds the only credentials with write access.

Tests inject a fake connection implementing the same `.cursor()` context-
manager API (`execute` / `fetchone`).
"""
import os
import re
from typing import Any

import psycopg

from sota_ingest.models import PaperRec, ResultClaim
from sota_ingest.upsert import CONFLICT_TARGET, build_result_row

# Postgres ON CONFLICT target columns must match Plan 1's CONFLICT_TARGET exactly.
CONFLICT_ON = ",".join(CONFLICT_TARGET)


def client_from_env() -> "psycopg.Connection":
    """Open a psycopg connection from DATABASE_URL (Neon pooled string). Never
    run in the test suite (would require a real DB); used at runtime only."""
    dsn = os.environ["DATABASE_URL"]
    return psycopg.connect(dsn)


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")


class SotaWriter:
    """Resolve/create reference rows and upsert results via a psycopg connection.

    `conn` is any object exposing psycopg's `.cursor()` context-manager API:
    `with conn.cursor() as cur: cur.execute(sql, params); cur.fetchone()`.
    Writes are committed after each operation so callers don't have to.
    """

    def __init__(self, conn: Any):
        self.conn = conn

    # --- low-level execution helper ---------------------------------------

    def _execute_returning(self, sql: str, params: tuple[Any, ...]) -> tuple | None:
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
        self._commit()
        return row

    def _commit(self) -> None:
        commit = getattr(self.conn, "commit", None)
        if callable(commit):
            commit()

    # --- reference resolvers (natural-key, idempotent) ---------------------

    def resolve_method(self, slug: str, name: str | None = None, org: str | None = None) -> int:
        slug = _slugify(slug)
        # INSERT or, on slug collision, no-op then return the existing id via the
        # RETURNING-or-SELECT pattern. ON CONFLICT DO NOTHING returns no row, so
        # fall back to a SELECT.
        row = self._execute_returning(
            "insert into methods (slug, name, org) values (%s, %s, %s) "
            "on conflict (slug) do nothing returning id",
            (slug, name or slug, org),
        )
        if row is not None:
            return int(row[0])
        existing = self._execute_returning(
            "select id from methods where slug = %s limit 1", (slug,)
        )
        return int(existing[0])

    def resolve_benchmark(self, slug: str, domain_slug: str | None = None, name: str | None = None) -> int:
        slug = _slugify(slug)
        domain_id = None
        if domain_slug:
            drow = self._execute_returning(
                "select id from domains where slug = %s limit 1", (domain_slug,)
            )
            domain_id = int(drow[0]) if drow else None
        row = self._execute_returning(
            "insert into benchmarks (slug, name, domain_id) values (%s, %s, %s) "
            "on conflict (slug) do nothing returning id",
            (slug, name or slug, domain_id),
        )
        if row is not None:
            return int(row[0])
        existing = self._execute_returning(
            "select id from benchmarks where slug = %s limit 1", (slug,)
        )
        return int(existing[0])

    def resolve_paper(self, paper: PaperRec) -> int:
        if paper.arxiv_id:
            existing = self._execute_returning(
                "select id from papers where arxiv_id = %s limit 1", (paper.arxiv_id,)
            )
        else:
            existing = self._execute_returning(
                "select id from papers where title = %s limit 1", (paper.title,)
            )
        if existing is not None:
            return int(existing[0])
        # arxiv_id is UNIQUE; title is not, so only the arxiv path can use
        # ON CONFLICT. For the title-only path we already SELECTed above.
        row = self._execute_returning(
            "insert into papers (arxiv_id, title, authors, abstract, published_date, url) "
            "values (%s, %s, %s, %s, %s, %s) "
            "on conflict (arxiv_id) do nothing returning id",
            (
                paper.arxiv_id,
                paper.title,
                paper.authors,
                paper.abstract,
                paper.published_date,
                paper.url,
            ),
        )
        if row is not None:
            return int(row[0])
        # Lost a race on arxiv_id (or DO NOTHING fired): re-select.
        existing = self._execute_returning(
            "select id from papers where arxiv_id = %s limit 1", (paper.arxiv_id,)
        )
        return int(existing[0])

    def resolve_code(self, repo_url: str, license: str | None = None) -> int:
        existing = self._execute_returning(
            "select id from code where repo_url = %s limit 1", (repo_url,)
        )
        if existing is not None:
            return int(existing[0])
        row = self._execute_returning(
            "insert into code (repo_url, license) values (%s, %s) "
            "on conflict (repo_url) do nothing returning id",
            (repo_url, license),
        )
        if row is not None:
            return int(row[0])
        existing = self._execute_returning(
            "select id from code where repo_url = %s limit 1", (repo_url,)
        )
        return int(existing[0])

    # --- results upsert (idempotent via Plan 1 constraint) -----------------

    def upsert_result(
        self,
        claim: ResultClaim,
        method_id: int,
        benchmark_id: int,
        task_id: int | None,
        paper_id: int | None,
        code_id: int | None,
        run_id: str,
    ) -> None:
        row = build_result_row(claim, method_id, benchmark_id, task_id, paper_id, code_id, run_id)
        cols = list(row.keys())
        placeholders = ", ".join(["%s"] * len(cols))
        col_list = ", ".join(cols)
        # On the Plan 1 unique key, refresh every non-key column so a re-run with
        # updated verification/skeptic fields overwrites in place (idempotent).
        update_cols = [c for c in cols if c not in CONFLICT_TARGET]
        set_clause = ", ".join(f"{c} = excluded.{c}" for c in update_cols)
        sql = (
            f"insert into results ({col_list}) values ({placeholders}) "
            f"on conflict ({CONFLICT_ON}) do update set {set_clause}"
        )
        params = tuple(_adapt(row[c]) for c in cols)
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
        self._commit()


def _adapt(value: Any) -> Any:
    """Adapt Python values for psycopg parameters. dict -> psycopg Jsonb so the
    JSONB `eval_conditions` column round-trips correctly."""
    if isinstance(value, dict):
        from psycopg.types.json import Jsonb

        return Jsonb(value)
    return value
