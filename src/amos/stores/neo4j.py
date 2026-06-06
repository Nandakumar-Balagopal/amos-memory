from __future__ import annotations

import json

from ..models import Relationship, to_dict
from .codec import relationship_from_dict


class Neo4jGraphStore:
    def __init__(self, uri: str, user: str, password: str, *, initialize: bool = True) -> None:
        try:
            from neo4j import GraphDatabase
        except ImportError as error:
            raise RuntimeError("Install AMOS database dependencies with: pip install -e .") from error
        self.driver = GraphDatabase.driver(uri, auth=(user, password), connection_timeout=3)
        if initialize:
            self.initialize()

    def initialize(self) -> None:
        self.driver.execute_query(
            "CREATE CONSTRAINT amos_entity IF NOT EXISTS FOR (n:Entity) REQUIRE n.key IS UNIQUE"
        )

    def add_relationship(self, relationship: Relationship) -> None:
        data = to_dict(relationship)
        self.driver.execute_query(
            """
            MERGE (source:Entity {key: $source_key})
            SET source.tenant_id = $tenant_id, source.name = $source
            MERGE (target:Entity {key: $target_key})
            SET target.tenant_id = $tenant_id, target.name = $target
            MERGE (source)-[edge:RELATED {id: $id}]->(target)
            SET edge.relation = $relation, edge.memory_id = $memory_id,
                edge.confidence = $confidence, edge.created_at = datetime($created_at),
                edge.metadata_json = $metadata_json
            """,
            **{
                **data,
                "source_key": f"{data['tenant_id']}::{data['source']}",
                "target_key": f"{data['tenant_id']}::{data['target']}",
                "metadata_json": json.dumps(data["metadata"]),
            },
        )

    def neighbors(self, tenant_id: str, node: str) -> list[Relationship]:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (source:Entity)-[edge:RELATED]->(target:Entity)
            WHERE source.tenant_id = $tenant_id AND target.tenant_id = $tenant_id
              AND (source.name = $node OR target.name = $node)
            RETURN edge.id AS id, source.tenant_id AS tenant_id, source.name AS source,
                   edge.relation AS relation, target.name AS target,
                   edge.memory_id AS memory_id, edge.confidence AS confidence,
                   toString(edge.created_at) AS created_at, edge.metadata_json AS metadata_json
            ORDER BY edge.created_at DESC
            """,
            tenant_id=tenant_id,
            node=node,
        )
        return [
            relationship_from_dict({**record.data(), "metadata": json.loads(record["metadata_json"] or "{}")})
            for record in records
        ]

    def health(self) -> bool:
        self.driver.verify_connectivity()
        return True

    def close(self) -> None:
        self.driver.close()
