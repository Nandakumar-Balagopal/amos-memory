from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(UTC)


class MemoryType(StrEnum):
    EPISODE = "EPISODE"
    FACT = "FACT"
    SKILL = "SKILL"
    PREFERENCE = "PREFERENCE"
    BELIEF = "BELIEF"
    RELATIONSHIP = "RELATIONSHIP"
    SUMMARY = "SUMMARY"
    GOAL = "GOAL"
    TASK = "TASK"
    OBSERVATION = "OBSERVATION"


class MemoryTier(StrEnum):
    ACTIVE = "ACTIVE"
    SURVIVOR = "SURVIVOR"
    DURABLE = "DURABLE"
    ARCHIVE = "ARCHIVE"


class MemoryScope(StrEnum):
    PRIVATE = "PRIVATE"
    TEAM = "TEAM"
    ORG = "ORG"
    PUBLIC = "PUBLIC"


class LifecycleDecision(StrEnum):
    PROMOTE = "PROMOTE"
    DEMOTE = "DEMOTE"
    CONSOLIDATE = "CONSOLIDATE"
    ARCHIVE = "ARCHIVE"
    DELETE = "DELETE"
    KEEP = "KEEP"


class RetrievalRoute(StrEnum):
    CURRENT_STATE = "CURRENT_STATE"
    TEMPORAL = "TEMPORAL"
    SKILL = "SKILL"
    RELATIONSHIP = "RELATIONSHIP"
    PREFERENCE = "PREFERENCE"
    TASK = "TASK"
    GENERAL = "GENERAL"


@dataclass(slots=True)
class Provenance:
    source: str = "user"
    source_memory_ids: list[str] = field(default_factory=list)
    derivation: str | None = None
    model: str | None = None


@dataclass(slots=True)
class Memory:
    tenant_id: str
    content: str
    type: MemoryType = MemoryType.OBSERVATION
    id: str = field(default_factory=lambda: str(uuid4()))
    agent_id: str | None = None
    scope: MemoryScope = MemoryScope.PRIVATE
    tier: MemoryTier = MemoryTier.ACTIVE
    heat_score: float = 0.5
    importance: float = 0.5
    confidence: float = 1.0
    retrieval_count: int = 0
    relationship_density: float = 0.0
    provenance: Provenance = field(default_factory=Provenance)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    accessed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TemporalFact:
    tenant_id: str
    entity: str
    attribute: str
    value: str
    source: str
    valid_from: datetime
    id: str = field(default_factory=lambda: str(uuid4()))
    memory_id: str | None = None
    valid_to: datetime | None = None
    confidence: float = 1.0
    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class Relationship:
    tenant_id: str
    source: str
    relation: str
    target: str
    id: str = field(default_factory=lambda: str(uuid4()))
    memory_id: str | None = None
    confidence: float = 1.0
    created_at: datetime = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DomainEvent:
    tenant_id: str
    kind: str
    payload: dict[str, Any]
    id: str = field(default_factory=lambda: str(uuid4()))
    occurred_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class RecallResult:
    memory: Memory
    score: float
    route: RetrievalRoute
    reasons: list[str]


@dataclass(slots=True)
class CompiledContext:
    text: str
    token_count: int
    selected: list[RecallResult]
    rejected: list[RecallResult]
    route: RetrievalRoute


def to_dict(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return {key: to_dict(item) for key, item in asdict(value).items()}
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, dict):
        return {key: to_dict(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_dict(item) for item in value]
    return value

