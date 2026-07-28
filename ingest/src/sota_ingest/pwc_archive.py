"""Load the frozen Papers-with-Code evaluation tables from the pwc-archive
HuggingFace dataset.

The archive used to be a single `evaluation-tables.json`; it was re-published
as four parquet shards (`data/train-0000{0..3}-of-00004.parquet`). Each parquet
row mirrors one top-level JSON task block (`task`, `datasets`, ...), so once
read back to Python dicts it feeds `parse_evaluation_tables` unchanged — after a
normalization pass that (a) coerces the free-form per-row `metrics` object back
to a dict (the JSON->arrow conversion may encode it as a map, list of pairs, or
JSON string) and (b) drops rows the parser can't slug (null dataset name / null
model_name). I/O is injected so the normalization is unit-tested without network.
"""
import io
import json
from typing import Any, Callable

import httpx
import pyarrow.parquet as pq

_BASE = "https://huggingface.co/datasets/pwc-archive/evaluation-tables/resolve/main/data"
SHARD_URLS = [f"{_BASE}/train-0000{i}-of-00004.parquet" for i in range(4)]


def _coerce_metrics(raw: Any) -> dict:
    """The per-row metrics object can survive JSON->parquet as a dict, an arrow
    map (list of (key, value) pairs), or a JSON string. Normalize to a dict."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except (ValueError, TypeError):
            return {}
    if isinstance(raw, (list, tuple)):
        try:
            return {k: v for k, v in raw}
        except (ValueError, TypeError):
            return {}
    return {}


def normalize_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Clean raw parquet pylist rows into the shape parse_evaluation_tables
    expects. Drops datasets with no name, rows with no model_name, and records
    left with no usable datasets."""
    out: list[dict[str, Any]] = []
    for rec in records:
        clean_datasets = []
        for ds in rec.get("datasets") or []:
            if not ds or not ds.get("dataset"):
                continue
            sota = ds.get("sota") or {}
            clean_rows = []
            for row in sota.get("rows") or []:
                if not row or not row.get("model_name"):
                    continue
                clean_rows.append({**row, "metrics": _coerce_metrics(row.get("metrics"))})
            if not clean_rows:
                continue
            clean_datasets.append({
                "dataset": ds["dataset"],
                "sota": {"metrics": sota.get("metrics") or ["score"], "rows": clean_rows},
            })
        if clean_datasets:
            out.append({"task": rec.get("task"), "datasets": clean_datasets})
    return out


def _looks_like_parquet(blob: bytes) -> bool:
    """A valid parquet file starts and ends with the magic bytes b'PAR1'. The
    large shards download flakily from HF's CDN and can arrive truncated; this
    catches a partial transfer before pyarrow raises a cryptic footer error."""
    return len(blob) > 8 and blob[:4] == b"PAR1" and blob[-4:] == b"PAR1"


def _http_get_bytes(url: str, retries: int = 4) -> bytes:
    """Download one shard, retrying on truncated/failed transfers. follow_redirects
    is required: HF LFS objects 302 to a CDN, and httpx does not follow redirects
    by default. The big shards (~65MB) intermittently arrive truncated, so we
    verify the parquet magic bytes and retry rather than persist a corrupt file."""
    last_err: Exception | None = None
    for _ in range(retries):
        try:
            resp = httpx.get(url, follow_redirects=True, timeout=300.0)
            resp.raise_for_status()
            if _looks_like_parquet(resp.content):
                return resp.content
            last_err = ValueError(f"truncated/non-parquet response ({len(resp.content)} bytes)")
        except httpx.HTTPError as e:
            last_err = e
    raise RuntimeError(f"failed to download {url} after {retries} attempts: {last_err}")


def fetch_pwc_archive(
    get_bytes: Callable[[str], bytes] = _http_get_bytes,
    shard_urls: list[str] = SHARD_URLS,
) -> list[dict[str, Any]]:
    """Download every parquet shard, read it, and return normalized task records
    concatenated across shards."""
    records: list[dict[str, Any]] = []
    for url in shard_urls:
        table = pq.read_table(io.BytesIO(get_bytes(url)))
        records.extend(table.to_pylist())
    return normalize_records(records)
