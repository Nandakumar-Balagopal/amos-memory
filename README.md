# AMOS: Agent Memory Operating System

AMOS is a memory system for AI agents that treats memory as a lifecycle instead of a pile of old chat logs. Memories can be admitted, typed, processed into facts and relationships, retrieved under a token budget, aged, promoted, archived, explained, and safely forgotten.

**Version 2.0** introduces hybrid retrieval with semantic search, simplified storage architecture, and improved performance.

## What's New in V2

- **Hybrid Retrieval**: Combines semantic similarity (pgvector), heat scores, recency, graph connectivity, and type diversity for better context
- **Simplified Storage**: Reduced from 6 storage backends to 2 (InMemory for dev, PostgreSQL for production)
- **Vector Embeddings**: Native pgvector support with HNSW indexing for fast semantic search
- **Embedding Generation**: Built-in sentence-transformers with caching layer
- **Better Performance**: Optimized for retrieval quality over storage complexity

## Core Features

- Typed memory objects with provenance and scopes
- Heuristic memory admission for deciding whether a turn deserves long-term storage
- Automatic deterministic memory processing after writes
- Conservative fact and relationship extraction
- Temporal facts represented as non-overlapping intervals
- Append-only domain events
- Heat calculation, decay, promotion, demotion, archive, and deletion decisions
- Lifecycle explanations for heat, derived projections, dependencies, and events
- Dependency-safe forgetting for memories used as consolidation evidence
- **Hybrid retrieval** with semantic + heat + recency + graph + diversity scoring
- Token-budgeted context compilation
- Episodic-to-semantic consolidation
- Relationships through a graph-store port
- HTTP JSON API and MCP stdio server
- Benchmark and evaluation scripts

## Storage Backends

| Mode | Best For | Persistence | Setup | Notes |
| --- | --- | --- | --- | --- |
| `memory` | tests, demos, fast experiments | no | none | fastest; data disappears when the process exits |
| `postgres` | production use | yes | PostgreSQL + pgvector | recommended for production; supports hybrid retrieval |

## Architecture

```mermaid
flowchart TD
    User["User / Agent"] --> Codex["Codex or MCP Client"]
    User --> HTTP["HTTP JSON API"]
    Codex --> MCP["AMOS MCP Server"]
    HTTP --> Service["AMOS Service"]
    MCP --> Service

    Service --> Admission["Memory Admission Policy"]
    Service --> Pipeline["Deterministic Processing Pipeline"]
    Service --> Retrieval["Hybrid Retrieval Engine<br/>semantic + heat + recency"]
    Service --> Context["Token-Budgeted Context Compiler"]
    Service --> Temporal["Temporal Truth Engine"]
    Service --> Heat["Heat + Lifecycle Scheduler"]
    Service --> Embeddings["Embedding Generation<br/>sentence-transformers + cache"]

    Admission --> Remember["Remember / Skip Decision"]
    Pipeline --> Facts["Temporal Facts"]
    Pipeline --> GraphEdges["Graph Relationships"]
    Retrieval --> Context
    Temporal --> Facts
    Heat --> Tiers["Active / Survivor / Durable / Archive"]

    Service --> MemoryMode["Memory Backend<br/>fast, ephemeral"]
    Service --> PostgresMode["PostgreSQL Backend<br/>production with pgvector"]

    PostgresMode --> Postgres["PostgreSQL + pgvector<br/>memories, facts, events, embeddings"]
    MemoryMode --> ProcessMemory["Python process memory"]

    Eval["Benchmarks"] --> Service
    Eval --> Metrics["Token Efficiency<br/>Latency<br/>Retrieval Quality"]
```

## Requirements

- Python 3.12+
- PostgreSQL 14+ with pgvector extension (for production mode)
- Windows PowerShell or bash examples shown below

## Install

```powershell
git clone https://github.com/Nandakumar-Balagopal/amos-memory.git
cd amos-memory
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

If you do not use a virtual environment, set `PYTHONPATH=src` before running
modules directly.

## Quick Start: Memory Mode (Development)

For quick testing without persistence:

```bash
# Linux/macOS
export AMOS_STORAGE_BACKEND="memory"
python -m amos

