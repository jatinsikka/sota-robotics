import json
from types import SimpleNamespace

from sota_ingest.agent.batch import (
    MODEL,
    build_batch_requests,
    collect_batch_results,
    paper_custom_id,
)
from sota_ingest.models import PaperRec


def _papers() -> list[PaperRec]:
    return [
        PaperRec(arxiv_id="2502.19645", title="A", url="https://arxiv.org/abs/2502.19645"),
        PaperRec(arxiv_id="2410.24164", title="B", url="https://arxiv.org/abs/2410.24164"),
    ]


def test_build_requests_one_per_paper_with_cached_prefix():
    reqs = build_batch_requests(_papers(), paper_texts={"2502.19645": "txt", "2410.24164": "txt2"})
    assert len(reqs) == 2
    r0 = reqs[0]
    # custom_id is deterministic + recoverable from the paper
    assert r0["custom_id"] == paper_custom_id(_papers()[0])
    params = r0["params"]
    assert params["model"] == MODEL == "claude-opus-4-8"
    assert params["thinking"] == {"type": "adaptive"}
    assert params["output_config"]["format"]["type"] == "json_schema"
    # NO prefill in a batch request either.
    assert params["messages"][-1]["role"] == "user"
    # cached prefix breakpoint present so the prefix caches across the batch.
    assert params["system"][-1]["cache_control"] == {"type": "ephemeral"}


def test_custom_id_is_stable_and_unique():
    p = _papers()
    assert paper_custom_id(p[0]) != paper_custom_id(p[1])
    assert paper_custom_id(p[0]) == paper_custom_id(p[0])


class _FakeBatches:
    """Mimics client.messages.batches with a canned results() iterator."""

    def __init__(self, results):
        self._results = results
        self.created = None

    def create(self, requests):
        self.created = requests
        return SimpleNamespace(id="msgbatch_123", processing_status="in_progress")

    def results(self, batch_id):
        return iter(self._results)


def _succeeded(custom_id, claims_json):
    msg = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=claims_json)],
        stop_reason="end_turn",
    )
    return SimpleNamespace(
        custom_id=custom_id,
        result=SimpleNamespace(type="succeeded", message=msg),
    )


def _errored(custom_id):
    return SimpleNamespace(
        custom_id=custom_id,
        result=SimpleNamespace(type="errored", error=SimpleNamespace(type="invalid_request")),
    )


def test_collect_parses_succeeded_and_skips_errored():
    p = _papers()
    cid0, cid1 = paper_custom_id(p[0]), paper_custom_id(p[1])
    claims_json = json.dumps({"claims": [{
        "method_slug": "openvla-oft", "benchmark_slug": "libero", "task_slug": None,
        "metric": "success_rate", "metric_value": 97.1, "eval_conditions": {"split": "test"},
        "realm": "sim", "origin": "public_reproducible",
        "source_url": "https://arxiv.org/abs/2502.19645", "result_date": None,
    }]})
    fake_batches = _FakeBatches([_succeeded(cid0, claims_json), _errored(cid1)])
    client = SimpleNamespace(messages=SimpleNamespace(batches=fake_batches))

    ok, errors = collect_batch_results(client, "msgbatch_123")
    assert set(ok) == {cid0}
    assert len(ok[cid0]) == 1
    assert ok[cid0][0].benchmark_slug == "libero"
    assert ok[cid0][0].metric_value == 97.1
    assert errors == {cid1: "invalid_request"}


def test_submit_batch_passes_requests_to_client():
    fake_batches = _FakeBatches([])
    client = SimpleNamespace(messages=SimpleNamespace(batches=fake_batches))
    reqs = build_batch_requests(_papers(), paper_texts={"2502.19645": "t", "2410.24164": "t2"})
    from sota_ingest.agent.batch import submit_batch

    batch = submit_batch(client, reqs)
    assert batch.id == "msgbatch_123"
    assert fake_batches.created == reqs
