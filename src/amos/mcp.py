from __future__ import annotations

import json
import sys
from datetime import datetime
from typing import Any, Callable

from .models import MemoryType, to_dict, utc_now
from .runtime import build_amos
from .service import Amos


PROTOCOL_VERSION = "2025-11-25"


def object_schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


TOOLS = [
    {
        "name": "remember",
        "description": "Store a typed memory in AMOS.",
        "inputSchema": object_schema(
            {
                "tenant_id": {"type": "string"},
                "content": {"type": "string"},
                "type": {"type": "string", "enum": [item.value for item in MemoryType]},
                "importance": {"type": "number", "minimum": 0, "maximum": 1},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "metadata": {"type": "object"},
            },
            ["tenant_id", "content"],
        ),
    },
    {
        "name": "assess_memory",
        "description": "Decide whether content is worth storing as long-term AMOS memory.",
        "inputSchema": object_schema(
            {
                "content": {"type": "string"},
                "type": {"type": "string", "enum": [item.value for item in MemoryType]},
                "importance": {"type": "number", "minimum": 0, "maximum": 1},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            ["content"],
        ),
    },
    {
        "name": "recall",
        "description": "Recall routed memories relevant to a query.",
        "inputSchema": object_schema(
            {
                "tenant_id": {"type": "string"},
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1},
            },
            ["tenant_id", "query"],
        ),
    },
    {
        "name": "get_context",
        "description": "Compile relevant memory into a token-budgeted context.",
        "inputSchema": object_schema(
            {
                "tenant_id": {"type": "string"},
                "query": {"type": "string"},
                "token_budget": {"type": "integer", "minimum": 1},
            },
            ["tenant_id", "query"],
        ),
    },
    {
        "name": "update_fact",
        "description": "Add a temporal fact and close a contradictory current interval.",
        "inputSchema": object_schema(
            {
                "tenant_id": {"type": "string"},
                "entity": {"type": "string"},
                "attribute": {"type": "string"},
                "value": {"type": "string"},
                "source": {"type": "string"},
                "valid_from": {"type": "string", "format": "date-time"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            ["tenant_id", "entity", "attribute", "value", "source"],
        ),
    },
    {
        "name": "get_timeline",
        "description": "Get temporal facts for an entity or attribute.",
        "inputSchema": object_schema(
            {
                "tenant_id": {"type": "string"},
                "entity": {"type": "string"},
                "attribute": {"type": "string"},
            },
            ["tenant_id"],
        ),
    },
    {
        "name": "get_relationships",
        "description": "Get graph relationships neighboring a node.",
        "inputSchema": object_schema(
            {"tenant_id": {"type": "string"}, "node": {"type": "string"}},
            ["tenant_id", "node"],
        ),
    },
    {
        "name": "forget",
        "description": "Forget a memory and emit an audit event.",
        "inputSchema": object_schema(
            {
                "tenant_id": {"type": "string"},
                "memory_id": {"type": "string"},
                "reason": {"type": "string"},
                "force": {"type": "boolean"},
            },
            ["tenant_id", "memory_id"],
        ),
    },
    {
        "name": "process_memory",
        "description": "Run AMOS extraction and lifecycle processing for a memory.",
        "inputSchema": object_schema(
            {
                "tenant_id": {"type": "string"},
                "memory_id": {"type": "string"},
                "force": {"type": "boolean"},
            },
            ["tenant_id", "memory_id"],
        ),
    },
    {
        "name": "explain_memory",
        "description": "Explain a memory's heat, derived facts, relationships, dependents, and lifecycle events.",
        "inputSchema": object_schema(
            {"tenant_id": {"type": "string"}, "memory_id": {"type": "string"}},
            ["tenant_id", "memory_id"],
        ),
    },
]


class McpServer:
    def __init__(self, amos: Amos | None = None) -> None:
        self.amos = amos or build_amos()
        self.calls: dict[str, Callable[[dict[str, Any]], Any]] = {
            "remember": self._remember,
            "assess_memory": self._assess_memory,
            "recall": self._recall,
            "get_context": self._get_context,
            "update_fact": self._update_fact,
            "get_timeline": self._get_timeline,
            "get_relationships": self._get_relationships,
            "forget": self._forget,
            "process_memory": self._process_memory,
            "explain_memory": self._explain_memory,
        }

    def handle(self, request: dict[str, Any]) -> dict[str, Any] | None:
        request_id = request.get("id")
        method = request.get("method")
        if request_id is None:
            return None
        try:
            if method == "initialize":
                requested = request.get("params", {}).get("protocolVersion")
                version = requested if requested == PROTOCOL_VERSION else PROTOCOL_VERSION
                return self._result(
                    request_id,
                    {
                        "protocolVersion": version,
                        "capabilities": {"tools": {"listChanged": False}},
                        "serverInfo": {"name": "amos", "version": "0.1.0"},
                        "instructions": "Use AMOS to manage temporal, lifecycle-aware agent memory.",
                    },
                )
            if method == "ping":
                return self._result(request_id, {})
            if method == "tools/list":
                return self._result(request_id, {"tools": TOOLS})
            if method == "tools/call":
                params = request.get("params", {})
                name = params.get("name")
                if name not in self.calls:
                    return self._error(request_id, -32602, f"unknown tool: {name}")
                output = to_dict(self.calls[name](params.get("arguments", {})))
                return self._result(
                    request_id,
                    {
                        "content": [{"type": "text", "text": json.dumps(output, separators=(",", ":"))}],
                        "structuredContent": output if isinstance(output, dict) else {"items": output},
                    },
                )
            return self._error(request_id, -32601, f"method not found: {method}")
        except (ValueError, KeyError, TypeError) as error:
            return self._error(request_id, -32602, str(error))

    def _remember(self, args: dict[str, Any]) -> Any:
        return self.amos.remember(
            tenant_id=args["tenant_id"],
            content=args["content"],
            type=MemoryType(args.get("type", "OBSERVATION")),
            importance=float(args.get("importance", 0.5)),
            confidence=float(args.get("confidence", 1.0)),
            metadata=args.get("metadata"),
        )

    def _assess_memory(self, args: dict[str, Any]) -> Any:
        return self.amos.assess_memory(
            content=args["content"],
            type=MemoryType(args.get("type", "OBSERVATION")),
            importance=float(args.get("importance", 0.5)),
            confidence=float(args.get("confidence", 1.0)),
        )

    def _recall(self, args: dict[str, Any]) -> Any:
        return self.amos.recall(
            tenant_id=args["tenant_id"],
            query=args["query"],
            limit=int(args.get("limit", 10)),
        )

    def _get_context(self, args: dict[str, Any]) -> Any:
        return self.amos.get_context(
            tenant_id=args["tenant_id"],
            query=args["query"],
            token_budget=int(args.get("token_budget", 300)),
        )

    def _update_fact(self, args: dict[str, Any]) -> Any:
        raw_date = args.get("valid_from")
        valid_from = datetime.fromisoformat(raw_date.replace("Z", "+00:00")) if raw_date else utc_now()
        return self.amos.update_fact(
            tenant_id=args["tenant_id"],
            entity=args["entity"],
            attribute=args["attribute"],
            value=args["value"],
            valid_from=valid_from,
            source=args["source"],
            confidence=float(args.get("confidence", 1.0)),
        )

    def _get_timeline(self, args: dict[str, Any]) -> Any:
        return self.amos.get_timeline(
            tenant_id=args["tenant_id"],
            entity=args.get("entity"),
            attribute=args.get("attribute"),
        )

    def _get_relationships(self, args: dict[str, Any]) -> Any:
        return self.amos.get_relationships(tenant_id=args["tenant_id"], node=args["node"])

    def _forget(self, args: dict[str, Any]) -> Any:
        return {
            "forgotten": self.amos.forget(
                tenant_id=args["tenant_id"],
                memory_id=args["memory_id"],
                reason=args.get("reason", "requested"),
                force=bool(args.get("force", False)),
            )
        }

    def _process_memory(self, args: dict[str, Any]) -> Any:
        return self.amos.process_memory(
            tenant_id=args["tenant_id"],
            memory_id=args["memory_id"],
            force=bool(args.get("force", False)),
        )

    def _explain_memory(self, args: dict[str, Any]) -> Any:
        return self.amos.explain_memory(tenant_id=args["tenant_id"], memory_id=args["memory_id"])

    @staticmethod
    def _result(request_id: Any, result: Any) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def main() -> None:
    server = McpServer()
    for line in sys.stdin:
        try:
            response = server.handle(json.loads(line))
            if response is not None:
                sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
                sys.stdout.flush()
        except json.JSONDecodeError as error:
            response = McpServer._error(None, -32700, str(error))
            sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
