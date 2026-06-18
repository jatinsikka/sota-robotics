"""Apply db/migrations/*.sql to the Neon Postgres in filename order.

Run:  python -m sota_ingest.migrate

Connects via DATABASE_URL and executes each migration file, in lexical
filename order, inside a single transaction. Every migration is written to be
idempotent (IF NOT EXISTS / ON CONFLICT), so re-running is safe. Effectively-
empty files (e.g. the RLS no-op) are skipped.
"""
import os
import sys
from pathlib import Path
from typing import Any, Callable, Iterable

import psycopg

# repo_root/db/migrations  (this file lives at repo_root/ingest/src/sota_ingest/)
DEFAULT_MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "db" / "migrations"


def list_migrations(migrations_dir: Path) -> list[Path]:
    """Return *.sql files sorted by filename (zero-padded numeric prefixes mean
    lexical order == apply order)."""
    return sorted(migrations_dir.glob("*.sql"), key=lambda p: p.name)


def _is_effectively_empty(sql: str) -> bool:
    """True if the file has no executable SQL once comments/whitespace are
    stripped (so an all-comment no-op migration is skipped cleanly)."""
    statements = []
    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        statements.append(stripped)
    return not statements


def apply_migrations(
    conn: Any,
    migrations_dir: Path = DEFAULT_MIGRATIONS_DIR,
    *,
    logger: Callable[[str], None] = print,
) -> list[str]:
    """Apply every migration in order. Returns the names of files actually
    executed (empties are listed as skipped, not executed)."""
    applied: list[str] = []
    files = list_migrations(migrations_dir)
    for path in files:
        sql = path.read_text(encoding="utf-8")
        if _is_effectively_empty(sql):
            logger(f"[migrate] skip (empty): {path.name}")
            continue
        with conn.cursor() as cur:
            cur.execute(sql)
        applied.append(path.name)
        logger(f"[migrate] applied: {path.name}")
    commit = getattr(conn, "commit", None)
    if callable(commit):
        commit()
    return applied


def main(argv: Iterable[str] | None = None) -> None:
    dsn = os.environ["DATABASE_URL"]
    with psycopg.connect(dsn) as conn:
        applied = apply_migrations(conn)
    print(f"[migrate] done: {len(applied)} migration(s) applied")


if __name__ == "__main__":
    main(sys.argv[1:])
