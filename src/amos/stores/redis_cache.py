from __future__ import annotations

import json

from ..models import Memory, to_dict
from ..ports import MemoryStore
from .codec import memory_from_dict


class RedisCachedMemoryStore:
    """Write-through Redis L1 backed by an authoritative memory store."""

    def __init__(self, url: str, source: MemoryStore, *, ttl_seconds: int = 86_400) -> None:
        try:
            import redis
        except ImportError as error:
            raise RuntimeError("Install AMOS database dependencies with: pip install -e .") from error
        self.client = redis.Redis.from_url(url, decode_responses=True)
        self.source = source
        self.ttl_seconds = ttl_seconds

    def put(self, memory: Memory) -> None:
        self.source.put(memory)
        try:
            self._cache(memory)
        except Exception:
            pass

    def get(self, memory_id: str) -> Memory | None:
        try:
            raw = self.client.get(self._key(memory_id))
        except Exception:
            raw = None
        if raw:
            return memory_from_dict(json.loads(raw))
        memory = self.source.get(memory_id)
        if memory:
            try:
                self._cache(memory)
            except Exception:
                pass
        return memory

    def delete(self, memory_id: str) -> bool:
        deleted = self.source.delete(memory_id)
        try:
            self.client.delete(self._key(memory_id))
        except Exception:
            pass
        return deleted

    def list(self, tenant_id: str) -> list[Memory]:
        memories = self.source.list(tenant_id)
        try:
            if memories:
                with self.client.pipeline(transaction=False) as pipeline:
                    for memory in memories:
                        pipeline.setex(self._key(memory.id), self.ttl_seconds, json.dumps(to_dict(memory)))
                    pipeline.execute()
        except Exception:
            pass
        return memories

    def health(self) -> bool:
        try:
            return bool(self.client.ping())
        except Exception:
            return False

    def close(self) -> None:
        close = getattr(self.client, "close", None)
        if close:
            close()

    def _cache(self, memory: Memory) -> None:
        self.client.setex(self._key(memory.id), self.ttl_seconds, json.dumps(to_dict(memory)))

    @staticmethod
    def _key(memory_id: str) -> str:
        return f"amos:memory:{memory_id}"
