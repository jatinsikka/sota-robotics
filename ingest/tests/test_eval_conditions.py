from sota_ingest.eval_conditions import canonical_hash


def test_key_order_does_not_change_hash():
    a = {"split": "test", "protocol": "visual_matching", "episodes": 50}
    b = {"episodes": 50, "protocol": "visual_matching", "split": "test"}
    assert canonical_hash(a) == canonical_hash(b)


def test_nested_key_order_stable():
    a = {"sim": {"engine": "mujoco", "seeds": [1, 2, 3]}}
    b = {"sim": {"seeds": [1, 2, 3], "engine": "mujoco"}}
    assert canonical_hash(a) == canonical_hash(b)


def test_different_values_change_hash():
    assert canonical_hash({"split": "test"}) != canonical_hash({"split": "train"})


def test_empty_dict_is_stable_nonempty_string():
    h = canonical_hash({})
    assert isinstance(h, str) and len(h) == 64  # sha256 hex
