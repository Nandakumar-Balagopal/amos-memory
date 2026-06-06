from __future__ import annotations

from contextlib import closing
import json
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any

from ..models import DomainEvent, Memory, Relationship, TemporalFact, to_dict
from .codec import event_from_dict, fact_from_dict, memory_from_dict, relationship_from_dict


class SQLiteStorage:
    """Local durable adapter implementing all AMOS storage ports."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._lock = RLock()
        self.initialize()

    def initialize(self) -> None:
        with closing(self._connect()) as connection:
            connection.executescript(SCHEMA_SQL)
            connection.commit()

    def put(self, memory: Memory) -> None:
        data = to_dict(memory)
        params = {
            **data,
            "provenance": json.dumps(data["provenance"], separators=(",", ":")),
            "metadata": json.dumps(data["metadata"], separators=(",", ":")),
        }
        with self._lock, closing(self._connect()) as connection:
            connection.execute(UPSERT_MEMORY_SQL, params)
            connection.commit()

    def get(self, memory_id: str) -> Memory | None:
        row = self._one("SELECT * FROM memories WHERE id = ?", (memory_id,))
        return memory_from_dict(row) if row else None

    def delete(self, memory_id: str) -> bool:
        with self._lock, closing(self._connect()) as connection:
            cursor = connection.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            connection.commit()
            return cursor.rowcount > 0

    def list(self, tenant_id: str) -> list[Memory]:
        rows = self._all("SELECT * FROM memories WHERE tenant_id = ? ORDER BY created_at DESC", (tenant_id,))
        return [memory_from_dict(row) for row in rows]

    def put_fact(self, fact: TemporalFact) -> None:
        with self._lock, closing(self._connect()) as connection:
            connection.execute(UPSERT_FACT_SQL, to_dict(fact))
            connection.commit()

    def facts(self, tenant_id: str, entity: str | None = None, attribute: str | None = None) -> list[TemporalFact]:
        clauses = ["tenant_id = ?"]
        params: list[Any] = [tenant_id]
        if entity is not None:
            clauses.append("entity = ?")
            params.append(entity)
        if attribute is not None:
            clauses.append("attribute = ?")
            params.append(attribute)
        rows = self._all(
            f"SELECT * FROM temporal_facts WHERE {' AND '.join(clauses)} ORDER BY valid_from",
            tuple(params),
        )
        return [fact_from_dict(row) for row in rows]

    def add_relationship(self, relationship: Relationship) -> None:
        data = to_dict(relationship)
        params = {**data, "metadata": json.dumps(data["metadata"], separators=(",", ":"))}
        with self._lock, closing(self._connect()) as connection:
            connection.execute(UPSERT_RELATIONSHIP_SQL, params)
            connection.commit()

    def neighbors(self, tenant_id: str, node: str) -> list[Relationship]:
        rows = self._all(
            """
            SELECT * FROM relationships
            WHERE tenant_id = ? AND (source = ? OR target = ?)
            ORDER BY created_at DESC
            """,
            (tenant_id, node, node),
        )
        return [relationship_from_dict(row) for row in rows]

    def publish(self, event: DomainEvent) -> None:
        data = to_dict(event)
        params = {**data, "payload": json.dumps(data["payload"], separators=(",", ":"))}
        with self._lock, closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO domain_events (id, tenant_id, kind, payload, occurred_at)
                VALUES (:id, :tenant_id, :kind, :payload, :occurred_at)
                """,
                params,
            )
            connection.commit()

    def events(self, tenant_id: str) -> list[DomainEvent]:
        rows = self._all("SELECT * FROM domain_events WHERE tenant_id = ? ORDER BY sequence", (tenant_id,))
        return [event_from_dict(row) for row in rows]

    def health(self) -> bool:
        row = self._one("SELECT 1 AS ok", ())
        return bool(row and row["ok"] == 1)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _one(self, query: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
        with self._lock, closing(self._connect()) as connection:
            row = connection.execute(query, params).fetchone()
            return self._decode(row) if row else None

    def _all(self, query: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        with self._lock, closing(self._connect()) as connection:
            return [self._decode(row) for row in connection.execute(query, params).fetchall()]

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        for key in ("provenance", "metadata", "payload"):
            if key in data and isinstance(data[key], str):
                data[key] = json.loads(data[key] or "{}")
        return data


UPSERT_MEMORY_SQL = """
INSERT INTO memories (
    id, tenant_id, agent_id, content, type, scope, tier, heat_score, importance,
    confidence, retrieval_count, relationship_density, provenance, created_at,
    updated_at, accessed_at, metadata
) VALUES (
    :id, :tenant_id, :agent_id, :content, :type, :scope, :tier, :heat_score,
    :importance, :confidence, :retrieval_count, :relationship_density,
    :provenance, :created_at, :updated_at, :accessed_at, :metadata
)
ON CONFLICT(id) DO UPDATE SET
    tenant_id = excluded.tenant_id,
    agent_id = excluded.agent_id,
    content = excluded.content,
    type = excluded.type,
    scope = excluded.scope,
    tier = excluded.tier,
    heat_score = excluded.heat_score,
    importance = excluded.importance,
    confidence = excluded.confidence,
    retrieval_count = excluded.retrieval_count,
    relationship_density = excluded.relationship_density,
    provenance = excluded.provenance,
    updated_at = excluded.updated_at,
    accessed_at = excluded.accessed_at,
    metadata = excluded.metadata
"""

UPSERT_FACT_SQL = """
INSERT INTO temporal_facts (
    id, tenant_id, entity, attribute, value, valid_from, valid_to,
    confidence, source, memory_id, created_at
) VALUES (
    :id, :tenant_id, :entity, :attribute, :value, :valid_from, :valid_to,
    :confidence, :source, :memory_id, :created_at
)
ON CONFLICT(id) DO UPDATE SET
    value = excluded.value,
    valid_from = excluded.valid_from,
    valid_to = excluded.valid_to,
    confidence = excluded.confidence,
    source = excluded.source,
    memory_id = excluded.memory_id
"""

UPSERT_RELATIONSHIP_SQL = """
INSERT INTO relationships (
    id, tenant_id, source, relation, target, memory_id, confidence, created_at, metadata
) VALUES (
    :id, :tenant_id, :source, :relation, :target, :memory_id, :confidence, :created_at, :metadata
)
ON CONFLICT(id) DO UPDATE SET
    source = excluded.source,
    relation = excluded.relation,
    target = excluded.target,
    memory_id = excluded.memory_id,
    confidence = excluded.confidence,
    metadata = excluded.metadata
"""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    agent_id TEXT,
    content TEXT NOT NULL,
    type TEXT NOT NULL,
    scope TEXT NOT NULL,
    tier TEXT NOT NULL,
    heat_score REAL NOT NULL,
    importance REAL NOT NULL,
    confidence REAL NOT NULL,
    retrieval_count INTEGER NOT NULL,
    relationship_density REAL NOT NULL,
    provenance TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    accessed_at TEXT,
    metadata TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS memories_tenant_tier_idx ON memories (tenant_id, tier);
CREATE INDEX IF NOT EXISTS memories_tenant_type_idx ON memories (tenant_id, type);
CREATE INDEX IF NOT EXISTS memories_heat_idx ON memories (tenant_id, heat_score DESC);

CREATE TABLE IF NOT EXISTS temporal_facts (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    entity TEXT NOT NULL,
    attribute TEXT NOT NULL,
    value TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    confidence REAL NOT NULL,
    source TEXT NOT NULL,
    memory_id TEXT REFERENCES memories(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS facts_timeline_idx ON temporal_facts (tenant_id, entity, attribute, valid_from);
CREATE UNIQUE INDEX IF NOT EXISTS facts_one_current_value_idx
    ON temporal_facts (tenant_id, entity, attribute) WHERE valid_to IS NULL;

CREATE TABLE IF NOT EXISTS relationships (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    source TEXT NOT NULL,
    relation TEXT NOT NULL,
    target TEXT NOT NULL,
    memory_id TEXT,
    confidence REAL NOT NULL,
    created_at TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS relationships_neighbors_idx ON relationships (tenant_id, source, target);

CREATE TABLE IF NOT EXISTS domain_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT UNIQUE NOT NULL,
    tenant_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_tenant_sequence_idx ON domain_events (tenant_id, sequence);
"""
