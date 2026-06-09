# AMOS V2 Quick Start Guide

## Prerequisites
- Python 3.12+
- PostgreSQL 14+ with pgvector extension
- Virtual environment activated

## Installation

### 1. Install Dependencies
```bash
# Activate your virtual environment first
source venv-benchmark/bin/activate  # or your venv path

# Install AMOS with all dependencies
pip install -e .

# Verify installation
python -c "import psycopg; import pgvector; import sentence_transformers; print('✅ All dependencies installed')"
```

### 2. Setup Database
```bash
# Run automated setup script
./scripts/setup-database.sh

# Or manually:
psql -U postgres -c "CREATE DATABASE amos;"
psql -U postgres -d amos -c "CREATE EXTENSION vector;"
psql -U postgres -d amos -f migrations/001_initial.sql
psql -U postgres -d amos -f migrations/002_pgvector_hybrid_retrieval.sql
```

### 3. Configure Environment
```bash
export AMOS_STORAGE_BACKEND="postgres"
export AMOS_POSTGRES_DSN="postgresql://amos:amos@localhost:5432/amos"
```

## Running AMOS V2

### Start the Server
```bash
python -m amos
```

The server will start on `http://127.0.0.1:8080`

### Test Hybrid Retrieval
```bash
# Create a memory
curl -X POST http://127.0.0.1:8080/v1/memories \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "demo",
    "content": "Alice is an expert Python developer",
    "type": "FACT",
    "importance": 0.9
  }'

# Search with hybrid retrieval (semantic + heat + recency + graph + diversity)
curl -X POST http://127.0.0.1:8080/v1/recall \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "demo",
    "query": "Who knows Python?",
    "limit": 5
  }'
```

## Running Benchmarks

### V1 vs V2 Comparison
```bash
# Set PostgreSQL connection
export AMOS_POSTGRES_DSN="postgresql://amos:amos@localhost:5432/amos"

# Run benchmark
python scripts/benchmark-hybrid-retrieval.py
```

**Expected Output:**
```
🔬 AMOS V2 Hybrid Retrieval Benchmark
============================================================
🚀 Running Benchmark: MEMORY (V1 Lexical)
  F1 Score: 0.56 (average across queries)
  Latency: 0.19ms (P95)

🚀 Running Benchmark: POSTGRES (V2 Hybrid)
  F1 Score: 0.92 (average across queries)
  Latency: 15.23ms (P95)

📈 V1 vs V2 Comparison
  → Quality improvement: +64.3%
  → Latency overhead: +7,900%
```

## Troubleshooting

### "No module named 'psycopg'"
```bash
pip install -e .
```

### "No module named 'einops'"
```bash
pip install einops
```

### "extension 'vector' is not available"
```bash
# Install pgvector
brew install pgvector  # macOS
# or
sudo apt-get install postgresql-14-pgvector  # Ubuntu

# Enable in database
psql -U postgres -d amos -c "CREATE EXTENSION vector;"
```

### Embedding model download slow
The first run downloads the nomic-embed-text-v1.5 model (~500MB). Subsequent runs use the cached model.

## Architecture

### V2 Hybrid Retrieval Flow
```
User Query
    ↓
Generate Query Embedding (sentence-transformers)
    ↓
PostgreSQL Hybrid Search:
  - 40% Semantic Similarity (pgvector cosine)
  - 25% Heat Score (AMOS lifecycle)
  - 15% Recency Score (30-day decay)
  - 10% Graph Connectivity (relationship count)
  - 10% Type Diversity (varied memory types)
    ↓
Filter: semantic_score > 0.3
    ↓
Sort by hybrid_score DESC
    ↓
Return Top K Results
```

### Storage Modes

| Mode | Use Case | Retrieval | Persistence |
|------|----------|-----------|-------------|
| `memory` | Development, testing | V1 Lexical | No |
| `postgres` | Production | V2 Hybrid | Yes |

## Performance Characteristics

### V1 Lexical Retrieval
- **Quality**: F1 ~0.56 (moderate)
- **Latency**: ~0.2ms (very fast)
- **Best for**: Simple keyword matching, low latency requirements

### V2 Hybrid Retrieval
- **Quality**: F1 ~0.92 (excellent)
- **Latency**: ~15ms (fast)
- **Best for**: Semantic understanding, production use

### Trade-offs
- V2 is 64% more accurate but 80x slower than V1
- Still fast enough for production (<20ms P95)
- Embedding cache reduces overhead for repeated queries

## Next Steps

1. **Phase 2**: Tiny LLM extraction fallback (Qwen2.5-1.5B)
2. **Phase 3**: MMR context compilation for diversity
3. **Phase 4**: Async storage (5,000+ writes/sec)
4. **Phase 5**: Temporal knowledge graph
5. **Phase 6**: Contradiction detection

## Support

- Documentation: See README.md
- Installation: See PGVECTOR_INSTALLATION.md
- Issues: Check error messages and troubleshooting section above