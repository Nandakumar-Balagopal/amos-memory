from __future__ import annotations

from collections import defaultdict
from threading import RLock

from ..models import DomainEvent, Memory, Relationship, TemporalFact


class InMemoryStorage:
    """Thread-safe reference adapter implementing all AMOS storage ports."""

    def __init__(self) -> None:
        self._memories: dict[str, Memory] = {}
        self._facts: dict[str, TemporalFact] = {}
        self._relationships: dict[str, Relationship] = {}
        self._events: defaultdict[str, list[DomainEvent]] = defaultdict(list)
        self._lock = RLock()

    def put(self, memory: Memory) -> None:
        with self._lock:
            self._memories[memory.id] = memory

    def get(self, memory_id: str) -> Memory | None:
        with self._lock:
            return self._memories.get(memory_id)

    def delete(self, memory_id: str) -> bool:
        with self._lock:
            return self._memories.pop(memory_id, None) is not None

    def list(self, tenant_id: str) -> list[Memory]:
        with self._lock:
            return [memory for memory in self._memories.values() if memory.tenant_id == tenant_id]

    def put_fact(self, fact: TemporalFact) -> None:
        with self._lock:
            self._facts[fact.id] = fact

    def facts(self, tenant_id: str, entity: str | None = None, attribute: str | None = None) -> list[TemporalFact]:
        with self._lock:
            result = [
                fact for fact in self._facts.values()
                if fact.tenant_id == tenant_id
                and (entity is None or fact.entity == entity)
                and (attribute is None or fact.attribute == attribute)
            ]
            return sorted(result, key=lambda fact: fact.valid_from)

    def add_relationship(self, relationship: Relationship) -> None:
        with self._lock:
            self._relationships[relationship.id] = relationship

    def neighbors(self, tenant_id: str, node: str) -> list[Relationship]:
        with self._lock:
            return [
                edge for edge in self._relationships.values()
                if edge.tenant_id == tenant_id and (edge.source == node or edge.target == node)
            ]

    def publish(self, event: DomainEvent) -> None:
        with self._lock:
            self._events[event.tenant_id].append(event)

    def events(self, tenant_id: str) -> list[DomainEvent]:
        with self._lock:
            return list(self._events[tenant_id])

