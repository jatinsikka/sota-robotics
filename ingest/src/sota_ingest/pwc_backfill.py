"""Filter the frozen PWC archive down to robotics tasks, then reuse
Plan 1's parse_evaluation_tables (imports everything HELD)."""
from typing import Any

from sota_ingest.models import ResultClaim
from sota_ingest.sota_extractor import parse_evaluation_tables

# Substrings (lowercased) that mark a PWC task block as in-scope for a
# robotics-native SOTA tracker. Conservative: manipulation, locomotion,
# navigation, grasping, pose, sim2real, world models, embodied control.
ROBOTICS_TASK_KEYWORDS = (
    "robot",
    "manipulation",
    "grasp",
    "locomotion",
    "humanoid",
    "navigation",
    "vision-and-language navigation",
    "pose estimation",
    "sim-to-real",
    "sim2real",
    "world model",
    "embodied",
    "whole-body",
    "dexterous",
)


def _is_robotics_task(task_name: str) -> bool:
    name = (task_name or "").lower()
    return any(kw in name for kw in ROBOTICS_TASK_KEYWORDS)


def filter_robotics_tasks(data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only task blocks whose task name matches a robotics keyword."""
    return [block for block in data if _is_robotics_task(block.get("task", ""))]


def claims_from_pwc(data: list[dict[str, Any]]) -> list[ResultClaim]:
    """Robotics-filtered PWC archive -> HELD ResultClaims (Plan 1 contract)."""
    return parse_evaluation_tables(filter_robotics_tasks(data))
