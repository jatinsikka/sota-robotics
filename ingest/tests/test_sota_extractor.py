import json
from pathlib import Path

from sota_ingest.sota_extractor import parse_evaluation_tables
from sota_ingest.models import Origin, VerificationStatus

FIXTURE = Path(__file__).parent / "fixtures" / "pwc_eval_table.json"


def test_parses_rows_into_result_claims():
    data = json.loads(FIXTURE.read_text())
    claims = parse_evaluation_tables(data)
    assert len(claims) == 2
    oft = next(c for c in claims if c.method_slug == "openvla-oft")
    assert oft.benchmark_slug == "libero"
    assert oft.metric == "success_rate"
    assert oft.metric_value == 97.1
    assert oft.source_url == "https://arxiv.org/abs/2502.19645"


def test_archive_rows_are_held_not_published():
    # PWC numbers are stale/self-reported -> must NOT auto-publish.
    data = json.loads(FIXTURE.read_text())
    claims = parse_evaluation_tables(data)
    assert all(c.verification_status == VerificationStatus.HELD for c in claims)
    assert all(c.origin == Origin.PUBLIC_REPRODUCIBLE for c in claims)


def test_non_numeric_metric_becomes_none():
    data = [
        {
            "task": "T",
            "datasets": [
                {
                    "dataset": "B",
                    "sota": {
                        "metrics": ["Score"],
                        "rows": [
                            {
                                "model_name": "M",
                                "metrics": {"Score": "N/A"},
                                "paper_url": "u",
                                "code_links": [],
                            }
                        ],
                    },
                }
            ],
        }
    ]
    claims = parse_evaluation_tables(data)
    assert claims[0].metric_value is None
