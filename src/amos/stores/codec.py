from __future__ import annotations

from datetime import datetime
from typing import Any

from ..models import DomainEvent, Memory, MemoryScope, MemoryTier, MemoryType, Provenance, Relationship, TemporalFact


def timestamp(value: str | datetime | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def memory_from_dict(data: dict[str, Any]) -> Memory:
    return Memory(
        id=str(data["id"]),
        tenant_id=str(data["tenant_id"]),
        agent_id=data.get("agent_id"),
        content=str(data["content"]),
        type=MemoryType(data["type"]),
        scope=MemoryScope(data["scope"]),
        tier=MemoryTier(data["tier"]),
        heat_score=float(data["heat_score"]),
        importance=float(data["importance"]),
        confidence=float(data["confidence"]),
        retrieval_count=int(data["retrieval_count"]),
        relationship_density=float(data["relationship_density"]),
        survivor_count=int(data.get("survivor_count", 0)),
        provenance=Provenance(**(data.get("provenance") or {})),
        created_at=timestamp(data["created_at"]),
        updated_at=timestamp(data["updated_at"]),
        accessed_at=timestamp(data.get("accessed_at")),
        metadata=data.get("metadata") or {},
    )


def fact_from_dict(data: dict[str, Any]) -> TemporalFact:
    return TemporalFact(
        id=str(data["id"]),
        tenant_id=str(data["tenant_id"]),
        entity=str(data["entity"]),
        attribute=str(data["attribute"]),
        value=str(data["value"]),
        valid_from=timestamp(data["valid_from"]),
        valid_to=timestamp(data.get("valid_to")),
        confidence=float(data["confidence"]),
        source=str(data["source"]),
        memory_id=str(data["memory_id"]) if data.get("memory_id") else None,
        created_at=timestamp(data["created_at"]),
    )


def relationship_from_dict(data: dict[str, Any]) -> Relationship:
    return Relationship(
        id=str(data["id"]),
        tenant_id=str(data["tenant_id"]),
        source=str(data["source"]),
        relation=str(data["relation"]),
        target=str(data["target"]),
        memory_id=str(data["memory_id"]) if data.get("memory_id") else None,
        confidence=float(data["confidence"]),
        created_at=timestamp(data["created_at"]),
        metadata=data.get("metadata") or {},
    )


def event_from_dict(data: dict[str, Any]) -> DomainEvent:
    return DomainEvent(
        id=str(data["id"]),
        tenant_id=str(data["tenant_id"]),
        kind=str(data["kind"]),
        payload=data.get("payload") or {},
        occurred_at=timestamp(data["occurred_at"]),
    )
