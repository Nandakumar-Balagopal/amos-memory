from __future__ import annotations

import os

from .service import Amos


def build_amos() -> Amos:
    backend = os.getenv("AMOS_STORAGE_BACKEND", "memory").lower()
    if backend == "memory":
        return Amos()
    if backend == "postgres":
        from .stores.postgres import PostgresStorage

        postgres = PostgresStorage(os.getenv("AMOS_POSTGRES_DSN", "postgresql://amos:amos@127.0.0.1:5432/amos"))
        return Amos(memories=postgres, timeline=postgres, graph=postgres, events=postgres)
    raise ValueError(f"unsupported AMOS_STORAGE_BACKEND: {backend} (supported: memory, postgres)")

# Made with Bob
