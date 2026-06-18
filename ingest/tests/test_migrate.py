# tests/test_migrate.py
from pathlib import Path

from sota_ingest.migrate import apply_migrations, list_migrations


def _write(d: Path, name: str, body: str) -> None:
    (d / name).write_text(body, encoding="utf-8")


def test_list_migrations_in_filename_order(tmp_path):
    # create out of order; expect lexical (== numeric prefix) order back
    _write(tmp_path, "0002_b.sql", "select 2;")
    _write(tmp_path, "0001_a.sql", "select 1;")
    _write(tmp_path, "0010_c.sql", "select 10;")
    _write(tmp_path, "notes.txt", "ignored")  # non-sql ignored
    names = [p.name for p in list_migrations(tmp_path)]
    assert names == ["0001_a.sql", "0002_b.sql", "0010_c.sql"]


class _FakeCursor:
    def __init__(self, executed):
        self._executed = executed

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def execute(self, sql, params=()):
        self._executed.append(sql)


class _FakeConn:
    """Records executed SQL; the real DB apply is never hit."""

    def __init__(self):
        self.executed: list[str] = []
        self.commits = 0

    def cursor(self):
        return _FakeCursor(self.executed)

    def commit(self):
        self.commits += 1


def test_apply_migrations_runs_each_file_in_order(tmp_path):
    _write(tmp_path, "0001_a.sql", "create table a ();")
    _write(tmp_path, "0002_b.sql", "create table b ();")
    conn = _FakeConn()
    applied = apply_migrations(conn, tmp_path, logger=lambda _m: None)
    assert applied == ["0001_a.sql", "0002_b.sql"]
    assert conn.executed == ["create table a ();", "create table b ();"]
    assert conn.commits == 1


def test_apply_migrations_skips_effectively_empty_file(tmp_path):
    # an all-comment no-op (mirrors 0003_rls.sql) must be tolerated and skipped
    _write(tmp_path, "0001_a.sql", "create table a ();")
    _write(
        tmp_path,
        "0003_rls.sql",
        "-- intentionally empty\n-- RLS not used; reads are server-side only\n\n",
    )
    conn = _FakeConn()
    applied = apply_migrations(conn, tmp_path, logger=lambda _m: None)
    assert applied == ["0001_a.sql"]  # empty file not executed
    assert conn.executed == ["create table a ();"]


def test_apply_migrations_uses_real_migrations_dir_default():
    # The packaged default points at db/migrations and finds the 4 real files.
    files = list_migrations(
        Path(__file__).resolve().parents[2] / "db" / "migrations"
    )
    names = [p.name for p in files]
    assert names == [
        "0001_extensions.sql",
        "0002_core_tables.sql",
        "0003_rls.sql",
        "0004_seed_taxonomy.sql",
    ]
