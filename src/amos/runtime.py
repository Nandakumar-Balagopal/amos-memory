from __future__ import annotations

import os

from .service import Amos


def build_amos() -> Amos:
    backend = os.getenv("AMOS_STORAGE_BACKEND", "memory").lower()
    if backend == "memory":
        return Amos()
    if backend == "sqlite":
        from .stores.sqlite import SQLiteStorage

        storage = SQLiteStorage(os.getenv("AMOS_SQLITE_PATH", ".amos.sqlite3"))
        return Amos(memories=storage, timeline=storage, graph=storage, events=storage)
    if backend != "hybrid":
        raise ValueError(f"unsupported AMOS_STORAGE_BACKEND: {backend}")

    from .stores.neo4j import Neo4jGraphStore
    from .stores.postgres import PostgresStorage
    from .stores.redis_cache import RedisCachedMemoryStore

    postgres = PostgresStorage(os.getenv("AMOS_POSTGRES_DSN", "postgresql://amos:amos@127.0.0.1:5432/amos"))
    memories = RedisCachedMemoryStore(
        os.getenv("AMOS_REDIS_URL", "redis://127.0.0.1:6379/0"),
        postgres,
        ttl_seconds=int(os.getenv("AMOS_REDIS_TTL_SECONDS", "86400")),
    )
    graph = Neo4jGraphStore(
        os.getenv("AMOS_NEO4J_URI", "bolt://127.0.0.1:7687"),
        os.getenv("AMOS_NEO4J_USER", "neo4j"),
        os.getenv("AMOS_NEO4J_PASSWORD", "amos-password"),
    )
    return Amos(memories=memories, timeline=postgres, graph=graph, events=postgres)
