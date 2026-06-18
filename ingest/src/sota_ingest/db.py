"""Service-role Supabase writer for Phase-0 backfill.

The ONLY module that writes to Postgres. Reference rows (methods/benchmarks/
papers/code) are resolved-or-created by natural key; results are upserted on
the Plan 1 UNIQUE constraint so re-runs are idempotent.

Auth: service-role client from SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY
(RLS allows writes only to the service role; the publishable key is read-only).
Tests inject a fake client implementing the same chainable .table(...) API.
"""
import os
import re
from typing import Any

from supabase import Client, create_client

from sota_ingest.models import PaperRec, ResultClaim
from sota_ingest.upsert import CONFLICT_TARGET, build_result_row

# Postgres on_conflict string must match Plan 1's CONFLICT_TARGET exactly.
CONFLICT_ON = ",".join(CONFLICT_TARGET)


def client_from_env() -> Client:
    """Build the service-role client. Never run in the test suite (would
    require real creds); used by backfill.py at runtime only."""
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(url, key)


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")


class SotaWriter:
    """Resolve/create reference rows and upsert results via a Supabase client."""

    def __init__(self, client: Any):
        self.client = client

    # --- generic helpers ---------------------------------------------------

    def _find_id(self, table: str, col: str, val: Any) -> int | None:
        resp = self.client.table(table).select("id").eq(col, val).limit(1).execute()
        rows = resp.data or []
        return int(rows[0]["id"]) if rows else None

    def _insert_returning_id(self, table: str, row: dict[str, Any]) -> int:
        resp = self.client.table(table).insert(row).execute()
        rows = resp.data or []
        if not rows:
            raise RuntimeError(f"insert into {table} returned no row: {row!r}")
        return int(rows[0]["id"])

    # --- reference resolvers (natural-key, idempotent) ---------------------

    def resolve_method(self, slug: str, name: str | None = None, org: str | None = None) -> int:
        slug = _slugify(slug)
        existing = self._find_id("methods", "slug", slug)
        if existing is not None:
            return existing
        return self._insert_returning_id("methods", {"slug": slug, "name": name or slug, "org": org})

    def resolve_benchmark(self, slug: str, domain_slug: str | None = None, name: str | None = None) -> int:
        slug = _slugify(slug)
        existing = self._find_id("benchmarks", "slug", slug)
        if existing is not None:
            return existing
        domain_id = self._find_id("domains", "slug", domain_slug) if domain_slug else None
        return self._insert_returning_id(
            "benchmarks", {"slug": slug, "name": name or slug, "domain_id": domain_id}
        )

    def resolve_paper(self, paper: PaperRec) -> int:
        if paper.arxiv_id:
            existing = self._find_id("papers", "arxiv_id", paper.arxiv_id)
            if existing is not None:
                return existing
        else:
            existing = self._find_id("papers", "title", paper.title)
            if existing is not None:
                return existing
        return self._insert_returning_id(
            "papers",
            {
                "arxiv_id": paper.arxiv_id,
                "title": paper.title,
                "authors": paper.authors,
                "abstract": paper.abstract,
                "published_date": paper.published_date,
                "url": paper.url,
            },
        )

    def resolve_code(self, repo_url: str, license: str | None = None) -> int:
        existing = self._find_id("code", "repo_url", repo_url)
        if existing is not None:
            return existing
        return self._insert_returning_id("code", {"repo_url": repo_url, "license": license})

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
        self.client.table("results").upsert([row], on_conflict=CONFLICT_ON).execute()
