"""Top-level entrypoint shim so `python -m sota_ingest.spine` runs the
orchestrator. The implementation lives in `sota_ingest.sources.spine`
(see the File Structure table in Plan 3); this module just re-exports it
and forwards `__main__` so the workflow's fully-qualified module path works.
"""
from sota_ingest.sources.spine import (
    dedup_code_rows,
    dedup_papers,
    main,
    run_upserts,
)

__all__ = ["dedup_code_rows", "dedup_papers", "main", "run_upserts"]


if __name__ == "__main__":
    main()
