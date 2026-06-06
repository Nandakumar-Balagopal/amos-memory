from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from amos.models import MemoryType, Provenance, to_dict
from amos.runtime import build_amos
from amos.service import Amos
from amos.stores.codec import memory_from_dict
from amos.stores.memory import InMemoryStorage
from amos.stores.redis_cache import RedisCachedMemoryStore
from amos.stores.sqlite import SQLiteStorage


class FakePipeline:
    def __init__(self, client):
        self.client = client
        self.commands = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def setex(self, key, ttl, value):
        self.commands.append((key, ttl, value))

    def execute(self):
        for key, ttl, value in self.commands:
            self.client.setex(key, ttl, value)


class FakeRedis:
    def __init__(self):
        self.values = {}

    def setex(self, key, ttl, value):
        self.values[key] = value

    def get(self, key):
        return self.values.get(key)

    def delete(self, key):
        self.values.pop(key, None)

    def pipeline(self, transaction=False):
        return FakePipeline(self)

    def ping(self):
        return True


class BrokenRedis(FakeRedis):
    def setex(self, key, ttl, value):
        raise ConnectionError("redis unavailable")

    def get(self, key):
        raise ConnectionError("redis unavailable")

    def delete(self, key):
        raise ConnectionError("redis unavailable")

    def ping(self):
        raise ConnectionError("redis unavailable")


class StorageTests(unittest.TestCase):
    def test_memory_codec_round_trip(self) -> None:
        memory = Amos().remember(
            tenant_id="tenant",
            content="Persistent memory",
            type=MemoryType.FACT,
            provenance=Provenance(source="test", source_memory_ids=["source"]),
        )

        decoded = memory_from_dict(json.loads(json.dumps(to_dict(memory))))

        self.assertEqual(decoded, memory)

    def test_redis_cache_reads_through_and_writes_through(self) -> None:
        source = InMemoryStorage()
        fake = FakeRedis()
        with patch("redis.Redis.from_url", return_value=fake):
            cache = RedisCachedMemoryStore("redis://unused", source)
        memory = Amos().remember(tenant_id="tenant", content="Cache me")

        cache.put(memory)
        source.delete(memory.id)
        cached = cache.get(memory.id)

        self.assertEqual(cached.id, memory.id)
        self.assertTrue(cache.health())

    def test_runtime_defaults_to_in_memory(self) -> None:
        with patch.dict(os.environ, {"AMOS_STORAGE_BACKEND": "memory"}):
            amos = build_amos()

        memory = amos.remember(tenant_id="tenant", content="Runtime memory")
        self.assertEqual(amos.get_memory(memory.id), memory)

    def test_sqlite_storage_persists_memory_graph_timeline_and_events(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "amos.sqlite3")
            storage = SQLiteStorage(path)
            amos = Amos(memories=storage, timeline=storage, graph=storage, events=storage)
            memory = amos.remember(tenant_id="tenant", content="AMOS uses SQLite", type=MemoryType.FACT)
            amos.add_relationship(tenant_id="tenant", source="AMOS", relation="USES", target="SQLite")

            restarted_storage = SQLiteStorage(path)
            restarted = Amos(
                memories=restarted_storage,
                timeline=restarted_storage,
                graph=restarted_storage,
                events=restarted_storage,
            )

            self.assertEqual(restarted.get_memory(memory.id).content, "AMOS uses SQLite")
            self.assertEqual(restarted.get_timeline(tenant_id="tenant", entity="AMOS")[0].value, "SQLite")
            self.assertEqual(restarted.get_relationships(tenant_id="tenant", node="AMOS")[0].target, "SQLite")
            self.assertTrue(restarted.events.events("tenant"))

    def test_runtime_supports_sqlite_backend(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "runtime.sqlite3")
            with patch.dict(os.environ, {"AMOS_STORAGE_BACKEND": "sqlite", "AMOS_SQLITE_PATH": path}):
                amos = build_amos()
                memory = amos.remember(tenant_id="tenant", content="Runtime SQLite memory")
                restarted = build_amos()

            self.assertEqual(restarted.get_memory(memory.id).content, "Runtime SQLite memory")

    def test_redis_outage_does_not_block_authoritative_store(self) -> None:
        source = InMemoryStorage()
        broken = BrokenRedis()
        with patch("redis.Redis.from_url", return_value=broken):
            cache = RedisCachedMemoryStore("redis://unused", source)
        memory = Amos().remember(tenant_id="tenant", content="Durable despite cache outage")

        cache.put(memory)

        self.assertEqual(cache.get(memory.id), memory)
        self.assertFalse(cache.health())


@unittest.skipUnless(os.getenv("AMOS_RUN_INTEGRATION") == "1", "requires live hybrid services")
class HybridIntegrationTests(unittest.TestCase):
    def test_persistence_timeline_graph_and_events(self) -> None:
        amos = build_amos()
        restarted = None
        try:
            tenant = "hybrid-integration"
            memory = amos.remember(tenant_id=tenant, content="AMOS uses hybrid storage", type=MemoryType.FACT)
            amos.add_relationship(tenant_id=tenant, source="AMOS", relation="USES", target="Postgres")

            restarted = build_amos()

            self.assertEqual(restarted.get_memory(memory.id).content, memory.content)
            self.assertEqual(restarted.get_relationships(tenant_id=tenant, node="AMOS")[0].target, "Postgres")
            self.assertTrue(restarted.events.events(tenant))
        finally:
            amos.close()
            if restarted:
                restarted.close()