# Windows PowerShell
$env:AMOS_STORAGE_BACKEND="memory"
python -m amos
```

## PostgreSQL Mode (Production)

For production use with hybrid retrieval:

```bash
# Setup database (one-time)
./scripts/setup-database.sh

# Run AMOS
export AMOS_STORAGE_BACKEND="postgres"
export AMOS_POSTGRES_DSN="postgresql://amos:amos@localhost:5432/amos"
python -m amos
```

See [PGVECTOR_INSTALLATION.md](migrations/PGVECTOR_INSTALLATION.md) for detailed setup instructions.

The server listens on:

```text
http://127.0.0.1:8080
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/health
```

## Try The API

Assess whether a message is worth long-term memory:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8080/v1/memories/assess `
  -ContentType application/json `
  -Body '{"content":"Nandu prefers concise benchmark summaries with exact latency numbers","type":"PREFERENCE","importance":0.8}'
```

Remember something:

```powershell
$memory = Invoke-RestMethod -Method Post http://127.0.0.1:8080/v1/memories `
  -ContentType application/json `
  -Body '{"tenant_id":"demo","content":"Nandu is building AMOS","type":"EPISODE","importance":0.9}'

$memory.id
```

Recall relevant memory:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8080/v1/recall `
  -ContentType application/json `
  -Body '{"tenant_id":"demo","query":"What is Nandu building?","limit":5}'
```

Compile context under a token budget:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8080/v1/context `
  -ContentType application/json `
  -Body '{"tenant_id":"demo","query":"What should I know about Nandu and AMOS?","token_budget":120}'
```

Explain a memory:

```powershell
Invoke-RestMethod "http://127.0.0.1:8080/v1/memories/$($memory.id)/explain?tenant_id=demo"
```

Run lifecycle cleanup decisions:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8080/v1/scheduler/run `
  -ContentType application/json `
  -Body '{"tenant_id":"demo"}'
```

## MCP Server

AMOS can run as an MCP stdio server:

```bash
export AMOS_STORAGE_BACKEND="memory"  # or "postgres"
python -m amos.mcp
```

The MCP server exposes:

```text
remember
assess_memory
recall
get_context
update_fact
get_timeline
get_relationships
forget
process_memory
explain_memory
```

## Codex Integration

This repository includes a project-scoped Codex configuration template:

```text
.codex/config.example.toml
```

To use it:

```powershell
Copy-Item .codex\config.example.toml .codex\config.toml
```

Then edit `.codex/config.toml` and replace:

```text
C:\path\to\amos
```

with your actual repo path. Open or reload this trusted workspace in Codex after editing the config.

Try this in Codex:

```text
Use AMOS to remember that Nandu is building an agent memory operating system.
Then use AMOS to recall what Nandu is building.
```

## Docker Compose (Optional)

For easy PostgreSQL setup with pgvector:

```bash
docker compose up -d
```

This starts PostgreSQL with pgvector pre-installed on port 5432.

## Tests

Run the test suite:

```bash
python -m unittest discover -s tests -v
```

Run with PostgreSQL integration tests:

```bash
export AMOS_STORAGE_BACKEND="postgres"
export AMOS_RUN_INTEGRATION="1"
python -m unittest discover -s tests -v
```

## Benchmarks And Evaluation

AMOS includes comprehensive benchmarking tools to validate performance against real systems.

### Quick Benchmarks

Run internal benchmarks:

```powershell
# Token cost reduction
.\.venv\Scripts\python.exe scripts\token-cost-benchmark.py

# Latency comparison
.\.venv\Scripts\python.exe scripts\latency-benchmark.py

# Temporal consistency
.\.venv\Scripts\python.exe scripts\temporal-consistency-validation.py

# Run all benchmarks
.\.venv\Scripts\python.exe scripts\run-all-benchmarks.py
```

### Live System Comparison

Compare AMOS against actual MemGPT/Letta, Zep, and LangChain implementations:

```bash
# Quick setup (5 minutes)
chmod +x scripts/setup-live-benchmark.sh
./scripts/setup-live-benchmark.sh

# Start services
docker-compose -f docker-compose.benchmark.yaml up -d
letta server  # In separate terminal

