from sota_ingest.models import PaperRec
from sota_ingest.sources.spine import (
    dedup_code_rows,
    dedup_papers,
    run_upserts,
)


def test_dedup_papers_by_arxiv_id_last_wins():
    papers = [
        PaperRec(arxiv_id="2506.01234", title="Old title"),
        PaperRec(arxiv_id="2506.05678", title="Other"),
        PaperRec(arxiv_id="2506.01234", title="New title"),
    ]
    out = dedup_papers(papers)
    assert len(out) == 2
    merged = next(p for p in out if p.arxiv_id == "2506.01234")
    assert merged.title == "New title"  # last writer wins


def test_dedup_papers_keeps_none_arxiv_distinct_by_title():
    papers = [
        PaperRec(arxiv_id=None, title="Workshop paper A"),
        PaperRec(arxiv_id=None, title="Workshop paper B"),
        PaperRec(arxiv_id=None, title="Workshop paper A"),
    ]
    out = dedup_papers(papers)
    assert len(out) == 2  # A collapsed, B kept


def test_dedup_code_rows_by_repo_url_last_wins():
    rows = [
        {"repo_url": "https://github.com/x/y", "stars": 10},
        {"repo_url": "https://github.com/a/b", "stars": 5},
        {"repo_url": "https://github.com/x/y", "stars": 99},
    ]
    out = dedup_code_rows(rows)
    assert len(out) == 2
    xy = next(r for r in out if r["repo_url"].endswith("y"))
    assert xy["stars"] == 99


class _FakeDB:
    def __init__(self):
        self.papers = []
        self.code = []
        self._next = 0

    def new_run_id(self):
        return "run-test"

    def upsert_paper(self, paper):
        self.papers.append(paper)
        self._next += 1
        return self._next

    def upsert_code(self, row):
        self.code.append(row)
        self._next += 1
        return self._next


def test_run_upserts_dedups_and_writes_code_subset_only():
    db = _FakeDB()
    papers = [
        PaperRec(arxiv_id="2506.01234", title="A"),
        PaperRec(arxiv_id="2506.01234", title="A2"),
    ]
    code_rows = [
        {
            "repo_url": "https://github.com/x/y",
            "stars": 99,
            "last_commit": "2026-06-17",
            "license": "Apache-2.0",
            "release_count": 14,
            "latest_release": "v0.4.0",
        }
    ]
    summary = run_upserts(db, papers=papers, code_rows=code_rows)
    assert summary == {"papers": 1, "code": 1}
    assert len(db.papers) == 1 and db.papers[0].title == "A2"
    # Only code-table columns reach the writer (no release_* keys).
    written = db.code[0]
    assert set(written) == {"repo_url", "stars", "last_commit", "license"}
    assert written["stars"] == 99
