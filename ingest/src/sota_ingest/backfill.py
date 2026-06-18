"""Phase-0 backfill orchestrator + CLI.

Run:  python -m sota_ingest.backfill            (both feeds)
      python -m sota_ingest.backfill --pwc      (PWC only)
      python -m sota_ingest.backfill --awesome  (awesome-lists only)

I/O is injected (fetch_json/fetch_text, writer) so the orchestration logic is
unit-tested with everything mocked. main() wires the real httpx fetchers and
the service-role Supabase writer.
"""
import argparse
import uuid
from dataclasses import dataclass
from typing import Callable

from sota_ingest.awesome_lists import SOURCES, AwesomeSource, parse_awesome_markdown
from sota_ingest.db import SotaWriter, client_from_env
from sota_ingest.fetch import fetch_json as _fetch_json
from sota_ingest.fetch import fetch_text as _fetch_text
from sota_ingest.pwc_backfill import claims_from_pwc

# Frozen PWC archive evaluation-tables JSON (CC-BY-SA on huggingface.co/pwc-archive).
PWC_ARCHIVE_URL = (
    "https://huggingface.co/datasets/pwc-archive/evaluation-tables/resolve/main/evaluation-tables.json"
)


@dataclass
class BackfillStats:
    results_upserted: int = 0
    papers_upserted: int = 0
    code_upserted: int = 0

    def total(self) -> int:
        return self.results_upserted + self.papers_upserted + self.code_upserted


def run_pwc_backfill(
    writer: SotaWriter,
    run_id: str,
    fetch_json: Callable = _fetch_json,
    source_url: str = PWC_ARCHIVE_URL,
) -> BackfillStats:
    """Fetch frozen PWC archive -> filter robotics -> HELD claims -> upsert."""
    data = fetch_json(source_url)
    claims = claims_from_pwc(data)
    stats = BackfillStats()
    for claim in claims:
        method_id = writer.resolve_method(claim.method_slug)
        benchmark_id = writer.resolve_benchmark(claim.benchmark_slug)
        writer.upsert_result(
            claim,
            method_id=method_id,
            benchmark_id=benchmark_id,
            task_id=None,
            paper_id=None,
            code_id=None,
            run_id=run_id,
        )
        stats.results_upserted += 1
    return stats


def run_awesome_backfill(
    writer: SotaWriter,
    sources: list[AwesomeSource] = list(SOURCES),
    fetch_text: Callable = _fetch_text,
) -> BackfillStats:
    """Fetch each awesome-list README -> parse -> resolve papers + code.

    Attribution: each source is CC-BY-SA; we stamp its license on every code
    row and credit the lists in db/ATTRIBUTION.md. (No results rows here —
    these feeds give corpus/taxonomy, not benchmark numbers.)
    """
    stats = BackfillStats()
    for src in sources:
        md = fetch_text(src.raw_url)
        for rec in parse_awesome_markdown(md, source_url=src.raw_url):
            writer.resolve_paper(rec.paper)
            stats.papers_upserted += 1
            if rec.repo_url:
                writer.resolve_code(rec.repo_url, license=src.license)
                stats.code_upserted += 1
    return stats


def run_all(writer: SotaWriter, run_id: str) -> BackfillStats:
    p = run_pwc_backfill(writer, run_id)
    a = run_awesome_backfill(writer)
    return BackfillStats(
        results_upserted=p.results_upserted,
        papers_upserted=a.papers_upserted,
        code_upserted=a.code_upserted,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Phase-0 backfill from frozen sources")
    parser.add_argument("--pwc", action="store_true", help="run only the PWC archive feed")
    parser.add_argument("--awesome", action="store_true", help="run only the awesome-list feeds")
    args = parser.parse_args(argv)

    writer = SotaWriter(client_from_env())
    run_id = f"backfill-{uuid.uuid4().hex[:12]}"

    if args.pwc and not args.awesome:
        stats = run_pwc_backfill(writer, run_id)
    elif args.awesome and not args.pwc:
        stats = run_awesome_backfill(writer)
    else:
        stats = run_all(writer, run_id)

    print(
        f"[{run_id}] results={stats.results_upserted} "
        f"papers={stats.papers_upserted} code={stats.code_upserted} total={stats.total()}"
    )


if __name__ == "__main__":
    main()
