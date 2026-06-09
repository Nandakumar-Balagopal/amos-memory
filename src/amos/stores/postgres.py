from __future__ import annotations

from typing import Any

from ..models import DomainEvent, Memory, Relationship, TemporalFact, to_dict
from .codec import event_from_dict, fact_from_dict, memory_from_dict, relationship_from_dict


class PostgresStorage:
    """Postgres source of truth for memories, temporal facts, and events."""

    def __init__(self, dsn: str, *, initialize: bool = True) -> None:
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
        if initialize:
            self.initialize()

    def initialize(self) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(SCHEMA_SQL)

    def put(self, memory: Memory) -> None:
        data = to_dict(memory)
        params = {**data, "provenance": self._jsonb(data["provenance"]), "metadata": self._jsonb(data["metadata"])}
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
    updated_at, accessed_at, metadata
) VALUES (
    %(id)s, %(tenant_id)s, %(agent_id)s, %(content)s, %(type)s, %(scope)s,
    %(tier)s, %(heat_score)s, %(importance)s, %(confidence)s, %(retrieval_count)s,
    %(relationship_density)s, %(provenance)s, %(created_at)s, %(updated_at)s,
    %(accessed_at)s, %(metadata)s
)
ON CONFLICT (id) DO UPDATE SET
    tenant_id = EXCLUDED.tenant_id, agent_id = EXCLUDED.agent_id,
    content = EXCLUDED.content, type = EXCLUDED.type, scope = EXCLUDED.scope,
    tier = EXCLUDED.tier, heat_score = EXCLUDED.heat_score,
    importance = EXCLUDED.importance, confidence = EXCLUDED.confidence,
    retrieval_count = EXCLUDED.retrieval_count,
    relationship_density = EXCLUDED.relationship_density,
    provenance = EXCLUDED.provenance, updated_at = EXCLUDED.updated_at,
    accessed_at = EXCLUDED.accessed_at, metadata = EXCLUDED.metadata
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
    provenance JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL, accessed_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS memories_tenant_tier_idx ON memories (tenant_id, tier);
CREATE INDEX IF NOT EXISTS memories_tenant_type_idx ON memories (tenant_id, type);
CREATE INDEX IF NOT EXISTS memories_heat_idx ON memories (tenant_id, heat_score DESC);
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