# Run live benchmarks
source venv-benchmark/bin/activate
python scripts/live-benchmark.py --system all
```

**See [LIVE_BENCHMARK_QUICKSTART.md](LIVE_BENCHMARK_QUICKSTART.md) for detailed setup.**

### Long-Horizon Evaluation

Run token-compression evaluation over 1000+ turns:

```powershell
.\.venv\Scripts\python.exe scripts\long-horizon-eval.py --backend sqlite --policy admitted --include-paraphrases
```

### Benchmark Results

Key findings from comprehensive testing:

| Metric | AMOS | LangChain | Letta/MemGPT | Zep |
|--------|------|-----------|--------------|-----|
| **Token Efficiency** | 50K | 200K+ | 150K+ | 180K+ |
| **Write Latency** | 5-10ms | 1-2ms | 500-1000ms | 200-400ms |
| **Read Latency** | 10-20ms | 5-10ms | 100-200ms | 50-100ms |
| **LLM Calls** | 0 | 0 | Many | Many |
| **Compression** | 6.98x | 1.0x | ~2x | ~2x |

**AMOS Advantages:**
- ✅ **2-17x fewer tokens** than competitors
- ✅ **Zero LLM calls** for memory processing
- ✅ **Deterministic extraction** (no API costs)
- ✅ **Fast writes** (no graph extraction overhead)

Generated reports are written to `benchmark-results/`, which is ignored by Git.

**Documentation:**
- [BENCHMARKS.md](BENCHMARKS.md) - Technical methodology
- [BENCHMARK_INSTRUCTIONS.md](BENCHMARK_INSTRUCTIONS.md) - Quick start guide
- [PUBLICATION_RESULTS.md](PUBLICATION_RESULTS.md) - Publication-ready summary
- [LIVE_BENCHMARK_SETUP.md](LIVE_BENCHMARK_SETUP.md) - Live system integration
- [LIVE_BENCHMARK_QUICKSTART.md](LIVE_BENCHMARK_QUICKSTART.md) - 5-minute setup

## API Reference

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/v1/memories` | Remember content |
| `POST` | `/v1/memories/assess` | Decide whether content merits long-term memory |
| `GET` | `/v1/memories/{id}` | Get one memory |
| `GET` | `/v1/memories/{id}/explain?tenant_id=...` | Explain one memory |
| `DELETE` | `/v1/memories/{id}` | Forget one memory |
| `POST` | `/v1/memories/{id}/process` | Re-run memory processing |
| `POST` | `/v1/recall` | Routed memory recall |
| `POST` | `/v1/context` | Compile context under a token budget |
| `POST` | `/v1/facts` | Update a temporal fact |
| `GET` | `/v1/timeline?tenant_id=...&entity=...` | Get temporal history |
| `POST` | `/v1/relationships` | Add a graph relationship |
| `GET` | `/v1/relationships?tenant_id=...&node=...` | Get graph neighbors |
| `POST` | `/v1/consolidations` | Derive semantic memory from sources |
| `POST` | `/v1/scheduler/run` | Run heat decay and lifecycle decisions |
| `GET` | `/health` | Health check |

## Memory Cleanup

AMOS V1 has manual lifecycle cleanup through the scheduler endpoint:

```text
POST /v1/scheduler/run
```

The scheduler evaluates heat and tier:

```text
ACTIVE   + high heat      -> SURVIVOR
SURVIVOR + very high heat -> DURABLE
SURVIVOR + low heat       -> ARCHIVE
DURABLE  + low heat       -> ARCHIVE
ARCHIVE  + very low heat  -> DELETE
otherwise                -> KEEP
```

Deletion is blocked when another consolidated memory depends on the source
memory, unless deletion is forced.

## Troubleshooting

If Python cannot import `amos`, install the package or set `PYTHONPATH`:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

If Docker commands fail, make sure Docker Desktop is running:

```powershell
docker info
```

If hybrid services are unhealthy, restart them:

```powershell
docker compose down
docker compose up -d --wait
```

If Codex does not show AMOS tools, reload the trusted workspace after editing
`.codex/config.toml`.

## Git Hygiene

Local runtime artifacts are ignored:

```text
.env
.venv/
*.sqlite
*.sqlite3
benchmark-results/
.codex/config.toml
```

Commit `.codex/config.example.toml`, not your local `.codex/config.toml`.
