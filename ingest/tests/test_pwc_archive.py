# tests/test_pwc_archive.py
"""normalize_records turns raw parquet pylist rows into the nested shape
parse_evaluation_tables expects, tolerating every way the HF JSON->parquet
conversion can encode the free-form `metrics` object and dropping rows the
parser would choke on (null dataset name / null model_name)."""
from sota_ingest.pwc_archive import normalize_records, fetch_pwc_archive


def test_metrics_as_dict_passthrough():
    recs = [{"task": "Robot Manipulation", "datasets": [
        {"dataset": "LIBERO", "sota": {"metrics": ["Success Rate"],
         "rows": [{"model_name": "X", "metrics": {"Success Rate": "90"}, "paper_url": "u"}]}}]}]
    out = normalize_records(recs)
    assert out[0]["datasets"][0]["sota"]["rows"][0]["metrics"] == {"Success Rate": "90"}


def test_metrics_as_map_pairs_coerced_to_dict():
    # pyarrow map type -> to_pylist() yields list of (key, value) tuples
    recs = [{"task": "Grasping", "datasets": [
        {"dataset": "GraspNet", "sota": {"metrics": ["AP"],
         "rows": [{"model_name": "Y", "metrics": [("AP", "0.5")], "paper_url": "u"}]}}]}]
    out = normalize_records(recs)
    assert out[0]["datasets"][0]["sota"]["rows"][0]["metrics"] == {"AP": "0.5"}


def test_metrics_as_json_string_parsed():
    recs = [{"task": "Locomotion", "datasets": [
        {"dataset": "Bench", "sota": {"metrics": ["Reward"],
         "rows": [{"model_name": "Z", "metrics": '{"Reward": "7"}', "paper_url": "u"}]}}]}]
    out = normalize_records(recs)
    assert out[0]["datasets"][0]["sota"]["rows"][0]["metrics"] == {"Reward": "7"}


def test_drops_null_dataset_and_null_model_rows():
    recs = [{"task": "Navigation", "datasets": [
        {"dataset": None, "sota": {"metrics": ["x"], "rows": [{"model_name": "A", "metrics": {}}]}},
        {"dataset": "Habitat", "sota": {"metrics": ["SR"], "rows": [
            {"model_name": None, "metrics": {}},
            {"model_name": "Good", "metrics": {"SR": "1"}, "paper_url": "u"}]}},
    ]}]
    out = normalize_records(recs)
    datasets = out[0]["datasets"]
    assert [d["dataset"] for d in datasets] == ["Habitat"]   # null-named dataset dropped
    rows = datasets[0]["sota"]["rows"]
    assert [r["model_name"] for r in rows] == ["Good"]        # null model_name row dropped


def test_record_with_no_usable_datasets_is_dropped():
    recs = [{"task": "Empty", "datasets": [{"dataset": None, "sota": {"rows": []}}]},
            {"task": "Robot X", "datasets": [{"dataset": "D", "sota": {
                "metrics": ["m"], "rows": [{"model_name": "M", "metrics": {"m": "1"}}]}}]}]
    out = normalize_records(recs)
    assert [r["task"] for r in out] == ["Robot X"]


def test_fetch_pwc_archive_reads_all_shards_via_injected_getter(tmp_path):
    # fetch_pwc_archive downloads each shard via the injected getter, reads the
    # parquet bytes, and returns normalized records concatenated across shards.
    import pyarrow as pa
    import pyarrow.parquet as pq
    import io

    def make_shard(task):
        tbl = pa.table({
            "task": [task],
            "datasets": [[{"dataset": "D", "sota": {
                "metrics": ["m"], "rows": [{"model_name": "M", "metrics": {"m": "1"}, "paper_url": "u"}]}}]],
        })
        buf = io.BytesIO()
        pq.write_table(tbl, buf)
        return buf.getvalue()

    shards = {"s0": make_shard("Robot A"), "s1": make_shard("Robot B")}
    out = fetch_pwc_archive(get_bytes=lambda url: shards[url], shard_urls=["s0", "s1"])
    assert sorted(r["task"] for r in out) == ["Robot A", "Robot B"]
