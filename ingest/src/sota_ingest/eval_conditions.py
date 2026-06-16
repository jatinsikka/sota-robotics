import hashlib
import json
from typing import Any


def canonical_hash(eval_conditions: dict[str, Any]) -> str:
    """SHA-256 of canonicalized eval_conditions.

    Keys are sorted recursively (json sort_keys handles nested dicts),
    separators are fixed, so logically-equal dicts hash identically.
    """
    canonical = json.dumps(
        eval_conditions, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
