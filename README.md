# AMOS: Agent Memory Operating System

AMOS is a Prototype V1 memory system for AI agents. It treats memory as a
lifecycle instead of a pile of old chat logs: memories can be admitted, typed,
processed into facts and relationships, retrieved under a token budget, aged,
promoted, archived, explained, and safely forgotten.

The goal is simple: help agents keep useful long-term context while reducing
prompt bloat.

## What V1 Includes

- typed memory objects with provenance and scopes
- heuristic memory admission for deciding whether a turn deserves long-term storage
- automatic deterministic memory processing after writes
- conservative fact and relationship extraction
- temporal facts represented as non-overlapping intervals
- append-only domain events
- heat calculation, decay, promotion, demotion, archive, and deletion decisions
- lifecycle explanations for heat, derived projections, dependencies, and events
- dependency-safe forgetting for memories used as consolidation evidence
- routed lexical retrieval
- semantic-lite retrieval with normalized terms and local similarity scoring
- token-budgeted context compilation
- episodic-to-semantic consolidation
- relationships through a graph-store port
- HTTP JSON API and MCP stdio server
- in-memory, SQLite, and hybrid Postgres/Redis/Neo4j storage modes
- benchmark and long-horizon evaluation scripts

## Backend Modes

| Mode | Best For | Persistence | Setup | Notes |
| --- | --- | --- | --- | --- |
| `memory` | tests, demos, fast experiments | no | none | fastest; data disappears when the process exits |
| `sqlite` | local Codex/user memory | yes | local file | recommended V1 default for real local use |
| `hybrid` | production-style experiments | yes | Docker services | Postgres source of truth, Redis cache, Neo4j graph |

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
    Service --> Retrieval["Semantic-Lite Retrieval Router"]
    Service --> Context["Token-Budgeted Context Compiler"]
    Service --> Temporal["Temporal Truth Engine"]
    Service --> Heat["Heat + Lifecycle Scheduler"]

    Admission --> Remember["Remember / Skip Decision"]
    Pipeline --> Facts["Temporal Facts"]
    Pipeline --> GraphEdges["Graph Relationships"]
    Retrieval --> Context
    Temporal --> Facts
    Heat --> Tiers["Active / Survivor / Durable / Archive"]

    Service --> MemoryMode["Memory Backend<br/>fast, ephemeral"]
    Service --> SQLiteMode["SQLite Backend<br/>local durable V1 default"]
    Service --> HybridMode["Hybrid Backend<br/>production-style"]

    HybridMode --> Postgres["Postgres<br/>memories, facts, events"]
    HybridMode --> Redis["Redis<br/>L1 memory cache"]
    HybridMode --> Neo4j["Neo4j<br/>relationship graph"]

    SQLiteMode --> SQLiteFile[".sqlite3 file<br/>memories, facts, graph, events"]
    MemoryMode --> ProcessMemory["Python process memory"]

    Eval["Long-Horizon Eval"] --> Service
    Eval --> Metrics["Hit Rate<br/>Compression Ratio<br/>Latency<br/>Misses"]
```

## Requirements

- Python 3.12+
- Windows PowerShell examples are shown below
- Docker Desktop only if you want `hybrid` mode

## Install

```powershell
git clone https://github.com/Nandakumar-Balagopal/amos-memory.git
cd amos-memory
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

If you do not use a virtual environment, set `PYTHONPATH=src` before running
modules directly.

## Quick Start: SQLite Mode

SQLite is the recommended V1 local mode because it persists memory without
Docker or external services.

```powershell
$env:AMOS_STORAGE_BACKEND="sqlite"
$env:AMOS_SQLITE_PATH=".amos.sqlite3"
.\.venv\Scripts\python.exe -m amos
```

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

```powershell
$env:AMOS_STORAGE_BACKEND="sqlite"
$env:AMOS_SQLITE_PATH=".amos.sqlite3"
.\.venv\Scripts\python.exe -m amos.mcp
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

with your actual repo path. For local V1 use, prefer the `amos_sqlite` server.
Open or reload this trusted workspace in Codex after editing the config.

Try this in Codex:

```text
Use AMOS to remember that Nandu is building an agent memory operating system.
Then use AMOS to recall what Nandu is building.
```

## Hybrid Mode

Hybrid mode uses:

- Postgres for memories, temporal facts, and domain events
- Redis as a memory cache
- Neo4j for graph relationships

Start the services:

```powershell
docker compose up -d --wait
```

Run AMOS in hybrid mode:

```powershell
$env:AMOS_STORAGE_BACKEND="hybrid"
$env:AMOS_POSTGRES_DSN="postgresql://amos:amos@127.0.0.1:5432/amos"
$env:AMOS_REDIS_URL="redis://127.0.0.1:6379/0"
$env:AMOS_NEO4J_URI="bolt://127.0.0.1:7687"
$env:AMOS_NEO4J_USER="neo4j"
$env:AMOS_NEO4J_PASSWORD="amos-password"
.\.venv\Scripts\python.exe -m amos
```

Service ports:

| Service | Port |
| --- | --- |
| Postgres | `5432` |
| Redis | `6379` |
| Neo4j Bolt | `7687` |
| Neo4j Browser | `http://127.0.0.1:7474` |

Stop hybrid services:

```powershell
docker compose down
```

## Tests

Run the normal unit suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Run live hybrid integration tests with Docker services running:

```powershell
$env:AMOS_STORAGE_BACKEND="hybrid"
$env:AMOS_RUN_INTEGRATION="1"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Benchmarks And Long-Horizon Evaluation

Run the MCP benchmark:

```powershell
.\.venv\Scripts\python.exe scripts\benchmark-mcp.py --backend sqlite
```

Run a long-horizon token-compression evaluation:

```powershell
.\.venv\Scripts\python.exe scripts\long-horizon-eval.py --backend sqlite --policy admitted --include-paraphrases
```

The long-horizon eval reports:

- memories stored
- probe count
- hit rate
- transcript token count
- AMOS context token budget
- compression ratio
- write and context latency
- misses

Generated reports are written to `benchmark-results/`, which is ignored by Git.

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
