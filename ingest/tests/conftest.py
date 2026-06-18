# tests/conftest.py
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


# --- Fake psycopg connection/cursor -------------------------------------------
# Stand-in for psycopg.Connection. db.py drives it via:
#     with conn.cursor() as cur:
#         cur.execute(sql, params)
#         row = cur.fetchone()
#     conn.commit()
# The fake parses only the SQL shapes db.py emits:
#   * select id from <table> where <col> = %s limit 1
#   * insert into <table> (<cols>) values (...) on conflict (<key>)
#       do nothing returning id
#   * insert into results (...) values (...) on conflict (...) do update set ...
# It keeps an in-memory store keyed by table, assigns incrementing ids on
# insert, and honours the unique/natural keys so idempotency is exercised.

_SELECT_RE = re.compile(
    r"select\s+id\s+from\s+(\w+)\s+where\s+(\w+)\s*=\s*%s", re.IGNORECASE
)
_INSERT_RE = re.compile(
    r"insert\s+into\s+(\w+)\s*\(([^)]*)\)\s*values", re.IGNORECASE
)
_ON_CONFLICT_RE = re.compile(
    r"on\s+conflict\s*\(([^)]*)\)\s*(do\s+nothing|do\s+update)", re.IGNORECASE
)


def _unwrap(value: Any) -> Any:
    """Unwrap a psycopg Jsonb-like adapter back to its dict for comparisons."""
    obj = getattr(value, "obj", None)
    if obj is not None and isinstance(obj, (dict, list)):
        return obj
    return value


class _FakeCursor:
    def __init__(self, store: "_FakeStore"):
        self._store = store
        self._result: tuple | None = None

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        params = tuple(_unwrap(p) for p in (params or ()))
        self._store.calls.append({"sql": " ".join(sql.split()), "params": params})

        sel = _SELECT_RE.search(sql)
        ins = _INSERT_RE.search(sql)
        if ins:
            self._result = self._store.do_insert(sql, ins, params)
        elif sel:
            self._result = self._store.do_select(sel.group(1), sel.group(2), params[0])
        else:
            self._result = None

    def fetchone(self) -> tuple | None:
        return self._result


class _FakeStore:
    """In-memory tables behind the fake connection."""

    def __init__(self, seed: dict | None = None):
        self.calls: list[dict] = []
        self._rows: dict[str, list[dict]] = {}
        self._next_id = 1
        for (table, _key), row in (seed or {}).items():
            self._rows.setdefault(table, []).append(dict(row))
            self._next_id = max(self._next_id, int(row.get("id", 0)) + 1)

    # -- helpers --
    def rows(self, table: str) -> list[dict]:
        return self._rows.setdefault(table, [])

    def do_select(self, table: str, col: str, val: Any) -> tuple | None:
        for r in self.rows(table):
            if r.get(col) == val:
                return (r["id"],)
        return None

    def do_insert(self, sql: str, ins: "re.Match", params: tuple) -> tuple | None:
        table = ins.group(1)
        cols = [c.strip() for c in ins.group(2).split(",")]
        row = dict(zip(cols, params))
        conflict = _ON_CONFLICT_RE.search(sql)
        if conflict:
            keys = [k.strip() for k in conflict.group(1).split(",")]
            action = conflict.group(2).lower().replace(" ", "")
            existing = self._find_by_keys(table, keys, row)
            if existing is not None:
                if action == "doupdate":
                    existing.update(row)
                    return None  # results upsert has no RETURNING
                # do nothing -> no row returned; caller re-SELECTs.
                return None
        new = dict(row)
        new["id"] = self._next_id
        self._next_id += 1
        self.rows(table).append(new)
        returning = re.search(r"returning\s+id", sql, re.IGNORECASE)
        return (new["id"],) if returning else None

    def _find_by_keys(self, table: str, keys: list[str], row: dict) -> dict | None:
        for r in self.rows(table):
            if all(r.get(k) == row.get(k) for k in keys):
                return r
        return None


class FakePsycopg:
    """Stand-in for a psycopg connection. `seed` pre-populates existing rows
    keyed by (table, natural-key); inserts assign incrementing ids."""

    def __init__(self, seed: dict | None = None):
        self._store = _FakeStore(seed)
        self.committed = 0

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._store)

    def commit(self) -> None:
        self.committed += 1

    # Exposed for test assertions (mirror old FakeSupabase surface).
    @property
    def calls(self) -> list[dict]:
        return self._store.calls

    @property
    def _store_rows(self) -> dict[str, list[dict]]:
        return self._store._rows


@pytest.fixture
def fake_db():
    return FakePsycopg


# --- Fake Anthropic client + canned-response helpers (agent pipeline, Plan 4) ---
# Never hits the network: returns canned structured-output payloads and records
# the kwargs each create() call received, so tests can assert on stop_reason
# handling, no-prefill, the cached system prefix, and the model id.


def _message(text: str, stop_reason: str = "end_turn") -> SimpleNamespace:
    """Mimic an anthropic Message: .content is a list of blocks, each with
    .type and .text; .stop_reason mirrors the API field."""
    block = SimpleNamespace(type="text", text=text)
    return SimpleNamespace(content=[block], stop_reason=stop_reason, stop_details=None)


class FakeMessages:
    def __init__(self, response_text: str, stop_reason: str):
        self._response_text = response_text
        self._stop_reason = stop_reason
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        return _message(self._response_text, self._stop_reason)


class FakeAnthropic:
    """Drop-in stand-in for anthropic.Anthropic. Records every create() call's
    kwargs and returns a canned structured-output message."""

    def __init__(self, response_text: str, stop_reason: str = "end_turn"):
        self.messages = FakeMessages(response_text, stop_reason)

    @property
    def calls(self) -> list[dict[str, Any]]:
        return self.messages.calls


@pytest.fixture
def extractor_payload() -> str:
    return (FIXTURES / "extractor_response.json").read_text()


@pytest.fixture
def skeptic_payload() -> str:
    return (FIXTURES / "skeptic_response.json").read_text()


@pytest.fixture
def fake_extractor_client(extractor_payload: str) -> FakeAnthropic:
    return FakeAnthropic(extractor_payload)


@pytest.fixture
def fake_skeptic_client(skeptic_payload: str) -> FakeAnthropic:
    return FakeAnthropic(skeptic_payload)
