$ErrorActionPreference = "Stop"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker Desktop is required. Install it, start it, then run this script again."
}

docker compose up -d --wait

$env:AMOS_STORAGE_BACKEND = "hybrid"
$env:AMOS_POSTGRES_DSN = "postgresql://amos:amos@127.0.0.1:5432/amos"
$env:AMOS_REDIS_URL = "redis://127.0.0.1:6379/0"
$env:AMOS_NEO4J_URI = "bolt://127.0.0.1:7687"
$env:AMOS_NEO4J_USER = "neo4j"
$env:AMOS_NEO4J_PASSWORD = "amos-password"

.\.venv\Scripts\python.exe -m amos
