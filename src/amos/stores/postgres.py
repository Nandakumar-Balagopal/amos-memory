from __future__ import annotations

from typing import Any
import numpy as np

from ..models import DomainEvent, Memory, Relationship, TemporalFact, to_dict
from .codec import event_from_dict, fact_from_dict, memory_from_dict, relationship_from_dict
from ..embeddings import get_default_embeddings, EmbeddingModel


class PostgresStorage:
    """Postgres source of truth for memories, temporal facts, and events with hybrid retrieval."""

    def __init__(
        self,
        dsn: str,
        *,
        initialize: bool = True,
        embedding_model: EmbeddingModel | None = None
    ) -> None:
        try:
            import psycopg
            from psycopg.rows import dict_row
            from psycopg.types.json import Jsonb
        except ImportError as error:
            raise RuntimeError("Install AMOS database dependencies with: pip install -e .") from error
        self._psycopg = psycopg
        self._dict_row = dict_row
        self._jsonb = Jsonb
        self.dsn = dsn
        self.embedding_model = embedding_model or get_default_embeddings()
        if initialize:
            self.initialize()

    def initialize(self) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(SCHEMA_SQL)

    def put(self, memory: Memory) -> None:
        """Store memory with automatic embedding generation."""
        data = to_dict(memory)
        
        # Generate embedding for the memory content
        embedding = self.embedding_model.encode(memory.content)[0]
        
        # Calculate recency score (1.0 for new memories, decays over time)
        from datetime import datetime, timezone
        age_hours = (datetime.now(timezone.utc) - memory.created_at).total_seconds() / 3600
        recency_score = max(0.0, 1.0 - (age_hours / (24 * 30)))  # Decay over 30 days
        
        params = {
            **data,
            "provenance": self._jsonb(data["provenance"]),
            "metadata": self._jsonb(data["metadata"]),
            "embedding": embedding.tolist(),
            "recency_score": recency_score
        }
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(UPSERT_MEMORY_SQL, params)

    def get(self, memory_id: str) -> Memory | None:
        row = self._one("SELECT * FROM memories WHERE id = %s", (memory_id,))
        return memory_from_dict(row) if row else None

    def delete(self, memory_id: str) -> bool:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("DELETE FROM memories WHERE id = %s", (memory_id,))
            return cursor.rowcount > 0

    def list(self, tenant_id: str) -> list[Memory]:
        rows = self._all("SELECT * FROM memories WHERE tenant_id = %s ORDER BY created_at DESC", (tenant_id,))
        return [memory_from_dict(row) for row in rows]
    
    def search_hybrid(
        self,
        tenant_id: str,
        query: str,
        limit: int = 10,
        *,
        semantic_weight: float = 0.40,
        heat_weight: float = 0.25,
        recency_weight: float = 0.15,
        graph_weight: float = 0.10,
        diversity_weight: float = 0.10
    ) -> list[Memory]:
        """Hybrid retrieval combining semantic similarity, heat, recency, graph, and diversity.
        
        Args:
            tenant_id: Tenant identifier
            query: Search query
            limit: Maximum number of results
            semantic_weight: Weight for semantic similarity (default 0.40)
            heat_weight: Weight for heat score (default 0.25)
            recency_weight: Weight for recency score (default 0.15)
            graph_weight: Weight for graph connectivity (default 0.10)
            diversity_weight: Weight for type diversity (default 0.10)
            
        Returns:
            List of memories ranked by hybrid score
        """
        # Generate query embedding
        query_embedding = self.embedding_model.encode(query)[0]
        
        # Hybrid retrieval SQL with pgvector cosine similarity
        sql = """
        WITH memory_scores AS (
            SELECT
                m.id,
                m.tenant_id,
                m.agent_id,
                m.content,
                m.type,
                m.scope,
                m.tier,
                m.heat_score,
                m.importance,
                m.confidence,
                m.retrieval_count,
                m.relationship_density,
                m.provenance,
                m.created_at,
                m.updated_at,
                m.accessed_at,
                m.metadata,
                -- Semantic similarity (cosine distance, 0=identical, 2=opposite)
                (1 - (m.embedding <=> %s::vector)) AS semantic_score,
                -- Recency score (already normalized 0-1)
                COALESCE(m.recency_score, 0.0) AS recency_score,
                -- Graph connectivity (count of relationships)
                (
                    SELECT COUNT(*)::float / 10.0  -- Normalize by dividing by 10
                    FROM relationships r
                    WHERE r.tenant_id = m.tenant_id
                    AND (r.source = m.id::text OR r.target = m.id::text)
                ) AS graph_score,
                -- Type diversity bonus (prefer varied types)
                CASE m.type
                    WHEN 'FACT' THEN 0.3
                    WHEN 'EPISODE' THEN 0.2
                    WHEN 'PREFERENCE' THEN 0.15
                    WHEN 'SKILL' THEN 0.15
                    WHEN 'TASK' THEN 0.1
                    WHEN 'GOAL' THEN 0.1
                    ELSE 0.0
                END AS diversity_score
            FROM memories m
            WHERE m.tenant_id = %s
            AND m.embedding IS NOT NULL
        )
        SELECT
            ms.id, ms.tenant_id, ms.agent_id, ms.content, ms.type, ms.scope, ms.tier,
            ms.heat_score, ms.importance, ms.confidence, ms.retrieval_count,
            ms.relationship_density, ms.provenance, ms.created_at, ms.updated_at,
            ms.accessed_at, ms.metadata,
            ms.semantic_score,
            ms.recency_score,
            ms.graph_score,
            ms.diversity_score,
            (
                (%s * ms.semantic_score) +
                (%s * ms.heat_score) +
                (%s * ms.recency_score) +
                (%s * LEAST(ms.graph_score, 1.0)) +
                (%s * ms.diversity_score)
            ) AS hybrid_score
        FROM memory_scores ms
        WHERE ms.semantic_score > 0.5  -- Filter out dissimilar results (increased from 0.3 for better precision)
        ORDER BY hybrid_score DESC
        LIMIT %s
        """
        
        rows = self._all(
            sql,
            (
                query_embedding.tolist(),
                tenant_id,
                semantic_weight,
                heat_weight,
                recency_weight,
                graph_weight,
                diversity_weight,
                limit
            )
        )
        
        return [memory_from_dict(row) for row in rows]

    def put_fact(self, fact: TemporalFact) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(UPSERT_FACT_SQL, to_dict(fact))

    def facts(self, tenant_id: str, entity: str | None = None, attribute: str | None = None) -> list[TemporalFact]:
        clauses = ["tenant_id = %s"]
        params: list[Any] = [tenant_id]
        if entity is not None:
            clauses.append("entity = %s")
            params.append(entity)
        if attribute is not None:
            clauses.append("attribute = %s")
            params.append(attribute)
        rows = self._all(
            f"SELECT * FROM temporal_facts WHERE {' AND '.join(clauses)} ORDER BY valid_from",
            tuple(params),
        )
        return [fact_from_dict(row) for row in rows]

    def publish(self, event: DomainEvent) -> None:
        data = to_dict(event)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO domain_events (id, tenant_id, kind, payload, occurred_at)
                VALUES (%(id)s, %(tenant_id)s, %(kind)s, %(payload)s, %(occurred_at)s)
                ON CONFLICT (id) DO NOTHING
                """,
                {**data, "payload": self._jsonb(data["payload"])},
            )

    def events(self, tenant_id: str) -> list[DomainEvent]:
        rows = self._all("SELECT * FROM domain_events WHERE tenant_id = %s ORDER BY sequence", (tenant_id,))
        return [event_from_dict(row) for row in rows]

    def add_relationship(self, relationship: Relationship) -> None:
        data = to_dict(relationship)
        params = {**data, "metadata": self._jsonb(data["metadata"])}
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(UPSERT_RELATIONSHIP_SQL, params)

    def neighbors(self, tenant_id: str, node: str) -> list[Relationship]:
        rows = self._all(
            """
            SELECT * FROM relationships
            WHERE tenant_id = %s AND (source = %s OR target = %s)
            ORDER BY created_at DESC
            """,
            (tenant_id, node, node),
        )
        return [relationship_from_dict(row) for row in rows]

    def health(self) -> bool:
        row = self._one("SELECT 1 AS ok", ())
        return bool(row and row["ok"] == 1)

    def _connect(self):
        return self._psycopg.connect(self.dsn, row_factory=self._dict_row, connect_timeout=3)

    def _one(self, query: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchone()

    def _all(self, query: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(query, params)
            return list(cursor.fetchall())


UPSERT_MEMORY_SQL = """
INSERT INTO memories (
    id, tenant_id, agent_id, content, type, scope, tier, heat_score, importance,
    confidence, retrieval_count, relationship_density, provenance, created_at,
    updated_at, accessed_at, metadata, embedding, recency_score
) VALUES (
    %(id)s, %(tenant_id)s, %(agent_id)s, %(content)s, %(type)s, %(scope)s,
    %(tier)s, %(heat_score)s, %(importance)s, %(confidence)s, %(retrieval_count)s,
    %(relationship_density)s, %(provenance)s, %(created_at)s, %(updated_at)s,
    %(accessed_at)s, %(metadata)s, %(embedding)s::vector, %(recency_score)s
)
ON CONFLICT (id) DO UPDATE SET
    tenant_id = EXCLUDED.tenant_id, agent_id = EXCLUDED.agent_id,
    content = EXCLUDED.content, type = EXCLUDED.type, scope = EXCLUDED.scope,
    tier = EXCLUDED.tier, heat_score = EXCLUDED.heat_score,
    importance = EXCLUDED.importance, confidence = EXCLUDED.confidence,
    retrieval_count = EXCLUDED.retrieval_count,
    relationship_density = EXCLUDED.relationship_density,
    provenance = EXCLUDED.provenance, updated_at = EXCLUDED.updated_at,
    accessed_at = EXCLUDED.accessed_at, metadata = EXCLUDED.metadata,
    embedding = EXCLUDED.embedding, recency_score = EXCLUDED.recency_score
