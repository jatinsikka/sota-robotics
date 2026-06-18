"""Pure parsers for the four community 'awesome-lists' we cold-start from.

All four are CC-BY-SA; we record attribution in db/ATTRIBUTION.md and stamp
each derived paper/code record's provenance in db.py. This module does NO I/O:
it turns raw markdown into AwesomeRecord objects only.
"""
import re
from dataclasses import dataclass

from sota_ingest.models import PaperRec

# --- Source registry (raw GitHub README URLs; CC-BY-SA-4.0) -----------------


@dataclass(frozen=True)
class AwesomeSource:
    name: str
    raw_url: str
    license: str


SOURCES: tuple[AwesomeSource, ...] = (
    AwesomeSource(
        "Awesome-Embodied-AI",
        "https://raw.githubusercontent.com/wadeKeith/Awesome-Embodied-AI/main/README.md",
        "CC-BY-SA-4.0",
    ),
    AwesomeSource(
        "awesome-embodied-vla-va-vln",
        "https://raw.githubusercontent.com/jonyzhang2023/awesome-embodied-vla-va-vln/main/README.md",
        "CC-BY-SA-4.0",
    ),
    AwesomeSource(
        "awesome-physical-ai",
        "https://raw.githubusercontent.com/natnew/awesome-physical-ai/main/README.md",
        "CC-BY-SA-4.0",
    ),
    AwesomeSource(
        "Awesome-Embodied-Robotics-and-Agent",
        "https://raw.githubusercontent.com/zchoi/Awesome-Embodied-Robotics-and-Agent/main/README.md",
        "CC-BY-SA-4.0",
    ),
)


# --- Output record ----------------------------------------------------------


@dataclass
class AwesomeRecord:
    paper: PaperRec
    repo_url: str | None
    domain_slug: str | None
    source_url: str


# --- Section header -> our 8 domain slugs -----------------------------------

# Each (keyword tuple) -> domain slug. Matched case-insensitively as a
# substring of the section header, first match wins. Order matters: more
# specific phrases must precede generic ones.
_SECTION_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("world-action", "world action", "action-conditioned"), "world-action-models"),
    (("world model",), "world-models"),
    (("locomotion", "whole-body", "whole body", "legged", "bipedal"), "locomotion-wbc"),
    (("sim-to-real", "sim2real", "domain randomization", "real-world rl"), "sim2real-rl"),
    (("navigation", "vln"), "navigation-vln"),
    (("perception", "grasp", "pose estimation", "3d vision"), "robot-perception"),
    (
        ("demonstration", "imitation", "teleop", "dataset", "cross-embodiment", "learning from"),
        "lfd-robot-data",
    ),
    (
        ("manipulation", "vla", "vision-language-action", "dexterous", "bimanual", "humanoid"),
        "humanoid-vla-manip",
    ),
)


def map_section_to_domain(header: str) -> str | None:
    """Map an awesome-list section header to one of our 8 domain slugs."""
    h = (header or "").lower()
    for keywords, slug in _SECTION_RULES:
        if any(kw in h for kw in keywords):
            return slug
    return None


# --- Markdown parsing -------------------------------------------------------

_HEADER_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
_LIST_ITEM_RE = re.compile(r"^\s*[-*+]\s+(.*\S.*)$")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_ARXIV_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", re.IGNORECASE)
_REPO_RE = re.compile(r"https?://(?:www\.)?github\.com/[^)\s\]]+", re.IGNORECASE)


def _arxiv_id(url: str) -> str | None:
    m = _ARXIV_RE.search(url)
    return m.group(1) if m else None


def parse_awesome_markdown(md: str, source_url: str) -> list[AwesomeRecord]:
    """Parse one awesome-list README into AwesomeRecords.

    Rules:
      - Track the current section header; map it to a domain slug.
      - Each list item that contains at least one markdown link becomes a
        record. The first arxiv link (or first link) is the paper; the first
        github link anywhere in the item is the repo.
      - Prose lines without links are ignored.
    """
    records: list[AwesomeRecord] = []
    current_domain: str | None = None

    for line in md.splitlines():
        header = _HEADER_RE.match(line)
        if header:
            current_domain = map_section_to_domain(header.group(1))
            continue

        item = _LIST_ITEM_RE.match(line)
        if not item:
            continue
        text = item.group(1)
        links = _MD_LINK_RE.findall(text)  # [(label, url), ...]
        if not links:
            continue

        # Pick the paper link: prefer an arxiv link, else the first link.
        paper_label, paper_url = links[0]
        for label, url in links:
            if _arxiv_id(url):
                paper_label, paper_url = label, url
                break

        # Repo: first github URL anywhere in the raw item text.
        repo_match = _REPO_RE.search(text)
        repo_url = repo_match.group(0).rstrip(").]") if repo_match else None
        # Don't let the paper link double as the repo.
        if repo_url == paper_url:
            repo_url = None

        arxiv = _arxiv_id(paper_url)
        normalized_url = (
            f"https://arxiv.org/abs/{arxiv}" if arxiv else paper_url
        )
        records.append(
            AwesomeRecord(
                paper=PaperRec(
                    arxiv_id=arxiv,
                    title=paper_label.strip(),
                    url=normalized_url,
                ),
                repo_url=repo_url,
                domain_slug=current_domain,
                source_url=source_url,
            )
        )
    return records
