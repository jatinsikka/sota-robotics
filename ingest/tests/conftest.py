# tests/conftest.py
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


class _FakeQuery:
    """Mimics the chainable supabase-py PostgREST query builder.

    Only the slice of the API our db.py uses is implemented:
      .select(cols).eq(col, val).limit(n).execute()      -> reads
      .insert(row).execute()                              -> single insert
      .upsert(rows, on_conflict=...).execute()            -> idempotent upsert
    Every terminal .execute() returns an object with a `.data` list,
    mirroring supabase-py's APIResponse.
    """

    def __init__(self, table: "_FakeTable"):
        self._table = table
        self._op = None
        self._payload = None
        self._on_conflict = None
        self._filters: list[tuple[str, object]] = []

    def select(self, *_cols):
        self._op = "select"
        return self

    def eq(self, col, val):
        self._filters.append((col, val))
        return self

    def limit(self, _n):
        return self

    def insert(self, row):
        self._op = "insert"
        self._payload = row
        return self

    def upsert(self, rows, on_conflict=None):
        self._op = "upsert"
        self._payload = rows
        self._on_conflict = on_conflict
        return self

    def execute(self):
        self._table.calls.append(
            {
                "table": self._table.name,
                "op": self._op,
                "payload": self._payload,
                "on_conflict": self._on_conflict,
                "filters": self._filters,
            }
        )
        if self._op == "select":
            data = self._table.select_handler(self._table.name, self._filters)
            return _FakeResponse(data)
        if self._op in ("insert", "upsert"):
            data = self._table.write_handler(
                self._table.name, self._op, self._payload, self._on_conflict
            )
            return _FakeResponse(data)
        return _FakeResponse([])


class _FakeResponse:
    def __init__(self, data):
        self.data = data


class _FakeTable:
    def __init__(self, name, calls, select_handler, write_handler):
        self.name = name
        self.calls = calls
        self.select_handler = select_handler
        self.write_handler = write_handler

    def select(self, *cols):
        return _FakeQuery(self).select(*cols)

    def insert(self, row):
        return _FakeQuery(self).insert(row)

    def upsert(self, rows, on_conflict=None):
        return _FakeQuery(self).upsert(rows, on_conflict=on_conflict)


class FakeSupabase:
    """Stand-in for supabase.Client.

    `seed` pre-populates existing rows keyed by (table, slug-or-natural-key);
    selects look up there, writes assign incrementing ids and remember rows.
    """

    def __init__(self, seed: dict | None = None):
        self.calls: list[dict] = []
        self._store: dict[str, list[dict]] = {}
        self._next_id = 1
        for (table, _key), row in (seed or {}).items():
            self._store.setdefault(table, []).append(row)
            self._next_id = max(self._next_id, int(row.get("id", 0)) + 1)

    def table(self, name):
        return _FakeTable(name, self.calls, self._select, self._write)

    def _select(self, table, filters):
        rows = self._store.get(table, [])
        out = []
        for r in rows:
            if all(r.get(c) == v for c, v in filters):
                out.append(r)
        return out

    def _write(self, table, op, payload, on_conflict):
        rows = payload if isinstance(payload, list) else [payload]
        written = []
        bucket = self._store.setdefault(table, [])
        for row in rows:
            existing = None
            if op == "upsert" and on_conflict:
                keys = [k.strip() for k in on_conflict.split(",")]
                for r in bucket:
                    if all(r.get(k) == row.get(k) for k in keys):
                        existing = r
                        break
            if existing is not None:
                existing.update(row)
                written.append(existing)
            else:
                new = dict(row)
                new.setdefault("id", self._next_id)
                self._next_id += 1
                bucket.append(new)
                written.append(new)
        return written


@pytest.fixture
def fake_supabase():
    return FakeSupabase
