from pathlib import Path

from sota_ingest.models import PaperRec
from sota_ingest.sources.arxiv_client import parse_atom

FIXTURE = Path(__file__).parent / "fixtures" / "arxiv_cs_ro.atom"


def test_parses_two_entries_into_paperrecs():
    recs = parse_atom(FIXTURE.read_text(encoding="utf-8"))
    assert len(recs) == 2
    assert all(isinstance(r, PaperRec) for r in recs)


def test_arxiv_id_is_stripped_of_version_and_url():
    recs = parse_atom(FIXTURE.read_text(encoding="utf-8"))
    ids = {r.arxiv_id for r in recs}
    assert ids == {"2506.01234", "2506.05678"}


def test_title_and_summary_whitespace_collapsed():
    recs = parse_atom(FIXTURE.read_text(encoding="utf-8"))
    first = next(r for r in recs if r.arxiv_id == "2506.01234")
    assert first.title == "Cross-Embodiment Skill Transfer for Humanoid Manipulation"
    assert first.abstract.startswith("We present a method")
    assert "\n" not in first.title
    assert "  " not in first.abstract


def test_authors_joined_and_published_date_iso():
    recs = parse_atom(FIXTURE.read_text(encoding="utf-8"))
    first = next(r for r in recs if r.arxiv_id == "2506.01234")
    assert first.authors == "Ada Lovelace, Alan Turing"
    assert first.published_date == "2026-06-17"
    assert first.url == "http://arxiv.org/abs/2506.01234v1"


def test_cross_listed_entry_kept_when_cs_ro_present():
    # Second entry's PRIMARY category is cs.AI but it cross-lists cs.RO.
    recs = parse_atom(FIXTURE.read_text(encoding="utf-8"))
    cross = next(r for r in recs if r.arxiv_id == "2506.05678")
    assert cross.title == "Real-World Robot Evaluation With RoboArena"
