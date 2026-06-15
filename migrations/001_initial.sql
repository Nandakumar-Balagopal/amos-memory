CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS memories (
    id UUID PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    agent_id TEXT,
    content TEXT NOT NULL,
    type TEXT NOT NULL,
    scope TEXT NOT NULL,
    tier TEXT NOT NULL,
    heat_score DOUBLE PRECISION NOT NULL,
    importance DOUBLE PRECISION NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    retrieval_count INTEGER NOT NULL,
    relationship_density DOUBLE PRECISION NOT NULL,
    survivor_count INTEGER NOT NULL DEFAULT 0,
    provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    accessed_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding vector(384),
    recency_score DOUBLE PRECISION DEFAULT 0.0
);

CREATE INDEX IF NOT EXISTS memories_tenant_tier_idx ON memories (tenant_id, tier);
CREATE INDEX IF NOT EXISTS memories_tenant_type_idx ON memories (tenant_id, type);
CREATE INDEX IF NOT EXISTS memories_heat_idx ON memories (tenant_id, heat_score DESC);
CREATE INDEX IF NOT EXISTS memories_embedding_idx ON memories USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE TABLE IF NOT EXISTS temporal_facts (
    id UUID PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    entity TEXT NOT NULL,
    attribute TEXT NOT NULL,
    value TEXT NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    confidence DOUBLE PRECISION NOT NULL,
    source TEXT NOT NULL,
    memory_id UUID REFERENCES memories(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS facts_timeline_idx ON temporal_facts (tenant_id, entity, attribute, valid_from);
CREATE UNIQUE INDEX IF NOT EXISTS facts_one_current_value_idx
    ON temporal_facts (tenant_id, entity, attribute) WHERE valid_to IS NULL;

CREATE TABLE IF NOT EXISTS relationships (
    id UUID PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    source TEXT NOT NULL,
    relation TEXT NOT NULL,
    target TEXT NOT NULL,
    memory_id UUID REFERENCES memories(id) ON DELETE SET NULL,
    confidence DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS relationships_tenant_source_idx ON relationships (tenant_id, source);
CREATE INDEX IF NOT EXISTS relationships_tenant_target_idx ON relationships (tenant_id, target);

CREATE TABLE IF NOT EXISTS domain_events (
    sequence BIGSERIAL UNIQUE NOT NULL,
    id UUID PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS events_tenant_sequence_idx ON domain_events (tenant_id, sequence);
