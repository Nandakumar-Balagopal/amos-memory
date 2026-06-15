from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MemoryType(str, Enum):
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


class SemanticType(str, Enum):
    """Types of semantic memories."""
    INTEREST = "INTEREST"
    SKILL = "SKILL"
    PREFERENCE = "PREFERENCE"
    FACT = "FACT"
    BELIEF = "BELIEF"
    GOAL = "GOAL"


class EntityType(str, Enum):
    """Types of entities."""
    PERSON = "PERSON"
    PROJECT = "PROJECT"
    COMPANY = "COMPANY"
    TECHNOLOGY = "TECHNOLOGY"
    LOCATION = "LOCATION"
    CONCEPT = "CONCEPT"


class MemoryTier(str, Enum):
    ACTIVE = "ACTIVE"
    SURVIVOR = "SURVIVOR"
    DURABLE = "DURABLE"
    ARCHIVE = "ARCHIVE"


class MemoryScope(str, Enum):
    PRIVATE = "PRIVATE"
    TEAM = "TEAM"
    ORG = "ORG"
    PUBLIC = "PUBLIC"


class Generation(str, Enum):
    """Memory generation for V3 lifecycle."""
    YOUNG = "young"
    SURVIVOR = "survivor"
    LONG_TERM = "long_term"
    ARCHIVE = "archive"


class LifecycleDecision(str, Enum):
    PROMOTE = "PROMOTE"
    DEMOTE = "DEMOTE"
    CONSOLIDATE = "CONSOLIDATE"
    ARCHIVE = "ARCHIVE"
    DELETE = "DELETE"
    KEEP = "KEEP"


class RetrievalRoute(str, Enum):
    CURRENT_STATE = "CURRENT_STATE"
    TEMPORAL = "TEMPORAL"
    SKILL = "SKILL"
    RELATIONSHIP = "RELATIONSHIP"
    PREFERENCE = "PREFERENCE"
    TASK = "TASK"
    GENERAL = "GENERAL"


@dataclass
class Provenance:
    source: str = "user"
    source_memory_ids: list[str] = field(default_factory=list)
    derivation: str | None = None
    model: str | None = None


@dataclass
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
    survivor_count: int = 0  # How many GC cycles this memory has survived (JVM GC pattern)
    provenance: Provenance = field(default_factory=Provenance)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    accessed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
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


@dataclass
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


@dataclass
class Episode:
    """Raw episode in young or survivor generation (V3)."""
    tenant_id: str
    role: str  # user, assistant, system, tool
    content: str
    source: str
    embedding: list[float]
    id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=utc_now)
    access_count: int = 0
    retrieval_count: int = 0
    mention_count: int = 0
    heat: float = 1.0
    generation: Generation = Generation.YOUNG
    promotion_score: float | None = None
    promoted_at: datetime | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class SemanticMemory:
    """Durable fact or preference (V3)."""
    tenant_id: str
    fact: str
    type: SemanticType
    confidence: float
    valid_from: datetime
    embedding: list[float]
    id: str = field(default_factory=lambda: str(uuid4()))
    valid_until: datetime | None = None
    source_episodes: list[str] = field(default_factory=list)
    heat: float = 1.0
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class EpisodicMemory:
    """Important experience or event (V3)."""
    tenant_id: str
    event: str
    timestamp: datetime
    importance: float
    embedding: list[float]
    id: str = field(default_factory=lambda: str(uuid4()))
    context: str | None = None
    source_episodes: list[str] = field(default_factory=list)
    heat: float = 1.0
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class ProceduralMemory:
    """Learned procedure or workflow (V3)."""
    tenant_id: str
    trigger: str
    procedure: str
    confidence: float
    embedding: list[float]
    id: str = field(default_factory=lambda: str(uuid4()))
    success_count: int = 0
    failure_count: int = 0
    source_episodes: list[str] = field(default_factory=list)
    heat: float = 1.0
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class Entity:
    """Named entity (V3)."""
    tenant_id: str
    name: str
    entity_type: EntityType
    embedding: list[float]
    id: str = field(default_factory=lambda: str(uuid4()))
    attributes: dict[str, Any] = field(default_factory=dict)
    source_episode_id: str | None = None
    heat: float = 1.0
    first_seen: datetime = field(default_factory=utc_now)
    last_seen: datetime = field(default_factory=utc_now)
    mention_count: int = 0
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class EntityRelationship:
    """Relationship between entities (V3)."""
    tenant_id: str
    source_id: str
    target_id: str
    relation: str
    confidence: float
    valid_from: datetime
    id: str = field(default_factory=lambda: str(uuid4()))
    valid_until: datetime | None = None
    heat: float = 1.0
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class DomainEvent:
    tenant_id: str
    kind: str
    payload: dict[str, Any]
    id: str = field(default_factory=lambda: str(uuid4()))
    occurred_at: datetime = field(default_factory=utc_now)


@dataclass
class RecallResult:
    memory: Memory
    score: float
    route: RetrievalRoute
    reasons: list[str]


@dataclass
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
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: to_dict(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_dict(item) for item in value]
    return value

