from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from amos import Amos
from amos.mcp import McpServer
from amos.models import MemoryTier, MemoryType, RetrievalRoute, utc_now


class AmosTests(unittest.TestCase):
    def setUp(self) -> None:
        self.amos = Amos()
        self.tenant = "tenant-a"

    def test_temporal_truth_closes_previous_value(self) -> None:
        first = self.amos.update_fact(
            tenant_id=self.tenant,
            entity="user",
            attribute="works_on",
            value="Presto",
            valid_from=datetime(2024, 1, 1, tzinfo=UTC),
            source="user",
        )
        second = self.amos.update_fact(
            tenant_id=self.tenant,
            entity="user",
            attribute="works_on",
            value="Trino",
            valid_from=datetime(2026, 5, 1, tzinfo=UTC),
            source="user",
        )

        timeline = self.amos.get_timeline(tenant_id=self.tenant, entity="user", attribute="works_on")
        self.assertEqual(first.valid_to, second.valid_from)
        self.assertIsNone(second.valid_to)
        self.assertEqual([fact.value for fact in timeline], ["Presto", "Trino"])

    def test_routed_recall_and_context_budget(self) -> None:
        skill = self.amos.remember(
            tenant_id=self.tenant,
            content="Skilled in distributed query execution and Presto internals",
            type=MemoryType.SKILL,
            importance=0.9,
        )
        self.amos.remember(
            tenant_id=self.tenant,
            content="Prefers concise status updates",
            type=MemoryType.PREFERENCE,
        )

        recalled = self.amos.recall(tenant_id=self.tenant, query="What query execution skills are known?")
        context = self.amos.get_context(
            tenant_id=self.tenant,
            query="What query execution skills are known?",
            token_budget=30,
        )

        self.assertEqual(recalled[0].memory.id, skill.id)
        self.assertEqual(recalled[0].route, RetrievalRoute.SKILL)
        self.assertLessEqual(context.token_count, 30)
        self.assertIn("distributed query execution", context.text)
        self.assertNotIn("concise status updates", context.text)

    def test_semantic_lite_retrieval_keeps_recall_method_under_tight_budget(self) -> None:
        self.amos.remember(
            tenant_id=self.tenant,
            content="AMOS uses Postgres as the durable source of truth for memories and domain events",
            type=MemoryType.FACT,
            importance=0.86,
        )
        self.amos.remember(
            tenant_id=self.tenant,
            content="AMOS uses Neo4j for relationship graph storage",
            type=MemoryType.FACT,
            importance=0.82,
        )
        self.amos.remember(
            tenant_id=self.tenant,
            content="AMOS recall is currently lexical rather than semantic",
            type=MemoryType.OBSERVATION,
            importance=0.88,
        )

        context = self.amos.get_context(
            tenant_id=self.tenant,
            query="What kind of recall does AMOS currently use?",
            token_budget=60,
        )

        self.assertIn("lexical rather than semantic", context.text)

    def test_admission_policy_filters_low_value_turns(self) -> None:
        important = self.amos.assess_memory(
            content="Nandu prefers concise benchmark summaries with exact latency numbers",
            type=MemoryType.PREFERENCE,
            importance=0.8,
        )
        noise = self.amos.assess_memory(
            content="temporary debug output from a one-off command",
            type=MemoryType.OBSERVATION,
            importance=0.1,
            confidence=0.5,
        )

        self.assertTrue(important.remember)
        self.assertFalse(noise.remember)

    def test_temporal_truth_normalizes_naive_timestamp(self) -> None:
        fact = self.amos.update_fact(
            tenant_id=self.tenant,
            entity="user",
            attribute="location",
            value="Bengaluru",
            valid_from=datetime(2026, 6, 1),
            source="user",
        )

        self.assertEqual(fact.valid_from.tzinfo, UTC)

    def test_scheduler_promotes_hot_active_memory(self) -> None:
        memory = self.amos.remember(
            tenant_id=self.tenant,
            content="AMOS is the active project",
            importance=1.0,
            confidence=1.0,
        )
        memory.retrieval_count = 10

        decisions = self.amos.run_scheduler(tenant_id=self.tenant)

        self.assertEqual(memory.tier, MemoryTier.SURVIVOR)
        self.assertEqual(decisions[0]["decision"], "PROMOTE")

    def test_scheduler_archives_cold_survivor(self) -> None:
        memory = self.amos.remember(
            tenant_id=self.tenant,
            content="Old low-confidence observation",
            importance=0.0,
            confidence=0.0,
        )
        memory.tier = MemoryTier.SURVIVOR
        memory.updated_at = utc_now() - timedelta(days=365)

        decisions = self.amos.run_scheduler(tenant_id=self.tenant)

        self.assertEqual(memory.tier, MemoryTier.ARCHIVE)
        self.assertEqual(decisions[0]["decision"], "ARCHIVE")

    def test_consolidation_preserves_provenance_and_blocks_unsafe_forget(self) -> None:
        episode = self.amos.remember(
            tenant_id=self.tenant,
            content="Optimized distributed joins",
            type=MemoryType.EPISODE,
        )
        summary = self.amos.consolidate(
            tenant_id=self.tenant,
            source_memory_ids=[episode.id],
            content="Skilled in distributed query optimization",
            type=MemoryType.SKILL,
            model="test-model",
        )

        forgotten = self.amos.forget(tenant_id=self.tenant, memory_id=episode.id)
        forced = self.amos.forget(tenant_id=self.tenant, memory_id=episode.id, force=True)
        events = self.amos.events.events(self.tenant)

        self.assertEqual(summary.provenance.source_memory_ids, [episode.id])
        self.assertFalse(forgotten)
        self.assertTrue(forced)
        self.assertIn("MemoryConsolidated", [event.kind for event in events])
        self.assertIn("MemoryForgetBlocked", [event.kind for event in events])
        self.assertIn("MemoryForgotten", [event.kind for event in events])

    def test_remember_auto_processes_facts_relationships_and_explanation(self) -> None:
        memory = self.amos.remember(
            tenant_id=self.tenant,
            content="Nandu is building AMOS",
            type=MemoryType.EPISODE,
            importance=0.8,
        )

        timeline = self.amos.get_timeline(tenant_id=self.tenant, entity="Nandu", attribute="works_on")
        relationships = self.amos.get_relationships(tenant_id=self.tenant, node="Nandu")
        explanation = self.amos.explain_memory(tenant_id=self.tenant, memory_id=memory.id)

        self.assertEqual(timeline[0].value, "AMOS")
        self.assertEqual(relationships[0].relation, "WORKS_ON")
        self.assertTrue(memory.metadata["pipeline_processed_at"])
        self.assertTrue(explanation["lifecycle"]["processed"])
        self.assertEqual(explanation["facts"][0].memory_id, memory.id)

    def test_process_memory_is_idempotent_unless_forced(self) -> None:
        memory = self.amos.remember(
            tenant_id=self.tenant,
            content="AMOS uses Postgres",
            auto_process=False,
        )

        first = self.amos.process_memory(tenant_id=self.tenant, memory_id=memory.id)
        second = self.amos.process_memory(tenant_id=self.tenant, memory_id=memory.id)

        self.assertEqual(len(first.extracted_facts), 1)
        self.assertEqual(second.skipped, ["already_processed"])

    def test_relationships_are_tenant_isolated(self) -> None:
        self.amos.add_relationship(
            tenant_id=self.tenant,
            source="AMOS",
            relation="USES",
            target="Postgres",
        )
        self.amos.add_relationship(
            tenant_id="other",
            source="AMOS",
            relation="USES",
            target="Redis",
        )

        edges = self.amos.get_relationships(tenant_id=self.tenant, node="AMOS")

        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0].target, "Postgres")

    def test_mcp_tools_use_the_same_service(self) -> None:
        server = McpServer(self.amos)
        created = server.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "remember",
                    "arguments": {"tenant_id": self.tenant, "content": "AMOS supports MCP"},
                },
            }
        )
        recalled = server.handle(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "recall",
                    "arguments": {"tenant_id": self.tenant, "query": "supports MCP"},
                },
            }
        )
        assessed = server.handle(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "assess_memory",
                    "arguments": {"content": "temporary debug output", "importance": 0.1},
                },
            }
        )

        self.assertIn("result", created)
        self.assertIn("AMOS supports MCP", recalled["result"]["content"][0]["text"])
        self.assertFalse(assessed["result"]["structuredContent"]["remember"])


if __name__ == "__main__":
    unittest.main()
