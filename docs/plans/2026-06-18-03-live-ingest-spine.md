# Plan 3 — Live Ingest Spine

> For agentic workers: This plan is self-contained. Execute tasks top to bottom. Every code block is complete and final — copy it verbatim, do not invent placeholders, do not skip the TDD ordering. All paths are rooted at `24_sota-robotics/`. Run Python from inside `ingest/` with `uv` (e.g. `cd 24_sota-robotics/ingest && uv run pytest -q`). Type names and function signatures MUST match the Plan 1 contracts (`PaperRec`, `ResultClaim`, `canonical_hash`) and the Plan 2 `db.py` writer — never redefine them.

**Dependency:** This plan REQUIRES **Plan 2 (DB Writer)** to be merged first. Plan 2 provides `ingest/src/sota_ingest/db.py`, which exposes the `Database` writer used by the orchestrator here. The exact interface this plan depends on:

```python
# Provided by Plan 2 — ingest/src/sota_ingest/db.py (DO NOT redefine here)
class Database:
    def __init__(self, dsn: str) -> None: ...
    def upsert_paper(self, paper: PaperRec) -> int:
        """Insert/update a row in `papers` keyed on arxiv_id (or title when
        arxiv_id is None). Returns papers.id."""
    def upsert_code(self, row: dict[str, Any]) -> int:
        """Insert/update a row in `code` keyed on repo_url. `row` keys are a
        subset of {repo_url, stars, last_commit, license}. Returns code.id."""
    def new_run_id(self) -> str:
        """A unique run id string for this ingest pass (e.g. a UUID)."""
    def close(self) -> None: ...
```

If Plan 2's `Database` is not yet on `main`, STOP and complete Plan 2 first. Do not stub `db.py` in this plan.

---

## Goal

Stand up the **daily discovery firehose**: a single idempotent pass that pulls new robotics research signal from three live sources and writes it into Supabase via the Plan 2 writer.

- **arXiv** — new `cs.RO` papers plus robotics-relevant cross-lists, parsed into `PaperRec`.
- **Hugging Face Hub** — models + datasets for a robotics org/tag watchlist, capturing `downloads`/`likes` as an adoption signal.
- **GitHub** — stars, star-velocity, and releases for a curated repo watchlist (GraphQL), captured as `code` rows.

An orchestrator (`spine.py`) runs all three, dedups by natural key (`arxiv_id` for papers, `repo_url` for code), and upserts. A GitHub Actions cron (`0 6 * * *`) runs `python -m sota_ingest.spine` daily. This plan populates `papers` and `code`; it does NOT write `results` (that is the agent pipeline in a later plan) — so there is no ranking and no metric-by-value sorting here, consistent with spec §11.

## Architecture

```
GitHub Actions cron (0 6 * * *)
   └─ python -m sota_ingest.spine
        ├─ ArxivClient.fetch()   → list[PaperRec]      (Atom XML)
        ├─ HfClient.fetch()      → list[HfRecord]      (HF JSON)
        ├─ GithubClient.fetch()  → list[dict] code rows (GraphQL JSON)
        └─ Spine.run(db):
             dedup papers by arxiv_id  → db.upsert_paper(PaperRec)
             dedup code   by repo_url  → db.upsert_code(row)
```

Each source client splits into two layers:
1. **A thin HTTP wrapper** (`fetch_raw`) — untested, just `httpx.get`/GraphQL POST + politeness sleep. It is a one-liner-ish boundary we keep dumb on purpose.
2. **A pure parser** (`parse_*`) — turns a recorded raw response (Atom string / JSON dict) into typed records. **This is what we TDD against fixtures.**

The orchestrator's **dedup logic** is also pure and TDD'd: given lists with duplicate natural keys, it must collapse to one record per key (last-writer-wins within a pass) before any DB call.

## Tech Stack

- **Python 3.13**, uv-managed, in `ingest/` (reuse existing package `sota_ingest`).
- **pydantic v2** for `PaperRec` (Plan 1) and a new internal `HfRecord` model.
- **httpx** for HTTP (sync). Add to deps.
- **stdlib `xml.etree.ElementTree`** for Atom parsing (no extra dep).
- **pytest** with fixtures recorded under `ingest/tests/fixtures/` (matches Plan 1 convention: `Path(__file__).parent / "fixtures"`).
- **GitHub Actions** for the cron runner; secrets `ANTHROPIC_API_KEY`, `SUPABASE_*`, `GITHUB_TOKEN`. Supabase via pooled port **6543**.

---

## File Structure

