import re
import time
import xml.etree.ElementTree as ET

import httpx

from sota_ingest.models import PaperRec

ATOM = "{http://www.w3.org/2005/Atom}"

# Robotics-relevant categories. We query cs.RO and keep any entry that lists
# cs.RO anywhere (primary OR cross-list), so cross-posted papers aren't lost.
PRIMARY_CATEGORY = "cs.RO"
API_URL = "http://export.arxiv.org/api/query"
POLITENESS_SECONDS = 3.0  # arXiv asks for >= 3s between requests

_ID_RE = re.compile(r"(\d{4}\.\d{4,5})(v\d+)?$")


def _clean(text: str | None) -> str | None:
    """Collapse internal whitespace/newlines that arXiv wraps into fields."""
    if text is None:
        return None
    return re.sub(r"\s+", " ", text).strip()


def _arxiv_id(id_url: str) -> str | None:
    m = _ID_RE.search(id_url.strip())
    return m.group(1) if m else None


def _entry_categories(entry: ET.Element) -> set[str]:
    return {c.get("term", "") for c in entry.findall(f"{ATOM}category")}


def parse_atom(xml_text: str) -> list[PaperRec]:
    """Pure parser: arXiv Atom feed -> list[PaperRec].

    Keeps entries whose categories include cs.RO (primary or cross-listed).
    arxiv_id is stripped of the version suffix and the URL prefix so it
    matches the natural key on the `papers` table (papers.arxiv_id UNIQUE).
    """
    root = ET.fromstring(xml_text)
    recs: list[PaperRec] = []
    for entry in root.findall(f"{ATOM}entry"):
        cats = _entry_categories(entry)
        if PRIMARY_CATEGORY not in cats:
            continue
        id_el = entry.find(f"{ATOM}id")
        id_url = id_el.text if id_el is not None and id_el.text else ""
        title = _clean(entry.findtext(f"{ATOM}title"))
        if not title:
            continue
        summary = _clean(entry.findtext(f"{ATOM}summary"))
        authors = [
            _clean(a.findtext(f"{ATOM}name"))
            for a in entry.findall(f"{ATOM}author")
        ]
        authors = [a for a in authors if a]
        published = entry.findtext(f"{ATOM}published")
        published_date = published[:10] if published else None
        recs.append(
            PaperRec(
                arxiv_id=_arxiv_id(id_url),
                title=title,
                authors=", ".join(authors) if authors else None,
                abstract=summary,
                published_date=published_date,
                url=id_url or None,
            )
        )
    return recs


def fetch_raw(
    client: httpx.Client | None = None,
    max_results: int = 100,
) -> str:
    """Thin HTTP wrapper (untested): fetch the cs.RO Atom feed.

    Sleeps POLITENESS_SECONDS before the call to honour arXiv's 1-req/3s ask.
    """
    owns = client is None
    client = client or httpx.Client(timeout=30.0)
    try:
        time.sleep(POLITENESS_SECONDS)
        resp = client.get(
            API_URL,
            params={
                "search_query": f"cat:{PRIMARY_CATEGORY}",
                "sortBy": "submittedDate",
                "sortOrder": "descending",
                "max_results": max_results,
            },
        )
        resp.raise_for_status()
        return resp.text
    finally:
        if owns:
            client.close()


def fetch() -> list[PaperRec]:
    """Convenience: fetch + parse. Used by the orchestrator."""
    return parse_atom(fetch_raw())
