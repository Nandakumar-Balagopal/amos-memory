# pgvector Installation Guide

## Problem

The error `extension "vector" is not available` means pgvector is not installed on your PostgreSQL server.

## Solution: Install pgvector

### macOS (Homebrew)

```bash
# Install pgvector
brew install pgvector

# Restart PostgreSQL
brew services restart postgresql@15
```

### Alternative: Manual Installation (macOS)

If Homebrew doesn't work:

```bash
# Clone pgvector
cd /tmp
git clone --branch v0.7.0 https://github.com/pgvector/pgvector.git
cd pgvector

# Build and install
make
make install  # May need sudo

# Restart PostgreSQL
brew services restart postgresql@15
```

### Verify Installation

```bash
# Check if pgvector is available
psql -U postgres -c "SELECT * FROM pg_available_extensions WHERE name = 'vector';"

# Should show:
#  name  | default_version | installed_version | comment
# -------+-----------------+-------------------+---------
# vector | 0.7.0           |                   | vector data type and ivfflat and hnsw access methods
```

### Then Run Setup Again

```bash
./scripts/setup-database.sh
```

## Docker Alternative

If you prefer Docker (includes pgvector):

```bash
# Stop local PostgreSQL
brew services stop postgresql@15

# Run PostgreSQL with pgvector
docker run -d \
  --name amos-postgres \
  -p 5432:5432 \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_DB=postgres \
  pgvector/pgvector:pg15

# Wait a few seconds for startup
sleep 5

# Run setup
./scripts/setup-database.sh
```

## Troubleshooting

### Error: "Could not open extension control file"

This means pgvector is not installed. Follow the installation steps above.

### Error: "access method 'hnsw' does not exist"

This means pgvector is installed but not enabled. The setup script will enable it automatically.

### Error: "type 'vector' does not exist"

This means the vector extension is not created in your database. The setup script handles this.

## What pgvector Does

pgvector adds:
- `vector` data type for embeddings
- `<->` operator for cosine distance
- HNSW index for fast similarity search
- IVFFlat index for approximate search

## Why We Need It

AMOS V2 uses pgvector for:
1. **Semantic search** - Find similar memories by meaning
2. **Hybrid retrieval** - Combine semantic + heat + recency
3. **Fast queries** - HNSW index for sub-5ms searches
4. **No second database** - Everything in PostgreSQL

## Verification

After installation, verify:

```bash
# Connect to database
psql -U amos -d amos

# Check extension
SELECT * FROM pg_extension WHERE extname = 'vector';

# Should show:
#  oid  | extname | extowner | extnamespace | extrelocatable | extversion | extconfig | extcondition
# ------+---------+----------+--------------+----------------+------------+-----------+--------------
# 16384 | vector  |       10 |         2200 | t              | 0.7.0      |           |

# Check vector type
SELECT typname FROM pg_type WHERE typname = 'vector';

# Should show:
#  typname
# ---------
#  vector

# Exit
\q
```

## Next Steps

Once pgvector is installed:

1. ✅ Run `./scripts/setup-database.sh`
2. ✅ Verify tables created (should be 4+)
3. ✅ Set environment variables
4. ✅ Test AMOS with PostgreSQL backend

```bash
export AMOS_POSTGRES_DSN="postgresql://amos:amos@localhost:5432/amos"
export AMOS_STORAGE_BACKEND="postgres"