"""

UPSERT_FACT_SQL = """
INSERT INTO temporal_facts (
    id, tenant_id, entity, attribute, value, valid_from, valid_to,
    confidence, source, memory_id, created_at
) VALUES (
    %(id)s, %(tenant_id)s, %(entity)s, %(attribute)s, %(value)s,
    %(valid_from)s, %(valid_to)s, %(confidence)s, %(source)s,
    %(memory_id)s, %(created_at)s
)
ON CONFLICT (id) DO UPDATE SET
    value = EXCLUDED.value, valid_from = EXCLUDED.valid_from,
    valid_to = EXCLUDED.valid_to, confidence = EXCLUDED.confidence,
    source = EXCLUDED.source, memory_id = EXCLUDED.memory_id
"""

UPSERT_RELATIONSHIP_SQL = """
INSERT INTO relationships (
    id, tenant_id, source, relation, target, memory_id, confidence, created_at, metadata
) VALUES (
    %(id)s, %(tenant_id)s, %(source)s, %(relation)s, %(target)s,
    %(memory_id)s, %(confidence)s, %(created_at)s, %(metadata)s
)
ON CONFLICT (id) DO UPDATE SET
    source = EXCLUDED.source, relation = EXCLUDED.relation, target = EXCLUDED.target,
    memory_id = EXCLUDED.memory_id, confidence = EXCLUDED.confidence, metadata = EXCLUDED.metadata
