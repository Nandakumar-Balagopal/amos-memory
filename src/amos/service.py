from __future__ import annotations

from datetime import datetime
from typing import Any

from .engines import (
    AdmissionDecision,
    ContextCompiler,
    DeterministicMemoryPipeline,
    GenerationalScheduler,
    HeatEngine,
    MemoryAdmissionPolicy,
    RetrievalRouter,
    TemporalTruthEngine,
)
from .models import (
    CompiledContext,
    DomainEvent,
    LifecycleDecision,
    Memory,
    MemoryScope,
    MemoryType,
    Provenance,
    RecallResult,
    Relationship,
    TemporalFact,
    to_dict,
    utc_now,
)
from .engines.pipeline import ProcessingReport
from .ports import EventBus, GraphStore, MemoryStore, TimelineStore
from .stores import InMemoryStorage


class Amos:
    def __init__(
        self,
        *,
        memories: MemoryStore | None = None,
        timeline: TimelineStore | None = None,
        graph: GraphStore | None = None,
        events: EventBus | None = None,
    ) -> None:
        default = InMemoryStorage()
        self.memories = memories or default
        self.timeline = timeline or default
        self.graph = graph or default
        self.events = events or default
        self.temporal = TemporalTruthEngine(self.timeline)
        self.heat = HeatEngine()
        self.scheduler = GenerationalScheduler(self.heat)
        self.retrieval = RetrievalRouter()
        self.compiler = ContextCompiler()
        self.pipeline = DeterministicMemoryPipeline()
        self.admission = MemoryAdmissionPolicy()

    def remember(
        self,
        *,
        tenant_id: str,
        content: str,
        type: MemoryType = MemoryType.OBSERVATION,
        agent_id: str | None = None,
        scope: MemoryScope = MemoryScope.PRIVATE,
        importance: float = 0.5,
        confidence: float = 1.0,
        metadata: dict[str, Any] | None = None,
        provenance: Provenance | None = None,
        auto_process: bool = True,
    ) -> Memory:
        if not content.strip():
            raise ValueError("content cannot be empty")
        memory = Memory(
            tenant_id=tenant_id,
            content=content.strip(),
            type=type,
            agent_id=agent_id,
            scope=scope,
            importance=self._unit(importance, "importance"),
            confidence=self._unit(confidence, "confidence"),
            metadata=metadata or {},
            provenance=provenance or Provenance(),
        )
        memory.heat_score = self.heat.calculate(memory)
        self.memories.put(memory)
        self._emit(tenant_id, "MemoryCreated", {"memory": to_dict(memory)})
        if auto_process:
            self.process_memory(tenant_id=tenant_id, memory_id=memory.id)
        return memory

    def get_memory(self, memory_id: str) -> Memory | None:
        return self.memories.get(memory_id)

    def assess_memory(
        self,
        *,
        content: str,
        type: MemoryType = MemoryType.OBSERVATION,
        importance: float = 0.5,
        confidence: float = 1.0,
    ) -> AdmissionDecision:
        if not content.strip():
            raise ValueError("content cannot be empty")
        return self.admission.evaluate(
            content=content.strip(),
            type=type,
            importance=self._unit(importance, "importance"),
            confidence=self._unit(confidence, "confidence"),
        )

    def forget(self, *, tenant_id: str, memory_id: str, reason: str = "requested", force: bool = False) -> bool:
        memory = self.memories.get(memory_id)
        if memory is None or memory.tenant_id != tenant_id:
            return False
        dependents = self.dependents(tenant_id=tenant_id, memory_id=memory_id)
        if dependents and not force:
            self._emit(
                tenant_id,
                "MemoryForgetBlocked",
                {"memory_id": memory_id, "dependent_memory_ids": [item.id for item in dependents], "reason": reason},
            )
            return False
        deleted = self.memories.delete(memory_id)
        if deleted:
            self._emit(
                tenant_id,
                "MemoryForgotten",
                {"memory_id": memory_id, "reason": reason, "force": force},
            )
        return deleted

    def recall(self, *, tenant_id: str, query: str, limit: int = 10) -> list[RecallResult]:
        candidates = self.retrieval.retrieve(query, self.memories.list(tenant_id), limit)
        now = utc_now()
        for result in candidates:
            result.memory.retrieval_count += 1
            result.memory.accessed_at = now
            result.memory.heat_score = self.heat.calculate(result.memory, now)
            self.memories.put(result.memory)
        self._emit(tenant_id, "MemoryRecalled", {"query": query, "memory_ids": [r.memory.id for r in candidates]})
        return candidates

    def get_context(self, *, tenant_id: str, query: str, token_budget: int = 300) -> CompiledContext:
        candidates = self.recall(tenant_id=tenant_id, query=query, limit=100)
        compiled = self.compiler.compile(candidates, token_budget)
        self._emit(
            tenant_id,
            "ContextCompiled",
            {
                "query": query,
                "token_budget": token_budget,
                "token_count": compiled.token_count,
                "selected_ids": [result.memory.id for result in compiled.selected],
            },
        )
        return compiled

    def update_fact(
        self,
        *,
        tenant_id: str,
        entity: str,
        attribute: str,
        value: str,
        valid_from: datetime,
        source: str,
        memory_id: str | None = None,
        confidence: float = 1.0,
    ) -> TemporalFact:
        fact, closed = self.temporal.update(
            tenant_id=tenant_id,
            entity=entity,
            attribute=attribute,
            value=value,
            valid_from=valid_from,
            source=source,
            memory_id=memory_id,
            confidence=self._unit(confidence, "confidence"),
        )
        self._emit(
            tenant_id,
            "TimelineUpdated",
            {"fact": to_dict(fact), "closed_fact_ids": [item.id for item in closed]},
        )
        return fact

    def get_timeline(self, *, tenant_id: str, entity: str | None = None, attribute: str | None = None) -> list[TemporalFact]:
        return self.timeline.facts(tenant_id, entity, attribute)

    def add_relationship(
        self,
        *,
        tenant_id: str,
        source: str,
        relation: str,
        target: str,
        memory_id: str | None = None,
        confidence: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> Relationship:
        relationship = Relationship(
            tenant_id=tenant_id,
            source=source,
            relation=relation,
            target=target,
            memory_id=memory_id,
            confidence=self._unit(confidence, "confidence"),
            metadata=metadata or {},
        )
        self.graph.add_relationship(relationship)
        self._emit(tenant_id, "GraphUpdated", {"relationship": to_dict(relationship)})
        return relationship

    def get_relationships(self, *, tenant_id: str, node: str) -> list[Relationship]:
        return self.graph.neighbors(tenant_id, node)

    def consolidate(
        self,
        *,
        tenant_id: str,
        source_memory_ids: list[str],
        content: str,
        type: MemoryType = MemoryType.SUMMARY,
        confidence: float = 0.8,
        model: str | None = None,
    ) -> Memory:
        sources = [self.memories.get(memory_id) for memory_id in source_memory_ids]
        if not source_memory_ids or any(source is None or source.tenant_id != tenant_id for source in sources):
            raise ValueError("all source memories must exist in the tenant")
        memory = self.remember(
            tenant_id=tenant_id,
            content=content,
            type=type,
            importance=max(source.importance for source in sources if source),
            confidence=confidence,
            provenance=Provenance(
                source="consolidator",
                source_memory_ids=source_memory_ids,
                derivation="episodic_to_semantic",
                model=model,
            ),
            auto_process=False,
        )
        self._emit(tenant_id, "MemoryConsolidated", {"memory_id": memory.id, "source_memory_ids": source_memory_ids})
        return memory

    def process_memory(self, *, tenant_id: str, memory_id: str, force: bool = False) -> ProcessingReport:
        memory = self.memories.get(memory_id)
        if memory is None or memory.tenant_id != tenant_id:
            raise ValueError("memory not found")
        if memory.metadata.get("pipeline_processed_at") and not force:
            report = ProcessingReport(memory_id=memory_id, skipped=["already_processed"])
            self._emit(tenant_id, "MemoryProcessingSkipped", to_dict(report))
            return report

        report = ProcessingReport(memory_id=memory_id)
        for candidate in self.pipeline.extract_facts(memory.content):
            fact = self.update_fact(
                tenant_id=tenant_id,
                entity=candidate.entity,
                attribute=candidate.attribute,
                value=candidate.value,
                valid_from=utc_now(),
                source=f"memory:{memory_id}",
                memory_id=memory_id,
                confidence=candidate.confidence,
            )
            report.extracted_facts.append(fact)
        for candidate in self.pipeline.extract_relationships(memory.content):
            relationship = self.add_relationship(
                tenant_id=tenant_id,
                source=candidate.source,
                relation=candidate.relation,
                target=candidate.target,
                memory_id=memory_id,
                confidence=candidate.confidence,
            )
            report.extracted_relationships.append(relationship)

        memory.relationship_density = min(1.0, len(report.extracted_relationships) / 5)
        memory.heat_score = self.heat.calculate(memory)
        memory.metadata["pipeline_processed_at"] = utc_now().isoformat()
        memory.metadata["pipeline_version"] = "deterministic-v1"
        memory.updated_at = utc_now()
        self.memories.put(memory)
        self._emit(
            tenant_id,
            "MemoryProcessed",
            {
                "memory_id": memory_id,
                "fact_count": len(report.extracted_facts),
                "relationship_count": len(report.extracted_relationships),
                "skipped": report.skipped,
            },
        )
        return report

    def dependents(self, *, tenant_id: str, memory_id: str) -> list[Memory]:
        return [
            memory
            for memory in self.memories.list(tenant_id)
            if memory_id in memory.provenance.source_memory_ids
        ]

    def explain_memory(self, *, tenant_id: str, memory_id: str) -> dict[str, Any]:
        memory = self.memories.get(memory_id)
        if memory is None or memory.tenant_id != tenant_id:
            raise ValueError("memory not found")
        facts = [fact for fact in self.timeline.facts(tenant_id) if fact.memory_id == memory_id]
        relationship_nodes = set()
        for fact in facts:
            relationship_nodes.add(fact.entity)
            relationship_nodes.add(fact.value)
        relationships = []
        seen_relationship_ids: set[str] = set()
        for node in relationship_nodes:
            for relationship in self.graph.neighbors(tenant_id, node):
                if relationship.memory_id == memory_id and relationship.id not in seen_relationship_ids:
                    seen_relationship_ids.add(relationship.id)
                    relationships.append(relationship)
        if not relationships:
            for relationship_memory in self.memories.list(tenant_id):
                if relationship_memory.id == memory_id:
                    continue
        events = [
            event for event in self.events.events(tenant_id)
            if event.payload.get("memory_id") == memory_id
            or event.payload.get("memory", {}).get("id") == memory_id
            or memory_id in event.payload.get("source_memory_ids", [])
        ]
        return {
            "memory": memory,
            "heat": self.heat.explain(memory),
            "facts": facts,
            "relationships": relationships,
            "dependents": self.dependents(tenant_id=tenant_id, memory_id=memory_id),
            "events": events,
            "lifecycle": {
                "tier": memory.tier.value,
                "processed": bool(memory.metadata.get("pipeline_processed_at")),
                "forget_requires_force": bool(self.dependents(tenant_id=tenant_id, memory_id=memory_id)),
            },
        }

    def run_scheduler(self, *, tenant_id: str) -> list[dict[str, str]]:
        decisions: list[dict[str, str]] = []
        for memory in self.memories.list(tenant_id):
            decision = self.scheduler.evaluate(memory)
            if decision == LifecycleDecision.DELETE:
                dependents = self.dependents(tenant_id=tenant_id, memory_id=memory.id)
                if dependents:
                    item = {
                        "memory_id": memory.id,
                        "decision": "DELETE_BLOCKED",
                        "tier": memory.tier.value,
                        "dependent_memory_ids": ",".join(item.id for item in dependents),
                    }
                    decisions.append(item)
                    self._emit(tenant_id, "SchedulerDeleteBlocked", item)
                    continue
                self.memories.delete(memory.id)
            else:
                self.memories.put(memory)
            if decision != LifecycleDecision.KEEP:
                item = {"memory_id": memory.id, "decision": decision.value, "tier": memory.tier.value}
                decisions.append(item)
                self._emit(tenant_id, "SchedulerEvaluated", item)
        return decisions

    def health(self) -> dict[str, bool]:
        stores = {
            "memories": self.memories,
            "timeline": self.timeline,
            "graph": self.graph,
            "events": self.events,
        }
        result: dict[str, bool] = {}
        for name, store in stores.items():
            health = getattr(store, "health", None)
            try:
                result[name] = bool(health()) if health else True
            except Exception:
                result[name] = False
        return result

    def close(self) -> None:
        seen: set[int] = set()
        for store in (self.memories, self.timeline, self.graph, self.events):
            if id(store) in seen:
                continue
            seen.add(id(store))
            close = getattr(store, "close", None)
            if close:
                close()

    def _emit(self, tenant_id: str, kind: str, payload: dict[str, Any]) -> None:
        self.events.publish(DomainEvent(tenant_id=tenant_id, kind=kind, payload=payload))

    @staticmethod
    def _unit(value: float, name: str) -> float:
        if not 0 <= value <= 1:
            raise ValueError(f"{name} must be between 0 and 1")
        return value
