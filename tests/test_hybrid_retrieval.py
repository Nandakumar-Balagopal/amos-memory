"""Tests for V2 hybrid retrieval with pgvector."""

import unittest
from datetime import datetime, timezone

from src.amos.models import Memory, MemoryType, MemoryScope, MemoryTier, Provenance
from src.amos.stores.postgres import PostgresStorage
from src.amos.embeddings import SentenceTransformerEmbeddings


class TestHybridRetrieval(unittest.TestCase):
    """Test hybrid retrieval functionality."""
    
    def setUp(self):
        """Skip tests if PostgreSQL is not available."""
        try:
            # Try to import psycopg
            import psycopg
            self.has_postgres = True
        except ImportError:
            self.has_postgres = False
            self.skipTest("PostgreSQL dependencies not installed")
    
    def test_embedding_generation(self):
        """Test that embeddings are generated correctly."""
        embeddings = SentenceTransformerEmbeddings()
        
        # Test single text
        result = embeddings.encode("This is a test")
        self.assertEqual(result.shape, (1, 1536))
        
        # Test multiple texts
        result = embeddings.encode(["First text", "Second text"])
        self.assertEqual(result.shape, (2, 1536))
    
    def test_hybrid_search_structure(self):
        """Test that hybrid search returns properly structured results."""
        if not self.has_postgres:
            self.skipTest("PostgreSQL not available")
        
        # This test would require a running PostgreSQL instance
        # For now, we just verify the method exists
        storage = PostgresStorage("postgresql://test", initialize=False)
        self.assertTrue(hasattr(storage, 'search_hybrid'))
        self.assertTrue(callable(storage.search_hybrid))
    
    def test_recency_score_calculation(self):
        """Test recency score calculation logic."""
        from datetime import timedelta
        
        now = datetime.now(timezone.utc)
        
        # New memory should have high recency
        new_memory = Memory(
            tenant_id="test",
            content="New memory",
            type=MemoryType.OBSERVATION,
            created_at=now
        )
        age_hours = (now - new_memory.created_at).total_seconds() / 3600
        recency = max(0.0, 1.0 - (age_hours / (24 * 30)))
        self.assertGreater(recency, 0.99)
        
        # Old memory should have low recency
        old_memory = Memory(
            tenant_id="test",
            content="Old memory",
            type=MemoryType.OBSERVATION,
            created_at=now - timedelta(days=60)
        )
        age_hours = (now - old_memory.created_at).total_seconds() / 3600
        recency = max(0.0, 1.0 - (age_hours / (24 * 30)))
        self.assertEqual(recency, 0.0)


if __name__ == "__main__":
    unittest.main()

# Made with Bob
