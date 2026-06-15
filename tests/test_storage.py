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

    def test_runtime_defaults_to_in_memory(self) -> None:
        with patch.dict(os.environ, {"AMOS_STORAGE_BACKEND": "memory"}):
            amos = build_amos()

        memory = amos.remember(tenant_id="tenant", content="Runtime memory")
        retrieved = amos.memories.get(memory.id)
        assert retrieved is not None
        self.assertEqual(retrieved.content, "Runtime memory")


@unittest.skipUnless(os.getenv("AMOS_RUN_INTEGRATION") == "1", "requires live PostgreSQL")
class PostgresIntegrationTests(unittest.TestCase):
    def test_persistence_and_retrieval(self) -> None:
        with patch.dict(os.environ, {"AMOS_STORAGE_BACKEND": "postgres"}):
            amos = build_amos()
            restarted = None
            try:
                tenant = "postgres-integration"
                memory = amos.remember(tenant_id=tenant, content="AMOS uses PostgreSQL storage", type=MemoryType.FACT)
                
                # Test persistence by restarting
                restarted = build_amos()
                retrieved = restarted.memories.get(memory.id)
                assert retrieved is not None
                self.assertEqual(retrieved.content, memory.content)
                
                # Test recall works
                results = restarted.recall(tenant_id=tenant, query="PostgreSQL", limit=5)
                self.assertTrue(len(results) > 0)
            finally:
                amos.close()
                if restarted:
                    restarted.close()
