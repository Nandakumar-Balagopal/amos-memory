from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

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
from .engines.adaptive_scheduler import AdaptiveScheduler
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
from .async_processor import AsyncProcessor, ProcessingTask


class Amos:
    def __init__(
        self,
        *,
        memories: MemoryStore | None = None,
        timeline: TimelineStore | None = None,
        graph: GraphStore | None = None,
        events: EventBus | None = None,
        use_cascading_extraction: bool = True,
        use_tiny_llm: bool = True,
        enable_async_processing: bool = False,
        async_workers: int = 1,
        use_adaptive_scheduler: bool = False,
    ) -> None:
        default = InMemoryStorage()
        self.memories = memories or default
        self.timeline = timeline or default
        self.graph = graph or default
        self.events = events or default
        self.temporal = TemporalTruthEngine(self.timeline)
        self.heat = HeatEngine()
        
        # Use adaptive or fixed scheduler
        if use_adaptive_scheduler:
            self.scheduler = AdaptiveScheduler(self.heat)
        else:
            self.scheduler = GenerationalScheduler(self.heat)
        
        self.retrieval = RetrievalRouter()
        self.compiler = ContextCompiler()
        self.pipeline = DeterministicMemoryPipeline(
            use_cascading=use_cascading_extraction,
            use_tiny_llm=use_tiny_llm
        )
        self.admission = MemoryAdmissionPolicy()
        
        # Async processing
        self.async_processor: AsyncProcessor | None = None
        if enable_async_processing:
            self.async_processor = AsyncProcessor(self, num_workers=async_workers)
            self.async_processor.start()

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
        auto_process: bool | Literal["async"] = True,
    ) -> Memory:
        """Store a memory and optionally process it.
        
        Args:
            auto_process:
                - True: Process synchronously (blocks until complete)
                - False: Don't process
                - "async": Queue for async processing (returns immediately)
        """
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
        
        if auto_process == "async":
            if self.async_processor is None:
                raise RuntimeError("Async processing not enabled. Set enable_async_processing=True")
            self.async_processor.queue_processing(tenant_id, memory.id)
        elif auto_process is True:
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
        """Recall memories using hybrid retrieval if available, fallback to lexical."""
        from .stores.postgres import PostgresStorage
        from .models import RetrievalRoute
        
        # Use hybrid retrieval if PostgresStorage is available
        if isinstance(self.memories, PostgresStorage):
            memories = self.memories.search_hybrid(tenant_id, query, limit)
            # Convert to RecallResult format
            candidates = [
                RecallResult(
                    memory=memory,
                    score=1.0,  # Score already calculated in hybrid search
                    route=RetrievalRoute.GENERAL,
                    reasons=["hybrid_retrieval"]
                )
                for memory in memories
            ]
        else:
            # Fallback to V1 lexical retrieval
            candidates = self.retrieval.retrieve(query, self.memories.list(tenant_id), limit)
        
        # Update retrieval stats
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
        
        # Extract facts and track sources
        if self.pipeline.use_cascading and self.pipeline._cascading_extractor:
            extracted_facts = self.pipeline._cascading_extractor.extract(memory.content)
            for extracted_fact in extracted_facts:
                fact = self.update_fact(
                    tenant_id=tenant_id,
                    entity=extracted_fact.entity,
                    attribute=extracted_fact.attribute,
                    value=extracted_fact.value,
                    valid_from=utc_now(),
                    source=f"memory:{memory_id}",
                    memory_id=memory_id,
                    confidence=extracted_fact.confidence,
                )
                report.extracted_facts.append(fact)
                # Track extraction source
                source_key = extracted_fact.source.value
                report.extraction_sources[source_key] = report.extraction_sources.get(source_key, 0) + 1
        else:
            # V1 extraction
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
        memory.metadata["pipeline_version"] = "cascading-v2" if self.pipeline.use_cascading else "deterministic-v1"
        memory.metadata["extraction_sources"] = report.extraction_sources
        memory.updated_at = utc_now()
        self.memories.put(memory)
        self._emit(
            tenant_id,
            "MemoryProcessed",
            {
                "memory_id": memory_id,
                "fact_count": len(report.extracted_facts),
                "relationship_count": len(report.extracted_relationships),
                "extraction_sources": report.extraction_sources,
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

    def get_tier_distribution(self, *, tenant_id: str) -> dict[str, int]:
        """Get distribution of memories across tiers.
        
        Returns:
            Dictionary mapping tier names to memory counts
        """
        from .models import MemoryTier
        
        distribution = {
            "ACTIVE": 0,
            "SURVIVOR": 0,
            "DURABLE": 0,
            "ARCHIVE": 0
        }
        
        for memory in self.memories.list(tenant_id):
            tier_name = memory.tier.value
            if tier_name in distribution:
                distribution[tier_name] += 1
        
        return distribution
    
    def get_memories_by_tier(self, *, tenant_id: str, tier: str) -> list[Memory]:
        """Get all memories in a specific tier.
        
        Args:
            tenant_id: Tenant identifier
            tier: Tier name (ACTIVE, SURVIVOR, DURABLE, ARCHIVE)
            
        Returns:
            List of memories in the specified tier
        """
        from .models import MemoryTier
        
        try:
            target_tier = MemoryTier(tier)
        except ValueError:
            raise ValueError(f"Invalid tier: {tier}. Must be one of: ACTIVE, SURVIVOR, DURABLE, ARCHIVE")
        
        return [
            memory for memory in self.memories.list(tenant_id)
            if memory.tier == target_tier
        ]
    
    def get_memory_heat(self, *, memory_id: str) -> float:
        """Get heat score for a specific memory.
        
        Args:
            memory_id: Memory identifier
            
        Returns:
            Heat score (0.0-1.0)
        """
        memory = self.memories.get(memory_id)
        if memory is None:
            raise ValueError("memory not found")
        
        return memory.heat_score
    
    def get_heat_distribution(self, *, tenant_id: str, simulated_now: datetime | None = None) -> dict[str, Any]:
        """Get heat score distribution across all memories.
        
        Args:
            tenant_id: Tenant identifier
            simulated_now: Optional simulated time for testing (uses real time if None)
        
        Returns:
            Dictionary with heat statistics:
            - hot: List of heat scores > 0.7
            - warm: List of heat scores 0.3-0.7
            - cold: List of heat scores < 0.3
            - all: List of all heat scores
            - stats: Summary statistics
        """
        hot = []
        warm = []
        cold = []
        all_scores = []
        
        for memory in self.memories.list(tenant_id):
            # Recalculate heat with simulated time if provided
            score = self.heat.calculate(memory, simulated_now) if simulated_now else memory.heat_score
            all_scores.append(score)
            
            if score > 0.7:
                hot.append(score)
            elif score >= 0.3:
                warm.append(score)
            else:
                cold.append(score)
        
        return {
            "hot": hot,
            "warm": warm,
            "cold": cold,
            "all": all_scores,
            "stats": {
                "hot_count": len(hot),
                "warm_count": len(warm),
                "cold_count": len(cold),
                "total_count": len(all_scores),
                "mean": sum(all_scores) / len(all_scores) if all_scores else 0.0,
                "min": min(all_scores) if all_scores else 0.0,
                "max": max(all_scores) if all_scores else 0.0
            }
        }
    
    def run_promotion_check(self, *, tenant_id: str, simulated_now: datetime | None = None) -> dict[str, Any]:
        """Run promotion check and return report.
        
        Args:
            tenant_id: Tenant identifier
            simulated_now: Optional simulated time for testing (uses real time if None)
        
        Returns:
            Report with promotion/demotion decisions
        """
        promoted = []
        demoted = []
        kept = []
        
        for memory in self.memories.list(tenant_id):
            # Save original tier before evaluation
            original_tier = memory.tier
            
            # Promotion check: don't increment survivor_count (just checking status)
            decision = self.scheduler.evaluate(memory, now=simulated_now, increment_survivor=False)
            
            if decision == LifecycleDecision.PROMOTE:
                promoted.append({
                    "memory_id": memory.id,
                    "from_tier": original_tier.value,
                    "to_tier": memory.tier.value,
                    "heat_score": memory.heat_score,
                    "survivor_count": memory.survivor_count
                })
                self.memories.put(memory)
            elif decision == LifecycleDecision.DEMOTE:
                demoted.append({
                    "memory_id": memory.id,
                    "from_tier": original_tier.value,
                    "to_tier": memory.tier.value,
                    "heat_score": memory.heat_score
                })
                self.memories.put(memory)
            else:
                kept.append({
                    "memory_id": memory.id,
                    "tier": memory.tier.value,
                    "heat_score": memory.heat_score
                })
        
        return {
            "promoted": promoted,
            "demoted": demoted,
            "kept": kept,
            "summary": {
                "promoted_count": len(promoted),
                "demoted_count": len(demoted),
                "kept_count": len(kept),
                "total_evaluated": len(promoted) + len(demoted) + len(kept)
            }
        }
    
    def run_gc(self, *, tenant_id: str, simulated_now: datetime | None = None) -> dict[str, Any]:
        """Run garbage collection and return report.
        
        Args:
            tenant_id: Tenant identifier
            simulated_now: Optional simulated time for testing (uses real time if None)
        
        Returns:
            Report with GC actions taken
        """
        archived = []
        deleted = []
        
        for memory in self.memories.list(tenant_id):
            # GC: increment survivor_count (memory survived another cycle)
            decision = self.scheduler.evaluate(memory, now=simulated_now, increment_survivor=True)
            
            if decision == LifecycleDecision.ARCHIVE:
                archived.append({
                    "memory_id": memory.id,
                    "tier": memory.tier.value,
                    "heat_score": memory.heat_score
                })
                self.memories.put(memory)
            elif decision == LifecycleDecision.DELETE:
                # Check for dependents
                dependents = self.dependents(tenant_id=tenant_id, memory_id=memory.id)
                if not dependents:
                    deleted.append({
                        "memory_id": memory.id,
                        "tier": memory.tier.value,
                        "heat_score": memory.heat_score
                    })
                    self.memories.delete(memory.id)
        
        return {
            "archived": archived,
            "deleted": deleted,
            "summary": {
                "archived_count": len(archived),
                "deleted_count": len(deleted),
                "total_actions": len(archived) + len(deleted)
            }
        }

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

    def get_processing_status(self, tenant_id: str, memory_id: str) -> ProcessingTask | None:
        """Get async processing status for a memory.
        
        Args:
            tenant_id: Tenant ID
            memory_id: Memory ID
            
        Returns:
            ProcessingTask if async processing is enabled and task exists, None otherwise
        """
        if self.async_processor is None:
            return None
        return self.async_processor.get_status(tenant_id, memory_id)
    
    def get_async_stats(self) -> dict[str, Any] | None:
        """Get async processing statistics.
        
        Returns:
            Stats dict if async processing is enabled, None otherwise
        """
        if self.async_processor is None:
            return None
        return self.async_processor.get_stats()

    def close(self) -> None:
        # Stop async processor first
        if self.async_processor is not None:
            self.async_processor.stop()
        
        # Close stores
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
