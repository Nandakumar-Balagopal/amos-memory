-- Migration 002: Add pgvector support and hybrid retrieval
-- This migration adds semantic search capabilities while maintaining existing functionality

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Add embedding column to memories table
ALTER TABLE memories ADD COLUMN IF NOT EXISTS embedding vector(1536);

-- Create HNSW index for fast similarity search
-- m=16 and ef_construction=64 are recommended defaults for good recall/speed balance
CREATE INDEX IF NOT EXISTS idx_memories_embedding_hnsw 
ON memories USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Composite index for hybrid queries (tenant + tier + heat)
-- This allows efficient filtering before vector search
CREATE INDEX IF NOT EXISTS idx_memories_tenant_tier_heat 
ON memories (tenant_id, tier, heat_score DESC);

-- Add final_score column for caching hybrid scores
ALTER TABLE memories ADD COLUMN IF NOT EXISTS final_score DOUBLE PRECISION DEFAULT 0.0;

-- Index for final_score ordering
CREATE INDEX IF NOT EXISTS idx_memories_final_score 
ON memories (tenant_id, final_score DESC);

-- Add columns for tracking extraction source
ALTER TABLE memories ADD COLUMN IF NOT EXISTS extraction_source TEXT DEFAULT 'regex';
ALTER TABLE memories ADD COLUMN IF NOT EXISTS extraction_latency_ms DOUBLE PRECISION DEFAULT 0.0;

-- Partitioning setup for time-based partitions
-- Note: Existing data will remain in the main table
-- New inserts should go to partitioned tables

-- Create partitioned table structure (if not already partitioned)
-- This is a non-breaking change - existing table continues to work
DO $$
BEGIN
    -- Check if table is already partitioned
    IF NOT EXISTS (
        SELECT 1 FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = 'memories' AND c.relkind = 'p'
    ) THEN
        -- Table is not partitioned yet
        -- We'll add partitioning in a future migration to avoid downtime
        RAISE NOTICE 'Table is not partitioned yet. Will partition in future migration.';
    END IF;
END $$;

-- Add indexes for relationship queries (for graph traversal)
CREATE INDEX IF NOT EXISTS idx_relationships_tenant_source 
ON relationships (tenant_id, source);

CREATE INDEX IF NOT EXISTS idx_relationships_tenant_target 
ON relationships (tenant_id, target);

-- Add index for temporal fact queries
CREATE INDEX IF NOT EXISTS idx_temporal_facts_memory_id 
ON temporal_facts (memory_id) WHERE memory_id IS NOT NULL;

-- Add materialized view for hot memories (ACTIVE tier)
-- This speeds up frequent queries for active memories
CREATE MATERIALIZED VIEW IF NOT EXISTS hot_memories AS
SELECT 
    id,
    tenant_id,
    content,
    type,
    heat_score,
    embedding,
    final_score,
    created_at,
    accessed_at
FROM memories
WHERE tier = 'ACTIVE'
ORDER BY tenant_id, heat_score DESC;

-- Index on materialized view
CREATE INDEX IF NOT EXISTS idx_hot_memories_tenant_heat 
ON hot_memories (tenant_id, heat_score DESC);

-- Refresh function for materialized view
CREATE OR REPLACE FUNCTION refresh_hot_memories()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY hot_memories;
END;
$$ LANGUAGE plpgsql;

-- Comments for documentation
COMMENT ON COLUMN memories.embedding IS 'Vector embedding for semantic search (1536 dimensions for OpenAI/nomic-embed-text)';
COMMENT ON COLUMN memories.final_score IS 'Cached hybrid score: 0.4*semantic + 0.25*heat + 0.15*recency + 0.1*graph + 0.1*type';
COMMENT ON COLUMN memories.extraction_source IS 'Source of fact extraction: regex, fuzzy, tiny_llm, full_llm';
COMMENT ON COLUMN memories.extraction_latency_ms IS 'Time taken for fact extraction in milliseconds';
COMMENT ON INDEX idx_memories_embedding_hnsw IS 'HNSW index for fast approximate nearest neighbor search';
COMMENT ON MATERIALIZED VIEW hot_memories IS 'Cached view of ACTIVE tier memories for fast access';

-- Made with Bob