"""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS memories (
    id UUID PRIMARY KEY, tenant_id TEXT NOT NULL, agent_id TEXT, content TEXT NOT NULL,
    type TEXT NOT NULL, scope TEXT NOT NULL, tier TEXT NOT NULL,
    heat_score DOUBLE PRECISION NOT NULL, importance DOUBLE PRECISION NOT NULL,
    confidence DOUBLE PRECISION NOT NULL, retrieval_count INTEGER NOT NULL,
    relationship_density DOUBLE PRECISION NOT NULL,
    survivor_count INTEGER NOT NULL DEFAULT 0,
    provenance JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL, accessed_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding vector(384),
    recency_score DOUBLE PRECISION DEFAULT 0.0
);
CREATE INDEX IF NOT EXISTS memories_tenant_tier_idx ON memories (tenant_id, tier);
CREATE INDEX IF NOT EXISTS memories_tenant_type_idx ON memories (tenant_id, type);
CREATE INDEX IF NOT EXISTS memories_heat_idx ON memories (tenant_id, heat_score DESC);
CREATE INDEX IF NOT EXISTS memories_embedding_idx ON memories USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE TABLE IF NOT EXISTS temporal_facts (
    id UUID PRIMARY KEY, tenant_id TEXT NOT NULL, entity TEXT NOT NULL,
    attribute TEXT NOT NULL, value TEXT NOT NULL, valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ, confidence DOUBLE PRECISION NOT NULL, source TEXT NOT NULL,
    memory_id UUID REFERENCES memories(id) ON DELETE SET NULL, created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS facts_timeline_idx ON temporal_facts (tenant_id, entity, attribute, valid_from);
CREATE UNIQUE INDEX IF NOT EXISTS facts_one_current_value_idx
    ON temporal_facts (tenant_id, entity, attribute) WHERE valid_to IS NULL;
CREATE TABLE IF NOT EXISTS relationships (
    id UUID PRIMARY KEY, tenant_id TEXT NOT NULL, source TEXT NOT NULL,
    relation TEXT NOT NULL, target TEXT NOT NULL,
    memory_id UUID REFERENCES memories(id) ON DELETE SET NULL,
    confidence DOUBLE PRECISION NOT NULL, created_at TIMESTAMPTZ NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS relationships_tenant_source_idx ON relationships (tenant_id, source);
CREATE INDEX IF NOT EXISTS relationships_tenant_target_idx ON relationships (tenant_id, target);
CREATE TABLE IF NOT EXISTS domain_events (
    sequence BIGSERIAL UNIQUE NOT NULL, id UUID PRIMARY KEY, tenant_id TEXT NOT NULL,
    kind TEXT NOT NULL, payload JSONB NOT NULL, occurred_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS events_tenant_sequence_idx ON domain_events (tenant_id, sequence);
"""