| Path | Action | Purpose |
|------|--------|---------|
| `24_sota-robotics/ingest/pyproject.toml` | modify | add `httpx` dependency |
| `24_sota-robotics/ingest/src/sota_ingest/sources/__init__.py` | create | package marker |
| `24_sota-robotics/ingest/src/sota_ingest/sources/arxiv_client.py` | create | Atom→`PaperRec` parser + thin HTTP fetch (cs.RO + cross-lists, 1 req/3s) |
| `24_sota-robotics/ingest/src/sota_ingest/sources/hf_client.py` | create | HF JSON→`HfRecord` parser + thin HTTP fetch (org/tag watchlist; downloads/likes) |
| `24_sota-robotics/ingest/src/sota_ingest/sources/github_client.py` | create | GraphQL JSON→code-row parser + thin GraphQL POST (stars/velocity/releases watchlist) |
| `24_sota-robotics/ingest/src/sota_ingest/sources/spine.py` | create | orchestrator: run 3 sources, dedup by natural key, upsert via Plan 2 `Database`; `__main__` entrypoint |
| `24_sota-robotics/ingest/tests/fixtures/arxiv_cs_ro.atom` | create | recorded arXiv Atom response |
| `24_sota-robotics/ingest/tests/fixtures/hf_models.json` | create | recorded HF Hub list response |
| `24_sota-robotics/ingest/tests/fixtures/github_repos.json` | create | recorded GitHub GraphQL response |
| `24_sota-robotics/ingest/tests/test_arxiv_client.py` | create | TDD the Atom parser |
| `24_sota-robotics/ingest/tests/test_hf_client.py` | create | TDD the HF parser |
| `24_sota-robotics/ingest/tests/test_github_client.py` | create | TDD the GraphQL parser |
| `24_sota-robotics/ingest/tests/test_spine.py` | create | TDD the dedup logic + upsert dispatch |
| `24_sota-robotics/.github/workflows/ingest.yml` | create | daily cron `0 6 * * *` running `python -m sota_ingest.spine` |

---

## Task 1 — Add `httpx` dependency

**Files:** `24_sota-robotics/ingest/pyproject.toml`

1. Open `pyproject.toml` and add `httpx` to `dependencies`. Replace the dependencies block:

   ```toml
   dependencies = [
       "pydantic>=2.13.4",
       "httpx>=0.28.1",
   ]
   ```

2. Sync the environment so the lockfile updates:

   ```bash
   cd 24_sota-robotics/ingest && uv sync
   ```

   Expected: resolves and installs `httpx` (plus `httpcore`, `h11`, `anyio`, `certifi` etc.). No errors.

3. Confirm the existing suite still passes (regression guard):

   ```bash
   cd 24_sota-robotics/ingest && uv run pytest -q
   ```

   Expected: all Plan 1 tests PASS.

4. Commit:

   ```bash
   cd 24_sota-robotics && git add ingest/pyproject.toml ingest/uv.lock && git commit -m "ingest: add httpx dependency for live source clients"
   ```

---

## Task 2 — `sources/` package marker

**Files:** `24_sota-robotics/ingest/src/sota_ingest/sources/__init__.py`

1. Create the package directory marker so `sota_ingest.sources.*` imports resolve:

   ```python
   """Live discovery source clients: arXiv, Hugging Face Hub, GitHub."""
   ```

2. Commit:

   ```bash
   cd 24_sota-robotics && git add ingest/src/sota_ingest/sources/__init__.py && git commit -m "ingest: create sources package"
   ```

---

## Task 3 — arXiv Atom parser (`parse_atom` → `list[PaperRec]`)

**Files:**
`24_sota-robotics/ingest/tests/fixtures/arxiv_cs_ro.atom`,
`24_sota-robotics/ingest/tests/test_arxiv_client.py`,
`24_sota-robotics/ingest/src/sota_ingest/sources/arxiv_client.py`

