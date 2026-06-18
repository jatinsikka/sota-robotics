# tests/test_awesome_lists.py
from sota_ingest.awesome_lists import (
    AwesomeRecord,
    map_section_to_domain,
    parse_awesome_markdown,
    SOURCES,
)
from sota_ingest.models import PaperRec


def test_section_header_maps_to_domain_slug():
    assert map_section_to_domain("Manipulation") == "humanoid-vla-manip"
    assert map_section_to_domain("Locomotion and Whole-Body Control") == "locomotion-wbc"
    assert map_section_to_domain("World Models") == "world-models"
    assert map_section_to_domain("Sim-to-Real") == "sim2real-rl"
    assert map_section_to_domain("Navigation") == "navigation-vln"


def test_unmappable_section_returns_none():
    assert map_section_to_domain("Misc") is None
    assert map_section_to_domain("Acknowledgements") is None


def test_parse_extracts_papers_repos_and_domain(fixtures_dir):
    md = (fixtures_dir / "awesome_embodied_ai.md").read_text()
    records = parse_awesome_markdown(md, source_url="https://example.com/list")
    by_arxiv = {r.paper.arxiv_id: r for r in records if r.paper.arxiv_id}

    # OpenVLA: arxiv id parsed, repo captured, domain = manipulation
    openvla = by_arxiv["2406.09246"]
    assert isinstance(openvla.paper, PaperRec)
    assert openvla.paper.title.startswith("OpenVLA")
    assert openvla.paper.url == "https://arxiv.org/abs/2406.09246"
    assert openvla.repo_url == "https://github.com/openvla/openvla"
    assert openvla.domain_slug == "humanoid-vla-manip"

    # pi0: no code link -> repo_url is None
    pi0 = by_arxiv["2410.24164"]
    assert pi0.repo_url is None

    # Locomotion item picks up the [[github]] style link + locomotion domain
    ntp = by_arxiv["2402.19469"]
    assert ntp.repo_url == "https://github.com/facebookresearch/humanoid"
    assert ntp.domain_slug == "locomotion-wbc"


def test_prose_lines_without_links_are_ignored(fixtures_dir):
    md = (fixtures_dir / "awesome_embodied_ai.md").read_text()
    records = parse_awesome_markdown(md, source_url="x")
    # the "Misc" prose line is not a link -> excluded
    assert all(r.paper.url is not None for r in records)
    assert all("Not a link" not in (r.paper.title or "") for r in records)


def test_second_list_parses_world_and_sim2real(fixtures_dir):
    md = (fixtures_dir / "awesome_vla.md").read_text()
    records = parse_awesome_markdown(md, source_url="x")
    domains = {r.domain_slug for r in records}
    assert "world-models" in domains
    assert "sim2real-rl" in domains
    dreureka = next(r for r in records if r.paper.arxiv_id == "2406.01967")
    assert dreureka.repo_url == "https://github.com/eureka-research/DrEureka"


def test_sources_registry_has_four_lists():
    # The four awesome-lists named in the Phase-0 spec.
    assert len(SOURCES) == 4
    urls = " ".join(s.raw_url for s in SOURCES)
    assert "wadeKeith/Awesome-Embodied-AI" in urls
    assert "jonyzhang2023/awesome-embodied-vla-va-vln" in urls
    assert "natnew/awesome-physical-ai" in urls
    assert "zchoi/Awesome-Embodied-Robotics-and-Agent" in urls
    assert all(s.license == "CC-BY-SA-4.0" for s in SOURCES)
