import uuid
from typing import Any, Protocol

from sota_ingest.models import PaperRec
from sota_ingest.sources import arxiv_client, github_client, hf_client


class _Writer(Protocol):
    def new_run_id(self) -> str: ...
    def upsert_paper(self, paper: PaperRec) -> int: ...
    def upsert_code(self, row: dict[str, Any]) -> int: ...


def dedup_papers(papers: list[PaperRec]) -> list[PaperRec]:
    """Dedup by natural key arxiv_id (fallback: title when arxiv_id is None).
    Last writer wins within a single pass."""
    by_key: dict[str, PaperRec] = {}
    for p in papers:
        key = p.arxiv_id or f"title::{p.title}"
        by_key[key] = p
    return list(by_key.values())


def dedup_code_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Dedup code rows by natural key repo_url. Last writer wins."""
    by_url: dict[str, dict[str, Any]] = {}
    for r in rows:
        by_url[r["repo_url"]] = r
    return list(by_url.values())


def _code_subset(row: dict[str, Any]) -> dict[str, Any]:
    """Keep only keys that exist on the `code` table for the writer."""
    return {k: v for k, v in row.items() if k in github_client.CODE_COLUMNS}


def run_upserts(
    db: _Writer,
    papers: list[PaperRec],
    code_rows: list[dict[str, Any]],
) -> dict[str, int]:
    """Dedup then upsert. Returns counts written. Idempotent: the DB writer
    upserts on natural keys (papers.arxiv_id, code.repo_url)."""
    deduped_papers = dedup_papers(papers)
    deduped_code = dedup_code_rows(code_rows)
    for paper in deduped_papers:
        db.upsert_paper(paper)
    for row in deduped_code:
        db.upsert_code(_code_subset(row))
    return {"papers": len(deduped_papers), "code": len(deduped_code)}


class _SotaWriterAdapter:
    """Adapt the Plan 2 `SotaWriter` to the `_Writer` Protocol the spine uses.

    Plan 2 ships `SotaWriter(client)` with natural-key resolvers
    (`resolve_paper(PaperRec) -> int`, `resolve_code(repo_url, license) -> int`)
    backed by a service-role Supabase client, NOT a DSN-based `Database` with
    `upsert_paper`/`upsert_code`. This thin shim maps the spine's expected
    method names onto the real writer so `run_upserts` works unchanged.
    """

    def __init__(self) -> None:
        from sota_ingest.db import SotaWriter, client_from_env  # Plan 2

        self._writer = SotaWriter(client_from_env())

    def new_run_id(self) -> str:
        return f"spine-{uuid.uuid4().hex[:12]}"

    def upsert_paper(self, paper: PaperRec) -> int:
        # resolve_paper is idempotent on papers.arxiv_id (fallback title).
        return self._writer.resolve_paper(paper)

    def upsert_code(self, row: dict[str, Any]) -> int:
        # resolve_code is idempotent on code.repo_url.
        return self._writer.resolve_code(row["repo_url"], license=row.get("license"))

    def close(self) -> None:
        pass


def main() -> None:
    """Daily firehose entrypoint. Run via: python -m sota_ingest.spine"""
    papers = arxiv_client.fetch()
    code_rows = github_client.fetch()
    hf_records = hf_client.fetch()  # adoption signal; logged, not yet stored

    db = _SotaWriterAdapter()
    try:
        run_id = db.new_run_id()
        summary = run_upserts(db, papers=papers, code_rows=code_rows)
    finally:
        db.close()

    print(
        f"[spine] run={run_id} "
        f"arxiv={len(papers)} code={len(code_rows)} hf={len(hf_records)} "
        f"upserted={summary}"
    )


if __name__ == "__main__":
    main()
