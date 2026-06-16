from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Realm(str, Enum):
    SIM = "sim"
    REAL = "real"


class Origin(str, Enum):
    PUBLIC_REPRODUCIBLE = "public_reproducible"
    VENDOR_INTERNAL = "vendor_internal"


class VerificationStatus(str, Enum):
    PENDING = "pending"
    PUBLISHED = "published"
    HELD = "held"
    REFUTED = "refuted"


class ResultClaim(BaseModel):
    method_slug: str
    benchmark_slug: str
    task_slug: str | None = None
    metric: str
    metric_value: float | None = None
    eval_conditions: dict[str, Any] = Field(default_factory=dict)
    realm: Realm = Realm.SIM
    origin: Origin = Origin.PUBLIC_REPRODUCIBLE
    source_url: str
    result_date: str | None = None  # ISO date string; validated downstream
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    verification_status: VerificationStatus = VerificationStatus.PENDING
    skeptic_notes: str | None = None


class PaperRec(BaseModel):
    arxiv_id: str | None = None
    title: str
    authors: str | None = None
    abstract: str | None = None
    published_date: str | None = None
    url: str | None = None