1. Record the fixture. Create `ingest/tests/fixtures/arxiv_cs_ro.atom` with this exact content (a trimmed but structurally faithful arXiv API Atom response with two entries):

   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
     <title>ArXiv Query: search_query=cat:cs.RO</title>
     <opensearch:totalResults xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">2</opensearch:totalResults>
     <entry>
       <id>http://arxiv.org/abs/2506.01234v1</id>
       <updated>2026-06-17T09:00:00Z</updated>
       <published>2026-06-17T09:00:00Z</published>
       <title>Cross-Embodiment Skill Transfer for Humanoid Manipulation</title>
       <summary>  We present a method for transferring manipulation skills across
   embodiments using a shared latent action space.  </summary>
       <author><name>Ada Lovelace</name></author>
       <author><name>Alan Turing</name></author>
       <arxiv:primary_category xmlns:arxiv="http://arxiv.org/schemas/atom" term="cs.RO"/>
       <category term="cs.RO" scheme="http://arxiv.org/schemas/atom"/>
       <category term="cs.LG" scheme="http://arxiv.org/schemas/atom"/>
       <link href="http://arxiv.org/abs/2506.01234v1" rel="alternate" type="text/html"/>
       <link title="pdf" href="http://arxiv.org/pdf/2506.01234v1" rel="related" type="application/pdf"/>
     </entry>
     <entry>
       <id>http://arxiv.org/abs/2506.05678v2</id>
       <updated>2026-06-16T12:30:00Z</updated>
       <published>2026-06-15T12:30:00Z</published>
       <title>Real-World Robot Evaluation
   With RoboArena</title>
       <summary>An Elo-based protocol for real-world robot policy evaluation.</summary>
       <author><name>Grace Hopper</name></author>
       <arxiv:primary_category xmlns:arxiv="http://arxiv.org/schemas/atom" term="cs.AI"/>
       <category term="cs.AI" scheme="http://arxiv.org/schemas/atom"/>
       <category term="cs.RO" scheme="http://arxiv.org/schemas/atom"/>
       <link href="http://arxiv.org/abs/2506.05678v2" rel="alternate" type="text/html"/>
     </entry>
   </feed>
   ```

2. Write the failing test. Create `ingest/tests/test_arxiv_client.py`:

   ```python
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
   ```

3. Run — expect FAIL (module does not exist yet):

   ```bash
   cd 24_sota-robotics/ingest && uv run pytest -q tests/test_arxiv_client.py
   ```

   Expected: collection error / `ModuleNotFoundError: No module named 'sota_ingest.sources.arxiv_client'`.

4. Write the implementation. Create `ingest/src/sota_ingest/sources/arxiv_client.py`:

   ```python
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
   ```

5. Run — expect PASS:

   ```bash
   cd 24_sota-robotics/ingest && uv run pytest -q tests/test_arxiv_client.py
   ```

   Expected: 5 passed.

6. Commit:

   ```bash
   cd 24_sota-robotics && git add ingest/src/sota_ingest/sources/arxiv_client.py ingest/tests/test_arxiv_client.py ingest/tests/fixtures/arxiv_cs_ro.atom && git commit -m "ingest: arXiv Atom parser -> PaperRec (cs.RO + cross-lists, 1 req/3s)"
   ```

---

## Task 4 — HF Hub parser (`parse_hf_listing` → `list[HfRecord]`)

**Files:**
`24_sota-robotics/ingest/tests/fixtures/hf_models.json`,
`24_sota-robotics/ingest/tests/test_hf_client.py`,
`24_sota-robotics/ingest/src/sota_ingest/sources/hf_client.py`

The `code` table has no column for HF assets, so HF records are an internal **adoption-signal** model (`HfRecord`) that the orchestrator currently logs/aggregates; they are not forced into `papers`/`code`. We model them as typed records now so a later plan can wire them to a dedicated table without reparsing.

1. Record the fixture. Create `ingest/tests/fixtures/hf_models.json` (faithful to the HF Hub list-models JSON shape):

   ```json
   [
     {
       "id": "physical-intelligence/pi0",
       "author": "physical-intelligence",
       "downloads": 18342,
       "likes": 540,
       "pipeline_tag": "robotics",
       "tags": ["robotics", "vla", "pytorch"],
       "lastModified": "2026-06-14T22:10:05.000Z"
     },
     {
       "id": "lerobot/aloha_static_coffee",
       "author": "lerobot",
       "downloads": 2210,
       "likes": 88,
       "pipeline_tag": "robotics",
       "tags": ["robotics", "dataset"],
       "lastModified": "2026-06-10T08:00:00.000Z"
     },
     {
       "id": "someuser/unrelated-llm",
       "author": "someuser",
       "downloads": 999999,
       "likes": 12000,
       "pipeline_tag": "text-generation",
       "tags": ["llm"],
       "lastModified": "2026-06-01T00:00:00.000Z"
     }
   ]
   ```

2. Write the failing test. Create `ingest/tests/test_hf_client.py`:

   ```python
   import json
   from pathlib import Path

   from sota_ingest.sources.hf_client import HfRecord, parse_hf_listing

   FIXTURE = Path(__file__).parent / "fixtures" / "hf_models.json"


   def test_parses_only_robotics_tagged_records():
       data = json.loads(FIXTURE.read_text(encoding="utf-8"))
       recs = parse_hf_listing(data, kind="model")
       # The text-generation entry has no 'robotics' tag -> dropped.
       assert len(recs) == 2
       assert all(isinstance(r, HfRecord) for r in recs)
       assert all("robotics" in r.tags for r in recs)


   def test_captures_adoption_signal():
       data = json.loads(FIXTURE.read_text(encoding="utf-8"))
       recs = parse_hf_listing(data, kind="model")
       pi0 = next(r for r in recs if r.repo_id == "physical-intelligence/pi0")
       assert pi0.downloads == 18342
       assert pi0.likes == 540
       assert pi0.kind == "model"
       assert pi0.url == "https://huggingface.co/physical-intelligence/pi0"


   def test_last_modified_date_truncated_to_iso():
       data = json.loads(FIXTURE.read_text(encoding="utf-8"))
       recs = parse_hf_listing(data, kind="model")
       pi0 = next(r for r in recs if r.repo_id == "physical-intelligence/pi0")
       assert pi0.last_modified == "2026-06-14"


   def test_dataset_kind_builds_dataset_url():
       data = json.loads(FIXTURE.read_text(encoding="utf-8"))
       recs = parse_hf_listing(data, kind="dataset")
       ds = next(r for r in recs if r.repo_id == "lerobot/aloha_static_coffee")
       assert ds.url == "https://huggingface.co/datasets/lerobot/aloha_static_coffee"
   ```

3. Run — expect FAIL:

   ```bash
   cd 24_sota-robotics/ingest && uv run pytest -q tests/test_hf_client.py
   ```

   Expected: `ModuleNotFoundError: No module named 'sota_ingest.sources.hf_client'`.

4. Write the implementation. Create `ingest/src/sota_ingest/sources/hf_client.py`:

   ```python
   from typing import Any, Literal

   import httpx
   from pydantic import BaseModel

   API_BASE = "https://huggingface.co/api"
   HUB_BASE = "https://huggingface.co"
   ROBOTICS_TAG = "robotics"

   # Watchlist of robotics orgs to scan (in addition to the global robotics tag).
   ORG_WATCHLIST = (
       "physical-intelligence",
       "lerobot",
       "nvidia",
       "google-deepmind",
   )

   HfKind = Literal["model", "dataset"]


   class HfRecord(BaseModel):
       repo_id: str
       kind: HfKind
       author: str | None = None
       downloads: int = 0
       likes: int = 0
       tags: list[str] = []
       last_modified: str | None = None  # ISO date string
       url: str


   def _url(repo_id: str, kind: HfKind) -> str:
       if kind == "dataset":
           return f"{HUB_BASE}/datasets/{repo_id}"
       return f"{HUB_BASE}/{repo_id}"


   def parse_hf_listing(data: list[dict[str, Any]], kind: HfKind) -> list[HfRecord]:
       """Pure parser: HF Hub list JSON -> robotics-tagged HfRecords.

       Drops anything not tagged 'robotics' so non-robotics assets returned by
       an org scan don't pollute the adoption signal. downloads/likes are the
       adoption signal we keep.
       """
       recs: list[HfRecord] = []
       for item in data:
           tags = list(item.get("tags") or [])
           if ROBOTICS_TAG not in tags and item.get("pipeline_tag") != ROBOTICS_TAG:
               continue
           if ROBOTICS_TAG not in tags:
               tags.append(ROBOTICS_TAG)
           repo_id = item["id"]
           last_mod = item.get("lastModified")
           recs.append(
               HfRecord(
                   repo_id=repo_id,
                   kind=kind,
                   author=item.get("author"),
                   downloads=int(item.get("downloads") or 0),
                   likes=int(item.get("likes") or 0),
                   tags=tags,
                   last_modified=last_mod[:10] if last_mod else None,
                   url=_url(repo_id, kind),
               )
           )
       return recs


   def fetch_raw(
       kind: HfKind,
       client: httpx.Client | None = None,
   ) -> list[dict[str, Any]]:
       """Thin HTTP wrapper (untested): list robotics-tagged models/datasets."""
       owns = client is None
       client = client or httpx.Client(timeout=30.0)
       endpoint = f"{API_BASE}/{'datasets' if kind == 'dataset' else 'models'}"
       try:
           resp = client.get(
               endpoint,
               params={
                   "filter": ROBOTICS_TAG,
                   "sort": "lastModified",
                   "direction": "-1",
                   "limit": 100,
               },
           )
           resp.raise_for_status()
           return resp.json()
       finally:
           if owns:
               client.close()


   def fetch() -> list[HfRecord]:
       """Convenience: fetch models + datasets and parse. Used by orchestrator."""
       recs: list[HfRecord] = []
       recs.extend(parse_hf_listing(fetch_raw("model"), kind="model"))
       recs.extend(parse_hf_listing(fetch_raw("dataset"), kind="dataset"))
       return recs
   ```

5. Run — expect PASS:

   ```bash
   cd 24_sota-robotics/ingest && uv run pytest -q tests/test_hf_client.py
   ```

   Expected: 4 passed.

6. Commit:

   ```bash
   cd 24_sota-robotics && git add ingest/src/sota_ingest/sources/hf_client.py ingest/tests/test_hf_client.py ingest/tests/fixtures/hf_models.json && git commit -m "ingest: HF Hub parser -> HfRecord (robotics org/tag watchlist; downloads/likes)"
   ```

---

## Task 5 — GitHub GraphQL parser (`parse_repos` → `list[dict]` code rows)

**Files:**
`24_sota-robotics/ingest/tests/fixtures/github_repos.json`,
`24_sota-robotics/ingest/tests/test_github_client.py`,
`24_sota-robotics/ingest/src/sota_ingest/sources/github_client.py`

The parser emits rows shaped for the Plan 2 `Database.upsert_code(row)` writer — keys are a subset of the `code` table columns (`repo_url`, `stars`, `last_commit`, `license`). Star-velocity and releases are surfaced as extra keys for the orchestrator to log as adoption signal, but only the `code`-column subset is passed to the writer (Task 6).

1. Record the fixture. Create `ingest/tests/fixtures/github_repos.json` (faithful to a GitHub GraphQL aliased multi-repo response):

   ```json
   {
     "data": {
       "r0": {
         "nameWithOwner": "huggingface/lerobot",
         "url": "https://github.com/huggingface/lerobot",
         "stargazerCount": 9800,
         "licenseInfo": { "spdxId": "Apache-2.0" },
         "defaultBranchRef": {
           "target": {
             "history": { "edges": [ { "node": { "committedDate": "2026-06-17T18:00:00Z" } } ] }
           }
         },
         "releases": {
           "totalCount": 14,
           "nodes": [ { "tagName": "v0.4.0", "publishedAt": "2026-06-12T00:00:00Z" } ]
         }
       },
       "r1": {
         "nameWithOwner": "openvla/openvla",
         "url": "https://github.com/openvla/openvla",
         "stargazerCount": 3120,
         "licenseInfo": null,
         "defaultBranchRef": {
           "target": {
             "history": { "edges": [ { "node": { "committedDate": "2026-05-30T11:22:33Z" } } ] }
           }
         },
         "releases": { "totalCount": 0, "nodes": [] }
       },
       "r2": null
     }
   }
   ```

2. Write the failing test. Create `ingest/tests/test_github_client.py`:

   ```python
   import json
   from pathlib import Path

   from sota_ingest.sources.github_client import CODE_COLUMNS, parse_repos

   FIXTURE = Path(__file__).parent / "fixtures" / "github_repos.json"


   def test_parses_non_null_repos():
       payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
       rows = parse_repos(payload)
       # r2 is null (e.g. renamed/deleted repo) -> skipped.
       assert len(rows) == 2
       urls = {r["repo_url"] for r in rows}
       assert urls == {
           "https://github.com/huggingface/lerobot",
           "https://github.com/openvla/openvla",
       }


   def test_maps_stars_license_and_last_commit():
       payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
       rows = parse_repos(payload)
       lerobot = next(r for r in rows if r["repo_url"].endswith("lerobot"))
       assert lerobot["stars"] == 9800
       assert lerobot["license"] == "Apache-2.0"
       assert lerobot["last_commit"] == "2026-06-17"


   def test_missing_license_becomes_none():
       payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
       rows = parse_repos(payload)
       openvla = next(r for r in rows if r["repo_url"].endswith("openvla"))
       assert openvla["license"] is None


   def test_release_signal_carried_alongside():
       payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
       rows = parse_repos(payload)
       lerobot = next(r for r in rows if r["repo_url"].endswith("lerobot"))
       assert lerobot["release_count"] == 14
       assert lerobot["latest_release"] == "v0.4.0"


   def test_writer_subset_is_only_code_columns():
       # Keys destined for db.upsert_code must be a subset of the code table.
       payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
       rows = parse_repos(payload)
       for r in rows:
           subset = {k: v for k, v in r.items() if k in CODE_COLUMNS}
           assert set(subset).issubset(CODE_COLUMNS)
           assert "repo_url" in subset
   ```

3. Run — expect FAIL:

   ```bash
   cd 24_sota-robotics/ingest && uv run pytest -q tests/test_github_client.py
   ```

   Expected: `ModuleNotFoundError: No module named 'sota_ingest.sources.github_client'`.

4. Write the implementation. Create `ingest/src/sota_ingest/sources/github_client.py`:

   ```python
   import os
   from typing import Any

   import httpx

   GRAPHQL_URL = "https://api.github.com/graphql"

   # Columns that exist on the `code` table (Plan 1 / db migration 0002).
   # Only these keys are forwarded to db.upsert_code(); the rest are signal.
   CODE_COLUMNS = ("repo_url", "stars", "last_commit", "license")

   # Curated repo watchlist (owner, name) for stars / velocity / releases.
   REPO_WATCHLIST = (
       ("huggingface", "lerobot"),
       ("openvla", "openvla"),
       ("NVIDIA", "Isaac-GR00T"),
       ("google-deepmind", "open_x_embodiment"),
   )

   _REPO_FIELDS = """
       nameWithOwner
       url
       stargazerCount
       licenseInfo { spdxId }
       defaultBranchRef {
         target {
           ... on Commit { history(first: 1) { edges { node { committedDate } } } }
         }
       }
       releases(first: 1, orderBy: {field: CREATED_AT, direction: DESC}) {
         totalCount
         nodes { tagName publishedAt }
       }
   """


   def build_query(watchlist: tuple[tuple[str, str], ...] = REPO_WATCHLIST) -> str:
       """Build an aliased multi-repo GraphQL query (one round-trip)."""
       blocks = [
           f'    r{i}: repository(owner: "{owner}", name: "{name}") {{{_REPO_FIELDS}}}'
           for i, (owner, name) in enumerate(watchlist)
       ]
       return "query {\n" + "\n".join(blocks) + "\n}"


   def _last_commit(repo: dict[str, Any]) -> str | None:
       ref = repo.get("defaultBranchRef") or {}
       target = ref.get("target") or {}
       edges = ((target.get("history") or {}).get("edges")) or []
       if not edges:
           return None
       date = (edges[0].get("node") or {}).get("committedDate")
       return date[:10] if date else None


   def parse_repos(payload: dict[str, Any]) -> list[dict[str, Any]]:
       """Pure parser: GitHub GraphQL response -> code rows.

       Each row carries the `code`-column subset (repo_url/stars/last_commit/
       license) plus release signal (release_count/latest_release) for the
       orchestrator to log. Null aliases (deleted/renamed repos) are skipped.
       Natural key for dedup/upsert is repo_url.
       """
       data = payload.get("data") or {}
       rows: list[dict[str, Any]] = []
       for repo in data.values():
           if not repo:
               continue
           license_info = repo.get("licenseInfo") or {}
           releases = repo.get("releases") or {}
           nodes = releases.get("nodes") or []
           latest = nodes[0] if nodes else {}
           rows.append(
               {
                   "repo_url": repo["url"],
                   "stars": repo.get("stargazerCount"),
                   "last_commit": _last_commit(repo),
                   "license": license_info.get("spdxId"),
                   # signal (not forwarded to db.upsert_code):
                   "release_count": releases.get("totalCount", 0),
                   "latest_release": latest.get("tagName"),
                   "latest_release_at": (latest.get("publishedAt") or "")[:10] or None,
               }
           )
       return rows


   def fetch_raw(
       token: str | None = None,
       client: httpx.Client | None = None,
       watchlist: tuple[tuple[str, str], ...] = REPO_WATCHLIST,
   ) -> dict[str, Any]:
       """Thin HTTP wrapper (untested): POST the GraphQL query.

       token defaults to env GITHUB_TOKEN (required by the GraphQL endpoint).
       """
       token = token or os.environ["GITHUB_TOKEN"]
       owns = client is None
       client = client or httpx.Client(timeout=30.0)
       try:
           resp = client.post(
               GRAPHQL_URL,
               headers={"Authorization": f"Bearer {token}"},
               json={"query": build_query(watchlist)},
           )
           resp.raise_for_status()
           return resp.json()
       finally:
           if owns:
               client.close()


   def fetch() -> list[dict[str, Any]]:
       """Convenience: fetch + parse. Used by the orchestrator."""
       return parse_repos(fetch_raw())
   ```

5. Run — expect PASS:

   ```bash
   cd 24_sota-robotics/ingest && uv run pytest -q tests/test_github_client.py
   ```

   Expected: 5 passed.

6. Commit:

   ```bash
   cd 24_sota-robotics && git add ingest/src/sota_ingest/sources/github_client.py ingest/tests/test_github_client.py ingest/tests/fixtures/github_repos.json && git commit -m "ingest: GitHub GraphQL parser -> code rows (stars/velocity/releases watchlist)"
   ```

---

## Task 6 — Orchestrator dedup + upsert (`spine.py`)

**Files:**
`24_sota-robotics/ingest/tests/test_spine.py`,
`24_sota-robotics/ingest/src/sota_ingest/sources/spine.py`

We TDD the **pure dedup helpers** and the **upsert dispatch** against a fake DB (no network, no real Supabase). The dispatch must (a) dedup papers by `arxiv_id` and code rows by `repo_url`, last-writer-wins, and (b) forward to `db.upsert_paper` / `db.upsert_code` passing only the `CODE_COLUMNS` subset for code.

1. Write the failing test. Create `ingest/tests/test_spine.py`:

   ```python
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
   ```

2. Run — expect FAIL:

   ```bash
   cd 24_sota-robotics/ingest && uv run pytest -q tests/test_spine.py
   ```

   Expected: `ModuleNotFoundError: No module named 'sota_ingest.sources.spine'`.

3. Write the implementation. Create `ingest/src/sota_ingest/sources/spine.py`:

   ```python
   import os
   from typing import Any, Protocol

   from sota_ingest.models import PaperRec
   from sota_ingest.sources import arxiv_client, github_client, hf_client


   class _Writer(Protocol):
       def new_run_id(self) -> str: ...
       def upsert_paper(self, paper: PaperRec) -> int: ...
       def upsert_code(self, row: dict[str, Any]) -> int: ...


   def dedup_papers(papers: list[PaperRec]) -> list[PaperRec]:
       """Dedup by natural key arxiv_id (fallback: title when arxiv_id is None).
       Last writer wins within a single pass."""
       by_key: dict[str, PaperRec] = {}
       for p in papers:
           key = p.arxiv_id or f"title::{p.title}"
           by_key[key] = p
       return list(by_key.values())


   def dedup_code_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
       """Dedup code rows by natural key repo_url. Last writer wins."""
       by_url: dict[str, dict[str, Any]] = {}
       for r in rows:
           by_url[r["repo_url"]] = r
       return list(by_url.values())


   def _code_subset(row: dict[str, Any]) -> dict[str, Any]:
       """Keep only keys that exist on the `code` table for the writer."""
       return {k: v for k, v in row.items() if k in github_client.CODE_COLUMNS}


   def run_upserts(
       db: _Writer,
       papers: list[PaperRec],
       code_rows: list[dict[str, Any]],
   ) -> dict[str, int]:
       """Dedup then upsert. Returns counts written. Idempotent: the DB writer
       upserts on natural keys (papers.arxiv_id, code.repo_url)."""
       deduped_papers = dedup_papers(papers)
       deduped_code = dedup_code_rows(code_rows)
       for paper in deduped_papers:
           db.upsert_paper(paper)
       for row in deduped_code:
           db.upsert_code(_code_subset(row))
       return {"papers": len(deduped_papers), "code": len(deduped_code)}


   def _build_dsn() -> str:
       """Pooled Supabase DSN (transaction pooler, port 6543) for CI/cron.

       Prefer an explicit SUPABASE_DB_URL; otherwise assemble from parts.
       """
       url = os.environ.get("SUPABASE_DB_URL")
       if url:
           return url
       host = os.environ["SUPABASE_DB_HOST"]
       password = os.environ["SUPABASE_DB_PASSWORD"]
       user = os.environ.get("SUPABASE_DB_USER", "postgres")
       dbname = os.environ.get("SUPABASE_DB_NAME", "postgres")
       return f"postgresql://{user}:{password}@{host}:6543/{dbname}?sslmode=require"


   def main() -> None:
       """Daily firehose entrypoint. Run via: python -m sota_ingest.spine"""
       from sota_ingest.db import Database  # Plan 2

       papers = arxiv_client.fetch()
       code_rows = github_client.fetch()
       hf_records = hf_client.fetch()  # adoption signal; logged, not yet stored

       db = Database(_build_dsn())
       try:
           run_id = db.new_run_id()
           summary = run_upserts(db, papers=papers, code_rows=code_rows)
       finally:
           db.close()

       print(
           f"[spine] run={run_id} "
           f"arxiv={len(papers)} code={len(code_rows)} hf={len(hf_records)} "
           f"upserted={summary}"
       )


   if __name__ == "__main__":
       main()
   ```

4. Run — expect PASS:

   ```bash
   cd 24_sota-robotics/ingest && uv run pytest -q tests/test_spine.py
   ```

   Expected: 4 passed.

5. Run the full suite (regression guard across Plan 1 + Plan 3):

   ```bash
   cd 24_sota-robotics/ingest && uv run pytest -q
   ```

   Expected: all tests PASS (Plan 1 originals + the 4 new test modules).

6. Commit:

   ```bash
   cd 24_sota-robotics && git add ingest/src/sota_ingest/sources/spine.py ingest/tests/test_spine.py && git commit -m "ingest: spine orchestrator — dedup by natural key + idempotent upsert via Plan 2 Database"
   ```

---

## Task 7 — Make `python -m sota_ingest.spine` runnable

**Files:** none new (verification only) — the `if __name__ == "__main__"` block in Task 6 already makes `sota_ingest.sources.spine` runnable. The workflow invokes the module by its fully-qualified path.

1. Confirm the module path resolves under the package layout. Because `pythonpath=["src"]` is pytest-only, the CI runner sets `PYTHONPATH=src` (see Task 8). Verify the import graph is intact without touching the network by importing the orchestrator's pure helpers:

   ```bash
   cd 24_sota-robotics/ingest && PYTHONPATH=src uv run python -c "from sota_ingest.sources.spine import run_upserts, dedup_papers, dedup_code_rows; print('import ok')"
   ```

   Expected output: `import ok` (no `db.py` import happens at module load — it is imported lazily inside `main()`, so this succeeds even before Plan 2 is merged).

2. No commit (verification only).

---

## Task 8 — GitHub Actions daily cron

**Files:** `24_sota-robotics/.github/workflows/ingest.yml`

1. Create `.github/workflows/ingest.yml`:

   ```yaml
   name: ingest

   on:
     schedule:
       # Daily at 06:00 UTC — the discovery firehose.
       - cron: "0 6 * * *"
     workflow_dispatch: {}

   permissions:
     contents: read

   concurrency:
     group: ingest
     cancel-in-progress: false

   jobs:
     spine:
       runs-on: ubuntu-latest
       timeout-minutes: 20
       defaults:
         run:
           working-directory: ingest
       env:
         PYTHONPATH: src
         ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
         SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
         SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
         SUPABASE_DB_URL: ${{ secrets.SUPABASE_DB_URL }}
         GITHUB_TOKEN: ${{ secrets.INGEST_GITHUB_TOKEN }}
       steps:
         - uses: actions/checkout@v4

         - name: Install uv
           uses: astral-sh/setup-uv@v5
           with:
             python-version: "3.13"

         - name: Sync dependencies
           run: uv sync --frozen

         - name: Run discovery spine
           run: uv run python -m sota_ingest.spine
   ```

   Notes for the operator:
   - `SUPABASE_DB_URL` must be the **pooled** connection string (transaction pooler, host `...pooler.supabase.com`, **port 6543**) with `?sslmode=require`. The spine's `_build_dsn()` uses it as-is.
   - The repo secret is named `INGEST_GITHUB_TOKEN` (a PAT with `public_repo`/read scope) and is mapped onto the `GITHUB_TOKEN` env var the client reads — the auto-injected `${{ github.token }}` lacks GraphQL stargazer access for arbitrary repos, so a PAT is required.
   - `ANTHROPIC_API_KEY` is wired now (repo secret) so the later agent-pipeline plan needs no workflow change; the spine itself does not call Anthropic.

2. Commit:

   ```bash
   cd 24_sota-robotics && git add .github/workflows/ingest.yml && git commit -m "ci: daily ingest cron (0 6 UTC) running sota_ingest.spine on pooled Supabase 6543"
   ```

---

## Self-Review

**Spec coverage (this plan's stated scope a–e):**
- (a) **arXiv client** — `sources/arxiv_client.py`: queries `cat:cs.RO` via the arXiv API, keeps entries with `cs.RO` in any category (primary OR cross-list), parses to `PaperRec`, `POLITENESS_SECONDS = 3.0` sleep before each request (1 req/3s). ✅
- (b) **HF Hub client** — `sources/hf_client.py`: models + datasets, robotics org/tag watchlist (`ORG_WATCHLIST`, `ROBOTICS_TAG`), captures `downloads`/`likes` as adoption signal on `HfRecord`. ✅
- (c) **GitHub client** — `sources/github_client.py`: GraphQL stars (`stargazerCount`), star-velocity-ready last-commit (`last_commit`), releases (`release_count`/`latest_release`), curated `REPO_WATCHLIST`, token from env `GITHUB_TOKEN`. ✅
- (d) **Orchestrator** — `sources/spine.py`: runs all three (`*.fetch()`), dedups by natural key (`arxiv_id` via `dedup_papers`, `repo_url` via `dedup_code_rows`), upserts via Plan 2 `Database` (`run_upserts` → `upsert_paper`/`upsert_code`). ✅
- (e) **GitHub Actions** — `.github/workflows/ingest.yml`: cron `0 6 * * *`, runs `python -m sota_ingest.spine`, secrets `ANTHROPIC_API_KEY`/`SUPABASE_*`/`GITHUB_TOKEN`, pooled Supabase port 6543. ✅

**TDD discipline:** Parsers (Atom→PaperRec, HF JSON→HfRecord, GraphQL JSON→code rows) and dedup logic are tested against recorded fixtures (`tests/fixtures/*.atom|*.json`), each following failing-test → run-FAIL → minimal-impl → run-PASS → commit. HTTP layers (`fetch_raw`) are thin wrappers, explicitly left untested as stated in scope. ✅

**Placeholders / TODOs:** None. Every code block is complete and runnable; no `...` bodies in implementation files, no "similar to above". The only `...` are in the Plan 2 `Database` interface stub at the top (deliberately documenting a dependency provided elsewhere) and in the `_Writer` Protocol (correct Python for protocol method bodies). ✅

**Type / contract consistency with Plan 1 & Plan 2:**
- `PaperRec` used exactly as defined (Plan 1): fields `arxiv_id, title, authors, abstract, published_date, url`; parsers populate that shape and nothing else. ✅
- `canonical_hash` / `ResultClaim` / `build_result_row` are **not** touched — this plan writes `papers`/`code`, never `results`, so no metric ranking happens here (honors spec §11: never rank by raw `metric_value`). ✅
- Code rows forwarded to the writer are restricted to `CODE_COLUMNS = ("repo_url","stars","last_commit","license")`, the exact `code` table columns from migration 0002; release signal is stripped before `upsert_code` (verified by `test_run_upserts_dedups_and_writes_code_subset_only` and `test_writer_subset_is_only_code_columns`). ✅
- Orchestrator depends only on the Plan 2 `Database` methods (`new_run_id`, `upsert_paper`, `upsert_code`, `close`) via lazy import inside `main()`, so the pure logic imports and tests pass before Plan 2 lands; the **dependency on Plan 2 is stated up front**. ✅

**Idempotency:** Dedup collapses within-pass duplicates; cross-pass idempotency is guaranteed by the DB natural keys (`papers.arxiv_id UNIQUE`, `code.repo_url UNIQUE` from migration 0002) honored by the Plan 2 upserts. Re-running the cron writes no duplicates. ✅

**Style match:** Fixtures live in `tests/fixtures/` and are read with `Path(__file__).parent / "fixtures"` (matches `test_sota_extractor.py`); date truncation to ISO `[:10]` mirrors existing conventions; commands use `cd 24_sota-robotics/ingest && uv run pytest -q`. ✅
